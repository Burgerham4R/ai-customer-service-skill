"""digital-human FastAPI 占位路由。

接口契约固定：
- GET  /status    返回占位状态 + 未来计划
- POST /render    返回 501 Not Implemented，提示由后续迭代提供
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/status")
def status() -> dict:
    return {
        "code": 0,
        "data": {
            "enabled": os.getenv("DH_ENABLED", "false").lower() == "true",
            "avatar_id": os.getenv("DH_AVATAR_ID", ""),
            "lipsync_provider": os.getenv("DH_LIPSYNC_PROVIDER", "tencent-cloud-vmp"),
            "expression_provider": os.getenv("DH_EXPRESSION_PROVIDER", "internal-rule"),
            "phase": "placeholder",
            "roadmap": [
                "Phase 3+: 接入第三方渲染 SDK（avatar / lipsync / expression）",
                "支持 WebRTC datachannel 推送驱动数据",
            ],
        },
    }


@router.post("/render")
def render() -> dict:
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "message": "digital-human render is a placeholder; rendering layer not shipped in Phase 2",
            "hint": "follow capabilities/digital-human/README.md for integration roadmap",
        },
    )
