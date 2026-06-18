---
name: ai-customer-service
version: 1.2.0
description: |
  基于腾讯云 TRTC Conversational AI 的 AI 客服快速搭建 Skill（语音为核心）。
  面向零基础用户，全程用通俗易懂的日常语言引导，无需编程经验也能跑起来。
  支持两条路径：
    快速体验 —— 装好即用的语音客服 UI + 工单看板（适合第一次用、想看看效果的朋友）
    接入我的系统 —— 把 TRTC Conversational AI 后端能力接入已有项目（只给后端能力，不生成 UI）
  全程由 Coding Agent 在对话窗内主导，用户不开终端、不手动跑脚本。
triggers:
  keywords:
    - "AI 客服"
    - "搭建客服"
    - "客服机器人"
    - "TRTC + 客服"
    - "voice agent + 客服"
  example_prompts:
    - "基于 TRTC 帮我搭建一个 AI 客服"
    - "给我的项目加一个 AI 客服功能"
    - "用 TRTC Conversational AI 做一个客服 demo"
---

# AI 客服 Skill（v1.2）

> 本文档是 Coding Agent 的执行 SOP，同时也是对零基础用户友好的引导文案参考。
> 任何"搭建 / 接入 AI 客服"自然语言意图，AI 应**先读完本文件**再开始操作。
> 所有脚本调用必须严格走 §10 工具白名单。

---

## 0. 路径基准（SKILL_ROOT / PROJECT_ROOT）—— 🔴 最高优先级，先读

本 Skill 的全部运行时资产（`capabilities/`、`scripts/`、`scenarios/`、`auto_adapters/`、
`start.sh`）都位于 **Skill 自身目录**，而**不一定**在用户的工作区根目录下。
Skill 可以被安装在任意位置：项目的二级目录、`.agents/skills/`、`.codebuddy/skills/`，
未来还会跨 IDE（Claude Code / Codex / Cursor）。因此 **绝不能假设 "Skill 根 == 工作区根"**。

### 0.1 两个根的定义

| 变量 | 含义 | 如何取得 |
|---|---|---|
| `SKILL_ROOT` | **Skill 自身目录**（含 `SKILL.md` / `scripts/` / `capabilities/` …） | = 本 Skill 加载时系统注入的 **Base directory** 绝对路径。Agent 必须记住它。 |
| `PROJECT_ROOT` | **用户当前项目根**（= 工作区根，路径 B 的集成目标） | = 当前工作区根目录绝对路径。 |

> 演示路径（A）只用 `SKILL_ROOT`；集成路径（B）同时用到 `SKILL_ROOT`（取能力源 + 启动 core）
> 和 `PROJECT_ROOT`（集成目标）。二者**可能相同也可能不同**，不要混用。

### 0.2 路径使用硬规则

1. **所有调用 Skill 自带脚本 / 资产的命令，必须用 `SKILL_ROOT` 的绝对路径**，例如：
   ```bash
   cd "$SKILL_ROOT" && python3 scripts/add-capability.py ...
   # 或
   python3 "$SKILL_ROOT/scripts/add-capability.py" ...
   ```
   **禁止**写裸相对路径（如 `python3 scripts/...`）后默认它相对工作区根——那是旧版 bug 根源。
2. 本文档后续所有命令模板里出现的 `$SKILL_ROOT` / `$PROJECT_ROOT`，Agent 执行前**必须替换为实际绝对路径**。
3. 脚本本身（`start.sh` / `add-capability.py` / `post-install-patch.py`）已做自定位
   （基于 `__file__` / `BASH_SOURCE`），因此只要用对它们的**绝对路径**调用，无论 cwd 在哪都能跑通。
4. 若一时无法确定 `SKILL_ROOT`，用一次性探测兜底（不要让用户搬目录）：
   ```bash
   find "$PWD" -maxdepth 4 -name SKILL.md -path '*ai-service*' 2>/dev/null | head -1
   ```
   仍找不到再询问用户 Skill 安装位置。**永远不要要求用户把 Skill 移动到工作区一级目录。**

---

## 1. 何时使用本 Skill

**触发判定**（命中任一即应启动本 Skill）：
- 用户消息包含 §triggers.keywords 关键词之一
- 用户消息包含"TRTC"且涉及"客服 / 售后 / 客户支持 / customer service"
- 用户在已加载本 Skill 的会话中，明确表达"开始用 / 跑起来 / 集成进来"

**不适用场景**（直接拒绝并解释）：
- 仅为通用语音对话 Demo（非客服业务）→ 引导走 conversation-core README
- 需要数字人 / 电话外呼 → 当前不在本期范围
- 用户在非 TRTC 生态（Agora / 声网）→ 提示走对应 Skill

> **产品定位提醒**：本 Skill 封装的是 **TRTC Conversational AI（语音）** 能力，卖点即"语音客服"。
> 因此演示场景（路径 A）以语音为主。若用户只想要纯文字、仅复用 RTC 通道，请提示其自行配置，
> 本 Skill **不**为纯文字场景生成产物。

---

## 2. 交互语言探测（贯穿全程的硬约束）

> **目的**：搭建过程中 AI 的所有引导话术、`ask_followup_question` 的 question / options、
> 提示与小结，都必须**跟随用户首条 prompt 的自然语言**，不要写死中文。

**判定规则**（启动 Skill 后、§3 之前完成，结果存入内部变量 `interaction_lang`）：
- 取用户**触发本 Skill 的那条消息**为判定依据
- 主体为中文 → `interaction_lang = zh`
- 主体为英文（或其他非中文语言）→ `interaction_lang = en`（其他语言就近用英文）
- 用户中途显式要求切换语言 → 立即更新 `interaction_lang` 并沿用到后续所有交互

**应用范围（必须遵守）**：

| 场景 | 要求 |
|---|---|
| 路径分流选项 | question 与每个 option 都用 `interaction_lang` |
| 路径 B 问答话术 | 用 `interaction_lang` |
| 三把 Key 的引导话术 | 用 `interaction_lang` |
| 契约对齐选项与清单 | 用 `interaction_lang` |
| 启动后的入口清单 / 试用建议 | 用 `interaction_lang` |
| 错误恢复 / 警告提示 | 用 `interaction_lang` |

**与产物 UI 语言的关系**（仅路径 A 涉及 UI）：
- `interaction_lang` 控制的是「**搭建过程对话**」语言。
- **路径 A** 产物 UI 的默认语言（`recipe.yaml metadata.language`）**默认跟随 `interaction_lang`**，
  除非用户另行指定。
- **路径 B** 不生成 UI，因此只有"对话语言"，无"产物 UI 语言"一说；交付的代码注释 / README 用 `interaction_lang`。

