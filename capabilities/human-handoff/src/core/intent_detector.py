"""转人工意图检测：关键字强匹配 + 弱意图（带否定上下文识别）。

从原 trigger.py 迁入。本模块**不依赖**任何 adapter 或全局状态，纯函数。
"""
from __future__ import annotations

import os
import re
from typing import List


_DEFAULT_TRIGGERS = [
    "人工", "转人工", "找人工", "客服小姐姐", "客服小哥",
    "real person", "talk to agent", "speak to a human", "human agent",
]
_DEFAULT_INTENT = ["投诉", "complain", "manager", "无法解决", "解决不了"]


def _csv_env(key: str, default: List[str]) -> List[str]:
    raw = os.getenv(key)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class IntentDetector:
    """以正则方式判断输入文本是否表达"转人工"意图。"""

    def __init__(
        self,
        *,
        triggers: List[str] | None = None,
        intent_keywords: List[str] | None = None,
    ) -> None:
        self._triggers = triggers if triggers is not None else _csv_env(
            "HH_TRIGGERS", _DEFAULT_TRIGGERS
        )
        self._intent = intent_keywords if intent_keywords is not None else _csv_env(
            "HH_INTENT_KEYWORDS", _DEFAULT_INTENT
        )
        self._triggers_re = re.compile(
            "|".join(re.escape(k) for k in self._triggers), re.IGNORECASE
        )
        self._intent_re = re.compile(
            "|".join(re.escape(k) for k in self._intent), re.IGNORECASE
        )
        self._negative_re = re.compile(
            r"\b(not|don't|do not|不|没有|不要|无需)\b", re.IGNORECASE
        )

    def is_handoff_intent(self, text: str) -> bool:
        if not text or len(text) > 4096:
            return False
        if self._triggers_re.search(text):
            return True
        if self._intent_re.search(text) and not self._negative_re.search(text):
            return True
        return False


# ---------------------------------------------------------------------------
# 默认单例（保持与旧 trigger.py 行为一致；测试可手动构造新实例覆盖）
# ---------------------------------------------------------------------------
_default_detector: IntentDetector | None = None


def get_default_detector() -> IntentDetector:
    global _default_detector
    if _default_detector is None:
        _default_detector = IntentDetector()
    return _default_detector


def is_handoff_intent(text: str) -> bool:
    return get_default_detector().is_handoff_intent(text)
