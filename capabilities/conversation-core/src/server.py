"""FastAPI 入口：暴露骨架 REST API + 静态 Web Demo。

路由：
  GET  /api/v1/health          —— 三把 Key 实时连通性
  POST /api/v1/get_config      —— 生成 RoomId / UserSig / 模态配置
  POST /api/v1/agent/start     —— 启动 AI 对话任务
  POST /api/v1/agent/stop      —— 停止 AI 对话任务
  POST /api/v1/agent/control   —— 文本注入 / 打断
  GET  /                       —— Web Demo 静态页

设计原则（与 §3.3 对齐）：
  - 零行业预设：所有路由仅做协议编排，不内置任何业务 Prompt
  - 配置即验证：health 端点为 Web Demo 三盏灯提供数据源
  - 安全合规：启动时安装日志脱敏过滤器，凭证仅来自环境变量
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# 在导入业务模块前加载 .env，确保 credentials 模块读到正确的环境变量
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env.local")
load_dotenv(_BASE_DIR / ".env")

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import ConversationAgent
from .credentials import load_from_env
from .health import check_all
from .log_filter import install_redacting_filter
from .modality import IoModality
from .trtc_client import AgentLifecycleConfig

logger = logging.getLogger("conversation_core")

# 安装日志脱敏过滤器（P0 安全项）
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
install_redacting_filter(logging.getLogger())


# ---------------------------------------------------------------------------
# 全局 Agent 单例（启动失败不影响 /api/v1/health 给出明确诊断）
# ---------------------------------------------------------------------------
_credentials = load_from_env()
_io_modality = IoModality()  # Phase 1 默认全模态启用
_agent: Optional[ConversationAgent] = None
_init_error: Optional[str] = None
try:
    _agent = ConversationAgent(_credentials, _io_modality)
    logger.info("ConversationAgent initialized")
except Exception as exc:  # 凭证缺失等问题不能让进程启动失败
    _init_error = str(exc)
    logger.warning("ConversationAgent not initialized: %s", _init_error)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class GetConfigRequest(BaseModel):
    user_id: Optional[str] = None
    room_id: Optional[str] = None


class StartAgentRequest(BaseModel):
    session_id: str = Field(..., description="get_config 返回的 session_id")
    instructions: Optional[str] = None
    greeting: Optional[str] = None
    language: Optional[str] = "en"  # en | zh
    voice_id: Optional[str] = None  # 留空使用 DEFAULT_VOICE_IDS 按 language 选择
    max_idle_time: Optional[int] = 60


class StopAgentRequest(BaseModel):
    session_id: str


class ControlRequest(BaseModel):
    session_id: str
    text: str
    interrupt: bool = True


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="conversation-core",
    version="1.0.0",
    description="TRTC Voice Agent 通用骨架（无业务预设）",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")


def _to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=f"internal: {exc}")


def _require_agent() -> ConversationAgent:
    if _agent is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "credentials_missing",
                "message": _init_error or "credentials not configured",
                "hint": "run scripts/setup-credentials.py first",
            },
        )
    return _agent


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@api.get("/health")
def health() -> Dict[str, Any]:
    """实时探测三把 Key 连通性，供 Web Demo 顶部状态栏使用。"""
    cred = load_from_env()
    tc, trtc, llm = check_all(cred.tencent_cloud, cred.trtc, cred.llm)
    overall = "ok" if tc.ok and trtc.ok and llm.ok else "partial_failure"
    return {
        "status": overall,
        "checks": {
            "tencent_cloud": tc.to_dict(),
            "trtc": trtc.to_dict(),
            "llm": llm.to_dict(),
        },
        "configured": cred.fully_configured,
        "missing": cred.missing(),
        "io_modality": _io_modality.to_dict(),
    }


# ---------------------------------------------------------------------------
# Config / Lifecycle
# ---------------------------------------------------------------------------
@api.post("/get_config")
def get_config(req: GetConfigRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        data = agent.issue_config(user_id=req.user_id, room_id=req.room_id)
        return {"code": 0, "msg": "success", "data": data}
    except Exception as exc:
        raise _to_http_error(exc)


@api.post("/agent/start")
def agent_start(req: StartAgentRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        defaults = AgentLifecycleConfig()
        cfg = AgentLifecycleConfig(
            instructions=req.instructions or defaults.instructions,
            greeting=req.greeting or defaults.greeting,
            language=req.language or "en",
            voice_id=req.voice_id or "",
            max_idle_time=req.max_idle_time or 60,
        )
        return {"code": 0, "msg": "success", "data": agent.start_agent(req.session_id, cfg)}
    except Exception as exc:
        raise _to_http_error(exc)


@api.post("/agent/stop")
def agent_stop(req: StopAgentRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        return {"code": 0, "msg": "success", "data": agent.stop_agent(req.session_id)}
    except Exception as exc:
        raise _to_http_error(exc)


@api.post("/agent/control")
def agent_control(req: ControlRequest) -> Dict[str, Any]:
    agent = _require_agent()
    try:
        return {
            "code": 0,
            "msg": "success",
            "data": agent.push_text(req.session_id, req.text, req.interrupt),
        }
    except Exception as exc:
        raise _to_http_error(exc)


@api.get("/sessions")
def sessions_list() -> Dict[str, Any]:
    agent = _require_agent()
    return {"code": 0, "data": agent.list_sessions()}


# ---------------------------------------------------------------------------
# Debug 端点：用于排查 InvalidParameter.UserSig 等问题
# 把当前配置 + 一份测试 UserSig 输出，方便对照 TRTC 官方工具校验：
#   https://console.cloud.tencent.com/trtc/usersigtools
# 安全：仅返回 SDKAppID / region / endpoint / 测试 UserSig，不返回 SecretKey 明文
# ---------------------------------------------------------------------------
@api.get("/debug/usersig")
def debug_usersig(user_id: str = "test_user_001") -> Dict[str, Any]:
    cred = load_from_env()
    if not cred.trtc.configured:
        raise HTTPException(status_code=503, detail="TRTC credential not configured")
    from .usersig import gen_user_sig

    sig = gen_user_sig(
        sdk_app_id=cred.trtc.sdk_app_id,
        sdk_secret_key=cred.trtc.sdk_secret_key,
        user_id=user_id,
        expire_seconds=86400,
    )
    return {
        "sdk_app_id": cred.trtc.sdk_app_id,
        "region": cred.trtc.region,
        "trtc_endpoint": cred.trtc.trtc_endpoint,
        "test_user_id": user_id,
        "test_user_sig": sig,
        "user_sig_length": len(sig),
        "verify_url": "https://console.cloud.tencent.com/trtc/usersigtools",
        "hint": (
            "把 sdk_app_id / test_user_id / test_user_sig 粘贴到 TRTC 控制台官方校验工具，"
            "若工具显示 UserSig 校验通过 → SDKSecretKey 正确；"
            "若工具显示校验失败 → 你填的 TRTC_SDK_SECRET_KEY 与该 SDKAppID 不匹配，"
            "请重新到 TRTC 控制台核对 SDKSecretKey（注意：不是腾讯云 API SecretKey）。"
        ),
    }


app.include_router(api)

# ---------------------------------------------------------------------------
# 能力包路由挂载（可选；通过 _capability_loader 动态加载，能力包未安装则静默跳过）
# 由 add-capability 注入；统一走 try_load_capability 以避免连字符 import 失败。
# ---------------------------------------------------------------------------
from ._capability_loader import try_load_capability as _try_load_capability  # noqa: E402

# [knowledge-base] mount sub-router
_kb_router_mod = _try_load_capability("knowledge-base", "src/router.py")
if _kb_router_mod is not None and hasattr(_kb_router_mod, "router"):
    app.include_router(
        _kb_router_mod.router, prefix="/api/v1/kb", tags=["knowledge-base"]
    )


# ---------------------------------------------------------------------------
# Web Demo 静态页（最小验证页，不含业务）
# 可通过 WEB_DEMO_DIR 环境变量指向自定义 Demo 目录（如路径 A 产物目录）
# 未设置时默认使用 conversation-core 自带的 web-demo 自检页
# ---------------------------------------------------------------------------
_DEMO_DIR = Path(os.getenv("WEB_DEMO_DIR", str(_BASE_DIR / "web-demo")))
if _DEMO_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(_DEMO_DIR), html=True),
        name="static",
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(_DEMO_DIR / "index.html"))


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
