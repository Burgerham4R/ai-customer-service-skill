# auto_adapters - 技术栈解耦适配器组件库

> 由 Agent 在集成阶段读取，根据 `stack_detector` 识别到的技术栈，
> 选择对应 adapter 渲染模板代码并注入用户项目。

## 适配器索引

| 适配器 | 命中技术栈 | 注入产物 | 默认目标 |
|:---|:---|:---|:---|
| `frontend-spa` | `react` / `vue` / `angular` / `next` | `VoiceAgent.{tsx,vue,ts}` 组件 | `src/components/` |
| `node-backend` | `express` / `koa` / `fastify` | 反向代理中间件 | `routes/voice-agent.js` |
| `java-backend` | `spring-boot` / `quarkus` | `Filter` 或 `Quarkus Filter` | `src/main/java/.../VoiceAgentFilter.java` |
| `python-backend` | `flask` / `fastapi` / `django` | 装饰器 / 子路由 | `voice_agent_proxy.py` |

## 模板渲染变量

所有 `.tpl` 文件统一使用 `${VAR}` 占位（避免与 JS / Python 的 `{{}}` 冲突）：

| 变量 | 默认 | 说明 |
|:---|:---|:---|
| `${SKELETON_BASE_URL}` | `http://localhost:3000` | conversation-core 进程地址 |
| `${API_PREFIX}` | `/api/v1` | 骨架 REST 前缀 |
| `${COMPONENT_NAME}` | `VoiceAgent` | 前端组件名 |
| `${ROUTE_PREFIX}` | `/voice-agent` | 后端代理路由前缀 |

## 三级降级链路

```
L1 全自动: stack_detector.primary 命中 → adapter.render() → 写入用户项目
       │
       │  失败（语法冲突 / 路径冲突）
       ▼
L2 半自动: 输出 INTEGRATION_GUIDE.md（基于 integration_templates/generic-*.md）
       │
       │  stack_detector.primary 为 None
       ▼
L3 手动 API: 输出 integration_templates/generic-rest-api.md
```

详见 `scripts/lib/degrader.py` 与 `scripts/add-capability.py`。
