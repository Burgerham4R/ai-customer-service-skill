"""trigger.py —— 兼容 facade。

保留 `maybe_handoff` / `is_handoff_intent` 公共符号，供 manifest.extensions
（agent.before_push_text）继续以 `_hh_trigger.maybe_handoff(session_id, text)` 调用，
内部委托给重构后的 core.service.HandoffService。

新代码请直接使用 core.service / core.intent_detector，不要再依赖本 facade。
"""
from __future__ import annotations

from typing import Optional

from .core.intent_detector import is_handoff_intent  # noqa: F401  (公共 API)
from .core.service import get_default_service


def maybe_handoff(session_id: str, text: str) -> Optional[str]:
    """供 conversation-core.before_push_text 注入点使用。

    与原版本签名完全一致：返回 None 表示未触发；返回字符串表示已替换为转人工话术。
    """
    return get_default_service().maybe_handoff(session_id, text)


__all__ = ["is_handoff_intent", "maybe_handoff"]
