"""human-handoff core models.

定义统一的领域模型：
- TicketStatusEnum  工单状态（与 business_contract.ticket.status_query.response.status 对齐）
- Ticket            工单完整记录（adapter 之间的传输对象）
- TicketStatus      轻量状态视图（status_query 返回）
- OverallStatus     队列整体状态（看板用）

核心层不感知任何具体后端实现，所有 adapter 必须使用本模块的数据结构。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TicketStatusEnum(str, Enum):
    """工单状态枚举。

    业务语义对照：
    - PENDING    用户已申请；尚未分配座席（与旧 HandoffState.WAITING 等价）
    - PROCESSING 已分配座席，正在处理（与旧 HandoffState.CONNECTED 等价）
    - CLOSED     座席已关闭工单
    - CANCELED   用户主动取消
    - TIMEOUT    超时无座席接通
    """

    PENDING = "pending"
    PROCESSING = "processing"
    CLOSED = "closed"
    CANCELED = "canceled"
    TIMEOUT = "timeout"


# 与旧 API 兼容的状态名映射（HandoffState 时代）
_LEGACY_STATE_MAP = {
    TicketStatusEnum.PENDING.value: "waiting",
    TicketStatusEnum.PROCESSING.value: "connected",
    TicketStatusEnum.CLOSED.value: "closed",
    TicketStatusEnum.CANCELED.value: "canceled",
    TicketStatusEnum.TIMEOUT.value: "timeout",
}


def to_legacy_state(status: str) -> str:
    """把新版 TicketStatusEnum 值转回旧 API 暴露的 state 名。"""
    if not status:
        return "idle"
    return _LEGACY_STATE_MAP.get(status, status)


@dataclass
class Ticket:
    """工单记录。adapter 间的传输对象。

    user_id 与 ticket_id 在 LocalQueue 实现下默认同值（沿用 session_id），
    REST 实现则使用业务方返回的 ticket_id。
    """

    ticket_id: str
    user_id: str
    subject: str = ""
    description: str = ""
    priority: str = "normal"
    status: str = TicketStatusEnum.PENDING.value
    queue_position: int = 0
    eta_seconds: int = 0
    agent_id: Optional[str] = None
    transcript: List[str] = field(default_factory=list)
    reason: str = ""                          # 触发原因摘要（兼容旧字段）
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    closed_at: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"tk_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "session_id": self.user_id,
            "user_id": self.user_id,
            "subject": self.subject,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "queue_position": self.queue_position,
            "eta_seconds": self.eta_seconds,
            "agent_id": self.agent_id,
            "transcript": list(self.transcript),
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            # 建单时由 human-handoff 联动 session-summary 写入（未装能力则为 None）
            "session_summary": self.extra.get("session_summary"),
        }

    def to_legacy_dict(self) -> dict:
        """旧 REST API（/api/v1/handoff/*）返回的字段格式，保持 Web Demo 兼容。"""
        return {
            "session_id": self.user_id,
            "state": to_legacy_state(self.status),
            "reason": self.reason,
            "requested_at": self.created_at,
            "connected_at": self.updated_at if self.status == TicketStatusEnum.PROCESSING.value else None,
            "closed_at": self.closed_at,
            "agent_id": self.agent_id,
            "queue_position": self.queue_position,
            "estimated_wait_seconds": self.eta_seconds,
        }


@dataclass
class TicketStatus:
    """对应 business_contract.ticket.status_query 的响应模型。"""

    ticket_id: str
    status: str
    agent_id: Optional[str] = None
    queue_position: int = 0
    eta_seconds: int = 0
    updated_at: Optional[float] = None

    @classmethod
    def from_ticket(cls, t: Ticket) -> "TicketStatus":
        return cls(
            ticket_id=t.ticket_id,
            status=t.status,
            agent_id=t.agent_id,
            queue_position=t.queue_position,
            eta_seconds=t.eta_seconds,
            updated_at=t.updated_at or t.created_at,
        )


@dataclass
class OverallStatus:
    agent_pool_size: int
    available_agents: int
    waiting: int
    connected: int
    capacity: int

    def to_dict(self) -> dict:
        return {
            "agent_pool_size": self.agent_pool_size,
            "available_agents": self.available_agents,
            "waiting": self.waiting,
            "connected": self.connected,
            "capacity": self.capacity,
        }


def now_ts() -> float:
    return time.time()
