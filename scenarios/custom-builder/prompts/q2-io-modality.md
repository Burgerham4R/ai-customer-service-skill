# Q2 —— I/O 模态（4 选 1）

> 路径 B 第 2 题。AI 用 `ask_followup_question` **单选**模式提问。
>
> 答复回写到内部变量 `io_modality`（取值如下表的英文枚举），将来用于：
> 1. 决定 `agent_runtime.greeting` 是否走 TTS 朗读
> 2. 决定 conversation-core 的 `io_modality.*.enabled` 字段
> 3. 决定浮窗 UI 是否暴露麦克风按钮

---

## AI 应该说（建议直接复制粘贴到 ask_followup_question）

> 第 2 题：终端用户和 AI 客服之间，使用什么样的 I/O 模态？

`options`（保持顺序，顺序与下方枚举一一对应）：

```text
① 纯文字 IM（用户打字 → AI 回文字；无语音）
② 文字 + TTS（用户打字 → AI 回文字 + 朗读，推荐）
③ 全模态（语音 + 文字双向；用户也可以说话）
④ 纯语音电话（用户拨号 → AI 接听 → 全语音；本期 demo 不展示）
```

`multiSelect: false`

---

## 选项 → 后端配置映射

| 用户选项 | 内部枚举 (`io_modality`) | conversation-core io_modality 配置 | UI 影响 |
|---|---|---|---|
| ① 纯文字 IM | `text_only` | voice_input=disabled, voice_output=disabled | 浮窗仅显示输入框；隐藏麦克风 |
| ② 文字 + TTS（推荐） | `text_with_tts` | voice_input=disabled, voice_output=enabled (trtc-tts) | 浮窗显示输入框 + "朗读"开关；隐藏麦克风 |
| ③ 全模态 | `omni` | voice_input=enabled (trtc-asr), voice_output=enabled | 浮窗显示输入框 + 麦克风（push-to-talk） |
| ④ 纯语音电话 | `voice_only` | voice_input=enabled, voice_output=enabled, text_input=disabled | 不出 UI；仅供后端电话网关使用（本期不渲染浮窗） |

---

## 校验 / 回退

- 用户挑了 ④ 但 Q3 选了"浮窗" → 警告冲突，引导用户重新选 Q3 改为"仅后端 API"
- 用户挑了 ② / ③ 但 LLM 验证未通过 → 暂存选择，仍按用户原意写入 recipe；启动后浮窗会显示提示"语音输出依赖 TTS Key，当前不可用"

---

## 答复回写

```yaml
# 渲染到 <workspace>/recipe.yaml
runtime_modality:
  preset: text_with_tts          # 来自上表"内部枚举"列
  voice_input: false
  voice_output: true
  text_input: true
  text_output: true
```