> 不要因为 SKILL.md 本身是中文写的，就默认用中文跟用户对话。**以用户语言为准**。

---

## 3. 环境检查（自动完成，用户无需操作）

> **AI 引导话术**（本节以下内容按 `interaction_lang` 输出）：

在正式开始之前，系统会自动检查你的运行环境是否满足要求。这一步你不需要做任何操作，稍等片刻就好。

**检查项目**：
- Python 版本是否 >= 3.9
- Skill 目录文件是否完整
- 三把钥匙（云服务凭据）是否已配置过

如果检查通过，会自动进入下一步。如果检查不通过，系统会告诉你具体缺少什么以及如何修复。

---

**AI 执行动作**（所有命令中的 `$SKILL_ROOT` 执行前替换为 §0 确定的绝对路径）：

### 3.1 Python ≥ 3.9
```bash
python3 -c "import sys; assert sys.version_info >= (3, 9), sys.version" && echo OK || echo BAD_PY
```
失败 → 提示用户：
> 你的 Python 版本太低了，需要 3.9 或以上版本。可以去 https://www.python.org/downloads/ 下载最新版安装。装好之后我们继续。

**不再继续**直到 Python 版本满足。

### 3.2 SKILL_ROOT 校验
```bash
test -f "$SKILL_ROOT/capabilities/conversation-core/manifest.yaml" && echo OK || echo MISSING
```
- OK → 路径基准正确，继续。
- MISSING → 说明 `$SKILL_ROOT` 取错了。用 §0.2 第 4 条的 `find` 兜底重新确定 `SKILL_ROOT`，再重跑本检查。仍失败才询问用户 Skill 安装位置。

### 3.3 .env 状态
```bash
test -f "$SKILL_ROOT/capabilities/conversation-core/.env" && echo OK || echo MISSING
```
- OK → 表示三把钥匙已配置过。告知用户：
  > 检测到你之前配置过钥匙了，我们可以直接复用。如果你想重新配置，跟我说一声就行。
  后续可直接跳过 §5（除非用户明确要"重新配 Key"）。
- MISSING → 后续第一步必须进入 §5 三把钥匙配置。

---

## 4. 路径选择

> **AI 引导话术**：

环境检查通过！接下来我们做一个选择——你想怎么开始？

---

**第一步必做**：用 `ask_followup_question` 工具发出**单选问题**：

```json
[{
  "id": "path",
  "question": "你想怎么开始搭建 AI 客服？",
  "options": [
    "快速体验 —— 先把客服跑起来，打开浏览器就能看到效果（一个网页聊天窗口 + 工单管理后台）。需要配置 3 把钥匙，系统会自动装好默认能力，大约 2-3 分钟就能看到东西。适合第一次用、想先看看「这东西长什么样」的朋友",
    "接入我的系统（只给后端能力）—— 如果你已经有自己的网站或 App，想把 AI 客服的「大脑」接进去，就选这个。系统会给你一套 API 接口，不生成任何网页界面。需要配置 3 把钥匙，然后选择客服的交互方式和额外能力"
  ],
  "multiSelect": false
}]
```

- 选 A → 跳转 §6（路径 A：快速体验）
- 选 B → 跳转 §7（路径 B：接入我的系统）

> Coding Agent 不支持 ask_followup_question 时的 fallback：
> 在自然语言中列出两条路径，靠对话收集用户回复。**不要凭空假设**。

**AI 应主动说明的关键边界**：
> 不管选哪个，我都会带着你一步步走完。简单说下两条路径的区别：
> - 快速体验：我帮你生成一套完整的客服网页界面，你在浏览器里就能看到和体验
> - 接入我的系统：只给你 AI 客服的后端能力（API 接口），界面用你自己的，我把接口文档和示例代码给你，你交给开发人员对接就行

---

## 5. 三把钥匙配置

> **触发条件**：§3.3 返回 MISSING，或某把钥匙在后续被 verify-credentials.py 判定为失败。
> 命令中的 `$SKILL_ROOT` 执行前替换为绝对路径。

---

> **AI 引导话术**：

要让客服跑起来，需要配置 3 把钥匙——它们是云服务的通行证。别担心，我会带着你一把一把来。

---

### 5.1 配置方式说明

你可以选择以下两种方式之一来配置钥匙：

**方式一：自己动手填**
在项目根目录的 `.env` 文件中，找到对应的配置项，把等号右边的值替换成你自己的。下面提供了完整的配置模板，你可以整块复制粘贴到 `.env` 文件中。

**方式二：发给我帮你填**
把每一把钥匙的值通过对话框发给我，我会帮你写入 `.env` 文件。你的钥匙信息仅用于本次配置写入，系统会做安全处理，不会记录或泄漏你的密钥。

---

### 5.2 完整配置模板（可提供给用户整块复制）

```bash
# ==========================================
# AI 客服 Skill - 环境变量配置模板
# 复制整块内容到 .env 文件，替换等号右边的值
# ==========================================

# --- 第 1 把钥匙：腾讯云 API 密钥 ---
# 获取地址：https://console.cloud.tencent.com/cam/capi
TENCENT_CLOUD_SECRET_ID=你的SecretId
TENCENT_CLOUD_SECRET_KEY=你的SecretKey

# --- 第 2 把钥匙：TRTC 应用凭据 ---
# 获取地址：https://console.trtc.io/app
# （国内账号使用：https://console.cloud.tencent.com/trtc）
TRTC_SDK_APP_ID=你的SDKAppID（例如：1400000000）
TRTC_SDK_SECRET_KEY=你的SDKSecretKey（64位字符串）

# --- 第 3 把钥匙：LLM API Key ---
# 填写你使用的 AI 大模型服务的 API Key
LLM_API_KEY=你的APIKey
LLM_API_BASE_URL=你的API地址（如使用非 OpenAI 服务需填写）
LLM_MODEL_NAME=你的模型名称（如 gpt-4o / deepseek-chat / claude-3-opus）
```

---

### 5.3 逐把钥匙收集流程

#### 第 1 把：腾讯云 API 密钥（SecretId / SecretKey）

**AI 应该说**：
> 我们先来配第 1 把钥匙——腾讯云 API 密钥。这把钥匙用来证明你有权限使用腾讯云的语音和通话服务。
>
> 获取步骤：
> 1. 打开这个网页：https://console.cloud.tencent.com/cam/capi （如果你还没登录腾讯云，先登录一下）
> 2. 打开后你会看到一个叫「API 密钥管理」的页面，里面有一个 **SecretId** 和一个 **SecretKey**（可能需要点「显示」才能看到完整内容）
>
> 把这两个值填到下面这个代码块里，注意替换掉中文占位符（`你的SecretId` 和 `你的SecretKey`），然后**整段复制发给我**就行：
>
> ```
> # 我的腾讯云 API 密钥
> TENCENT_CLOUD_SECRET_ID=你的SecretId
> TENCENT_CLOUD_SECRET_KEY=你的SecretKey
> ```

