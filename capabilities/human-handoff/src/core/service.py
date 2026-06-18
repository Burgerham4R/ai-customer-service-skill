"""HandoffService —— 串联 IntentDetector 与 HandoffClient 的应用服务。

只依赖 ports（HandoffClient 接口），不感知具体后端实现。
切换 adapter 仅需重新注入 client（adapters.factory.set_client）。
"""
from __future__ import annotations

from typing import List, Optional

from ..ports.handoff_client import HandoffClient
from ..summary_link import attach_summary_to_ticket
from .intent_detector import IntentDetector, get_default_detector
from .models import OverallStatus, Ticket, TicketStatus, TicketStatusEnum


class HandoffService:
    """转人工业务服务。"""

    def __init__(
        self,
        *,
        client: HandoffClient,
        detector: Optional[IntentDetector] = None,
    ) -> None:
        self._client = client
        self._detector = detector or get_default_detector()

    # ------------------------------------------------------------------
    # 意图检测 + 触发（供注入到 conversation-core.before_push_text）
    # ------------------------------------------------------------------
    def maybe_handoff(self, session_id: str, text: str) -> Optional[str]:
        """识别转人工意图，命中则申请工单并返回拼装的话术；否则返回 None。"""
        if not session_id or not text:
            return None
        if not self._detector.is_handoff_intent(text):
            return None

        # 复用已有工单（同一 user 进行中的不重复创建）
        existing = self._client.get_or_attach(session_id)
        if existing is not None and existing.status in (
            TicketStatusEnum.PENDING.value,
            TicketStatusEnum.PROCESSING.value,
        ):
            return self._render_handoff_message(existing)

        ticket = self._client.create_ticket(
            user_id=session_id,
            subject=text[:64],
            description=text[:512],
            priority="normal",
        )
        # 建单即附带会话纪要，便于坐席在看板里立刻掌握客户问题（session-summary 未装则 no-op）
        attach_summary_to_ticket(ticket)
        return self._render_handoff_message(ticket)

    @staticmethod
    def _render_handoff_message(t: Ticket) -> Optional[str]:
        if t.status == TicketStatusEnum.PROCESSING.value:
            return (
                f"[handoff state=connected agent={t.agent_id}]\n"
                "您已接通人工座席，请稍等。"
            )
        if t.status == TicketStatusEnum.PENDING.value:
            return (
                f"[handoff state=waiting position={t.queue_position} "
                f"eta={t.eta_seconds}s]\n"
                f"已为您申请人工座席，当前排在第 {t.queue_position} 位，"
                f"预计等待 {t.eta_seconds} 秒。"
            )
        if t.status == TicketStatusEnum.TIMEOUT.value:
            return "[handoff state=timeout]\n人工座席暂无空闲，请稍后重试。"
        return None

    # ------------------------------------------------------------------
    # 显式操作（供 router 调用）
    # ------------------------------------------------------------------
    def request(
        self,
        session_id: str,
        *,
        reason: str = "",
        subject: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Ticket:
        existing = self._client.get_or_attach(session_id)
        if existing is not None and existing.status in (
            TicketStatusEnum.PENDING.value,
            TicketStatusEnum.PROCESSING.value,
        ):
            return existing
        ticket = self._client.create_ticket(
            user_id=session_id,
            subject=(subject or reason or "human handoff")[:64],
            description=(description or reason or "")[:512],
            priority="normal",
        )
        # 建单即附带会话纪要（session-summary 未装则 no-op，不影响主流程）
        attach_summary_to_ticket(ticket)
        return ticket

    def connect(self, session_id: str, agent_id: str) -> Ticket:
        """供 /api/v1/handoff/connect 使用：把 session 强制接通到指定 agent。"""
        # 先按 user_id 反查活跃工单
        ticket = self._client.get_or_attach(session_id)
        if ticket is None:
            raise ValueError(f"session {session_id} not waiting")
        if ticket.status == TicketStatusEnum.PROCESSING.value:
            return ticket
        updated = self._client.update_status(
            ticket.ticket_id,
            TicketStatusEnum.PROCESSING.value,
            agent_id=agent_id,
        )
        if updated is None:
            raise ValueError(f"ticket {ticket.ticket_id} not found")
        return updated

    def cancel(self, session_id: str, *, reason: str = "") -> Ticket:
        ticket = self._client.get_or_attach(session_id)
        if ticket is None:
            raise ValueError(f"session not found: {session_id}")
        result = self._client.cancel_ticket(ticket.ticket_id, reason=reason)
        if result is None:
            raise ValueError(f"ticket {ticket.ticket_id} not found")
        return result

    def get_by_session(self, session_id: str) -> Optional[Ticket]:
        return self._client.get_or_attach(session_id)

    def overall_status(self) -> OverallStatus:
        return self._client.overall_status()

    # ------------------------------------------------------------------
    # 看板辅助
    # ------------------------------------------------------------------
    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        return self._client.list_tickets(limit=limit, status=status)

    def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        *,
        agent_id: Optional[str] = None,
    ) -> Optional[Ticket]:
        return self._client.update_status(ticket_id, status, agent_id=agent_id)

    def query_ticket(self, ticket_id: str) -> Optional[TicketStatus]:
        return self._client.query_status(ticket_id)


# ---------------------------------------------------------------------------
# 默认 service 单例
# ---------------------------------------------------------------------------
_default_service: Optional[HandoffService] = None


def get_default_service() -> HandoffService:
    """按当前环境构造 service 单例（client 来自 adapters.factory）。"""
    global _default_service
    if _default_service is None:
        from ..adapters.factory import get_client
        _default_service = HandoffService(client=get_client())
    return _default_service


def reset_default_service() -> None:
    global _default_service
    _default_service = None
