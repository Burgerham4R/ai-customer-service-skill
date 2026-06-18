# session-summary · 会话纪要 + 结构化摘要

> 在 conversation-core 之上自动归档每个 session 的轮次记录，
> 调用 `finalize` 后产出结构化摘要（topics / intents / next_actions）。

## 安装

```bash
python scripts/add-capability.py session-summary
```

## 配置

| 环境变量 | 默认 | 说明 |
|:---|:---|:---|
| `SS_STORAGE_DIR`    | `capabilities/session-summary/data/` | 纪要落盘目录（权限 0600） |
| `SS_RETENTION_DAYS` | `30` | 保留天数，过期自动清理 |
| `SS_LLM_SUMMARY`    | `true` | 是否调用 LLM 二次总结（依赖 `LLM_API_KEY`） |

## REST API

| 方法 | 路径 | 用途 |
|:---|:---|:---|
| GET  | `/api/v1/summary/_list?_offset=0&_limit=20` | 最近纪要列表 |
| GET  | `/api/v1/summary/{session_id}` | 单会话纪要详情 |
| POST | `/api/v1/summary/{session_id}/finalize` | 关闭会话并触发摘要 |

## 摘要输出

```json
{
  "topics":       ["订单", "shipping"],
  "user_intents": ["订单何时发货？"],
  "next_actions": ["请帮我修改地址"],
  "highlights":   ["12 turns recorded"],
  "engine":       "heuristic",
  "model":        null
}
```

LLM 路径失败会自动降级到本地启发式实现，保证离线可用。

## 安全

- 落盘文件权限强制 `0600`
- 写入前对 `secret_id / api_key / token / credential` 等字段执行脱敏
- 转写文本最大长度 `4096`
