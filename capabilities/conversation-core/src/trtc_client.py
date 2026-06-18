"""TRTC Conversational AI 控制面客户端。

封装 StartAIConversation / StopAIConversation / ControlAIConversation
三个 REST API 的最小调用链路。骨架层只做"协议封装 + 凭证签名"，
不内置任何业务 Prompt、行业知识库或 FAQ 模板。

API 文档：
- StartAIConversation: https://cloud.tencent.com/document/product/647/108514
- StopAIConversation:  https://cloud.tencent.com/document/product/647/108513
- ControlAIConversation: https://cloud.tencent.com/document/product/647/109408
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from .credentials import LlmCredential, TencentCloudCredential, TrtcCredential

logger = logging.getLogger(__name__)

_SERVICE = "trtc"
_VERSION = "2019-07-22"


def _sign_tc3(secret_key: str, date: str, string_to_sign: str) -> str:
    k_date = hmac.new(
        ("TC3" + secret_key).encode("utf-8"),
        date.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    k_service = hmac.new(k_date, _SERVICE.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"tc3_request", hashlib.sha256).digest()
    return hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_request(
    cred: TencentCloudCredential,
    host: str,
    region: str,
    action: str,
    payload: Dict[str, Any],
    timeout: float = 5.0,
) -> Dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

    canonical_headers = (
        f"content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
    canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
    credential_scope = f"{date}/{_SERVICE}/tc3_request"
    hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashed_canonical}"
    signature = _sign_tc3(cred.secret_key, date, string_to_sign)
    authorization = (
        f"TC3-HMAC-SHA256 Credential={cred.secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": _VERSION,
        "X-TC-Region": region,
    }
    resp = requests.post(
        f"https://{host}",
        headers=headers,
        data=body.encode("utf-8"),
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"TRTC API HTTP {resp.status_code}: {resp.text[:200]}")
    parsed = resp.json()
    response_obj = parsed.get("Response", {})
    err = response_obj.get("Error")
    request_id = response_obj.get("RequestId", "n/a")
    if err:
        raise RuntimeError(
            f"TRTC API error {err.get('Code')}: {err.get('Message')} "
            f"[endpoint={host}, action={action}, RequestId={request_id}]"
        )
    return response_obj


@dataclass
class AgentLifecycleConfig:
    """会话生命周期参数（与业务逻辑无关）。"""

    instructions: str = "You are a helpful voice assistant. Reply briefly."
    greeting: str = "Hello, how can I help you?"
    max_idle_time: int = 60  # 秒
    welcome_message: str = ""
    language: str = "en"  # 默认英文（最广泛兼容；中文需要 TRTC 应用启用对应能力）
    voice_id: str = "v-female-A4b9KqP2"  # TRTC FlowTTS 默认女声（英文 Articulate Narrator）
    tts_model: str = "flow_01_turbo"


# TRTC FlowTTS 真实音色 ID（取自 oral-coach 项目验证可用）
# 完整音色列表：https://trtc.io/document/79682?product=conversationalai
DEFAULT_VOICE_IDS = {
    ("en", "female"): "v-female-p9Xy7Q1L",  # Articulate Narrator
    ("en", "male"):   "v-male-A4b9KqP2",     # Scholarly Lecturer
    ("zh", "female"): "female-kefu-xiaoyue",
    ("zh", "male"):   "male-kefu-xiaoxu",
}


class TrtcConversationClient:
    """TRTC ConversationAI 控制面薄封装。

    构造参数：
        tencent: 腾讯云 API 密钥（用于签名 REST 请求）。
        trtc:    TRTC SDKAppID / SDKSecretKey（StartAIConversation 中的 SdkAppId）。
        llm:     LLM 凭据，用于注入 LLMConfig（仅做参数透传，不在骨架内调用）。
    """

    def __init__(
        self,
        tencent: TencentCloudCredential,
        trtc: TrtcCredential,
        llm: LlmCredential,
    ) -> None:
        if not tencent.configured:
            raise ValueError("tencent cloud credential not configured")
        if not trtc.configured:
            raise ValueError("trtc credential not configured")
        if not llm.configured:
            raise ValueError("llm credential not configured")
        self.tencent = tencent
        self.trtc = trtc
        self.llm = llm

    # ------------------------------------------------------------------
    # StartAIConversation
    # ------------------------------------------------------------------
    def start(
        self,
        room_id: str,
        agent_user_id: str,
        agent_user_sig: str,
        target_user_id: str,
        config: Optional[AgentLifecycleConfig] = None,
        room_id_type: int = 0,
    ) -> Dict[str, Any]:
        cfg = config or AgentLifecycleConfig()
        # 解析 voice_id：用户显式指定 > 按 language 取默认
        voice_id = cfg.voice_id or DEFAULT_VOICE_IDS.get(
            (cfg.language, "female"),
            DEFAULT_VOICE_IDS[("en", "female")],
        )
        payload: Dict[str, Any] = {
            "SdkAppId": self.trtc.sdk_app_id,
            "RoomId": str(room_id),
            "RoomIdType": room_id_type,
            "AgentConfig": {
                "UserId": agent_user_id,
                "UserSig": agent_user_sig,
                "MaxIdleTime": cfg.max_idle_time,
                "TargetUserId": target_user_id,
                "WelcomeMessage": cfg.welcome_message or cfg.greeting,
                # 智能打断（关键）：
                #   InterruptMode 2 = 自动 + 手动双轨
                #     • 自动：用户开口说话超过 InterruptSpeechDuration ms → 停 TTS
                #     • 手动：前端发 type:20001 自定义消息 → 立即停 TTS（用于
                #       文字输入场景：发文字前先打断，再 type:20000 触发新回合）
                "InterruptMode": 2,
                "InterruptSpeechDuration": 500,
                # 字幕模式：1 = 一并下发用户与 AI 字幕到端上
                "SubtitleMode": 1,
                # 单字过滤：避免 ASR 把"嗯/啊"等碎音切成单字
                "FilterOneWord": True,
                # 回合检测：3 = 语义 + VAD 双信号识别用户讲完
                "TurnDetectionMode": 3,
                "TurnDetection": {"SemanticEagerness": "auto"},
            },
            "STTConfig": {
                "Language": cfg.language,
                "VadLevel": 3,
                "VadSilenceTime": 1000,
            },
            "LLMConfig": json.dumps(
                {
                    "LLMType": self.llm.llm_type,
                    "Model": self.llm.model,
                    "APIKey": self.llm.api_key,
                    "APIUrl": self.llm.api_url,
                    "Streaming": True,
                    "SystemPrompt": cfg.instructions,
                    "History": 20,
                    "Temperature": 0.4,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            "TTSConfig": json.dumps(
                {
                    "TTSType": "flow",
                    "Model": cfg.tts_model,
                    "VoiceId": voice_id,
                    "Speed": 1.0,
                    "Volume": 1.0,
                    "Pitch": 0,
                    "Language": cfg.language,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        }
        # 启动前打印关键诊断信息（脱敏 UserSig）
        logger.info(
            "StartAIConversation: endpoint=%s region=%s SdkAppId=%s RoomId=%s "
            "agent=%s target=%s userSig=%s...%s(len=%d) lang=%s voice=%s",
            self.trtc.trtc_endpoint,
            self.trtc.trtc_region,
            self.trtc.sdk_app_id,
            room_id,
            agent_user_id,
            target_user_id,
            agent_user_sig[:6],
            agent_user_sig[-4:],
            len(agent_user_sig),
            cfg.language,
            voice_id,
        )
        resp = _signed_request(
            self.tencent,
            host=self.trtc.trtc_endpoint,
            region=self.trtc.trtc_region,
            action="StartAIConversation",
            payload=payload,
            timeout=10.0,
        )
        return {
            "task_id": resp.get("TaskId"),
            "request_id": resp.get("RequestId"),
        }

    # ------------------------------------------------------------------
    # StopAIConversation
    # ------------------------------------------------------------------
    def stop(self, task_id: str) -> None:
        if not task_id:
            raise ValueError("task_id is required")
        _signed_request(
            self.tencent,
            host=self.trtc.trtc_endpoint,
            region=self.trtc.trtc_region,
            action="StopAIConversation",
            payload={"TaskId": task_id},
            timeout=5.0,
        )

    # ------------------------------------------------------------------
    # ControlAIConversation：用于文本注入 / 打断
    # ------------------------------------------------------------------
    def control(
        self,
        task_id: str,
        command: str,
        text: Optional[str] = None,
        interrupt: bool = True,
    ) -> Dict[str, Any]:
        """向运行中的对话任务注入文本或下达控制指令。"""
        if not task_id or not command:
            raise ValueError("task_id and command are required")
        payload: Dict[str, Any] = {"TaskId": task_id, "Command": command}
        if text is not None:
            payload["ServerPushText"] = {
                "Text": text,
                "Interrupt": interrupt,
            }
        return _signed_request(
            self.tencent,
            host=self.trtc.trtc_endpoint,
            region=self.trtc.trtc_region,
            action="ControlAIConversation",
            payload=payload,
            timeout=5.0,
        )
