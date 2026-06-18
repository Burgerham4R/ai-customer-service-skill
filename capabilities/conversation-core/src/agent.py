"""Voice Agent 会话编排（ASR / LLM / TTS / 会话管理统一链路）。

骨架仅做协议编排：
1) 客户端通过 /api/v1/get_config 获取 RoomId / 用户 UserSig
2) 前端 SDK 入房并发起 /api/v1/agent/start
3) 服务端使用 trtc_client.start() 拉起 AI 通道机器人
   ↳ TRTC ConversationAI 内部串接 ASR → LLM → TTS 全链路
4) /api/v1/agent/stop 关闭任务
5) /api/v1/agent/control 用于文本注入 / 打断（覆盖 text_input 模态）

注意：本模块不引入任何业务 Prompt、行业知识库或 FAQ 模板，
所有业务逻辑均通过外层能力包以 manifest.yaml 注入点形式叠加。
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Optional

from .credentials import Credentials
from .modality import IoModality
from .trtc_client import AgentLifecycleConfig, TrtcConversationClient
from .usersig import gen_user_sig

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    session_id: str
    room_id: str
    user_id: str
    agent_user_id: str
    user_sig: str
    agent_user_sig: str
    task_id: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    request_id: Optional[str] = None


class ConversationAgent:
    """Voice Agent 会话总管。

    单例风格，由 server 在启动时实例化并复用。仅维护内存中的 session
    映射，不做持久化（生产化由外层能力包负责）。
    """

    def __init__(self, credentials: Credentials, io_modality: IoModality) -> None:
        if not credentials.fully_configured:
            raise ValueError(
                f"credentials missing: {credentials.missing()}; "
                "请先执行 scripts/setup-credentials.py 完成配置"
            )
        self._cred = credentials
        self._io = io_modality
        self._client = TrtcConversationClient(
            tencent=credentials.tencent_cloud,
            trtc=credentials.trtc,
            llm=credentials.llm,
        )
        self._sessions: Dict[str, SessionInfo] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------
    # /api/v1/get_config
    # ------------------------------------------------------------------
    def issue_config(
        self,
        user_id: Optional[str] = None,
        room_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成入房凭据（房间号 / 用户 UserSig / AI 机器人 UserSig）。

        默认使用 **数字房间号**（与 TRTC 控制台默认应用一致），避免与未启用
        PrivateMapKey 的应用产生 ``InvalidParameter.UserSig`` 误判。
        UserId 命名仅使用 ``[A-Za-z0-9_-]``，长度 ≤ 32（TRTC 强制约束）。
        """
        # 数字房间号：取 32-bit 范围内的随机正整数
        room = str(room_id) if room_id else str(secrets.randbelow(2_000_000_000) + 1)
        u_id = str(user_id) if user_id else f"u_{secrets.token_hex(6)}"
        agent_u_id = f"ai_{secrets.token_hex(6)}"
        # TRTC UserId 长度上限 32，做一次防御性截断
        u_id = u_id[:32]
        agent_u_id = agent_u_id[:32]
        user_sig = gen_user_sig(
            sdk_app_id=self._cred.trtc.sdk_app_id,
            sdk_secret_key=self._cred.trtc.sdk_secret_key,
            user_id=u_id,
        )
        agent_sig = gen_user_sig(
            sdk_app_id=self._cred.trtc.sdk_app_id,
            sdk_secret_key=self._cred.trtc.sdk_secret_key,
            user_id=agent_u_id,
        )
        sid = secrets.token_urlsafe(12)
        info = SessionInfo(
            session_id=sid,
            room_id=room,
            user_id=u_id,
            agent_user_id=agent_u_id,
            user_sig=user_sig,
            agent_user_sig=agent_sig,
        )
        with self._lock:
            self._sessions[sid] = info
        logger.info("issue_config session=%s room=%s user=%s", sid, room, u_id)
        return {
            "session_id": sid,
            "sdk_app_id": self._cred.trtc.sdk_app_id,
            "room_id": room,
            "room_id_type": 0,  # 数字房间号
            "user_id": u_id,
            "user_sig": user_sig,
            "agent_user_id": agent_u_id,
            "io_modality": self._io.to_dict(),
        }

    # ------------------------------------------------------------------
    # /api/v1/agent/start
    # ------------------------------------------------------------------
    def start_agent(
        self,
        session_id: str,
        config: Optional[AgentLifecycleConfig] = None,
    ) -> Dict[str, Any]:
        info = self._require_session(session_id)
        # _ext_before_start_  (capability extension anchor; do not remove)
        # Capabilities (e.g. knowledge-base) injected via add-capability.py land here,
        # inside the start_agent method body, where `config` and `info` are in scope.
        #
        # [knowledge-base] 若已安装 knowledge-base 能力包，则把命中的 FAQ 拼到 instructions
        # 通过 _capability_loader 动态加载，独立于 cwd / 仓库目录名 / 连字符目录
        if config is not None and getattr(config, "instructions", None):
            from ._capability_loader import try_load_capability
            _kb = try_load_capability("knowledge-base", "src/retriever.py")
            if _kb is not None:
                try:
                    config.instructions = _kb.attach_faq_to_instructions(config.instructions)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("knowledge-base FAQ injection failed: %s", exc)
        result = self._client.start(
            room_id=info.room_id,
            agent_user_id=info.agent_user_id,
            agent_user_sig=info.agent_user_sig,
            target_user_id=info.user_id,
            config=config,
            room_id_type=0,  # 数字房间号（与 issue_config 保持一致）
        )
        with self._lock:
            info.task_id = result.get("task_id")
            info.request_id = result.get("request_id")
        logger.info("start_agent session=%s task=%s", session_id, info.task_id)
        # _ext_after_start_  (capability extension anchor; do not remove)
        # Capabilities (e.g. human-handoff) injected via add-capability.py land here,
        # inside the method body, where `session_id` and `info` are in scope.
        return {
            "session_id": session_id,
            "task_id": info.task_id,
            "request_id": info.request_id,
            "status": "started",
        }

    # ------------------------------------------------------------------
    # /api/v1/agent/stop
    # ------------------------------------------------------------------
    def stop_agent(self, session_id: str) -> Dict[str, Any]:
        info = self._require_session(session_id)
        if info.task_id:
            self._client.stop(info.task_id)
        with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("stop_agent session=%s task=%s", session_id, info.task_id)
        return {"session_id": session_id, "status": "stopped"}

    # ------------------------------------------------------------------
    # /api/v1/agent/control
    # ------------------------------------------------------------------
    def push_text(
        self,
        session_id: str,
        text: str,
        interrupt: bool = True,
    ) -> Dict[str, Any]:
        """文本输入通道：将文字注入运行中的 AI 任务。"""
        info = self._require_session(session_id)
        if not info.task_id:
            raise RuntimeError("session has no active task; call start_agent first")
        if not text or not text.strip():
            raise ValueError("text cannot be empty")
        # _ext_before_push_text_  (capability extension anchor; do not remove)
        # Capabilities (human-handoff / tool-calling / session-summary) injected
        # via add-capability.py land here, inside push_text's body, where the
        # locals `session_id` and `text` are in scope.
        self._client.control(
            task_id=info.task_id,
            command="ServerPushText",
            text=text,
            interrupt=interrupt,
        )
        return {"session_id": session_id, "task_id": info.task_id, "delivered": True}

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def list_sessions(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sessions": [
                    {
                        "session_id": s.session_id,
                        "room_id": s.room_id,
                        "user_id": s.user_id,
                        "task_id": s.task_id,
                        "started_at": s.started_at,
                    }
                    for s in self._sessions.values()
                ]
            }

    def _require_session(self, session_id: str) -> SessionInfo:
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            info = self._sessions.get(session_id)
        if not info:
            raise ValueError(f"session not found: {session_id}")
        return info
