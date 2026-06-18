# 通用前端集成指南（L2 半自动）

> 当 Agent 已识别到你的前端技术栈，但自动渲染因路径冲突或语法异常失败时，
> 请按以下步骤手动完成集成。

## 第 1 步 · 安装依赖

```bash
npm install trtc-sdk-v5
```

## 第 2 步 · 复制组件模板

按你的框架从仓库 `auto_adapters/frontend-spa/` 选择对应模板：

- React / Next:  `react/VoiceAgent.tsx.tpl`
- Vue:           `vue/VoiceAgent.vue.tpl`
- Angular:       `angular/voice-agent.component.ts.tpl`

把模板内容复制到你项目的组件目录，并把以下占位变量替换为真实值：

| 占位 | 默认 | 说明 |
|:---|:---|:---|
| `${SKELETON_BASE_URL}` | `http://localhost:3000` | 骨架进程地址 |
| `${API_PREFIX}` | `/api/v1` | 骨架 REST 前缀 |
| `${COMPONENT_NAME}` | `VoiceAgent` | 组件 / 文件名 |

## 第 3 步 · 在父组件中挂载

```tsx
import { VoiceAgent } from './components/VoiceAgent';

export default function Page() {
  return <main><VoiceAgent /></main>;
}
```

## 第 4 步 · CSP 与 HTTPS

如果生产环境部署了 CSP，请追加：

```
connect-src https://${SKELETON_BASE_URL} wss://*.trtc.tencent-cloud.com;
```

## 第 5 步 · 验证

打开页面，应看到顶部三盏灯：`tencent_cloud / trtc / llm`。
均为绿色后点击 `Start` 即可入房与 AI 对话。

如有任何一盏灯红色，按页面控制台输出的诊断 JSON 检查 `.env` 与三把 Key。