**用户回复代码块后**，AI 需解析其中等号右边的值：
1. 校验格式：SecretId 长度通常 36，`^[A-Za-z0-9]+$`；SecretKey 不为空
2. 工具：`write_to_file("$SKILL_ROOT/capabilities/conversation-core/.env", <写入 TENCENT_CLOUD_SECRET_ID=... + TENCENT_CLOUD_SECRET_KEY=... + TENCENT_CLOUD_REGION=ap-guangzhou>)`
3. 不回显 Key 原文；只确认"已收到，长度/格式 OK"
4. 工具：`execute_command("cd \"$SKILL_ROOT\" && python3 scripts/verify-credentials.py --type tencent")`
5. 解析 stdout JSON：
   - `{"ok": true, ...}` → 告知用户"第 1 把钥匙验证通过"，进入第 2 把
   - `{"ok": false, "error": "E001"}` → 按 §5.5 错误码表应答，请用户重试
   - `{"ok": false, "error": "E000"}` → 检查是否用户发来的代码块中某个值仍为中文占位符，若有则提示"我看到某个值好像还是占位符没替换，麻烦再发一次完整的代码块"

#### 第 2 把：TRTC 应用凭据（SDKAppID / SDKSecretKey）

**AI 应该说**：
> 配好了！现在来第 2 把——TRTC 应用凭据。这把钥匙让客服能打电话、能语音聊天。
>
> 获取步骤：
> 1. 打开这个网页：https://console.trtc.io/app （如果你用的是腾讯云国内账号，走这个：https://console.cloud.tencent.com/trtc）
> 2. 找到你之前创建过的「智能对话」应用（如果没有，点一下新建就行）
> 3. 进入应用后，你会看到两个信息需要找出来：
>    - **SDKAppID**：一串数字
>    - **SDKSecretKey**：一串很长的字母和数字混合的字符（在「服务端集成」那个区域里）
> 4. ⚠️ 注意区分：页面上可能还有一个叫 STSecretKey 的东西，那个是给客户端用的，我们不要那个。我们要的是 **SDKSecretKey**（服务端用的那个）
>
> 把这两个值填到下面这个代码块里，注意替换掉中文占位符（`你的SDKAppID` 和 `你的SDKSecretKey`），然后**整段复制发给我**就行：
>
> ```
> # 我的 TRTC 应用凭据
> TRTC_SDK_APP_ID=你的SDKAppID
> TRTC_SDK_SECRET_KEY=你的SDKSecretKey
> ```

**用户回复代码块后**，AI 需解析其中等号右边的值：
1. 校验：SDKAppID 是整数；SDKSecretKey 必须是 64 字符 `[0-9a-f]`
   （**特例**：检测到 128 字符且前后 64 完全相同 → 自动截断为前 64，并提示用户）
2. 工具：`write_to_file` 追加 `TRTC_SDK_APP_ID=` + `TRTC_SDK_SECRET_KEY=`（默认国际站，不写 TRTC_REGION）
3. 工具：`execute_command("cd \"$SKILL_ROOT\" && python3 scripts/verify-credentials.py --type trtc")`
4. 解析 stdout JSON 同上（失败按 §5.5 错误码表应答；若值仍为中文占位符，提示重新发送）

#### 第 3 把：LLM API Key

**AI 应该说**：
> 很好！最后一把——LLM API Key。这把钥匙让客服能"思考"——理解客户的问题并给出回答。你需要有一个 AI 大模型服务的账号。
>
> 如果你还没有大模型账号，可以从下面这些服务商里选一个去注册和获取 API Key（每个服务商的 API Key 获取网址都列出来了，直接点进去就行）：

| 服务商 | 模型系列 | 获取 API Key 的网址（点进去就能看到 Key） |
|--------|----------|------------------------------------------|
| OpenAI | GPT 系列 | https://platform.openai.com/api-keys |
| Anthropic | Claude 系列 | https://console.anthropic.com/settings/keys |
| Google AI | Gemini 系列 | https://aistudio.google.com/apikey |
| DeepSeek | DeepSeek 系列（高性价比，中文能力强） | https://platform.deepseek.com/api_keys |
| Together AI | 开源模型托管 | https://api.together.ai/settings/api-keys |
| Groq | 高性能推理 | https://console.groq.com/keys |
| Cohere | 企业级 AI | https://dashboard.cohere.com/api-keys |
| Mistral AI | Mistral 系列（欧洲服务商） | https://console.mistral.ai/api-keys |

> 选好服务商、拿到 API Key 之后，填到下面这个代码块里（注意替换掉中文占位符），然后**整段复制发给我**：
>
> ```
> # 我的 LLM API 配置
> LLM_API_KEY=你的APIKey
> LLM_API_BASE_URL=你的API地址
> LLM_MODEL=你的模型名称
> ```
>
> 填的时候留意：
> - 如果你用的是 **OpenAI**，`LLM_API_BASE_URL` 这一行可以删掉不用填（默认就是 OpenAI 的地址）
> - 如果你用的是其他服务（比如 DeepSeek、Claude、Gemini 等），`LLM_API_BASE_URL` 和 `LLM_MODEL` 都要填。具体填什么，去你注册的那个服务商的文档里查一下，关键词搜「API Base URL」和「Model Name」就能找到

**用户回复代码块后**，AI 需解析其中等号右边的值：
1. 校验：`LLM_API_KEY` 不为空
2. 若 `LLM_API_BASE_URL` 为空或值为占位符，默认用 `https://api.openai.com/v1`
3. 若 `LLM_MODEL` 为空或值为占位符，默认用 `gpt-4o`
4. 工具：`write_to_file` 追加 `LLM_API_KEY=` + `LLM_API_URL=...` + `LLM_MODEL=...`
5. 工具：`execute_command("cd \"$SKILL_ROOT\" && python3 scripts/verify-credentials.py --type llm")`
6. 解析 stdout JSON：
   - `{"ok": true, ...}` → 告知用户"三把钥匙全部就绪，进入下一步"
   - `{"ok": false, "error": "E003"}` → 按 §5.5 错误码表应答，给出提示
   - 若值仍为中文占位符，提示"我看到代码块里还有中文占位符没替换，麻烦重新填好再发一次"

---

### 5.4 安全约束（红线，违反即视为缺陷）

