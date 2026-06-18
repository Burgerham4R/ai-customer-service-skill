"""Phase 2 共享基础设施（不含业务）。

本包向 add-capability / detect-stack 等 CLI 暴露可复用模块：

- manifest_resolver  能力包 manifest 加载 / 依赖图 / 拓扑排序 / 循环依赖检测
- stack_detector     技术栈识别（package.json / pom.xml / requirements.txt 等）
- degrader           三级降级（L1 全自动 / L2 半自动 / L3 手动）决策机
- injector           按 manifest.injection_points 的 position 描述执行代码注入
- arbitrator         α/β 双轨制工具调用仲裁（供 tool-calling 能力包内部复用）

设计原则：本包不依赖任何业务逻辑，仅做协议解析与策略决策。
"""

__all__ = [
    "manifest_resolver",
    "stack_detector",
    "degrader",
    "injector",
    "arbitrator",
]
