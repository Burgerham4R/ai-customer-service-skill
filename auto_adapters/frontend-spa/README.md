# frontend-spa 适配器

> 把 conversation-core 骨架的 REST 接入到任意前端 SPA。
> Agent 在 L1 阶段会按当前 `tech_stack` 选择子目录的模板渲染并写入用户项目。

| tech_stack | 模板 | 默认目标 |
|:---|:---|:---|
| react / next | `react/VoiceAgent.tsx.tpl` | `src/components/${COMPONENT_NAME}.tsx` |
| vue          | `vue/VoiceAgent.vue.tpl`   | `src/components/${COMPONENT_NAME}.vue` |
| angular      | `angular/voice-agent.component.ts.tpl` | `src/app/voice-agent/voice-agent.component.ts` |

## 安装依赖（由 Agent 写入 package.json）

- `trtc-sdk-v5 >= 5.0.0`

## 安全

- 模板中 fetch 使用 `${SKELETON_BASE_URL}`，生产环境必须替换为 HTTPS 地址（骨架 manifest `security.network.enforce_https = true`）。
- TRTC SDK 需要 wss 通道；CSP 中允许：
  ```
  connect-src https://${SKELETON_BASE_URL} wss://*.trtc.tencent-cloud.com;
  ```

## 与能力包叠加

- 已安装 `tool-calling`：在 `Send` 框中输入 `/tool xxx {...}` 即触发本地工具调用。
- 已安装 `human-handoff`：发送"转人工"等关键字即触发排队接通流程。
