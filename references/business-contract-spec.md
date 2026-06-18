# `business_contract` 字段规范 (v1.0)

> 适用范围：`capabilities/<name>/manifest.yaml` 中新增的 `business_contract` 段。
>
> 目的：让能力包以**结构化方式**对外声明它会调用 / 被调用的业务接口契约，使
> `scripts/contract-adapt.py`（Phase 3 阶段 4）能据此生成可执行 adapter，并使
> 装配引导（路径 A / 路径 B）能在收尾时主动列出契约清单。

---

## 1. 顶层结构

```yaml
business_contract:
  port_class: "<dotted.path>"             # ABC 抽象基类完整路径
  default_adapter: "<dotted.path>"        # 默认实现（生产用）
  mock_adapter: "<dotted.path>"           # mock 实现（演示 / 录视频用）
  external_apis:                          # outbound / inbound 接口契约清单
    - <ExternalApi>
  customization_sop: "INTERFACE_ADAPT.md" # 接口适配 SOP 路径（相对能力包根）
```

**特例**：`tool-calling` 不走 port/adapter 抽象，使用 §5 定义的 α/β 双轨契约段替代。

---

## 2. `external_apis[]` 字段定义

```yaml
- name: <string>                  # 契约名（snake_case 点号分隔），全局唯一
  direction: outbound | inbound   # outbound = 我方调用业务方；inbound = 业务方回调我方
  method: GET | POST | PUT | DELETE | PATCH
  path: <string>                  # 路径模板，可含 {placeholder}
  description: <string>           # 一句话说明（用于装配收尾打印）
  request_schema:                 # 入参 schema（简化 JSON Schema）
    <field>: <type | enum[...] | object | array>
  response_schema:                # 出参 schema
    <field>: <type | enum[...] | object | array>
  adapter_slots:                  # 允许用户重映射的字段路径（点号分隔）
    - <request|response>.<field-path>
  auth:                           # （可选）认证方式
    type: bearer | api_key | none
    location: header | query
    name: <header-name | query-key>
  retry:                          # （可选）重试策略
    max: <int>
    backoff_ms: <int>
  timeout_ms: <int>               # （可选）超时
```

### 2.1 `type` 取值约定

| 类型 | 含义 |
|---|---|
| `string` | 字符串 |
| `int` / `integer` | 整数 |
| `float` / `number` | 浮点 |
| `bool` / `boolean` | 布尔 |
| `string[]` / `int[]` / `<T>[]` | 同质数组 |
| `enum[a, b, c]` | 枚举字面量 |
| `object` | 嵌套对象（可继续展开为 sub-schema） |
| 嵌套 dict | 直接写嵌套结构 |

### 2.2 `adapter_slots` 字段路径规则

- 起始 `request.` 或 `response.`
- 嵌套用点号分隔：`response.data.ticket_id`
- 数组用 `[]`：`request.transcript[]`
- 仅列出**允许用户重映射**的字段；未列出的字段视为"我方契约固定，禁止用户改动"

### 2.3 `direction = inbound` 的特殊性

inbound 契约表示"业务方回调我方"，此时：
- `path` 是我方暴露的端点（例：`/api/v1/handoff/callback/ticket-status`）
- `request_schema` 是业务方发来的 payload 结构
- `response_schema` 是我方返回的 ack 结构（一般为 `{code: int, message: string}`）
- `adapter_slots` 用于声明"业务方 payload 字段名可能与我方期望不同"，由 contract-adapt 生成入站字段映射器

---

## 3. 命名约定

| 元素 | 规则 | 示例 |
|---|---|---|
| `name` | `<域>.<动作>` snake_case | `ticket.create`, `faq.search`, `crm.write` |
| `port_class` | `src.ports.<file>.<ClassName>` | `src.ports.handoff_client.HandoffClient` |
| `default_adapter` / `mock_adapter` | `src.adapters.<file>.<ClassName>` | `src.adapters.local_queue.LocalQueueHandoffClient` |

---

## 4. 完整示例：`human-handoff`

```yaml
business_contract:
  port_class: "src.ports.handoff_client.HandoffClient"
  default_adapter: "src.adapters.local_queue.LocalQueueHandoffClient"
  mock_adapter: "src.adapters.mock.MockHandoffClient"
  customization_sop: "INTERFACE_ADAPT.md"
  external_apis:
    - name: ticket.create
      direction: outbound
      method: POST
      path: /tickets
      description: "用户触发转人工时，向工单系统创建新工单"
      request_schema:
        user_id: string
        subject: string
        description: string
        priority: enum[low, normal, high, urgent]
        transcript: string[]
      response_schema:
        ticket_id: string
        queue_position: int
        eta_seconds: int
      adapter_slots:
        - request.subject
        - request.priority
        - response.ticket_id
        - response.queue_position
        - response.eta_seconds
      auth:
        type: bearer
        location: header
        name: Authorization
      timeout_ms: 5000

    - name: ticket.status_query
      direction: outbound
      method: GET
      path: /tickets/{ticket_id}
      description: "轮询工单状态，用于排队态进度更新"
      request_schema:
        ticket_id: string
      response_schema:
        ticket_id: string
        status: enum[pending, processing, closed, canceled]
        agent_id: string
        updated_at: int
      adapter_slots:
        - response.status
        - response.agent_id
      timeout_ms: 3000

    - name: ticket.cancel
      direction: outbound
      method: POST
      path: /tickets/{ticket_id}/cancel
      description: "用户取消转人工时通知工单系统"
      request_schema:
        ticket_id: string
        reason: string
      response_schema:
        ticket_id: string
        canceled: bool
      adapter_slots:
        - request.reason
      timeout_ms: 3000

    - name: ticket.status_callback
      direction: inbound
      method: POST
      path: /api/v1/handoff/callback/ticket-status
      description: "工单系统主动回调通知状态变更（可选；未启用时由 status_query 轮询替代）"
      request_schema:
        ticket_id: string
        status: enum[pending, processing, closed, canceled]
        agent_id: string
      response_schema:
        code: int
        message: string
      adapter_slots:
        - request.status
        - request.agent_id
```