| 红线 | 正确做法 |
|---|---|
| 不要把 Key 作为命令行参数传给任何脚本 | 通过 write_to_file 写入 .env，再调无参数 verify-credentials.py |
| 不要在对话回复中回显 Key 完整值 | 仅确认"已收到 + 长度/格式 OK" |
| 不要把 Key 输出到日志 / stdout | verify-credentials.py 自动只输出 ok/error/message/latency_ms |
| 不要使用 `echo $SECRET` / `cat .env` | shell history / 终端日志会记录 |
| .env 写完后权限应为 600 | execute_command("chmod 600 \"$SKILL_ROOT/capabilities/conversation-core/.env\"") |

---

### 5.5 错误码 → AI 应答模板

| error | 含义 | AI 应对用户说的内容 |
|---|---|---|
| E000 | 凭证未配置/为空 | "我看 .env 里这一项没写或为空，请重新发一次" |
| E001 | 腾讯云 API 验证失败 | "腾讯云 API 验证没通过。常见原因：①Id/Key 顺序发反了 ②Key 已被禁用 ③账号没开通 STS 服务。请到 console.cloud.tencent.com/cam 核对一下" |
| E002 | TRTC 验证失败 | "TRTC 验证没通过。请确认：①SDKAppID 是不是属于你的账号 ②有没有把 SDKSecretKey 和 STSecretKey 搞混 ③国内站应用可能需要在 .env 里加一行 TRTC_REGION=cn" |
| E003 | LLM 验证失败 | "LLM 验证没通过。如果你用的是非 OpenAI 服务，可能需要同时改 API 地址，请告诉我你用的是哪家服务" |
| E004 | 网络不可达 | "无法连接到验证服务器。请检查：①是否需要开代理 ②公司防火墙是否拦了 ③当前网络是否正常。也可以先跳过深度校验继续往下走" |

---

## 6. 路径 A：快速体验

> 用户在 §4 选择了 A。
> 默认产物：**语音客服 UI**（TRTC 真接通、FAQ 静默 RAG、转人工排队动画 + 模拟接通、商品/订单业务面板）。
> 所有命令中的 `$SKILL_ROOT` 执行前替换为绝对路径。

---

> **AI 引导话术**（路径 A 入口）：
> 好的，走快速体验路径！我会帮你把整套客服系统装好，你什么都不用做，稍等片刻就好。
>
> 这条路径会自动帮你装好以下能力：
> - **对话能力**：客服真的能听懂你说什么并回答你（因为配了真实的 AI 钥匙）
> - **转人工**：你能看到转人工的流程和界面（用的是演示数据）
> - **知识库**：你能看到知识库检索的效果（用的是演示文档）
>
> 装好后，你打开浏览器就能看到一个完整的客服对话界面和一个工单管理后台。

---

### 6.0 部署参数（可调整）

| 参数 | 默认 | 说明 |
|---|---|---|
| 部署目录 | `$SKILL_ROOT/capabilities/conversation-core/web-demo/` | 演示 UI 落地位置；如用户要求改，用其指定目录 |
| 端口 | `3000` | 被占用或用户指定时改：`bash "$SKILL_ROOT/start.sh" --port <N>`，后续 health/URL 同步换端口 |

---

### 6.1 步骤序列（6 步）

**Step 1：配置三把钥匙**
- 工具：`execute_command("test -f \"$SKILL_ROOT/capabilities/conversation-core/.env\" && echo OK || echo MISSING")`
- 返回 OK → 进入 Step 2
- 返回 MISSING → 进入 §5 三把钥匙配置子流程，完成后回到 Step 2

**Step 2：装配能力包**

> **AI 提示用户**：
> 正在安装依赖包、装配默认能力，大约需要 30-60 秒...

- 工具：`execute_command("cd \"$SKILL_ROOT\" && python3 scripts/add-capability.py knowledge-base human-handoff --apply --json")`
- 期望：返回 JSON 中所有 `reports[*].errors == []`，无致命 `injection.error`
- 失败处理：
  - 循环依赖/版本冲突 → 按 stderr 信息向用户解释，停步
  - L2 (templates) → 装到 templates 目录，告知用户手动注入位置
  - L3 (manual) → 输出 `$SKILL_ROOT/auto_adapters/integration_templates/generic-frontend.md` 路径

**Step 2.5：装后兜底补丁（必跑）**
- 工具：`execute_command("cd \"$SKILL_ROOT\" && python3 scripts/post-install-patch.py")`
- 期望：返回 `{"ok": true, ...}`
- 该脚本干 3 件事：
  - 修旧版扩展点错位注入
  - 把 recipe 默认 capability 配置追加到 `.env`（已存在的不动）
  - 校验 `server.py` 的 `StaticFiles(html=True)`

**Step 3：UI overlay（必跑，路径 A 专属）—— 默认语音客服 UI**
- 工具（一条命令）：
  ```bash
  execute_command(
    "cp \"$SKILL_ROOT\"/scenarios/customer-service/ui/voice-customer-service/{index.html,app.js,styles.css,data.js,mock-shop.json,tokens.css} \
        \"$SKILL_ROOT\"/capabilities/conversation-core/web-demo/ && \
     mkdir -p \"$SKILL_ROOT\"/capabilities/conversation-core/web-demo/admin && \
     cp -R \"$SKILL_ROOT\"/scenarios/customer-service/ui/admin-board/. \
           \"$SKILL_ROOT\"/capabilities/conversation-core/web-demo/admin/"
  )
  ```
- 期望：`web-demo/` 下出现 `index.html / app.js / styles.css / data.js / mock-shop.json / tokens.css` + `admin/` 子目录
- 失败处理：检查 `$SKILL_ROOT/scenarios/customer-service/ui/voice-customer-service/` 是否完整

**Step 4：主动列出 business_contract**（进入 §9）

**Step 5：启动 demo**

> **AI 提示用户**：
> 正在启动客服系统，第一次启动需要安装一些依赖包，可能需要 30-60 秒，请稍等...

- 工具：`execute_command("cd \"$SKILL_ROOT\" && nohup bash start.sh > /tmp/ai-cs-start.log 2>&1 &")`
- 工具：`execute_command("sleep 8 && curl -sS http://localhost:3000/api/v1/health")`
- 第一次启动会创建 venv + 跑 pip install，**通常需 30-60s**
  - 若 sleep 8 后健康检查失败 → 工具：`execute_command("sleep 25 && curl -sS http://localhost:3000/api/v1/health")` 再试一次
  - 仍失败 → `tail -80 /tmp/ai-cs-start.log` 看是否 pip install 错/端口被占
- 健康检查返回 `{"status":"ok",...}` → 进入 Step 6

**Step 6：输出入口清单 + 试用建议**

> **AI 应该说**：
> 搞定了！你的 AI 客服已经跑起来了，在浏览器里打开下面这些地址就能看到效果：

