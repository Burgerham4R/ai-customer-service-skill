# Web Demo · 3 步启动指南

> 本目录为 conversation-core 的最小可运行验证页，**不含任何业务逻辑**。

## 三步启动

```bash
# 1. 安装依赖（首次）
pip install -r capabilities/conversation-core/requirements.txt

# 2. 配置三把 Key（交互式引导）
python scripts/setup-credentials.py

# 3. 启动 Demo
bash start.sh
# 或：cd capabilities/conversation-core && python -m src.server
```

打开浏览器访问 <http://localhost:3000>。

## 验证清单

打开页面后按以下顺序检查：

1. 顶部状态栏三盏指示灯由 `灰色` → `黄色（pending）` → `绿色`。
2. 三盏灯全绿后「开始对话」按钮可点击。
3. 点击后会自动调用 `/api/v1/get_config` 与 `/api/v1/agent/start`，控制台会输出 `task_id`。
4. 文字输入框中发送任意文字，可在 TRTC 控制台看到 ServerPushText 注入记录。

## 故障诊断

页面右上角点击「重新检测」可强制刷新连通性。失败时浏览器控制台会输出结构化诊断，例如：

```json
{
  "tencent_cloud": { "status": "ok", "latency_ms": 120 },
  "trtc":          { "status": "ok", "latency_ms": 12 },
  "llm":           { "status": "failed", "error_code": "E003", "detail": "unauthorized: 401" }
}
```

参照表中 `error_code` 对照 `INTEGRATION.md` 故障字典定位问题。

## 不在本 Demo 范围内的内容

- 真实音频采集与 TRTC RTC 入房（由 Phase 2 `frontend-spa` 适配器或集成方负责）
- 业务知识库 / FAQ / 工具调用（由独立能力包叠加）
- 数字人渲染、转人工、会话纪要等（由独立能力包叠加）
