"""LocalQueueHandoffClient —— 默认本地实现。

零外部依赖，进程内排队 + 座席分配。是从原 queue.py 实现迁入的"默认开箱即用"版本。

实现说明：
- user_id 同时作为 ticket_id（保持与旧 session_id 行为一致）
- 状态机：
    PENDING ──connect──▶ PROCESSING
       │  ▲                  │
       │  │                  ▼
     cancel/timeout       cancel/close
- 单进程 RLock 保护；跨进程同步由集成方上层（如 Redis）负责
- 容量与座席数从环境变量读取，可通过构造函数覆盖
"""
from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional

from ..core.models import (
    OverallStatus,
    Ticket,
    TicketStatus,
    TicketStatusEnum,
    now_ts,
)
from ..ports.handoff_client import HandoffClient


class LocalQueueHandoffClient(HandoffClient):
    """进程内内存排队的 HandoffClient 实现。"""

    def __init__(
        self,
        *,
        capacity: int = 50,
        agent_pool_size: int = 1,
        estimated_wait_per_slot: int = 30,
    ) -> None:
        self._lock = threading.RLock()
        self._tickets: Dict[str, Ticket] = {}     # ticket_id -> Ticket
        self._waiting: List[str] = []             # ticket_id 列表，FIFO
        self._connected: Dict[str, str] = {}      # ticket_id -> agent_id
        self._capacity = int(capacity)
        self._pool = int(agent_pool_size)
        self._wait_per_slot = max(1, int(estimated_wait_per_slot))

    # ------------------------------------------------------------------
    # HandoffClient 必须实现的方法
    # ------------------------------------------------------------------
    def create_ticket(
        self,
        *,
        user_id: str,
        subject: str = "",
        description: str = "",
        priority: str = "normal",
        transcript: Optional[List[str]] = None,
    ) -> Ticket:
        if not user_id:
            raise ValueError("user_id is required")
        with self._lock:
            # 一个 user 进行中的工单只允许一条；存在则刷新位置后返回
            existing = self._find_active_by_user(user_id)
            if existing is not None:
                if existing.status == TicketStatusEnum.PROCESSING.value:
                    return existing
                self._refresh_position(existing)
                return existing

            ticket_id = user_id  # 兼容旧行为：session_id 即 ticket_id
            t = Ticket(
                ticket_id=ticket_id,
                user_id=user_id,
                subject=subject,
                description=description,
                priority=priority or "normal",
                transcript=list(transcript or []),
                reason=description[:128] if description else "",
                created_at=now_ts(),
                updated_at=now_ts(),
            )

            # 容量已满且无空座席：记 TIMEOUT
            if (
                len(self._waiting) >= self._capacity
                and self._available_agents() == 0
            ):
                t.status = TicketStatusEnum.TIMEOUT.value
                t.closed_at = now_ts()
                self._tickets[ticket_id] = t
                return t

            t.status = TicketStatusEnum.PENDING.value
            self._tickets[ticket_id] = t
            self._waiting.append(ticket_id)

            # 若有空座席自动接通
            if self._available_agents() > 0:
                self._auto_connect()
            self._refresh_position(t)
            return t

    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        with self._lock:
            t = self._tickets.get(ticket_id)
            if t is None:
                return None
            return TicketStatus.from_ticket(t)

    def cancel_ticket(self, ticket_id: str, reason: str = "") -> Optional[Ticket]:
        with self._lock:
            t = self._tickets.get(ticket_id)
            if t is None:
                return None
            if t.status == TicketStatusEnum.PROCESSING.value:
                self._connected.pop(ticket_id, None)
            self._waiting = [s for s in self._waiting if s != ticket_id]
            t.status = TicketStatusEnum.CANCELED.value
            t.reason = reason or t.reason
            t.closed_at = now_ts()
            t.updated_at = now_ts()
            self._refresh_all_positions()
            return t

    def overall_status(self) -> OverallStatus:
        with self._lock:
            return OverallStatus(
                agent_pool_size=self._pool,
                available_agents=self._available_agents(),
                waiting=len(self._waiting),
                connected=len(self._connected),
                capacity=self._capacity,
            )

    # ------------------------------------------------------------------
    # 看板辅助方法
    # ------------------------------------------------------------------
    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        with self._lock:
            items = list(self._tickets.values())
            if status:
                items = [t for t in items if t.status == status]
            items.sort(
                key=lambda x: (x.created_at or 0.0),
                reverse=True,
            )
            return items[: max(1, int(limit))]

    def update_status(
        self,
        ticket_id: str,
        status: str,
        *,
        agent_id: Optional[str] = None,
    ) -> Optional[Ticket]:
        try:
            new_status = TicketStatusEnum(status).value
        except ValueError as exc:
            raise ValueError(f"invalid status: {status}") from exc

        with self._lock:
            t = self._tickets.get(ticket_id)
            if t is None:
                return None

            old_status = t.status
            t.status = new_status
            t.updated_at = now_ts()

            if new_status == TicketStatusEnum.PROCESSING.value:
                if old_status != TicketStatusEnum.PROCESSING.value:
                    if self._available_agents() <= 0 and ticket_id not in self._connected:
                        # 强制接通（手动操作）：座席池外开新槽
                        pass
                    t.agent_id = agent_id or t.agent_id or f"agent_{ticket_id[-4:]}"
                    self._connected[ticket_id] = t.agent_id
                    self._waiting = [s for s in self._waiting if s != ticket_id]
            elif new_status in (
                TicketStatusEnum.CLOSED.value,
                TicketStatusEnum.CANCELED.value,
                TicketStatusEnum.TIMEOUT.value,
            ):
                t.closed_at = now_ts()
                self._connected.pop(ticket_id, None)
                self._waiting = [s for s in self._waiting if s != ticket_id]
            elif new_status == TicketStatusEnum.PENDING.value:
                self._connected.pop(ticket_id, None)
                if ticket_id not in self._waiting:
                    self._waiting.append(ticket_id)

            self._refresh_all_positions()
            if self._available_agents() > 0:
                self._auto_connect()
            return t

    def get_or_attach(self, user_id: str) -> Optional[Ticket]:
        with self._lock:
            return self._find_active_by_user(user_id)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _available_agents(self) -> int:
        return max(0, self._pool - len(self._connected))

    def _find_active_by_user(self, user_id: str) -> Optional[Ticket]:
        for t in self._tickets.values():
            if t.user_id == user_id and t.status in (
                TicketStatusEnum.PENDING.value,
                TicketStatusEnum.PROCESSING.value,
            ):
                return t
        return None

    def _auto_connect(self) -> None:
        while self._waiting and self._available_agents() > 0:
            tid = self._waiting.pop(0)
            t = self._tickets.get(tid)
            if t is None:
                continue
            t.status = TicketStatusEnum.PROCESSING.value
            t.updated_at = now_ts()
            t.agent_id = f"agent_auto_{int(t.updated_at)}"
            self._connected[tid] = t.agent_id

    def _refresh_position(self, t: Ticket) -> None:
        if (
            t.status == TicketStatusEnum.PENDING.value
            and t.ticket_id in self._waiting
        ):
            pos = self._waiting.index(t.ticket_id) + 1
            t.queue_position = pos
            t.eta_seconds = pos * self._wait_per_slot
        else:
            t.queue_position = 0
            t.eta_seconds = 0

    def _refresh_all_positions(self) -> None:
        for t in self._tickets.values():
            self._refresh_position(t)


# ---------------------------------------------------------------------------
# 工厂：根据环境变量构造默认参数
# ---------------------------------------------------------------------------
def from_env() -> LocalQueueHandoffClient:
    return LocalQueueHandoffClient(
        capacity=int(os.getenv("HH_QUEUE_CAPACITY", "50")),
        agent_pool_size=int(os.getenv("HH_AGENT_POOL_SIZE", "1")),
        estimated_wait_per_slot=int(os.getenv("HH_WAIT_PER_SLOT", "30")),
    )