| 页面 | 链接 | 说明 |
|---|---|---|
| AI Voice Agent | http://localhost:3000 | (客服对话界面) |
| Admin board | http://localhost:3000/static/admin/ | (工单管理后台) |
| API docs (Swagger) | http://localhost:3000/docs | (接口文档) |
| Health probe | http://localhost:3000/api/v1/health | (健康检查) |

```
Try saying / typing:
  · "How do I get a refund"        → AI replies; KB silently augments answer
  · "Talk to agent"                → handoff queue + 8s progress bar + simulated connect
  · Click any product / order card → auto-asks the AI about that item
```

> 提示：转人工和知识库用的是模拟数据，所以你看不到真实的业务对接效果。如果你想接入真实的业务系统，可以重新来一遍选「B 接入我的系统」。

---

### 6.2 不要做的事

- ❌ 用裸相对路径调脚本（必须 `cd "$SKILL_ROOT"` 或用绝对路径，见 §0）
- ❌ 跳过 .env 检查直接装能力包
- ❌ 把任何 Key 通过命令行参数传给脚本
- ❌ 修改 `capabilities/*/src/core/`（这是骨架层；不要动）
- ❌ 跳过 Step 2.5（不跑 post-install-patch.py 会让 add-capability 的已知错位注入残留 → 启动报 NameError）
- ❌ 跳过 Step 3（不跑 UI overlay 会让 `/` 留在 conversation-core 自带的 voice 自检页 → 不是产物）
- ❌ 把"工单看板地址"说成 `/admin/tickets`（**正确是 `/static/admin/`**）
- ❌ 执行 `git commit` / `git push`（除非用户明确要求）
- ❌ 在对话回复中回显完整 Key 内容

---

## 7. 路径 B：接入我的系统（只给后端能力）

> 用户在 §4 选择了 B。
> **关键定位**：把 TRTC Conversational AI 的**后端能力**接入用户**已有项目**（`PROJECT_ROOT`）。
> - `conversation-core` 是核心：必须**端到端跑通语音对话链路**（测到能对话为止）。
> - 其余增量能力（knowledge-base / human-handoff / session-summary / tool-calling）：
>   只交付**接口规范 + mock 实现 + 示例代码**，由用户按需替换成自己的系统。
> - **本路径 Skill 绝不生成任何前端 UI**——UI 由用户用自己的前后端自备。

---

> **AI 引导话术**（路径 B 入口，必须显式声明边界）：
> 好的，走「接入我的系统」路径。这条路径会把 AI 客服的**后端能力**接进你现有的项目。
>
> 我会帮你做这些事情：
> - 把语音对话核心（conversation-core）装好，并端到端跑通，确保能正常对话
> - 知识库、转人工、会话纪要等额外能力，我只提供**接口规范 + 模拟实现 + 示例代码**，你按需替换成自己的真实系统
> - **我不会生成任何网页界面**——界面用你自己项目的前端来接
>
> 接下来分几步走：先确认你的项目，然后选能力，最后选客服的交互方式。

---

### 7.1 确认集成目标（PROJECT_ROOT 与技术栈）

1. 确认 `PROJECT_ROOT`（默认 = 当前工作区根）。若用户的项目在子目录，请其指明，作为 `--target-project`。
2. 让脚本自动识别项目技术栈（无需手填）：
   ```bash
   cd "$SKILL_ROOT" && python3 scripts/add-capability.py --list --json
   ```
   技术栈识别在 Step 7.3 装配时由 `--target-project` 自动触发（`stack_detector`）。
   如自动识别不准，可用 `--tech-stack <react|vue|node|python|java|...>` 覆盖。

### 7.2 配置三把钥匙
- 工具：`execute_command("test -f \"$SKILL_ROOT/capabilities/conversation-core/.env\" && echo OK || echo MISSING")`
- MISSING → 进入 §5 完成三把钥匙（语音核心强依赖三把钥匙，全部必需）。

### 7.3 能力选择（可选增量能力，可多选）

> **AI 应该说**（用 `ask_followup_question` 多选模式）：
> 接下来决定客服具备哪些额外能力。除了默认自带的语音对话能力，你还可以选以下能力。可以多选，也可以一个都不选。不选的话客服就只有最基本的对话能力。

| 编号 | 能力包 | 功能描述 | 选了之后的效果 |
|------|--------|----------|----------------|
| 1 | 知识库 | FAQ/知识库检索 | 上传一份退货政策 PDF，客户问"怎么退货"时客服就能自动回答 |
| 2 | 转人工 | 客服搞不定时自动转给真人 | 复杂问题（如投诉、退款纠纷）自动转给人工坐席，附带工单看板 |
| 3 | 工具调用 | 让客服能主动查你系统里的数据 | 客户问"我的订单到哪了"，客服能直接查数据库返回物流状态 |
| 4 | 对话总结 | 每次聊完自动生成一份摘要 | 对话结束后自动写纪要，方便你回顾客户说了什么、存档备查 |

```json
[{
  "id": "capabilities",
  "question": "需要哪些额外能力？（可多选）",
  "options": [
    "① 知识库 —— FAQ/知识库检索",
    "② 转人工 —— 转人工 + 工单流",
    "③ 工具调用 —— 让 AI 调你的业务工具",
    "④ 对话总结 —— 会话结束自动生成纪要",
    "（都不选，只要基本对话能力）"
  ],
  "multiSelect": true
}]
```

> 选好了吗？直接告诉我编号就行（比如"1、2、3"或"全要"）。

**装配命令**（把增量能力的接入适配器/示例渲染进用户项目）：
```bash
cd "$SKILL_ROOT" && python3 scripts/add-capability.py <勾选的增量能力...> \
    --target-project "$PROJECT_ROOT" --apply --json
# 全不选则跳过本命令（仅跑核心语音）
```
- `--target-project` 会触发 `auto_adapters` 三级降级渲染：
  - L1：按检测到的技术栈，把**入房组件/后端代理路由示例**渲染进 `$PROJECT_ROOT`
  - L2：渲染到 templates 目录并列出 TODO
  - L3：输出通用接入指引让用户手接
- 解析返回 JSON，把落地文件路径告诉用户

**兜底补丁（必跑）**：
```bash
cd "$SKILL_ROOT" && python3 scripts/post-install-patch.py
```

### 7.4 I/O 模态选择（选定客服的"沟通方式"）

> **AI 应该说**（用 `ask_followup_question` 单选模式）：
> 接下来定一下客服的"沟通方式"——你的客服用什么方式和客户交流？下面是 4 种方式，**选一种**最适合你业务场景的就行：

