# 通用后端集成指南（L2 半自动）

> 当 Agent 已识别到你的后端技术栈，但自动渲染失败时，参考以下步骤完成集成。
> 核心思路：在你的 Web 框架中挂载一个反向代理路由，把 `${ROUTE_PREFIX}/*`
> 透传到骨架进程的 `${API_PREFIX}/*`。

## 1. 部署 conversation-core 骨架

```bash
cd capabilities/conversation-core
python -m src.server     # 默认监听 0.0.0.0:3000
```

## 2. 复制反向代理模板

| 框架 | 模板 |
|:---|:---|
| Express   | `auto_adapters/node-backend/express.js.tpl` |
| Koa       | `auto_adapters/node-backend/koa.js.tpl` |
| Fastify   | `auto_adapters/node-backend/fastify.js.tpl` |
| Spring Boot | `auto_adapters/java-backend/springboot/VoiceAgentFilter.java.tpl` |
| Quarkus   | `auto_adapters/java-backend/quarkus/VoiceAgentFilter.java.tpl` |
| Flask     | `auto_adapters/python-backend/flask.py.tpl` |
| FastAPI   | `auto_adapters/python-backend/fastapi.py.tpl` |
| Django    | `auto_adapters/python-backend/django.py.tpl` |

替换占位变量（`${SKELETON_BASE_URL}` / `${API_PREFIX}` / `${ROUTE_PREFIX}`）。

## 3. 注册路由

按模板顶部 `install_hint` 描述把 router / filter / blueprint 挂到你的应用入口。

## 4. 安全核对

- **HTTPS**：生产环境强制启用。
- **SSRF**：骨架地址不应直接来自用户输入；如需对接内网骨架，先在用户明确确认后再放开。
- **请求体限制**：默认 `64KB`，避免大包冲击 ASR/LLM 链路。
- **鉴权**：在反向代理中可植入鉴权逻辑（JWT / API Key），骨架本身只信任反向代理来源。

## 5. 验证

```bash
curl -s http://localhost:8000${ROUTE_PREFIX}/health | jq .status
# 期望: "ok"
```
