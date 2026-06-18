# 设计规范（DESIGN_GUIDELINES）

> 适用范围：`scenarios/customer-service/` 所有 UI（voice-customer-service、admin-board）。
>
> 来源：`voice_ai_customer_service (3).html` 原型设计，v2.0.0（浅色 / 毛玻璃 / 紫粉渐变）。

---

## 1. 主题与背景

| 类目 | 规则 |
|---|---|
| **主题** | 浅色主题（light mode），不做暗色切换 |
| **背景** | 多层径向渐变叠加（柔紫 + 浅粉 + 淡蓝），底色 `#f7f3ff` |
| **面板** | 毛玻璃玻璃面板（`glass` class）：`backdrop-filter: blur(22px) saturate(140%)` |

## 2. 色彩规范

### 2.1 调色板

展开全部：CSS 变量（定义于 `tokens.css`，由 `design_tokens.json` 编译生成）
按命名空间分组：

```
前景 / 文本
  --foreground : #1a1530     主文字色（深紫黑）
  --muted      : #6b6580     次要/辅助文字

卡片 / 面板
  --card        : rgba(255,255,255,0.55)   玻璃面板底色
  --card-strong : rgba(255,255,255,0.78)   强玻璃面板
  --card-border : rgba(255,255,255,0.85)   面板描边

品牌 / 强调
  --primary : #9b7bf7       主紫色（渐变起点）
  --pink    : #f7b7d4       粉红（渐变终点）
  --blue    : #7ba8f7       辅蓝色
  --accent-grad : linear-gradient(135deg, #9b7bf7 0%, #f7b7d4 100%)

状态色
  --green : #34c77b         成功 / 在线 / 连通
  --red   : #ff5c7a         错误 / 挂断 / 静音
```

**正确用法**：
```css
.my-button {
  background: var(--accent-grad);
  color: white;
}
.badge-success {
  background: rgba(52,199,123,0.15);
  color: var(--green);
}
```

**禁止用法**：
```css
.my-button {
  background: linear-gradient(135deg, #9b7bf7, #f7b7d4);   /* 应引用 --accent-grad */
}
```

### 2.2 Tailwind 集成

原型使用 Tailwind CSS CDN，自定义颜色在 `tailwind.config` 中注入：

```js
tailwind.config = {
  theme: { extend: {
    colors: { ink:'#1a1530', muted:'#6b6580', primary:'#9b7bf7', pink:'#f7b7d4', blue2:'#7ba8f7' },
    fontFamily: { sans: ['Inter','SF Pro Display','system-ui','sans-serif'] }
  } }
}
```

> **注意**：Tailwind 类名（如 `text-ink`、`text-muted`、`bg-primary`）与上述 CSS 变量名对应，但属于 **两套独立的命名体系**。新增 UI 时优先走 Tailwind 类名做布局，核心样式走 `styles.css` 中的 CSS 变量。

---

## 3. 布局规范

### 3.1 整体布局

```
+----------------------------------------------------------+
|  HEADER: logo + 连接状态指示灯                             |
+----------------------------------------------------------+
|  SIDEBAR (300px)        |  MAIN CONSOLE (flex:1)          |
|  - Products / Orders    |  - Orb 呼吸球                   |
|    标签页                |  - 状态文案 (Ready/Listening/…)  |
|  - 搜索框                |  - 大波形动画                   |
|  - 卡片列表（可滚动）     |  - Dock 控制栏                 |
|                          |  - IM 聊天抽屉                 |
+----------------------------------------------------------+
|  FOOTER                                                  |
+----------------------------------------------------------+
```

### 3.2 响应式断点

| 断点 | 布局 |
|---|---|
| `≥ 1024px` (lg) | 双栏：`grid-cols-[300px,1fr]`，固定高度 620px |
| `< 1024px` | 侧边栏缩为 `max-height: 50vh`，主面板自动撑高 |

---

## 4. 组件规范

### 4.1 Orb 呼吸球