| 编号 | 模态 | 通俗描述 | 适合的场景 |
|------|------|----------|------------|
| 1 | 纯文字 IM | 客服只通过打字聊天回复客户 | 网页在线客服、App 内消息、微信客服 |
| 2 | 文字 + TTS | 客服打字回复，同时能把文字转成语音播报给客户听 | 需要语音反馈但不想接电话线路，比如智能音箱、App 语音助手 |
| 3 | 全模态 | 文字、语音都能用，最完整的交互方式 | 需要文字、语音多种方式通用的高级客服场景 |
| 4 | 纯语音电话 | 客服只通过电话语音沟通，没有文字界面 | 呼叫中心、400 电话客服、语音热线 |

```json
[{
  "id": "modality",
  "question": "选哪种沟通方式？",
  "options": [
    "① 纯文字 IM —— 打字聊天",
    "② 文字 + TTS —— 打字回复 + 语音播报",
    "③ 全模态 —— 文字、语音都能用",
    "④ 纯语音电话 —— 只通过电话语音沟通"
  ],
  "multiSelect": false
}]
```

> 选好了吗？直接告诉我编号就行。

### 7.5 端到端验收（语音核心，无 UI）

> 因不提供 UI，语音听感由用户在自己前端验证。Skill 侧验收口径如下（三项全过即视为端到端跑通）：

1. **健康自检**：`GET /api/v1/health` 三盏 LED（tencent_cloud / trtc / llm）全绿
2. **控制面拉起**：`POST /api/v1/agent/start` 成功返回 `TaskId / SessionId`
3. **接入示例交付**：按用户技术栈渲染出的入房/控制示例代码已落到 `$PROJECT_ROOT`

启动 core：
```bash
cd "$SKILL_ROOT" && nohup bash start.sh > /tmp/ai-cs-start.log 2>&1 &
sleep 8 && curl -sS http://localhost:3000/api/v1/health
```

### 7.6 收尾交付物

> **AI 应该说**：
> 装配完成！你的 AI 客服后端能力已经就绪。以下是交付给你的内容：

- `/api/v1/*` 后端接口契约（§9 输出）
- 各增量能力的 outbound 契约清单 + mock 说明 + 替换指引
- 用户技术栈对应的接入示例代码路径
- 联调入口：启动后的 `/docs`（Swagger）

> 接下来你要做的事：把接口清单交给开发人员，让他们按照文档把 AI 客服能力接到你的网站或 App 里。如果你在对接过程中遇到问题，随时回来找我。

### 7.7 不要做的事（路径 B）
- ❌ 生成任何前端 UI/套用 voice-customer-service/widget-floating 等 UI（那是路径 A 的）
- ❌ 用裸相对路径调脚本（见 §0）
- ❌ 替用户把 mock 改成接真实业务系统（只给规范 + 适配器，替换由用户决定）
- ❌ 改 `capabilities/*/src/core/` 骨架层

---

## 8. 能力联动：转人工 ↔ 会话纪要（已实装）

> 当 **human-handoff 与 session-summary 同时安装**时，二者自动联动，无需 AI 额外配置。
> 本联动属后端能力，路径 A / B 都生效。

**行为**：转人工**建单的瞬间**，human-handoff 会 best-effort 触发 session-summary
对该 session 生成纪要（建单链路走**启发式**摘要，本地零延迟、不阻塞），
并把摘要**快照进工单 payload**（`ticket.session_summary`）。坐席在看板点开工单详情，
即可**直接看到**客户问题上下文（主题/用户意图/后续动作），无需手动点"生成纪要"。

**实现要点（维护者须知）**：
- 联动入口：`capabilities/human-handoff/src/summary_link.py`（`attach_summary_to_ticket`）
- **软依赖**：通过 conversation-core 的 `_capability_loader` 动态加载 session-summary；
  未安装/任何异常 → 静默跳过，**不影响转人工主流程**
- 看板渲染（路径 A）：`admin-board/app.js` **优先**读工单内嵌的 `session_summary`
- 建单链路默认 `prefer_llm=False`（避免 LLM 往返阻塞建单）

> **不要**把建单时的摘要生成改成同步调用 LLM —— 会让 `/handoff/request` 卡住 ≥数秒。

---

## 9. 接口契约对齐

> 触发条件：装配完成后必做。命令中的 `$SKILL_ROOT` 执行前替换为绝对路径。

### 9.1 列出本次能力包的 outbound API

读各能力包的 `manifest.yaml.business_contract.external_apis`，
**仅列 `direction == outbound`** 的条目，按以下格式自然语言输出：

```
✓ 已装好 conversation-core + knowledge-base + human-handoff。
本次使用 mock / local 实现作为演示数据。

我们的能力包会调用以下外部业务接口：

  1. POST   /tickets                      ← human-handoff 工单创建
  2. GET    /tickets/{ticket_id}          ← human-handoff 工单状态查询
  3. POST   /tickets/{ticket_id}/cancel   ← human-handoff 工单取消
  4. POST   /faq/search                   ← knowledge-base FAQ 检索
  5. GET    /faq                          ← knowledge-base FAQ 列表
  6. POST   /faq                          ← knowledge-base FAQ 新增/更新
  7. DELETE /faq/{entry_id}               ← knowledge-base FAQ 删除
```

> 路径 B 提醒：契约清单是**交付给用户**的核心产物之一；即便用户选"先用 mock 跑"，也要把这份清单留给他。

### 9.2 询问用户

> **AI 应该说**：
> 要切换到真实的工单/知识库系统吗？
> - 接入我自己的系统，做相应接口适配
> - 先用模拟数据跑：跳过接口对接，直接启动

用 `ask_followup_question` 单选：
- 接入自己系统 → 进入 §9.3
- 先用 mock 跑 → 跳到 §10（不动 adapter 配置）

### 9.3 contract-adapt 流程

1. AI 询问"按哪个能力包对齐？"（多选：human-handoff / knowledge-base）
2. 对每个能力包：
   - AI 询问"贴你的接口描述：①curl 命令 ②OpenAPI YAML 文件路径"
   - 收集后**写入临时文件**：
     - curl → `write_to_file(/tmp/adapt_<cap>.curl.txt, <用户原文>)`
     - OpenAPI → 用户已有路径，直接传
   - 工具：`execute_command("cd \"$SKILL_ROOT\" && python3 scripts/contract-adapt.py <cap> --curl-file /tmp/adapt_<cap>.curl.txt --json")`
     或 `--openapi-file <path>`
3. 解析返回 JSON：
   - `{"level":"L1","artifact":"<path>"}` → 告知用户"已生成 user_custom.py，可直接启用"
   - `{"level":"L2","artifact":"<path>","todos":[...]}` → 列出 TODO 让用户填
   - `{"level":"L3","guide":"INTERFACE_ADAPT.md#section"}` → 让用户照抄文档

