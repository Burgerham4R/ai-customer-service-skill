"""conversation-core: Voice Agent 通用骨架。

本包仅实现 ASR / LLM / TTS / 会话管理的链路编排，不内置任何
行业知识库、FAQ 模板或业务规则，所有业务能力通过外层独立
能力包以 manifest.yaml 注入点形式叠加。
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
