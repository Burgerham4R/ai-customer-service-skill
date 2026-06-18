"""MockHandoffClient —— Recipe 录视频用的 mock 实现。

继承 LocalQueueHandoffClient，启动时预填若干样例工单，让坐席看板打开即有内容。

与 LocalQueueHandoffClient 的区别：
- 构造时种入示例工单（待处理 / 处理中 / 已关闭 各一）
- 标记 `is_mock = True`，方便看板上加"演示数据"水印
- 演示数据使用稳定 ticket_id 前缀 `demo_` 便于截图复现
"""
from __future__ import annotations

from typing import List, Optional

from ..core.models import Ticket, TicketStatusEnum, now_ts
from .local_queue import LocalQueueHandoffClient


class MockHandoffClient(LocalQueueHandoffClient):
    """演示用 mock 实现。"""

    is_mock = True

    def __init__(
        self,
        *,
        capacity: int = 50,
        agent_pool_size: int = 2,
        estimated_wait_per_slot: int = 30,
        seed_demo_data: bool = True,
    ) -> None:
        super().__init__(
            capacity=capacity,
            agent_pool_size=agent_pool_size,
            estimated_wait_per_slot=estimated_wait_per_slot,
        )
        if seed_demo_data:
            self._seed()

    def _seed(self) -> None:
        """种入演示数据。座席池占用 1 个槽位，留 1 个空闲用于实时接通演示。"""
        ts_base = now_ts() - 600

        # 1) 已关闭工单（10 分钟前）
        closed = Ticket(
            ticket_id="demo_closed_001",
            user_id="demo_user_001",
            subject="发票抬头修改",
            description="已发货订单需要修改发票抬头",
            priority="normal",
            status=TicketStatusEnum.CLOSED.value,
            agent_id="agent_alice",
            transcript=[
                "用户：你好，我想修改一下发票抬头",
                "AI：请问是哪一笔订单？",
                "用户：订单号 SO20260601-0042",
                "[handoff] 用户请求转人工",
                "座席 alice：已为您处理，新发票将在 30 分钟内开具完成",
            ],
            reason="发票抬头修改",
            created_at=ts_base,
            updated_at=ts_base + 120,
            closed_at=ts_base + 240,
        )
        self._tickets[closed.ticket_id] = closed

        # 2) 处理中工单（占用 1 个座席槽位）
        processing = Ticket(
            ticket_id="demo_processing_001",
            user_id="demo_user_002",
            subject="退货物流异常",
            description="退货已 5 天未取件",
            priority="high",
            status=TicketStatusEnum.PROCESSING.value,
            agent_id="agent_bob",
            transcript=[
                "用户：我的退货已经申请 5 天了还没人来取",
                "AI：让我帮您查一下物流状态…",
                "AI：抱歉，物流接口暂时无法获取实时信息",
                "[handoff] 升级到人工座席",
                "座席 bob：您好，我正在跟进您的物流问题",
            ],
            reason="退货物流异常",
            created_at=ts_base + 300,
            updated_at=ts_base + 320,
        )
        self._tickets[processing.ticket_id] = processing
        self._connected[processing.ticket_id] = processing.agent_id  # type: ignore[assignment]

        # 3) 待处理工单（FIFO 队首）
        pending = Ticket(
            ticket_id="demo_pending_001",
            user_id="demo_user_003",
            subject="退款进度查询",
            description="申请退款 3 天未到账",
            priority="normal",
            status=TicketStatusEnum.PENDING.value,
            transcript=[
                "用户：我 3 天前申请的退款还没到账",
                "AI：请提供订单号便于查询",
                "用户：订单 SO20260605-0099",
                "[handoff] 转人工",
            ],
            reason="退款进度",
            created_at=ts_base + 540,
            updated_at=ts_base + 540,
        )
        self._tickets[pending.ticket_id] = pending
        self._waiting.append(pending.ticket_id)
        self._refresh_all_positions()

    def list_tickets(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Ticket]:
        # mock 模式下默认按创建时间倒序，与 LocalQueue 行为一致
        return super().list_tickets(limit=limit, status=status)


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------
def from_env() -> MockHandoffClient:
    import os

    return MockHandoffClient(
        capacity=int(os.getenv("HH_QUEUE_CAPACITY", "50")),
        agent_pool_size=int(os.getenv("HH_AGENT_POOL_SIZE", "2")),
        estimated_wait_per_slot=int(os.getenv("HH_WAIT_PER_SLOT", "30")),
        seed_demo_data=os.getenv("HH_MOCK_SEED", "1") not in ("0", "false", "False"),
    )
