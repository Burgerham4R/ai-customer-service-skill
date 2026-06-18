"""Phase 3 阶段 6：human-handoff 能力包 ports/adapters 单元测试。

覆盖目标：
- LocalQueueHandoffClient：FIFO 队列 + 自动接通 + 取消 / 状态切换
- MockHandoffClient：演示数据预填（_seed 三条）+ list_tickets
- DefaultRestHandoffClient：base_url 安全校验（私网拒绝）+ HTTP 路径调用 + 透传响应

注：本测试文件在 import 前会清理 sys.modules 中残留的 ``src.*`` 模块，
以避免与 ``test_kb_ports.py`` 中同名 ``src`` 包冲突；同样地 KB 的测试也会自我清理。
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 隔离 import：清理同名 src.* 缓存 + 插入 human-handoff 自身的 src 父目录
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_HH = _ROOT / "capabilities" / "human-handoff"

for _name in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
    del sys.modules[_name]
sys.path[:] = [p for p in sys.path if "/capabilities/" not in p]
sys.path.insert(0, str(_HH))

# 提前从 core.models 模块直接 import，绕过 src/core/__init__.py 的循环依赖
# （src/core/__init__.py 同时引入 service.py，而 service.py 依赖 ports.handoff_client）
import importlib  # noqa: E402

_models = importlib.import_module("src.core.models")
TicketStatusEnum = _models.TicketStatusEnum

from src.adapters.local_queue import LocalQueueHandoffClient  # noqa: E402
from src.adapters.mock import MockHandoffClient  # noqa: E402
# 预先导入 default_rest（HH 版本）并在模块作用域固化引用，
# 避免后续测试运行时 ``src`` 已被 test_kb_ports 替换为 KB 命名空间
from src.adapters import default_rest as _hh_default_rest  # noqa: E402

DefaultRestHandoffClient = _hh_default_rest.DefaultRestHandoffClient


class LocalQueueAdapterTests(unittest.TestCase):
    """覆盖 LocalQueueHandoffClient 的核心行为。"""

    def test_create_then_query_pending(self):
        c = LocalQueueHandoffClient(
            capacity=5, agent_pool_size=0, estimated_wait_per_slot=10
        )
        t = c.create_ticket(
            user_id="u1",
            subject="退款",
            description="3 天未到账",
            priority="normal",
            transcript=["用户：申请退款"],
        )
        # agent_pool_size=0 → 不会自动接通；进入排队
        self.assertEqual(t.status, TicketStatusEnum.PENDING.value)
        self.assertEqual(t.queue_position, 1)
        self.assertEqual(t.eta_seconds, 10)

        status = c.query_status(t.ticket_id)
        self.assertIsNotNone(status)
        self.assertEqual(status.status, TicketStatusEnum.PENDING.value)

    def test_auto_connect_when_agent_available(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=1)
        t = c.create_ticket(user_id="u_auto", subject="物流")
        self.assertEqual(t.status, TicketStatusEnum.PROCESSING.value)
        self.assertEqual(t.queue_position, 0)
        self.assertIsNotNone(t.agent_id)

    def test_cancel_releases_slot(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=1)
        t = c.create_ticket(user_id="u_cancel", subject="发票")
        canceled = c.cancel_ticket(t.ticket_id, reason="用户主动取消")
        self.assertIsNotNone(canceled)
        self.assertEqual(canceled.status, TicketStatusEnum.CANCELED.value)
        # 取消后，状态仍可查（已关闭工单），但 overall_status.connected = 0
        status = c.overall_status()
        self.assertEqual(status.connected, 0)

    def test_capacity_full_yields_timeout(self):
        c = LocalQueueHandoffClient(capacity=1, agent_pool_size=0)
        c.create_ticket(user_id="u_fill")
        t2 = c.create_ticket(user_id="u_overflow")
        self.assertEqual(t2.status, TicketStatusEnum.TIMEOUT.value)
        self.assertIsNotNone(t2.closed_at)

    def test_update_status_manual_close(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=1)
        t = c.create_ticket(user_id="u_close")
        # auto-connected → close
        closed = c.update_status(t.ticket_id, "closed")
        self.assertEqual(closed.status, TicketStatusEnum.CLOSED.value)
        self.assertIsNotNone(closed.closed_at)
        self.assertEqual(c.overall_status().connected, 0)

    def test_get_or_attach_returns_active_only(self):
        c = LocalQueueHandoffClient(capacity=5, agent_pool_size=0)
        t = c.create_ticket(user_id="u_query")
        same = c.get_or_attach("u_query")
        self.assertEqual(same.ticket_id, t.ticket_id)
        # cancel 后，get_or_attach 应返回 None（仅返回 active 工单）
        c.cancel_ticket(t.ticket_id)
        self.assertIsNone(c.get_or_attach("u_query"))


class MockAdapterTests(unittest.TestCase):
    """MockHandoffClient 的演示数据应预先就位。"""

    def test_seed_three_tickets(self):
        c = MockHandoffClient(seed_demo_data=True, agent_pool_size=2)
        tickets = c.list_tickets(limit=10)
        ids = {t.ticket_id for t in tickets}
        # 三条 demo 工单全部存在
        self.assertIn("demo_pending_001", ids)
        self.assertIn("demo_processing_001", ids)
        self.assertIn("demo_closed_001", ids)
        statuses = {t.status for t in tickets}
        self.assertIn(TicketStatusEnum.PENDING.value, statuses)
        self.assertIn(TicketStatusEnum.PROCESSING.value, statuses)
        self.assertIn(TicketStatusEnum.CLOSED.value, statuses)

    def test_seed_can_be_disabled(self):
        c = MockHandoffClient(seed_demo_data=False, agent_pool_size=2)
        self.assertEqual(c.list_tickets(), [])

    def test_inherits_create_behavior(self):
        c = MockHandoffClient(seed_demo_data=False, agent_pool_size=2)
        t = c.create_ticket(user_id="u_new", subject="测试")
        # agent_pool_size=2 → 立即接通
        self.assertEqual(t.status, TicketStatusEnum.PROCESSING.value)


class DefaultRestAdapterSecurityTests(unittest.TestCase):
    """DefaultRestHandoffClient 的 base_url 安全校验（不实际发请求）。"""

    def test_https_public_allowed(self):
        # 不依赖 requests 真发包：只构造对象就足以触发 _validate_base_url
        c = DefaultRestHandoffClient(base_url="https://crm.example.com")
        # 通过 _base 反查校验后的 url
        self.assertTrue(c._base.startswith("https://"))

    def test_localhost_http_allowed(self):
        c = DefaultRestHandoffClient(base_url="http://localhost:8080")
        self.assertIn("localhost", c._base)

    def test_private_network_denied(self):
        for url in (
            "https://10.1.2.3",
            "https://192.168.0.1",
            "https://172.16.0.5",
            "https://9.0.0.1",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    DefaultRestHandoffClient(base_url=url)

    def test_non_https_remote_denied(self):
        with self.assertRaises(ValueError):
            DefaultRestHandoffClient(base_url="http://crm.example.com")

    def test_create_ticket_calls_post(self):
        """模拟 requests 走通一次 create_ticket，验证 payload 关键字段。"""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "ticket_id": "T-9001",
            "queue_position": 2,
            "eta_seconds": 60,
        }

        c = DefaultRestHandoffClient(base_url="https://crm.example.com", token="tok")
        with patch.object(c._session, "post", return_value=fake_resp) as p:
            t = c.create_ticket(
                user_id="u9", subject="退款", description="3 天未到账"
            )
        self.assertEqual(t.ticket_id, "T-9001")
        self.assertEqual(t.queue_position, 2)
        # 校验调用参数
        self.assertEqual(p.call_count, 1)
        _, kwargs = p.call_args
        self.assertEqual(kwargs["json"]["user_id"], "u9")
        # Authorization 头应携带 Bearer
        self.assertIn("Bearer ", kwargs["headers"]["Authorization"])


if __name__ == "__main__":
    unittest.main()