- **位置**：主控制台居中
- **尺寸**：160×160px（≥760px 时 200×200px）
- **样式**：多层渐变圆形 + `inset` 阴影模拟玻璃质感 + 高光点
- **动画**：
  | 状态 | 动画 | 周期 |
  |---|---|---|
  | idle（空闲） | `breathe` | 4.5s |
  | listening（听） | `breathe` | 1.2s |
  | speaking（说） | `breathe` | 0.7s |
- **光环**：3 层 `orb-halo`，动画延迟 0 / 1.1s / 2.2s，从 scale(0.85) 扩散到 scale(1.7) 并渐隐

### 4.2 大波形（wave-big）

- **位置**：Orb 下方
- **尺寸**：宽 `min(520px, 90%)`，高 80px
- **组成**：32 根竖条，`background: linear-gradient(180deg, #9b7bf7, #f7b7d4)`
- **动画**：
  | 状态 | 动画 | 周期 |
  |---|---|---|
  | idle | 暂停，高度固定 10px，opacity 0.4 | — |
  | listening | `wv` | 0.7s |
  | speaking | `wv` | 0.5s |

### 4.3 Dock 控制栏

**收起态**：单个绿色圆形 Start 按钮，58×58px

**展开态**（Start 后）：
- 毛玻璃胶囊容器（`border-radius: 999px`）
- 内含 3 个按钮：
  | 按钮 | 图标 | 样式 |
  |---|---|---|
  | 麦克风 | `mic` / `mic-off` | 圆角 46×46px，白色底；静音时红色渐变 |
  | 转人工 | `headphones` + "Human Support" | 蓝色渐变底 + 白色文字 |
  | 挂断 | `phone-off` | 圆形 46×46px，红色渐变底 |

**切换动画**：Start 按钮缩小消失（`scale(0.4)`），展开栏从 `scale(0.6)` 弹出

### 4.4 知识库侧边栏（KB Sidebar）

- **标签页切换**：Products / Orders，`kb-tabs` 容器
- **搜索框**：带搜索图标，圆形输入框
- **产品卡片**：
  - 缩略图 52×52px + 名称 + 价格 + 标签（Hot / In stock / Low stock）
  - Hover：上浮 2px + 阴影增强
- **订单卡片**：
  - 订单号 + 日期 + 状态徽章 + 产品缩略图 38×38px

### 4.5 详情视图（Detail View）

- 点击产品/订单卡片后切换布局：
  - 顶部紧凑栏（返回按钮 + 迷你 Orb + 波形）
  - 中央：问题文案 + 详情卡片
  - 底部：展开态 Dock
- **产品详情卡**：大图 140×140px + 名称 + 评分 + 描述 + 价格 + 购物车按钮
- **订单详情卡**：订单号 + 日期 + 状态 + 产品缩略图 64×64px + 总价

### 4.6 IM 聊天抽屉

- **位置**：右下角浮动，`position: absolute; right: 18px; bottom: 90px`
- **尺寸**：宽 360px，`max-width: calc(100% - 36px)`
- **结构**：标题栏 + 消息列表（max-height: 280px）+ 输入栏
- **气泡样式**：
  - AI 气泡：白色底、左上角切角
  - 用户气泡：紫色渐变底、白色文字、右上角切角
  - 系统气泡：半透明白底、斜体居中、胶囊形
- **打字指示器**：3 个跳动圆点

### 4.7 排队进度条

- 转人工后显示在 Orb 下方
- 进度条：`background: var(--accent-grad)` 在白色底上填充
- 计时器：每分钟更新格式化时间（`0:00` → `0:08`）

### 4.8 Toast 提示

- 未连接时点击卡片 → 紫色半透明底 Toast："Please press Start to connect AI before viewing..."
- 自动 2.6s 后消失

---

## 5. 字体规范

| 角色 | 字体 | 来源 |
|---|---|---|
| 全局正文 | `Inter` | Google Fonts CDN |
| 备选 | `SF Pro Display` | 系统内置 |
| 回退 | `system-ui`, `sans-serif` | 浏览器默认 |

**例外**：原型使用 Google Fonts CDN 加载 Inter 字体，以满足设计需求（SF Pro / Helvetica Neue 无法保证跨平台一致性）。