---

## 5. `tool-calling` 专属契约段（替代 §1 的 port/adapter 三件套）

```yaml
business_contract:
  alpha_track:                          # α 轨：本地函数注册规范
    interface: "src.ports.local_tool.LocalTool"
    registration_schema:
      name: string                     # 工具名（全局唯一）
      description: string
      parameters: object               # JSON Schema 描述参数结构
      handler: callable                # 函数对象（仅运行时持有）
    invocation_schema:
      input: object                    # 与 parameters 同 schema
      output: object                   # 用户自定义返回结构
    fail_fast: bool                    # 默认 true：本地异常立即抛出供 arbitration 决策

  beta_track:                           # β 轨：远程业务 API 对接规范
    interface: "src.ports.remote_tool.RemoteToolClient"
    api_schema:
      method: enum[GET, POST, PUT, DELETE, PATCH]
      path: string
      request_schema: object
      response_schema: object
      auth: enum[bearer, api_key, none]
    timeout_ms: 5000
    retry: { max: 1, backoff_ms: 200 }

  arbitration:                          # 仲裁规则
    default_priority: enum[alpha, beta, manifest_order]
    fallback_on_failure: bool
    timeout_ms: int                     # 单轨调用上限；超时即触发 fallback
    merge_strategy: enum[first_success, alpha_then_beta_diff]
```

`merge_strategy` 取值含义：

| 取值 | 行为 |
|---|---|
| `first_success` | 优先轨成功即返回，备用轨不调用（默认） |
| `alpha_then_beta_diff` | 双轨都调用，结果不一致时记录 diff 日志（用于灰度对比） |

---

## 6. `contract-adapt.py` 如何消费本字段

1. 读 `business_contract.external_apis[].request_schema` / `response_schema`
2. 解析用户提交的 curl / OpenAPI，提取用户接口的 schema
3. 对照 `adapter_slots` 列表生成字段映射 `mapping.yaml`
4. 渲染 adapter 模板（继承 `port_class`），输出到 `src/adapters/user_custom.py`
5. 三级降级：
   - **L1**：仅 `adapter_slots` 内字段差异 → 完整可执行 adapter
   - **L2**：存在 schema 嵌套层级或类型差异 → adapter 模板 + TODO 注释
   - **L3**：协议级差异（webhook / MQ / gRPC）或解析失败 → 输出 `INTERFACE_ADAPT.md` 对应章节路径

---

## 7. 验证规则（resolver 阶段必查）

| 规则 | 错误码 | 行为 |
|---|---|---|
| `port_class` / `default_adapter` / `mock_adapter` 任一不可 import | `BC001` | resolve 失败，阻止安装 |
| `external_apis[].name` 重复 | `BC002` | 同上 |
| `direction = outbound` 时未提供 `method` 或 `path` | `BC003` | 同上 |
| `adapter_slots` 路径未出现在 `request_schema` / `response_schema` 中 | `BC004` | 仅 warning，不阻断 |
| `tool-calling.arbitration.default_priority` 取值非法 | `BC005` | resolve 失败 |
| `auth.type = bearer` 但未声明环境变量来源 | `BC006` | 仅 warning |

实现位置：`scripts/lib/contract_resolver.py`（Phase 3 阶段 4 实现）。
本期阶段 1 仅约定字段定义，resolver 校验在阶段 4 实施。

---

## 8. 与既有 manifest 字段的关系

- `business_contract` 与既有 `extensions` / `endpoints` / `integration` 字段**互不影响**，可独立增删
- `endpoints` 描述"我方暴露给前端 / 用户的 REST 端点"
- `business_contract.external_apis` 描述"我方调用 / 被业务方回调的接口"
- 二者并存不冲突，分别服务不同消费者（前端 / Agent / 业务侧）

---

## 9. 版本兼容

- 当前规范版本：`v1.0`
- 不向前兼容；如未来需要 breaking change，将以 `business_contract.spec_version: "2.0"` 字段标记
- 资源解析器（`manifest_resolver.py`）当前忽略未知字段，本字段加入不会破坏 Phase 1/2 已有功能