### 9.4 启用 user_custom

`write_to_file` 追加到 `$SKILL_ROOT/capabilities/conversation-core/.env`：
```
HH_ADAPTER=user_custom         # 或 KB_ADAPTER=user_custom
HH_REST_BASE_URL=https://...
HH_REST_TOKEN=...              # 如有
```

---

## 10. 启动验证

> 端口默认 3000，可用 `--port <N>` 调整；调整后下面所有 URL / health 同步换端口。
> 命令中的 `$SKILL_ROOT` 执行前替换为绝对路径。

### 10.1 启动
```bash
cd "$SKILL_ROOT" && nohup bash start.sh > /tmp/ai-cs-start.log 2>&1 &
# 自定义端口：cd "$SKILL_ROOT" && nohup bash start.sh --port 8080 > /tmp/ai-cs-start.log 2>&1 &
```

### 10.2 健康自检（首次启动需要 ≥30s — pip install）
```bash
sleep 8 && curl -sS http://localhost:3000/api/v1/health
# 若返回连接失败：再等等
sleep 25 && curl -sS http://localhost:3000/api/v1/health
```
期望返回包含 `"status":"ok"`，三盏 LED（tencent_cloud / trtc / llm）全 ok。

### 10.3A 路径 A 全绿 → 输出最终消息
```
Setup complete. Open the following URLs:

  · AI Voice Agent     http://localhost:3000             (default)
  · Admin board        http://localhost:3000/static/admin/
  · API docs (Swagger) http://localhost:3000/docs
  · Health probe       http://localhost:3000/api/v1/health

To stop: lsof -ti :3000 -sTCP:LISTEN | xargs kill
```

> **正确入口**：管理看板路径是 `/static/admin/`（**不是** `/admin/tickets`，这条路由不存在）。

### 10.3B 路径 B 验收 → 输出最终消息（无 UI）
```
Backend capabilities integrated. Verification:

  · Health probe       http://localhost:3000/api/v1/health   (3 LEDs green)
  · Control-plane      POST /api/v1/agent/start  → returns TaskId / SessionId
  · API docs (Swagger) http://localhost:3000/docs            (联调入口)

Delivered to your project ($PROJECT_ROOT):
  · 接入示例代码（入房/控制），调用顺序：get_config → 入房 → agent/start → agent/control → agent/stop
  · 各增量能力 outbound 契约清单 + mock 说明（按需替换为你的真实系统）

UI 由你自己的前端实现；语音听感请在你的前端入房后验证。
To stop: lsof -ti :3000 -sTCP:LISTEN | xargs kill
```

---

## 11. 常见问题处理

如果在使用过程中遇到以下问题，这里提供了对应的解决方法：

| 问题 | 原因 | 解决方法 |
|------|------|----------|
| Key 验证失败 | 配置的 Key 过期或填错 | 回到 §5 重新检查每把钥匙的值是否正确，可以只重填失败的那一把 |
| 端口被占用 | 端口 3000 被其他程序占用 | 可以换一个端口（如 `--port 8080`），或者关掉占用 3000 端口的程序 |
| 网络不可达 | 企业内网或防火墙限制 | 检查是否需要配置代理，或联系网络管理员开放相关域名 |
| Python 版本过低 | Python < 3.9 | 去 https://www.python.org/downloads/ 下载最新版本安装 |
| 启动后报错 | 依赖包版本冲突 | 系统会自动修复，如果持续报错请把错误信息发给我 |
| 浏览器看到的是旧界面（路径 A） | 浏览器缓存了旧页面 | `Cmd+Shift+R`（Mac）或 `Ctrl+Shift+R`（Windows）强制刷新 |
| `/admin/tickets` 返回 404（路径 A） | 这条路由不存在 | 正确入口是 `http://localhost:3000/static/admin/` |

---

### 11.1 错误恢复技术详情

#### 找不到资产/报 "No such file" / scripts 跑不起来
- **根因**：用了裸相对路径，cwd 不是 `SKILL_ROOT`（旧版最常见问题）。
- **解决**：按 §0 重新确定 `SKILL_ROOT` 绝对路径，所有命令 `cd "$SKILL_ROOT"` 或用绝对路径重跑。
- **绝不要**让用户把 Skill 目录移动到工作区一级目录。

#### .env 已存在但 Key 失效
1. AI 主动询问"是否重新配置？需要保留旧值还是全部覆盖？"
2. 选"重新配置" → 在 §5 流程中只追问失败的那把 Key（其他保留）
3. 选"全部覆盖" → 备份 .env 为 .env.bak，从 §5 第 1 把开始

#### 端口被占用
- 工具：`execute_command("lsof -ti :3000 -sTCP:LISTEN")`
- 询问用户"是否杀进程 PID xxx？或改用其他端口？"
- 改端口：`cd "$SKILL_ROOT" && bash start.sh --port 8080`
- 杀进程：`kill <PID>` （需用户明确同意）

#### add-capability 报循环依赖
- 解析 stderr 中的"circular dependency among: [...]"
- 告知用户哪些能力冲突；引导**改 manifest.yaml.dependencies** 后重试
- 不要自己擅自修改任何 manifest

#### LLM 验证失败但用户用的是非 OpenAI 服务
- 询问用户使用的服务名（DeepSeek/Qwen/Moonshot/Anthropic 等）
- 引导改 `LLM_API_URL` 与 `LLM_MODEL`：
  - DeepSeek: `https://api.deepseek.com/chat/completions`，model: `deepseek-chat`
  - 其他：让用户提供官方 base_url + chat completions 路径
- 重新跑 `cd "$SKILL_ROOT" && python3 scripts/verify-credentials.py --type llm`

#### verify-credentials.py 报 E004（网络不可达）
- 询问是否在企业内网/是否需要代理
- 临时方案：让用户在 .env 中追加 `HTTPS_PROXY=...`
- TRTC 深度校验失败可降级：`--no-deep` 仅做本地 UserSig 自洽检查

#### 启动后 `NameError: name 'session_id' is not defined`
- **根因**：旧版注入位置错误
- **解决**：跑 `cd "$SKILL_ROOT" && python3 scripts/post-install-patch.py`
- 不要直接手改 agent.py — 让 patch 脚本做

#### contract-adapt.py 解析失败
- 输出 `{"level":"L3", ...}` → 引导用户读对应能力包的 INTERFACE_ADAPT.md
- 不要让用户重贴 curl 多于 2 次，第 3 次直接走 L3 手工流程

---

## 12. AI 工具白名单（强制）

