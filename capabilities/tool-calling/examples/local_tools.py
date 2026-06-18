"""tool-calling 能力包内置「通用 AI 客服工具集」（α 轨默认实现 = 本地 mock）。

设计原则（与 SKILL §6 点 2 对齐）：
- 行业中立：不绑定具体行业，覆盖绝大多数客服场景的通用动作
  （查单据状态 / 查营业信息 / 预约 / 提交反馈）。
- 开箱即用：每个工具都有可直接运行的 α 轨 mock 实现，
  用户走路径 A 或本地演示、即使没有真实后端接口，也能立刻看到能力效果。
- 可平滑替换：每个工具在 data/tools.yaml 同时声明 β 轨（远程 HTTPS）占位；
  用户接真实系统时只需把 β endpoint 指向自己的 API（或按 INTERFACE_ADAPT.md 适配）。

返回值必须 JSON-serializable；mock 数据统一带 "_mock": true 标记，
便于前端 / 日志区分「演示数据」与「真实业务数据」。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict


def _stable_pick(seed: str, choices):
    """根据 seed 稳定地选一个值（同一输入每次返回一致，便于演示可复现）。"""
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    return choices[h % len(choices)]


def query_order_status(order_id: str = "", **_: Any) -> Dict[str, Any]:
    """查询单据 / 订单 / 工单状态（通用客服动作）。

    参数:
        order_id: 单据号（订单号 / 工单号 / 预约号均可）。
    """
    if not order_id:
        return {"_mock": True, "error": "order_id is required"}
    status = _stable_pick(order_id, ["processing", "confirmed", "in_progress", "completed", "cancelled"])
    return {
        "_mock": True,
        "order_id": order_id,
        "status": status,
        "updated_at": int(time.time()),
        "note": "Demo data from built-in mock tool; point the β endpoint to your real system to use live data.",
    }


def get_business_info(topic: str = "hours", **_: Any) -> Dict[str, Any]:
    """查询营业信息（营业时间 / 地址 / 联系方式等），通用客服高频问题。

    参数:
        topic: hours | address | contact | all
    """
    info = {
        "hours": "Mon-Sun 10:00-22:00 (last entry 21:00)",
        "address": "No.1 Demo Street, Example District",
        "contact": "+86-000-0000-0000 / support@example.com",
    }
    topic = (topic or "hours").lower()
    data = info if topic == "all" else {topic: info.get(topic, info["hours"])}
    return {"_mock": True, "topic": topic, **data,
            "note": "Demo data from built-in mock tool; replace with your real business profile."}


def book_appointment(date: str = "", time_slot: str = "", party_size: int = 2, **_: Any) -> Dict[str, Any]:
    """创建预约 / 预订（餐厅订位、服务预约、回电预约等通用动作）。

    参数:
        date: 日期，如 2026-06-12
        time_slot: 时间段，如 18:30
        party_size: 人数 / 数量
    """
    if not date or not time_slot:
        return {"_mock": True, "error": "date and time_slot are required"}
    confirm = "BK" + hashlib.md5(f"{date}{time_slot}{party_size}".encode()).hexdigest()[:8].upper()
    return {
        "_mock": True,
        "confirmation_id": confirm,
        "date": date,
        "time_slot": time_slot,
        "party_size": int(party_size) if str(party_size).isdigit() else party_size,
        "status": "confirmed",
        "note": "Demo booking created by built-in mock tool; wire the β endpoint to your reservation system.",
    }


def submit_feedback(rating: int = 5, comment: str = "", **_: Any) -> Dict[str, Any]:
    """提交满意度 / 反馈（会话尾部常见动作）。

    参数:
        rating: 1-5 评分
        comment: 文字反馈（可选）
    """
    try:
        rating = max(1, min(5, int(rating)))
    except (TypeError, ValueError):
        rating = 5
    return {
        "_mock": True,
        "received": True,
        "rating": rating,
        "comment": (comment or "")[:512],
        "note": "Demo acknowledgement from built-in mock tool.",
    }
