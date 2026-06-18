# conversation-core · 集成指南（Agent 可读）

> 本文档面向 **AI 编码助手 / 集成 Agent**，用于在用户项目中自动完成
> conversation-core 骨架的代码融合。所有指令均可程序化解析与执行。

---

## 第 1 节 · 技术栈检测

Agent 在集成入口处按以下顺序检测用户项目特征，输出标记 `tech_stack`：

| 信号文件 | 关键字段 | 推断技术栈 |
|:---|:---|:---|
| `package.json` | `dependencies.react` | `react` |
| `package.json` | `dependencies.vue` | `vue` |
| `package.json` | `dependencies['@angular/core']` | `angular` |
| `package.json` | `dependencies.express` / `koa` / `fastify` | `express` / `koa` / `fastify` |
| `package.json` | `dependencies.next` | `next` |
| `pom.xml` | `<artifactId>spring-boot-starter</artifactId>` | `spring-boot` |
| `build.gradle` | `org.springframework.boot` | `spring-boot` |
| `pom.xml` | `quarkus-core` | `quarkus` |
| `requirements.txt` / `pyproject.toml` | `flask` / `fastapi` / `django` | `flask` / `fastapi` / `django` |

如检测到多个候选技术栈，按以下优先级取最具体者：
`next > react/vue/angular > express/koa/fastify > spring-boot/quarkus > flask/fastapi/django`。

---

## 第 2 节 · 适配规则匹配

读取本能力包 `manifest.yaml` 的 `integration.auto_adapters` 列表，找到第一个 `tech_stack` 命中项即为目标 adapter：

```text
match(tech_stack_detected, manifest.integration.auto_adapters[*].tech_stack)
  → adapter_name (e.g. "frontend-spa")
```

适配器名 → 实际生成器映射由 Phase 2 提供，本骨架仅声明接口契约。

---

## 第 3 节 · 代码生成与融合

Phase 1 骨架仅暴露 REST API（端口默认 `3000`）。集成方在自有项目中调用骨架的方式：

### 3.1 前端（任意 SPA）

```js
// 1) 健康检查（顶部状态栏）
const health = await fetch('http://localhost:3000/api/v1/health').then(r => r.json());

// 2) 申请房间凭据
const cfg = await fetch('http://localhost:3000/api/v1/get_config', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
}).then(r => r.json());
const { session_id, sdk_app_id, room_id, user_id, user_sig } = cfg.data;

// 3) 用 sdk_app_id / user_sig 通过 TRTC Web SDK 入房（由前端能力包封装）

// 4) 启动 AI 通道机器人
await fetch('http://localhost:3000/api/v1/agent/start', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id, language: 'zh' })
});
```

### 3.2 后端（任意运行时）

| 运行时 | 注入位置 | 生成器输出 |
|:---|:---|:---|
| Express / Koa / Fastify | 路由层 | 中间件代码（反向代理 `/api/v1/*` 到骨架进程） |
| Spring Boot / Quarkus | Filter Chain | Filter 代码 + `@Value("${trtc.voice-agent.endpoint}")` 注入 |
| Flask / FastAPI / Django | 路由处理函数 | 装饰器 + 子路由挂载 |

### 3.3 注入点（声明式）

`manifest.yaml.injection_points` 中已声明 5 个标准注入点，Phase 2 能力包按 `id` 引用，例如：

```yaml
# 知识库能力包的 manifest.yaml 片段
extensions:
  - inject_at: "agent.before_start"
    code_template: "templates/inject_kb_to_instructions.py.tpl"
```

---

## 第 4 节 · 三级降级路径

| 级别 | 触发条件 | Agent 行为 |
|:---:|:---|:---|
| **L1 全自动融合** | 技术栈识别成功且代码生成无冲突 | 直接写入用户项目并自动完成 `npm install` / `pip install` |
| **L2 半自动引导** | 技术栈识别成功但代码生成失败（语法 / 路径冲突） | 输出 `INTEGRATION_GUIDE.md`，包含模板代码 + 手动注入步骤 |
| **L3 手动 API 兜底** | 技术栈无法识别 | 输出 REST API 文档（基础地址 `/api/v1`）+ SDK 包安装命令 |

L2 / L3 的输出模板位于 `integration-templates/`（Phase 2 提供）。

---

## 第 5 节 · 验证检查

集成完成后 Agent 必须依次执行：

1. **进程存活** — `curl -s http://localhost:3000/api/v1/health | jq .status`，期望 `"ok"`。
2. **三盏灯** — `health.checks.{tencent_cloud,trtc,llm}.status == "ok"`。
3. **会话握手** — `POST /api/v1/get_config` → 返回包含非空 `session_id` 与 `user_sig`。
4. **文字注入** — 启动 AI 后调用 `POST /api/v1/agent/control { text: "ping" }` 返回 `delivered: true`。
5. **优雅停止** — `POST /api/v1/agent/stop` 返回 `status: "stopped"`。

任何步骤失败 Agent 都需输出诊断 JSON：

```json
{ "step": "get_config", "error": "...", "remediation": "检查 .env 中 TRTC_SDK_APP_ID 是否为整数" }
```

---

## 附录 A · 错误码字典

| 错误码 | 含义 | 修复建议 |
|:---|:---|:---|
| E001 | 腾讯云 SecretId/SecretKey 无效 | 重新执行 `python scripts/setup-credentials.py` |
| E002 | TRTC SDKAppID/SDKSecretKey 无效或 UserSig 生成失败 | 校验 SDKAppID 是否为整数；SecretKey 是否完整 |
| E003 | LLM API Key 无效 | 检查 `LLM_API_URL` 是否为 OpenAI 兼容 Endpoint |
| E004 | 网络不可达 | 检查出口 IP 白名单 / 代理 |
| E005 | 服务未开通 | 在 TRTC 控制台开通 Conversational AI |

## 附录 B · 安全合规

- 凭证仅来自环境变量（`security.credential_storage.source = env-only`）
- 凭证缓存与 `.env` 文件强制权限 `0600`
- 全链路 HTTPS（`security.network.enforce_https = true`）
- 日志脱敏过滤器在进程启动时安装（见 `src/log_filter.py`）
- XSS / Prompt Injection 防护开关声明在 `security.injection_protection`
