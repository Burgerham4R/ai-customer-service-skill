# session-summary 接口适配 SOP

> 会话纪要 + 结构化摘要写回 CRM / 工单 / 数据中台。
> 本能力包源码本期未做 ports/adapters/core 重构（阶段 1 折中策略）。

---

## 1. 默认契约速览

| 契约名 | 方法 | 路径 | 用途 |
|---|---|---|---|
| `summary.write_to_crm`  | POST | `/sessions/{session_id}/summary` | 把 finalize 后的纪要写入用户的 CRM / 工单 |
| `summary.llm_summarize` | —   | 复用 conversation-core 的 `llm.chat_completions` | LLM 二次总结，无需单独适配 |

完整字段见 `manifest.yaml.business_contract.external_apis`。

---

## 2. 默认行为

session-summary 当前**默认仅落盘到本地文件**（路径 `data/<session_id>.json`），
不会主动写入任何远程系统。这意味着：

- 集成方需要自行扫描 `data/` 目录或调用 `/api/v1/summary/{session_id}` 拉取
- 未启用任何 outbound 调用，安全风险低
- 适合作为"草稿态"，集成方按需对接业务系统

---

## 3. 启用 CRM 写回

### 3.1 配置默认契约

```bash
# 启用 CRM 写回 + 用户的 CRM 接口完全符合默认契约
export SS_CRM_WRITE_ENABLED=1
export SS_CRM_BASE_URL=https://crm.example.com
export SS_CRM_TOKEN=sk-xxx
```

> 当前能力包源码**未实现** `SS_CRM_*` 环境变量逻辑；启用前需要按下文 §4 编写适配
> 子类。Phase 4 完整重构后此处会变为开箱即用。

### 3.2 自定义字段映射

如果用户 CRM 接口字段不同（例如 `summary` / `priority` / `tags` 等），写一个简单
的 webhook 中间层，或在 `recorder.py` 的 `finalize_session` 函数尾部追加 HTTP 调用。

参考代码片段（手动追加到 `src/recorder.py` 的 finalize 处）：

```python
import os, requests
def _maybe_write_crm(session_id: str, summary_payload: dict):
    base = os.getenv("SS_CRM_BASE_URL")
    if not base or os.getenv("SS_CRM_WRITE_ENABLED") != "1":
        return
    # 字段重映射示例
    body = {
        "session_id": session_id,
        "summary": summary_payload.get("topic"),       # 用户字段叫 summary
        "priority": summary_payload.get("outcome"),    # 用户字段叫 priority
        "tags": summary_payload.get("next_actions"),
    }
    requests.post(
        f"{base}/sessions/{session_id}/summary",
        json=body,
        headers={"Authorization": f"Bearer {os.getenv('SS_CRM_TOKEN', '')}"},
        timeout=5,
    )
```

---

## 4. Phase 4 计划：完整 ports/adapters 重构

未来将引入：

```
capabilities/session-summary/src/
├── ports/
│   └── crm_client.py          # ABC：write_summary / query_summary
└── adapters/
    ├── local_file.py          # 默认实现：仅落盘（当前行为）
    ├── default_rest.py        # 按默认 CRM 契约调用
    ├── mock.py                # 演示用 mock
    └── user_custom.py         # 用户接入向导生成
```

到时支持 `SS_ADAPTER=user_custom` 直接切换，无需手改 recorder.py。

---

## 5. 安全清单

- [ ] CRM 写回前自动脱敏（`secret_id` / `api_key` / `token` 等字段）
- [ ] `SS_CRM_BASE_URL` 必须 https://（localhost 例外）
- [ ] 拒绝私网地址
- [ ] 落盘文件权限强制 0600（已在 manifest.security.storage 声明）
- [ ] 纪要 transcript 中过滤掉用户敏感 PII（手机号 / 身份证）—— 当前能力包**未实现**，需用户业务层处理
