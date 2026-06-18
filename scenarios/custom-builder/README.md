# scenarios/custom-builder —— 路径 B 自定义流程

> 配套文档：仓库根 `SKILL.md`（路径 B SOP §6）。

本目录是 **路径 B**（"自定义"）的全部产物。它**没有可执行脚本**——
4 轮问答完全由 Coding Agent 用 `ask_followup_question` 主持，
本目录只提供两类静态资料：

```
scenarios/custom-builder/
├── README.md                              ← 本文件
├── prompts/                               ← AI 读取的提问模板（不会改写用户工程）
│   ├── q1-business-scenario.md            ←  Q1：业务描述（自由文本）
│   ├── q2-io-modality.md                  ←  Q2：I/O 模态（4 选 1）
│   ├── q3-ui-form.md                      ←  Q3：UI 形态（3 选 1）
│   └── q4-capabilities.md                 ←  Q4：能力勾选（多选；默认全空）
└── output-templates/
    └── recipe.yaml.j2                     ← AI 渲染产物模板（输出到 <workspace>/recipe.yaml）
```

---

## 给 AI 的执行流程（与 SKILL.md §6 对齐）

| Step | 工具 | 来源 |
|---|---|---|
| 6.1 | `ask_followup_question`（自由文本） | `prompts/q1-business-scenario.md` |
| 6.2 | `ask_followup_question`（单选 4 项） | `prompts/q2-io-modality.md` |
| 6.3 | `ask_followup_question`（单选 3 项） | `prompts/q3-ui-form.md` |
| 6.4 | `ask_followup_question`（多选 4 项） | `prompts/q4-capabilities.md` |
| 6.5 | `write_to_file` 渲染 `recipe.yaml` | `output-templates/recipe.yaml.j2` |
| 6.6 | `execute_command("python3 scripts/add-capability.py <Q4 勾选项> --apply --json")` | Q4 勾选项；全空则跳过 |
| 6.7 | 余下与路径 A 相同（§7 Key → §8 契约 → §9 启动） | SKILL.md |

---

## 约束 / 红线

- **不写 builder.py**：4 轮问答**完全**由 AI 主持；不允许把这部分变成本地脚本（用户体验会从对话窗跌出）
- **不再生成 manifest.yaml**：每个能力包已有自己的 `manifest.yaml`，路径 B 不需要重新生成
- **prompts/q*.md 是静态资料**：AI **只读**它们；不会做内容修改 / 二次格式化
- **recipe.yaml.j2 用 Jinja2 语法**：但 AI 不必真正调用 Jinja2 解释器；可在脑内做字符串替换后直接 `write_to_file` 出最终 yaml。模板只是给 AI 一个**结构契约**

---

## 答复变量收齐后，AI 应在脑内构造的上下文

```python
context = {
    # Q1
    "business_desc": "<用户原文>",
    "business_name": "<可选；用户没说就走 default('我们')>",

    # Q2 选项 → 内部枚举
    "io_modality": "text_with_tts",     # text_only | text_with_tts | omni | voice_only

    # Q3 选项 → 内部枚举
    "ui_form": "floating",              # floating | fullscreen | headless

    # Q4 用户勾选项数组
    "extra_capabilities": [             # 任何子集；空数组时仅装骨架
        "knowledge-base",
        "human-handoff",
        # "tool-calling",
        # "session-summary",
    ],

    # 元信息（AI 自填）
    "render_time": "<ISO 8601>",
    "rendered_by": "Coding Agent",
}
```

把它喂给 `output-templates/recipe.yaml.j2` 即可得到本次定制的 `<workspace>/recipe.yaml`。

---

## 与路径 A 的差异（参照对照表）

| 维度 | 路径 A | 路径 B |
|---|---|---|
| 入口 | "基于 TRTC 帮我搭建一个 AI 客服" | 同左，SKILL.md §4 选 B |
| 装哪些能力 | 默认 `knowledge-base + human-handoff` | 默认全空，由用户 Q4 勾选 |
| 业务 prompt | 启动前问一句"业务描述"即可 | Q1 必答（更显式） |
| UI | 浮窗 + 工单看板（默认） | 看 Q3：浮窗 / 全屏 / 仅后端 |
| recipe.yaml 位置 | `scenarios/customer-service/recipe.yaml`（仓库内静态） | `<workspace>/recipe.yaml`（每次生成；可被人工编辑后重装） |
