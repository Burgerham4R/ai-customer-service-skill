# digital-human · 数字人能力包（占位）

> Phase 2 仅声明接口契约。渲染 / 口型同步 / 表情驱动等渲染层实现
> 留待后续迭代（Phase 3+）。

## 当前能力

- 通过 manifest 注册占位 REST 端点：`/api/v1/digital-human/*`
- 不修改骨架运行时行为，仅作为后续渲染层的对接锚点

## REST 占位

| 方法 | 路径 | 行为 |
|:---|:---|:---|
| GET  | `/api/v1/digital-human/status` | 返回当前形态 / 路线图 |
| POST | `/api/v1/digital-human/render` | 固定返回 `501 Not Implemented` |

## 路线图

1. 接入第三方渲染 SDK（Avatar / Lipsync / Expression）
2. 通过 WebRTC datachannel 推送渲染驱动数据
3. 与 `conversation-core` 的 TTS 输出帧对齐

## 配置

| 环境变量 | 默认 | 说明 |
|:---|:---|:---|
| `DH_ENABLED` | `false` | 真实启用前请保持 false 避免误用 |
| `DH_AVATAR_ID` | _(空)_ | 形象 ID |
| `DH_LIPSYNC_PROVIDER` | `tencent-cloud-vmp` | 口型同步提供方 |
| `DH_EXPRESSION_PROVIDER` | `internal-rule` | 表情驱动提供方 |
