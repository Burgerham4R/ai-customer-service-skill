"""human-handoff FastAPI 子路由。

挂载到骨架：app.include_router(router, prefix="/api/v1/handoff")

改造说明：
- 业务逻辑全部委托到 core.service.HandoffService
- 响应字段保持与 Phase 2 完全一致（to_legacy_dict），不破坏 Web Demo
- 新增 /admin/* 子段供 Phase 3 路径 A 的工单坐席看板使用
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .core.models import TicketStatusEnum
from .core.service import get_default_service


router = APIRouter()


# ---------------------------------------------------------------------------
# 请求体
# ---------------------------------------------------------------------------
class RequestBody(BaseModel):
    session_id: str = Field(..., max_length=64)
    reason: Optional[str] = Field(default="", max_length=512)


class ConnectBody(BaseModel):
    session_id: str = Field(..., max_length=64)
    agent_id: str = Field(..., max_length=64)


class CancelBody(BaseModel):
    session_id: str = Field(..., max_length=64)


class AdminUpdateBody(BaseModel):
    status: str = Field(..., max_length=32)
    agent_id: Optional[str] = Field(default=None, max_length=64)


# ---------------------------------------------------------------------------
# 现有端点（与 Phase 2 完全兼容）
# ---------------------------------------------------------------------------
@router.get("/status")
def overall() -> dict:
    return {"code": 0, "data": get_default_service().overall_status().to_dict()}


@router.get("/{session_id}")
def session_status(session_id: str) -> dict:
    ticket = get_default_service().get_by_session(session_id)
    if ticket is None:
        raise HTTPException(
            status_code=404, detail=f"session not tracked: {session_id}"
        )
    return {"code": 0, "data": ticket.to_legacy_dict()}


@router.post("/request")
def request_handoff(body: RequestBody) -> dict:
    ticket = get_default_service().request(
        body.session_id, reason=body.reason or ""
    )
    return {"code": 0, "data": ticket.to_legacy_dict()}


@router.post("/connect")
def connect(body: ConnectBody) -> dict:
    try:
        ticket = get_default_service().connect(body.session_id, body.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": 0, "data": ticket.to_legacy_dict()}


@router.post("/cancel")
def cancel(body: CancelBody) -> dict:
    try:
        ticket = get_default_service().cancel(body.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"code": 0, "data": ticket.to_legacy_dict()}


# ---------------------------------------------------------------------------
# 新增：工单坐席看板专用端点（Phase 3 路径 A 使用）
# 路径：/admin/tickets
# 这些端点输出"新版"字段（含 ticket_id / subject / priority / transcript），
# 与现有 /handoff/{session_id} 的旧字段格式并存。
# ---------------------------------------------------------------------------
@router.get("/admin/tickets")
def admin_list_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None, max_length=32),
) -> dict:
    items = get_default_service().list_tickets(limit=limit, status=status)
    return {
        "code": 0,
        "data": {
            "items": [t.to_dict() for t in items],
            "count": len(items),
        },
    }


@router.get("/admin/tickets/{ticket_id}")
def admin_get_ticket(ticket_id: str) -> dict:
    status = get_default_service().query_ticket(ticket_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    items = [
        t for t in get_default_service().list_tickets(limit=200)
        if t.ticket_id == ticket_id
    ]
    if not items:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    return {"code": 0, "data": items[0].to_dict()}


@router.post("/admin/tickets/{ticket_id}/status")
def admin_update_status(ticket_id: str, body: AdminUpdateBody) -> dict:
    # 校验 status 取值
    try:
        TicketStatusEnum(body.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {body.status}",
        ) from exc

    try:
        ticket = get_default_service().update_ticket_status(
            ticket_id, body.status, agent_id=body.agent_id
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=405, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if ticket is None:
        raise HTTPException(status_code=404, detail=f"ticket not found: {ticket_id}")
    return {"code": 0, "data": ticket.to_dict()}
