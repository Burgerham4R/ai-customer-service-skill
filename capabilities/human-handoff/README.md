# human-handoff · 转人工 + 排队状态同步

> 在 conversation-core 之上提供"语义触发转人工 + 排队状态同步 + 座席接通"能力。

## 安装

```bash
python scripts/add-capability.py human-handoff
```

## 配置

| 环境变量 | 默认 | 说明 |
|:---|:---|:---|
| `HH_TRIGGERS`        | 见下文 | 强触发关键词，CSV |
| `HH_INTENT_KEYWORDS` | 见下文 | 弱意图关键词，CSV |
| `HH_QUEUE_CAPACITY`  | 50   | 排队容量 |
| `HH_AGENT_POOL_SIZE` | 1    | 可用座席数 |
| `HH_WAIT_PER_SLOT`   | 30   | 每槽位估算等待秒 |

默认强触发：`人工 / 转人工 / talk to agent / real person`
默认弱触发：`投诉 / complain / manager / 无法解决`（需排除否定上下文）

## REST API

| 方法 | 路径 | 用途 |
|:---|:---|:---|
| GET  | `/api/v1/handoff/status`         | 整体排队状态 |
| GET  | `/api/v1/handoff/{session_id}`   | 单会话状态 |
| POST | `/api/v1/handoff/request`        | 显式申请转人工 |
| POST | `/api/v1/handoff/connect`        | 模拟接通 |
| POST | `/api/v1/handoff/cancel`         | 取消申请 |

## 状态机

```
   idle ──request──▶ waiting ──connect──▶ connected
                       │  ▲                  │
                       │  │                  ▼
                     cancel/timeout       cancel
```

集成方应在自身座席系统中订阅 `/handoff/status` 或 `/handoff/{id}` 做同步推送。
