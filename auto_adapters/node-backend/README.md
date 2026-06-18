# node-backend 适配器

把 conversation-core 骨架以反向代理形式接入 Node.js 后端，
避免前端直接暴露骨架地址，并使后端可以在转发前后注入鉴权 / 限流 / 业务策略。

| 框架 | 模板 | 默认安装位置 |
|:---|:---|:---|
| Express | `express.js.tpl` | `routes/voice-agent.js` |
| Koa     | `koa.js.tpl`     | `routes/voice-agent.js` |
| Fastify | `fastify.js.tpl` | `routes/voice-agent.js` |

## 配置

| 环境变量 | 默认 | 说明 |
|:---|:---|:---|
| `SKELETON_BASE_URL` | `http://localhost:3000` | 骨架进程地址 |
| `API_PREFIX`        | `/api/v1`             | 骨架 REST 前缀 |
| `ROUTE_PREFIX`      | `/voice-agent`         | 自身挂载路径 |

## 安全

- **SSRF 防护**：模板会检测 `SKELETON_BASE_URL` 是否落在私有网段（`10/192.168/172.16-31/9/11/21/30/127`），
  生产环境会输出告警；如需访问内网骨架，必须在用户明确确认后再放开。
- **HTTPS**：生产部署强制 HTTPS。
- **请求体限制**：默认 `64KB`，避免恶意大包冲击骨架 ASR/LLM 链路。
