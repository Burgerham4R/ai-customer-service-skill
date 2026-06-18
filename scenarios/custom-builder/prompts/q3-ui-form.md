# Q3 —— UI 形态（3 选 1）

> 路径 B 第 3 题。AI 用 `ask_followup_question` **单选**模式提问。
>
> 答复回写到内部变量 `ui_form`，将来用于决定：
> 1. 浮窗 / 全屏页 / 无 UI 三种部署形态
> 2. 是否做 UI 覆盖到 `capabilities/conversation-core/web-demo`
> 3. 是否生成接入指引（`integration-templates/*.md` 的引用清单）

---

## AI 应该说

> 第 3 题：你希望 AI 客服在哪儿"长出来"？

`options`：

```text
① 浮窗（在你现有页面右下角嵌入，推荐）
② 全屏对话页（独立页面 / 子路由，整页对话）
③ 仅后端 API（你自己写前端 / 接入到已有 IM，不需要 demo UI）
```

`multiSelect: false`

---

## 选项 → 行为映射

| 用户选项 | 内部枚举 (`ui_form`) | recipe.ui_overlay | 备注 |
|---|---|---|---|
| ① 浮窗 | `floating` | source=`scenarios/customer-service/ui/widget-floating`，target=`web-demo/` | 与路径 A 一致 |
| ② 全屏对话页 | `fullscreen` | source=`scenarios/customer-service/ui/widget-floating` 但 `target=web-demo/`；启动后引导用户打开 `/?layout=full`（或自行扩展专属模板） | 本期不内置专属全屏模板，沿用浮窗模板让其全屏占满（CSS class hook） |
| ③ 仅后端 API | `headless` | `ui_overlay: null` | 仅装能力包；产物只暴露 `/api/v1/*` |

> **注**：本期不专门生成全屏对话模板（`fullscreen` 复用浮窗 CSS 强制全屏）；
> 如要更精细化，可后续在 `scenarios/customer-service/ui/` 下拆出 `widget-fullscreen/` 子目录。

---

## 校验 / 回退

- 与 Q2 (`io_modality`) 联动校验：见 Q2 文档"校验 / 回退"
- 选 ③ 时不需要做 cp 覆盖；但 AI 仍要按 §8 提示用户外部接入文档（`auto_adapters/integration_templates/generic-frontend.md`）

---

## 答复回写

```yaml
# 渲染到 <workspace>/recipe.yaml
ui:
  form: floating                 # floating | fullscreen | headless
  overlay_required: true         # headless 模式时为 false
```
