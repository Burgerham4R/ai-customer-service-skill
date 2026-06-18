# tool-calling · α/β 双轨制工具调用

> 在 conversation-core 之上提供"本地函数（α）+ 远程 API（β）"的工具调用能力，
> 默认 α 优先，α 不可用自动降级 β（P1 仲裁规则）。

## 安装

```bash
python scripts/add-capability.py tool-calling
```

## 配置

| 环境变量 | 默认 | 说明 |
|:---|:---|:---|
| `TC_REGISTRY_FILE` | `capabilities/tool-calling/data/tools.yaml` | 工具声明文件 |

工具声明格式见 `data/tools.yaml`，支持热重载（`POST /api/v1/tools/reload`）。

## REST API

| 方法 | 路径 | 用途 |
|:---|:---|:---|
| GET  | `/api/v1/tools/list`   | 列出全部工具 |
| POST | `/api/v1/tools/invoke` | 显式调用 `{name, params, priority?}` |
| POST | `/api/v1/tools/reload` | 重新加载注册表 |

## 对话内触发

向 `agent/control` 推送以下文本即可触发：

```
/tool get_order {"order_id": "A1234"}
```

dispatcher 会以 `[tool_result ...]...[/tool_result]` 块替换原文本注入到 LLM。

## 仲裁规则

- `priority=alpha`（默认）：先 α 后 β
- `priority=beta`：先 β 后 α
- `priority=manifest_order`：按声明顺序

任一轨失败时自动降级到下一个可用轨；全部失败返回 `ok=false` 与 `fallback_chain`。

## 安全

- β 轨强制 HTTPS（除 `http://localhost*`）；
- 工具名 ≤ 64，触发文本 ≤ 4096；
- 日志中工具参数自动脱敏（manifest 已声明 `log_redaction.patterns`）。
