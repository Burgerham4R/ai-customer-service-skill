# Q4 —— 能力勾选（多选；默认全空）

> 路径 B 第 4 题。AI 用 `ask_followup_question` **多选**模式提问（`multiSelect: true`）。
>
> 答复回写到内部变量 `extra_capabilities`（字符串数组），用于决定：
> 1. 路径 B 装配命令的能力清单：`add-capability.py conversation-core <勾选项>`
> 2. recipe.yaml 的 `capabilities.install` 列表
>
> **重要**：与路径 A（默认装 KB + HH）不同；路径 B 默认**全空**，仅装 conversation-core 骨架。
> 用户**显式勾选**的能力才会被加入清单。

---

## AI 应该说

> 第 4 题：除了对话骨架（conversation-core），还要叠加哪些能力？
> （可多选，不勾选也可以；默认仅装骨架）

`options`：

```text
① knowledge-base   — FAQ / 知识库检索
② human-handoff    — 转人工 + 工单流（带坐席看板）
③ tool-calling     — 让 AI 能调你的业务工具 / 远程 API
④ session-summary  — 会话结束自动写一条纪要 / 工单备注
```

`multiSelect: true`

---

## 不在选项里的能力（解释口径）

| 能力 | 为什么不出现 |
|---|---|
| `digital-human` | 当前为占位能力（manifest 未补齐 ports/adapters）；如需数字人请等后续版本 |

---

## 校验 / 回退

- Q4 全空 → 跳过 `add-capability.py` 调用（仅 conversation-core 骨架，已在仓库内）
- 选了 `tool-calling` 但 Q2 选了"纯语音电话" → 警告"工具调用在纯语音通道不会显示中间状态"，让用户确认是否保留
- 选了 `session-summary` 但未配 `LLM_API_KEY` → 警告"会话纪要依赖 LLM Key，请在 §7 完成 LLM Key 配置"

---

## 选项 → 装配命令

```bash
# AI 在路径 B Step 6 执行（Q4 全空时跳过整条命令）：
python3 scripts/add-capability.py \
    knowledge-base human-handoff tool-calling session-summary \
    --apply --json
```

> 实际命令只包含用户**勾选**的能力名；上面是"全选"示例。

---

## 答复回写

```yaml
# 渲染到 <workspace>/recipe.yaml
capabilities:
  required:
    - name: conversation-core
      role: skeleton
  install:
    # 用户勾选的能力（每勾一项追加一条；adapter 缺省走 manifest.config.adapter.default）
    - name: knowledge-base
      adapter: mock
    - name: human-handoff
      adapter: local_queue
  optional: []
  excluded:
    - name: digital-human          # 本期不参与
```