> 所有 `$SKILL_ROOT` / `$PROJECT_ROOT` 执行前替换为绝对路径；调脚本一律 `cd "$SKILL_ROOT"` 或用绝对路径。

### 12.1 允许的命令（execute_command）

| 命令 | 用途 |
|---|---|
| `python3 -c "import sys; assert sys.version_info >= (3,9)"` | 前置检查 |
| `test -f "$SKILL_ROOT/<path>" && echo OK \|\| echo MISSING` | 文件存在判断 |
| `find "$PWD" -maxdepth 4 -name SKILL.md -path '*ai-service*'` | SKILL_ROOT 兜底探测 |
| `cd "$SKILL_ROOT" && python3 scripts/verify-credentials.py [--type tencent\|trtc\|llm] [--no-deep]` | Key 验证 |
| `cd "$SKILL_ROOT" && python3 scripts/add-capability.py <names> --apply --json [--target-project "$PROJECT_ROOT"] [--tech-stack ...]` | 装配能力包 |
| `cd "$SKILL_ROOT" && python3 scripts/post-install-patch.py` | 装后兜底补丁 |
| `cd "$SKILL_ROOT" && python3 scripts/contract-adapt.py <name> [--curl-file ... \| --openapi-file ...] --json` | 接口适配 |
| `cp "$SKILL_ROOT"/scenarios/customer-service/ui/voice-customer-service/{index.html,app.js,styles.css,data.js,mock-shop.json,tokens.css} "$SKILL_ROOT"/capabilities/conversation-core/web-demo/` | UI overlay（仅路径 A）|
| `cp -R "$SKILL_ROOT"/scenarios/customer-service/ui/admin-board/. "$SKILL_ROOT"/capabilities/conversation-core/web-demo/admin/` | 工单看板挂载（仅路径 A）|
| `cd "$SKILL_ROOT" && bash start.sh [--port N] [--https]` | 启动 |
| `cd "$SKILL_ROOT" && nohup bash start.sh > /tmp/ai-cs-start.log 2>&1 &` | 后台启动 |
| `sleep N && curl -sS http://localhost:3000/api/v1/health` | 健康自检 |
| `tail -80 /tmp/ai-cs-start.log` | 启动失败排查 |
| `lsof -ti :3000 -sTCP:LISTEN` | 看端口占用 |
| `chmod 600 "$SKILL_ROOT/capabilities/conversation-core/.env"` | 权限收紧 |

### 12.2 禁止的命令

| 命令 | 禁止原因 |
|---|---|
| `python3 scripts/setup-credentials.py validate-tencent-cloud --secret-id ...` | Key 通过命令行 → shell history 泄漏 |
| `echo $TENCENT_CLOUD_SECRET_ID` | shell history 泄漏 |
| `cat "$SKILL_ROOT/capabilities/conversation-core/.env"` | 可能在终端记录/截图泄漏 |
| `git add . && git commit` | 凭证可能被误提交 |
| 任何带明文 Key 作为参数的命令 | 同上 |
| 裸相对路径调脚本（`python3 scripts/...` 不带 `cd "$SKILL_ROOT"`） | cwd 假设错误 → 找不到资产 |

### 12.3 文件写入白名单（write_to_file）

| 路径 | 用途 |
|---|---|
| `$SKILL_ROOT/capabilities/conversation-core/.env` | Key 写入 |
| `$PROJECT_ROOT/<adapter 渲染产物>` | 路径 B：接入示例（脚本写，非 AI 手写） |
| `$SKILL_ROOT/capabilities/<cap>/src/adapters/user_custom.py` | contract-adapt.py 生成 |
| `/tmp/adapt_<cap>.curl.txt` | 用户 curl 临时存放 |
| `/tmp/ai-cs-start.log` | nohup 启动日志 |

其他文件写入需用户**明确确认**后再写。
**特别提示**：`capabilities/conversation-core/src/agent.py` 与 `capabilities/conversation-core/src/server.py` 是骨架层，AI **不应**直接手改。

---

## 13. 设计规范引用（仅路径 A 涉及 UI）

> 路径 B 不生成 UI，本节不适用于路径 B。

路径 A 的 UI 必须遵循 `$SKILL_ROOT/scenarios/customer-service/ui/design-system/DESIGN_GUIDELINES.md`：

| 项 | 强制要求 |
|---|---|
| 主题 | dark 锁定（不做亮色切换） |
| 配色 | 全部走 `tokens.css` 暴露的 CSS 变量；**禁止硬编码 hex** |
| 字体 | `SF Pro / Inter / Helvetica Neue`，中文回退系统默认 |
| Icon | Lucide / Phosphor 风格单色线性 SVG，尺寸 16/20/24/32 四档 |
| Emoji | UI 渲染层**全面禁用**（用 SVG icon + 文字替代） |
| 毛玻璃面板 | `backdrop-filter: blur(20px)` + `@supports` 兜底 |

### 13.1 顶栏 LED tooltip 约定

右上角 3 盏 LED 各自 hover 显示 tooltip：

| LED | 标题 | 解释要点 |
|---|---|---|
| Cloud | Tencent Cloud API | Control-plane（CAM/STS）；用于签发临时凭据 |
| TRTC | TRTC (Real-Time Communication) | Data-plane 媒体通道；承载语音流/字幕/自定义消息 |
| LLM | LLM provider | 推理引擎；OpenAI 兼容协议；可换 DeepSeek/GPT/Claude 等 |

---

> **最后提醒**（Coding Agent 自己读）：
> - 🔴 **路径基准第一**：先按 §0 确定 `SKILL_ROOT`（= 注入的 Base directory）与 `PROJECT_ROOT`；
>   所有调脚本/资产命令一律 `cd "$SKILL_ROOT"` 或用绝对路径。**永不要求用户搬目录**。
> - 每一步都要先调工具拿事实，再向用户解释（不要凭印象作答）
> - 工具调用失败 → 把 stderr 摘要给用户，**不要**隐藏错误
> - 不确定的字段/路径 → 用 `read_file` 看 manifest，再回答
> - 全程严格走 §12 工具白名单与 §5.4 安全红线
> - **本 Skill 卖点是语音**；纯文字诉求 → 提示用户自行配置，不生成产物
> - **路径 A** 必须跑全 6 步，绝不跳过 Step 2.5 (post-install-patch) 和 Step 3 (UI overlay)
> - **路径 B** 绝不生成任何 UI；core 端到端跑通 + 增量能力只给规范/mock/示例
> - human-handoff legacy API 字段是 `state`（值 `waiting/connected/closed/canceled/timeout`），不是 `status`/`queued`/`cancelled`
> - 交互语言跟随用户首条 prompt（§2）；路径 A 产物 UI 默认英文，路径 B 无 UI
