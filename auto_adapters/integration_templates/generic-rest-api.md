# 通用 REST API 接入指南（L3 手动兜底）

> 当 Agent 无法识别你的技术栈，或不在已支持的适配器列表内时，
> 直接通过 conversation-core 暴露的 REST API 接入。

## 1. 启动骨架

```bash
cd capabilities/conversation-core
python -m src.server   # 默认 0.0.0.0:3000
```

## 2. 端点列表

| 方法 | 路径 | 描述 |
|:---|:---|:---|
| GET  | `/api/v1/health`         | 三把 Key 实时连通性 |
| POST | `/api/v1/get_config`     | 颁发 RoomId / UserSig |
| POST | `/api/v1/agent/start`    | 启动 AI 通道机器人 |
| POST | `/api/v1/agent/stop`     | 停止 AI 通道机器人 |
| POST | `/api/v1/agent/control`  | 文本注入 / 打断 |
| GET  | `/api/v1/sessions`       | 内存会话列表（调试用） |

能力包追加端点：

| 能力 | 前缀 |
|:---|:---|
| knowledge-base   | `/api/v1/kb/*` |
| tool-calling     | `/api/v1/tools/*` |
| human-handoff    | `/api/v1/handoff/*` |
| session-summary  | `/api/v1/summary/*` |
| digital-human    | `/api/v1/digital-human/*` |

## 3. 调用示例

### 3.1 申请房间凭据

```bash
curl -X POST http://localhost:3000/api/v1/get_config \
  -H "Content-Type: application/json" \
  -d '{}'
```

返回：

```json
{
  "code": 0,
  "data": {
    "session_id": "xxx",
    "sdk_app_id": 1234567890,
    "room_id": "987654321",
    "user_id": "u_abc",
    "user_sig": "...",
    "agent_user_id": "ai_xyz",
    "io_modality": { "voice_input": { ... } }
  }
}
```

### 3.2 启动 AI 机器人

```bash
curl -X POST http://localhost:3000/api/v1/agent/start \
  -H "Content-Type: application/json" \
  -d '{"session_id":"xxx","language":"zh"}'
```

### 3.3 文本注入

```bash
curl -X POST http://localhost:3000/api/v1/agent/control \
  -H "Content-Type: application/json" \
  -d '{"session_id":"xxx","text":"你好","interrupt":true}'
```

## 4. SDK 包

如不希望直接调 REST，可使用以下 SDK：

| 生态 | 包名 |
|:---|:---|
| npm   | `@trtc/voice-agent-sdk` |
| maven | `com.tencent.trtc:voice-agent-sdk` |
| pypi  | `trtc-voice-agent` |

> SDK 版本与骨架 manifest 对齐；当前 Phase 2 阶段以 REST 为准。

## 5. 安全合规

- **HTTPS**：生产环境强制启用。
- **SecretKey 不下发**：骨架仅向客户端下发 `user_sig`（带 TTL），不暴露 `SDKSecretKey`。
- **日志脱敏**：骨架自带 `RedactingFilter`，反向代理层也应禁止打印 Authorization 头。
