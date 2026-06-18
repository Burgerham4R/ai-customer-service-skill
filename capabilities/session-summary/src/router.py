"""session-summary FastAPI 子路由。"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from .recorder import get_recorder
from .summarizer import summarize

router = APIRouter()


@router.get("/_list")
def list_recent(_offset: int = 0, _limit: int = 20) -> dict:
    if _limit < 1 or _limit > 200:
        raise HTTPException(status_code=400, detail="_limit out of range [1,200]")
    return {"code": 0, "data": get_recorder().list_recent(offset=_offset, limit=_limit)}


@router.get("/{session_id}")
def get_summary(session_id: str) -> dict:
    rec = get_recorder().get(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return {"code": 0, "data": rec.to_dict()}


@router.post("/{session_id}/finalize")
def finalize(session_id: str) -> dict:
    rec = get_recorder().get(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    prefer_llm = os.getenv("SS_LLM_SUMMARY", "true").lower() == "true"
    summary = summarize(rec, prefer_llm=prefer_llm)
    rec = get_recorder().finalize(session_id, summary)
    # 写回：按 SS_ADAPTER 选择 mock / local_json / default_rest（失败安全降级 mock）
    writeback = None
    try:
        from .adapters.factory import get_sink
        writeback = get_sink().write(rec.to_dict())
    except Exception as exc:  # noqa: BLE001
        writeback = {"accepted": False, "error": str(exc)}
    data = rec.to_dict()
    data["writeback"] = writeback
    return {"code": 0, "data": data}
