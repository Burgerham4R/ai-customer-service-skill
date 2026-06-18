# scenarios/customer-service —— 路径 A 默认 Recipe

> 配套文档：仓库根 `SKILL.md`（路径 A SOP §5）。

本目录是路径 A 的"开箱即用"AI 客服 Demo —— Coding Agent 在用户说"基于 TRTC 帮我搭建一个 AI 客服"
后，按 `SKILL.md §5` 的 6 步流程装好 `knowledge-base` + `human-handoff` 两个能力包，跑 `post-install-patch.py`，
覆盖 UI，即可在 `http://localhost:3000` 看到本目录提供的 **Voice Agent UI**。

---

## 默认产物：voice-customer-service（v1.1）

- **真 Voice Agent**：基于 conversation-core voice 链路（TRTC enterRoom + agent/start + ASR/LLM/TTS）
- **静默 RAG**：用户每发一句，前端调 `/api/v1/kb/search`，命中**不弹卡片**，由 LLM 自然吸纳（保持对话流干净）
- **转人工排队动画**：8s 进度条 + shimmer 高光 + 倒计时；走完调 `/handoff/connect` 模拟 `demo_agent_alex` 接入；轮询拿到 `state=connected` 切换徽章
- **商品 / 订单业务面板**：左侧侧栏，点击卡片自动发起咨询
- **设计规范合规**：dark + 毛玻璃 + 薄荷绿 accent + Lucide SVG icon + tokens.css；UI 内**无 emoji**
- **英文化**：UI 文案 / mock 数据 / FAQ / 关键词触发全英文（面向海外开发者）
- **顶栏 LED hover 解释**：Tencent Cloud (CAM/STS 控制面) / TRTC (媒体数据面) / LLM (可替换推理引擎) 三者职责区分清楚

---

## 目录速览

```
scenarios/customer-service/
├── README.md                                 ← 本文件
├── recipe.yaml                               ← 路径 A 菜谱（AI 解析）
├── system-prompt.template.md                 ← 中性 system prompt 模板
├── sample-data/
│   └── faq-sample.json                       ← 5 条 demo FAQ（英文）
└── ui/
    ├── design-system/
    │   └── DESIGN_GUIDELINES.md              ← 设计规范（强制规范）
    ├── voice-customer-service/               ← ⭐ 默认 UI（v1.1 Voice Agent）
    │   ├── README.md
    │   ├── index.html                        ← 含 Lucide SVG icon defs + 三栏布局
    │   ├── app.js                            ← TRTC 链路 + KB 静默 + HH 进度条 + dedup
    │   ├── styles.css                        ← dark + 毛玻璃 + tooltip + 进度动画
    │   ├── mock-shop.json                    ← 3 商品 + 3 订单（英文）
    │   └── tokens.css                        ← 自动生成；禁止手改
    ├── widget-floating/                      ← 备选：轻量文本 IM 浮窗（不接 TRTC voice）
    └── admin-board/                          ← 工单坐席看板（运营端）
```

---

## 给 AI / 开发者：手工部署一次

> 路径 A 的 SOP 由 `SKILL.md §5` 主导；下面是**裸命令版本**（供本地手动验证）：

```bash
# 1. 装 KB + HH（默认 mock + local_queue adapter）
python3 scripts/add-capability.py knowledge-base human-handoff --apply --json

# 2. 兜底补丁（修旧版注入错位 + 写默认 .env capability 配置 + 校验 server.py）
python3 scripts/post-install-patch.py

# 3. UI overlay：voice-customer-service（默认） + admin-board
cp scenarios/customer-service/ui/voice-customer-service/{index.html,app.js,styles.css,data.js,mock-shop.json,tokens.css} \
   capabilities/conversation-core/web-demo/
mkdir -p capabilities/conversation-core/web-demo/admin
cp -R scenarios/customer-service/ui/admin-board/. \
      capabilities/conversation-core/web-demo/admin/

# 4. 启动（首次启动会创建 venv + pip install，30-60s）
bash start.sh
```

启动后访问：

| 入口 | URL | 用途 |
|---|---|---|
| AI Voice Agent | http://localhost:3000 | 终端用户 voice + text 双模对话 |
| Admin board | http://localhost:3000/static/admin/ | 坐席查看 / 接通 / 关闭工单 |
| Health probe | http://localhost:3000/api/v1/health | 三盏 LED JSON |
| API docs | http://localhost:3000/docs | FastAPI Swagger |

> ⚠ 之前文档误写过 `/admin/tickets`，那个路由不存在。**正确是 `/static/admin/`**。

---

## 切换到其他 UI

如果你不想要 voice 通道、只想要个轻量文字 IM 浮窗，把 Step 3 改成：

```bash
cp -R scenarios/customer-service/ui/widget-floating/. \
      capabilities/conversation-core/web-demo/
```

`widget-floating` 调的是 `/api/v1/kb/search` + `/api/v1/handoff/request`（纯 REST 文本 IM），**不会**拉起 TRTC 房间。

---

## 设计语言

- 全量引用 `design_tokens.json` v1.1.0；UI 中所有色值 / 字号 / 间距走 CSS 变量
- 字体锁定 `SF Pro / Inter / Helvetica Neue`
- UI 内**禁用 emoji**；状态指示走 `color.status.{success,info,warning,error}` 命名空间
- 毛玻璃面板带 `@supports` 兜底；旧浏览器降级为半透明纯色面板

任何对 `tokens.css` 的修改必须先改 `design_tokens.json`，再编译。

---

## 走向生产

1. **KB**：`KB_ADAPTER=mock` → `local_json`（指向真实 FAQ 文件）或 `default_rest`（接外部知识库）
2. **Handoff**：`HH_ADAPTER=local_queue` → `default_rest`；接口若与默认契约不一致，走 `SKILL.md §8.3` contract-adapt 流程生成 `user_custom.py`
3. **UI**：voice-customer-service 的 `<aside class="sidebar">` 商品 / 订单面板是占位 mock，实际接入时把 `loadShopPanel` 换成你自己的接口
4. **HTTPS**：`bash start.sh --https`（自签证书；正式环境建议挂反向代理换正式证书）
5. **看板权限**：`/static/admin/` 当前是公开静态页，上线时建议加路径前缀 + 反向代理鉴权
