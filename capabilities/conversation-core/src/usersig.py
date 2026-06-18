"""TLS-SIG-API-v2 UserSig 生成器（纯 Python 实现，无第三方依赖）。

TRTC 房间鉴权使用 SDKAppID + SDKSecretKey 对 UserId 做 HMAC-SHA256
签名，再以 zlib 压缩+base64url 编码得到 UserSig。本实现与官方
``TLSSigAPIv2`` 行为一致，便于在最小骨架中无需引入额外 SDK。

参考：https://cloud.tencent.com/document/product/647/17275
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import zlib


def _base64_encode(data: bytes) -> str:
    s = base64.b64encode(data).decode("utf-8")
    # TRTC 自定义 base64url：+ -> *、/ -> -、= -> _
    return s.replace("+", "*").replace("/", "-").replace("=", "_")


def _hmac_sha256(
    sdk_app_id: int,
    user_id: str,
    secret_key: str,
    current_ts: int,
    expire: int,
    base64_userbuf: str | None = None,
) -> str:
    raw_to_sign = (
        f"TLS.identifier:{user_id}\n"
        f"TLS.sdkappid:{sdk_app_id}\n"
        f"TLS.time:{current_ts}\n"
        f"TLS.expire:{expire}\n"
    )
    if base64_userbuf is not None:
        raw_to_sign += f"TLS.userbuf:{base64_userbuf}\n"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        raw_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def gen_user_sig(
    sdk_app_id: int,
    sdk_secret_key: str,
    user_id: str,
    expire_seconds: int = 86400,
) -> str:
    """生成 UserSig。

    Args:
        sdk_app_id: TRTC SDKAppID（整数）。
        sdk_secret_key: TRTC SDKSecretKey。
        user_id: 房间内用户标识，需保持稳定。
        expire_seconds: 有效期（秒），默认 24 小时。

    Returns:
        可直接用于 TRTC Web SDK 入房的 UserSig 字符串。
    """
    if not sdk_app_id or not sdk_secret_key:
        raise ValueError("sdk_app_id and sdk_secret_key are required")
    if not user_id:
        raise ValueError("user_id is required")

    current_ts = int(time.time())
    sig = _hmac_sha256(
        sdk_app_id=sdk_app_id,
        user_id=user_id,
        secret_key=sdk_secret_key,
        current_ts=current_ts,
        expire=expire_seconds,
    )

    payload = {
        "TLS.ver": "2.0",
        "TLS.identifier": str(user_id),
        "TLS.sdkappid": int(sdk_app_id),
        "TLS.expire": int(expire_seconds),
        "TLS.time": int(current_ts),
        "TLS.sig": sig,
    }
    compressed = zlib.compress(json.dumps(payload).encode("utf-8"))
    return _base64_encode(compressed)
