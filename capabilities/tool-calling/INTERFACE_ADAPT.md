# tool-calling 接口适配 SOP

> α/β 双轨制工具调用。本能力包源码本期未做 ports/adapters/core 重构（阶段 1 折中策略），
> 但 manifest 已声明完整的 `business_contract.alpha_track` / `beta_track` / `arbitration` 契约。

---

## 1. 双轨契约速览

### 1.1 α 轨（本地函数）

```yaml
alpha_track:
  registration_schema:
    name: string                # 例：query_order
    description: string         # 给 LLM 看的工具说明
    parameters: object          # JSON Schema
    handler: callable           # 同步或异步 Python 函数
```

α 轨适合：低延迟、强业务耦合、不便暴露为 HTTP 服务的工具。

### 1.2 β 轨（远程 API）

```yaml
beta_track:
  api_schema:
    method: GET | POST | PUT | DELETE | PATCH
    path: string
    request_schema: object
    response_schema: object
    auth: bearer | api_key | none
```

β 轨适合：跨服务调用、需要复用已有 API 网关的工具。

### 1.3 仲裁规则

```yaml
arbitration:
  default_priority: alpha               # alpha 优先
  fallback_on_failure: true             # α 失败自动降级 β
  timeout_ms: 3000                       # 单轨调用上限
  merge_strategy: first_success         # 仅取首个成功
```

---

## 2. 用户接口对不上时的三类场景

### 2.1 场景一：用户的 α 轨函数签名不同

**症状**：用户已有一批本地函数（如 `def get_order(order_id, user_id) -> dict`），
但骨架默认期望参数命名为 `id` / `customer_id`。

**解决方案**：写一层薄包装注册函数，无需改骨架。

```python
# 用户项目内
from capabilities.tool_calling.src.dispatcher import register_tool

def get_order(order_id, user_id):
    """用户已有函数。"""
    return {"order_id": order_id, "status": "shipped"}

# 适配层：参数重映射
register_tool(
    name="query_order",
    description="查询订单状态",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "customer_id": {"type": "string"},
        },
        "required": ["id", "customer_id"],
    },
    handler=lambda id, customer_id: get_order(id, customer_id),  # 字段重映射
)
```

### 2.2 场景二：用户的 β 轨远程 API 协议不同

**症状**：远程业务 API 不是 OpenAI Tool Calling 默认风格的 JSON-RPC，
而是用户自有的 REST 端点（如 `POST /api/v1/orders/query`）。

**解决方案**：在 `tools.yaml` 注册时声明完整 API schema。

```yaml
# capabilities/tool-calling/data/tools.yaml
tools:
  - name: query_order
    description: 查询订单状态
    alpha: null                          # 不提供本地实现
    beta:
      base_url: https://api.example.com  # 必须 HTTPS
      method: POST
      path: /api/v1/orders/query
      headers:
        X-Api-Key: ${USER_KB_TOKEN}      # 从环境变量读
      request_template:
        body:
          order_no: "{{ id }}"           # 模板渲染：把工具入参 id 映射为 order_no
          uid: "{{ customer_id }}"
      response_path: "$.data.order"      # 响应字段抽取（JSONPath）
```

> 本期 tools.yaml 的高级模板渲染**未完整实现**；如用户接口有复杂映射需求，
> 推荐改写为 α 轨本地函数 + 内部调用 requests。

### 2.3 场景三：用户希望禁用 β 轨（仅本地函数）

```bash
export TC_PRIORITY=alpha
export TC_DISABLE_BETA=1
```

骨架仅用 α 轨；β 失败不会触发。反之亦然（`TC_DISABLE_ALPHA=1`）。

---

## 3. 仲裁优先级覆盖

manifest 默认 `priority=alpha`；可被环境变量覆盖：

```bash
export TC_PRIORITY=beta              # β 优先（适用于 α 实现尚未稳定）
export TC_PRIORITY=manifest_order    # 按 tools.yaml 中 alpha/beta 字段先后顺序
```

---

## 4. Phase 4 计划：完整 ports/adapters 重构

未来将引入：

```
capabilities/tool-calling/src/
├── ports/
│   ├── local_tool.py            # ABC：LocalTool
│   └── remote_tool.py           # ABC：RemoteToolClient
└── adapters/
    ├── alpha_python.py          # α 默认实现（当前 dispatcher 行为）
    ├── beta_rest.py             # β 默认实现
    └── user_custom.py           # 用户接入向导生成
```

到时本文档会补充自动化适配流程。

---

## 5. 安全清单

- [ ] β 轨 `base_url` 必须使用 https://（localhost 例外）
- [ ] 拒绝访问私网（9.* / 10.* / 172.16-31.* / 192.168.*）
- [ ] `Authorization` / `X-Api-Key` 仅来自环境变量
- [ ] α 轨 handler 不应暴露 `eval` / `exec` / 任意命令执行
- [ ] 工具结果回注前必须做 prompt injection 防护（manifest.security.injection_protection）
