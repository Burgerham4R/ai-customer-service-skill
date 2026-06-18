# voice-customer-service —— 路径 A 默认 UI（v1.1）

> 设计规范：`scenarios/customer-service/ui/design-system/DESIGN_GUIDELINES.md`
> 部署位置：`capabilities/conversation-core/web-demo/`（由路径 A SOP §5 Step 3 拷贝）

---

## 这套 UI 解决了什么

- conversation-core 自带的 `web-demo/` 是**开发自检页**（"Voice Agent Demo / All three indicators must be green before starting"），不能当作客服业务产物
- `widget-floating/` 是**轻量文本 IM 演示**，不拉起 TRTC voice 通道，只能展示 KB + 工单 REST API
- 本目录是**真 Voice Agent 客服**——基于 conversation-core voice 链路 + 客服业务能力叠加 + 业务面板

---

## 功能清单

| 模块 | 实现 |
|---|---|
| **顶栏** | 业务标题 + Cloud/TRTC/LLM 三盏 LED + Recheck 按钮 + 会话状态徽章；LED hover 显示 tooltip 解释三者职责差异 |
| **侧栏** | 商品列表（点击 → "I'd like to know more about..." 自动发送）+ 订单列表（点击 → "Can you check the status of order ..."）|
| **消息流** | IM 气泡（用户右 / AI 左 / 系统居中）；AI 字幕实时增量 / 累积自适应聚合；用户语音 ASR finalize 后落入气泡 |
| **语音** | 一键 Start → enterRoom + agent/start；麦克风开关；切换前自动智能打断 |
| **文字** | sendCustomMessage(cmdId:2, type:20000) 直送 AI bot；IME（中文输入法）兼容回车 |
| **KB 静默** | 用户每发一句调 `/api/v1/kb/search`；命中**不显示卡片**，仅 console.debug；保持对话窗干净 |
| **转人工** | 按钮 + 关键词触发（"talk to agent" 等）；工单卡 + 8s 进度条 + shimmer 高光 + 倒计时；走完调 `/handoff/connect` 模拟坐席接入；轮询切换 `state=connected` |
| **去重** | sendText 主动渲染 + 30s TTL local-echo 列表 → 跳过 AI bot 回放的同文本字幕（避免双气泡）|

---

## 文件清单

| 文件 | 说明 |
|---|---|
| `index.html` | 三栏布局 + 顶栏 + 控制栏；含 Lucide-style SVG icon defs（无 emoji）|
| `app.js` | 全套前端逻辑（health / TRTC / KB / HH / 商品订单 / dedup）|
| `styles.css` | dark theme + 毛玻璃 + 进度动画 + tooltip；100% 走 tokens.css 变量 |
| `mock-shop.json` | 3 商品 + 3 订单（英文 mock 数据）|
| `tokens.css` | 自动生成自 `design_tokens.json` v1.1.0；**禁止手改** |

---

## 接口契约（前端调用清单）

```
GET  /api/v1/health                 三盏 LED 自检
POST /api/v1/get_config             获取 sessionId / sdkAppId / roomId / userSig / agentUserId
POST /api/v1/agent/start            { session_id, language: "en" }
POST /api/v1/agent/stop             { session_id }
POST /api/v1/kb/search              { query, top_k: 1 }（静默；不渲染卡片）
POST /api/v1/handoff/request        { session_id, reason }
POST /api/v1/handoff/connect        { session_id, agent_id: "demo_agent_alex" }（用于模拟接通）
POST /api/v1/handoff/cancel         { session_id }
GET  /api/v1/handoff/{session_id}   工单状态轮询；返回 legacy_dict（字段是 state，不是 status）
GET  /static/mock-shop.json         商品 / 订单数据
```

> ⚠ **legacy 字段陷阱**：`/handoff/*` 用 `to_legacy_dict`，字段是 `state`，值 `waiting / connected / closed / canceled / timeout`（"canceled" 单 L），**没有顶层 ticket_id**（用 `session_id` 当跟踪 ID）。`/admin/tickets` 用 `to_dict`，那才有 `status` + `ticket_id`。

---

## 二次开发要点

- **改 KB 介入方式**：当前 `silentKbLookup` 命中只 console.debug；如需真 RAG，把命中条目作为 system prompt 上下文（需后端配合，conversation-core 当前不支持 system prompt 注入；可走修改 `agent_runtime.system_prompt.variables` 间接实现）
- **改排队等待时长**：`HANDOFF_QUEUE_MS = 8_000`
- **改模拟坐席名**：`SIM_AGENT_ID = "demo_agent_alex"`
- **添加业务面板**：`renderProducts` / `renderOrders` 已是模板，直接照抄改字段
- **多语**：当前默认英文（`agent/start` body `language: "en"`）；需要中/英切换时把语言切换写到 `state` + UI dropdown