---

## 6. Icon 规范

| 类目 | 规则 |
|---|---|
| **图源** | [Lucide](https://lucide.dev/)，CDN 加载 `unpkg.com/lucide@latest` |
| **风格** | 单色线性 SVG，保持统一 |
| **尺寸** | `w-3 h-3`（小 pill）/ `w-4 h-4`（标准）/ `w-5 h-5`（按钮） |
| **初始化** | DOM 变更后调用 `lucide.createIcons()` 刷新 |

---

## 7. 禁 emoji 的替代方案

emoji 在不同操作系统下渲染差异极大、与设计语言不统一，因此 **全站 UI 渲染层禁用 emoji**。

| 场景 | ✅ 替代方式 |
|---|---|
| 状态/成功 | 绿色 `<span class="status-dot">` + 文字 "Live · Connected" |
| 断开/挂断 | 灰色圆点 + 文字 "Disconnected" |
| 通知/toast | 纯文字 toast，不附加图标 |
| 业务标签 | `tag-hot`（粉底红字）、`tag-instock`（绿底绿字）、`tag-low`（黄底橙字）CSS 类 |

---

## 8. 动画与动效

| 动画 | 用途 | 时长/周期 |
|---|---|---|
| `breathe` | Orb 呼吸缩放 | 4.5s（idle）/ 1.2s（listening）/ 0.7s（speaking） |
| `halo` | Orb 光环扩散消失 | 3.4s |
| `core-pulse` | Orb 核心光晕脉冲 | 2s |
| `wv` | 大波形波动 | 1.1s（idle 暂停） |
| `cwv` | 紧凑波形波动 | 1s |
| `bubble-in` | 聊天气泡弹出 | 0.35s ease-out |
| `tdot` | 打字指示器跳动 | 1.2s（3 点 0.2s 交错） |
| `fade-in-down` | 紧凑栏滑入 | 0.35s ease |
| `detail-in` | 详情页淡入上移 | 0.4s ease |
| `pulse-dot` | 连接指示灯脉冲 | 1.6s |

---

## 9. 浏览器兼容性

毛玻璃 `backdrop-filter` 在部分旧版浏览器下不可用，玻璃面板在 `styles.css` 中已同时声明 `-webkit-backdrop-filter` 前缀：

```css
.glass {
  backdrop-filter: blur(22px) saturate(140%);
  -webkit-backdrop-filter: blur(22px) saturate(140%);
}
```

不支持的浏览器会降级为纯色半透明背景（`rgba(255,255,255,0.55)`），忽略模糊效果。

---

## 10. 状态文案

| 状态 | 主文案 (ai-state) | 副文案 (ai-substate) | Orb/Wave 状态 |
|---|---|---|---|
| 未连接（pre） | "Ready to start conversation" | "Press Start below to begin a real-time voice session" | idle |
| 空闲监听（idle） | "Listening for you" | "Speak naturally · I will respond in real time" | idle |
| 收听中（listening） | "Listening…" | "Capturing your voice" | listening |
| 思考中（thinking） | "Thinking…" | "Processing your request" | listening |
| AI 说话（speaking） | "AI is speaking…" | "Streaming response over TRTC" | speaking |

---

## 11. 检查清单（提交 UI 前自检）

- [ ] 所有颜色走 CSS 变量（`--primary`、`--accent-grad` 等）或 Tailwind 预设，禁止裸 hex
- [ ] 所有 icon 来自 Lucide，尺寸落在 3 / 4 / 5（Tailwind `w-* h-*`）
- [ ] UI 文案、状态、按钮中无任何 emoji 字符
- [ ] 毛玻璃元素带 `-webkit-backdrop-filter` 前缀
- [ ] 字体仅引用 Inter + SF Pro + system-ui 组合
- [ ] Orb/Wave 动画状态切换正确（idle/listening/speaking 三态）
- [ ] 响应式：移动端侧边栏收缩至 50vh
- [ ] 每次 DOM 插入新 icon 后调用 `lucide.createIcons()`
