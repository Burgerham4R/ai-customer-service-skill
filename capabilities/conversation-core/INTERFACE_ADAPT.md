# conversation-core 接口适配 SOP

> 骨架层接口适配指南。本期 conversation-core **未做 ports/adapters/core 重构**（阶段 1 折中策略，留待 Phase 4），
> 因此本文档仅说明"哪些接口允许替换、如何替换"，不提供自动化生成入口。

---

## 1. 默认契约速览

| 契约名 | 方法 | 路径 | 是否可适配 |
|---|---|---|---|
| `llm.chat_completions`        | POST | `/v1/chat/completions` (OpenAI 兼容)             | **可适配** |
| `trtc.start_ai_conversation`  | POST | 腾讯云 TencentCloudAPI                            | **不可适配**（强绑腾讯云） |

完整字段定义见 `manifest.yaml.business_contract.external_apis`。

---

## 2. LLM 接口替换（最常见）

骨架默认按 OpenAI Chat Completions 协议调用 LLM：
- 默认 `LLM_API_URL = https://api.openai.com/v1/chat/completions`
- 支持任意 OpenAI 兼容代理（DeepSeek / Qwen / 腾讯混元 OpenAPI / vLLM 等）

### 2.1 OpenAI 兼容协议（推荐路径）

仅需切换环境变量，**无需改代码**：

```bash
# 切换到 DeepSeek
export LLM_API_URL=https://api.deepseek.com/v1/chat/completions
export LLM_API_KEY=sk-xxx
export LLM_MODEL=deepseek-chat

# 切换到 Qwen（DashScope OpenAI 兼容入口）
export LLM_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
export LLM_API_KEY=sk-xxx
export LLM_MODEL=qwen-turbo

# 切换到 vLLM 自托管
export LLM_API_URL=http://your-vllm:8000/v1/chat/completions
export LLM_API_KEY=any-string
export LLM_MODEL=Qwen2.5-7B-Instruct
```

> 安全：自托管 LLM 必须使用 https://；http 仅允许 localhost。详见 `security_rules`。

### 2.2 非 OpenAI 协议（如 Claude Anthropic Messages API）

需要在骨架层引入"LLM 协议适配器"。本期未交付该机制，临时方案：

1. 在用户项目中部署 OpenAI ↔ Anthropic 协议转换网关（如 LiteLLM）
2. 把骨架的 `LLM_API_URL` 指向网关
3. 由网关完成协议转换

```bash
# 启动 LiteLLM 网关（参考 https://docs.litellm.ai/）
litellm --model anthropic/claude-3-5-sonnet --port 4000

# 骨架配置
export LLM_API_URL=http://localhost:4000/v1/chat/completions
export LLM_API_KEY=sk-anthropic-xxx
export LLM_MODEL=anthropic/claude-3-5-sonnet
```

### 2.3 Phase 4 计划：LLM Adapter 抽象

未来骨架将引入 `LlmClient` 抽象（同 human-handoff / knowledge-base 模式）：

```
capabilities/conversation-core/src/
├── ports/
│   └── llm_client.py          # ABC：chat / stream_chat / count_tokens
└── adapters/
    ├── openai_compat.py       # 当前默认实现
    ├── claude_anthropic.py    # 原生 Anthropic Messages API
    ├── tencent_hunyuan.py     # 腾讯混元原生 OpenAPI
    └── user_custom.py         # 用户接入向导生成
```

到时本文档会补充自动化适配流程。

---

## 3. TRTC Conversational AI 控制面（不可适配）

`trtc.start_ai_conversation` / `StopAIConversation` / `ControlAIConversation` /
`ServerPushText` 等控制面接口**强绑腾讯云协议**。如用户业务方不使用 TRTC，
不应继续使用本能力包，建议改用纯文本对话方案（参考 conversation-core 的
`text_input` / `text_output` 通道，绕开 TRTC 控制面）。

---

## 4. ASR / TTS 服务替换

骨架默认走 TRTC 内置的 ASR/TTS（由 `STTConfig` / `TTSConfig` 在 StartAIConversation
请求中声明）。如需切换到自有 ASR/TTS，可在 manifest 的
`config.io_modality.voice_input.provider` / `voice_output.provider` 中替换为自定义
provider 名称，并在用户项目中按 TRTC ConversationAI 文档实现自定义 provider 扩展。

本期未提供自定义 provider 的脚手架。

---

## 5. 安全清单

- [ ] 三把 Key 仅来自环境变量，**禁止**硬编码
- [ ] `LLM_API_URL` 必须使用 https:// 或 http://localhost
- [ ] 自托管 LLM 时拒绝私网地址（除 localhost）
- [ ] 日志中 `LLM_API_KEY` / `Authorization` 头自动脱敏（由骨架 `log_redaction` 负责）
- [ ] 凭证缓存文件权限强制 600
