"""三把 Key 凭证读取与封装。

凭证仅来自环境变量（P0 Secrets 规范：env-only），不从代码或
配置文件中读取明文。读取后以 dataclass 形式向上层暴露，调用
方不应在日志中打印整个对象——而是依赖 log_filter.RedactingFilter
做兜底脱敏。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TencentCloudCredential:
    """第一把 Key：腾讯云 API 密钥（用于 STS / TRTC 控制面 REST 调用）。"""

    secret_id: str
    secret_key: str
    region: str = "ap-guangzhou"

    @property
    def configured(self) -> bool:
        return bool(self.secret_id and self.secret_key)


@dataclass(frozen=True)
class TrtcCredential:
    """第二把 Key：TRTC Conversational AI 应用凭据。

    SDKAppID 与 SDKSecretKey 用于生成 UserSig 及调用 ConversationAI。
    region 决定调用国际站还是国内站 endpoint：
      - "intl" → 应用在 https://console.trtc.io 申请（默认）
      - "cn"   → 应用在 https://console.cloud.tencent.com/trtc 申请
    """

    sdk_app_id: int
    sdk_secret_key: str
    region: str = "intl"  # intl | cn

    @property
    def configured(self) -> bool:
        return bool(self.sdk_app_id and self.sdk_secret_key)

    @property
    def trtc_endpoint(self) -> str:
        return (
            "trtc.intl.tencentcloudapi.com"
            if self.region == "intl"
            else "trtc.tencentcloudapi.com"
        )

    @property
    def trtc_region(self) -> str:
        return "ap-singapore" if self.region == "intl" else "ap-guangzhou"


@dataclass(frozen=True)
class LlmCredential:
    """第三把 Key：外部 LLM 接入密钥（OpenAI 兼容协议）。"""

    api_key: str
    api_url: str = "https://api.openai.com/v1/chat/completions"
    model: str = "gpt-4o-mini"
    llm_type: str = "openai"

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_url and self.model)


@dataclass(frozen=True)
class Credentials:
    """三把 Key 聚合容器。"""

    tencent_cloud: TencentCloudCredential
    trtc: TrtcCredential
    llm: LlmCredential

    @property
    def fully_configured(self) -> bool:
        return all(
            (
                self.tencent_cloud.configured,
                self.trtc.configured,
                self.llm.configured,
            )
        )

    def missing(self) -> list[str]:
        miss: list[str] = []
        if not self.tencent_cloud.configured:
            miss.append("tencent_cloud")
        if not self.trtc.configured:
            miss.append("trtc")
        if not self.llm.configured:
            miss.append("llm")
        return miss


def _int_env(key: str, default: int = 0) -> int:
    raw = os.getenv(key, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def load_from_env() -> Credentials:
    """从环境变量加载三把 Key。

    所有键名与 .env.example / setup-credentials.py 输出保持一致。
    """
    return Credentials(
        tencent_cloud=TencentCloudCredential(
            secret_id=os.getenv("TENCENT_CLOUD_SECRET_ID", ""),
            secret_key=os.getenv("TENCENT_CLOUD_SECRET_KEY", ""),
            region=os.getenv("TENCENT_CLOUD_REGION", "ap-guangzhou"),
        ),
        trtc=TrtcCredential(
            sdk_app_id=_int_env("TRTC_SDK_APP_ID", 0),
            sdk_secret_key=os.getenv("TRTC_SDK_SECRET_KEY", ""),
            region=os.getenv("TRTC_REGION", "intl"),
        ),
        llm=LlmCredential(
            api_key=os.getenv("LLM_API_KEY", ""),
            api_url=os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            llm_type=os.getenv("LLM_TYPE", "openai"),
        ),
    )
