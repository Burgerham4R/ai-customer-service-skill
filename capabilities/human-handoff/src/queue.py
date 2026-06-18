"""queue.py —— 兼容 facade。

保留 `attach_session` 公共符号，供 manifest.extensions（agent.after_start）
继续以 `_hh_queue.attach_session(session_id, info=...)` 调用。

旧版本同时暴露的 `get_queue()` / `HandoffQueue` / `HandoffRecord` / `HandoffState`
在新分层下不再使用；保留为废弃 shim，仅用于第三方代码的渐进式迁移。

新代码请直接使用：
- adapters.factory.get_client()    获取 HandoffClient 实例
- core.service.get_default_service() 获取 HandoffService 实例
"""
from __future__ import annotations

import warnings
from typing import Any

from .adapters.factory import get_client
from .core.models import (  # noqa: F401  (向后兼容导出)
    OverallStatus,
    Ticket,
    TicketStatus,
    TicketStatusEnum,
)


def attach_session(session_id: str, info: Any = None) -> None:
    """供 conversation-core.after_start 注入点使用。

    在重构后的实现下，"会话登记"由 client 在 create_ticket 时按需完成；
    此处保留为 no-op 入口，避免破坏 manifest.extensions 的旧调用。
    info 参数预留以兼容旧签名。
    """
    # 触发 client 单例初始化，便于在启动阶段尽早暴露配置错误
    _ = get_client()
    return None


# --------------------------------------------------------------------
# 弃用 shim（仅供旧测试 / 旧外部代码渐进迁移；新代码不应依赖）
# --------------------------------------------------------------------
def get_queue():
    warnings.warn(
        "human_handoff.queue.get_queue() is deprecated; "
        "use adapters.factory.get_client() or core.service.get_default_service() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_client()


# 旧符号别名（部分集成方可能直接 import）
HandoffState = TicketStatusEnum
HandoffRecord = Ticket


__all__ = [
    "HandoffRecord",
    "HandoffState",
    "attach_session",
    "get_queue",
]
