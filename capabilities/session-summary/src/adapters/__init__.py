"""session-summary 写回适配层。"""
from .base import SummarySink
from .factory import get_sink

__all__ = ["SummarySink", "get_sink"]
