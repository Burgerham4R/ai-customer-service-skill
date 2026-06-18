# conversation-core · 快速开始

> 配置 → 运行 → 验证，三步搞定。

## 0. 前置依赖

- Python ≥ 3.9
- 已开通：腾讯云账户 + TRTC Conversational AI 应用 + 任一 OpenAI 兼容 LLM 服务

## 1. 安装

```bash
# 在仓库根目录
pip install -r capabilities/conversation-core/requirements.txt
```

## 2. 配置三把 Key

```bash
python scripts/setup-credentials.py
```

脚本会按 `[1/3] 腾讯云 → [2/3] TRTC → [3/3] LLM` 顺序交互式引导，每把 Key
输入后立即自检。失败不进入下一把；中途中断后再次执行会自动跳过已通过的
Key（断点续配）。

成功后产物：

| 路径 | 内容 | 权限 |
|:---|:---|:---:|
| `.env` | 三把 Key 的环境变量声明 | 600 |
| `.credentials_cache` | 已通过验证的 Key 摘要（SHA256） | 600 |
| `config-report.json` | 各 Key 的验证时间 / 延迟 / 状态 | 644 |

## 3. 启动 Web Demo

```bash
bash start.sh
# 等价：
# cd capabilities/conversation-core && python -m src.server
```

浏览器访问 <http://localhost:3000>。

## 4. 验收标准

- [x] ASR/LLM/TTS 链路无业务硬编码（仅做协议透传）
- [x] `setup-credentials.py` 支持实时连通性自检与断点续配
- [x] Web Demo 顶部状态栏三盏指示灯全绿
- [x] manifest.yaml 包含 skeleton 类型 / 注入点 / 模态 / 安全声明
- [x] INTEGRATION.md 提供 Agent 可读的检测逻辑与三级降级路径
- [x] `.credentials_cache` / `.env` 权限 600，日志中无明文 Key

## 5. 后续步骤

按 `manifest.yaml.injection_points` 声明的 5 个注入点叠加业务能力包：

```bash
voice-agent add knowledge-base
voice-agent add tool-calling
voice-agent add human-handoff
```
