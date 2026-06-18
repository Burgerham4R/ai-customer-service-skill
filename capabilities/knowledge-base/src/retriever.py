"""retriever.py —— 兼容 facade。

保留原 `attach_faq_to_instructions` / `get_retriever` / `FaqEntry` / `SearchHit`
公共符号，供 manifest.extensions（agent.before_start）和外部调用方继续使用。

新代码请直接使用：
- adapters.factory.get_client()        获取 KnowledgeBaseClient 实例
- core.service.get_default_service()   获取 KbService 实例
"""
from __future__ import annotations

import warnings

from .core.models import FaqEntry, SearchHit  # noqa: F401  (公共 API)
from .core.service import get_default_service


def attach_faq_to_instructions(instructions: str) -> str:
    """供 conversation-core.before_start 注入点使用。

    保持旧签名：单参数 instructions，返回拼接后的 instructions。
    """
    return get_default_service().attach_faq_to_instructions(instructions)


# --------------------------------------------------------------------
# 弃用 shim：原 FaqRetriever 全局实例 / 类
# --------------------------------------------------------------------
def get_retriever():
    """[DEPRECATED] 返回 KnowledgeBaseClient 实例。

    旧 FaqRetriever 类的方法名（list_entries/upsert/delete/search/reload）
    在新 client 上有对应方法（list_all/upsert/delete/search/reload），
    但部分签名略有差异（list_entries -> list_all）。
    """
    warnings.warn(
        "knowledge_base.retriever.get_retriever() is deprecated; "
        "use adapters.factory.get_client() or core.service.get_default_service() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from .adapters.factory import get_client
    return get_client()


# 兼容旧别名
FaqRetriever = "FaqRetriever (deprecated; use adapters.local_json.LocalJsonKbClient)"


__all__ = [
    "FaqEntry",
    "FaqRetriever",
    "SearchHit",
    "attach_faq_to_instructions",
    "get_retriever",
]
