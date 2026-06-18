"""human-handoff 抽象端口（Port）。

与 manifest.yaml.business_contract 字段一一对应：
- create_ticket   -> ticket.create
- query_status    -> ticket.status_query
- cancel_ticket   -> ticket.cancel
- overall_status  -> 内部状态（不在外部契约中，仅供本地看板使用）

所有具体实现（local_queue / default_rest / mock / user_custom）必须继承本 ABC。
core 层只依赖本接口，不感知任何具体后端类型；切换后端仅需更换 adapter。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..core.models import OverallStatus, Ticket, TicketStatus


class HandoffClient(ABC):
    """转人工 / 工单后端的统一接口契约。"""

    # --- 与 business_contract 对齐的方法 -----------------------------

    @abstractmethod
    def create_ticket(
        self,
        *,
        user_id: str,
        subject: str = "",
        description: str = "",
        priority: str = "normal",
        transcript: Optional[List[str]] = None,
    ) -> Ticket:
        """创建工单。对应 business_contract.ticket.create。"""

    @abstractmethod
    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        """查询单工单状态。对应 ticket.status_query。

        返回 None 表示工单不存在。
        """

    @abstractmethod
    def cancel_ticket(self, ticket_id: str, reason: str = "") -> Optional[Ticket]:
        """用户取消工单。对应 ticket.cancel。返回 None 表示工单不存在。"""

    @abstractmethod
    def overall_status(self) -> OverallStatus:
        """整体队列状态（看板用，非外部契约）。"""

    # --- 看板辅助方法（默认实现：远程后端可不覆写） -----------------

    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        """列出工单（默认返回空，远程后端按需覆写）。"""
        return []

    def update_status(
        self,
        ticket_id: str,
        status: str,
        *,
        agent_id: Optional[str] = None,
    ) -> Optional[Ticket]:
        """坐席手动更新工单状态（默认不支持，可由 mock / local_queue 覆写）。"""
        raise NotImplementedError(
            f"{type(self).__name__} does not support manual status update"
        )

    # --- 兼容旧 trigger.maybe_handoff 的桥接接口 ----------------------

    def get_or_attach(self, user_id: str) -> Optional[Ticket]:
        """根据 user_id（旧 session_id）查找已存在的工单；未找到返回 None。

        本方法供 facade 层在不破坏旧 API 的前提下查询现有工单状态。
        默认实现遍历 list_tickets。
        """
        for t in self.list_tickets(limit=200):
            if t.user_id == user_id:
                return t
        return None
