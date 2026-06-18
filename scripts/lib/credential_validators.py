"""三把 Key 验证函数下沉模块（Phase 3 阶段 5 新增）。

设计目的：
- 让 ``scripts/setup-credentials.py``（开发者交互式 fallback）和
  ``scripts/verify-credentials.py``（AI 主导无参数验证）共享同一套验证函数。
- 验证逻辑本体来自 ``capabilities/conversation-core/src/health.py``，
  本模块仅做"凭证装载 + 结果归一化为 JSON"。

核心 API：
- ``validate_tencent(env)`` / ``validate_trtc(env, deep=True)`` / ``validate_llm(env)``
  → 统一返回 ``ValidationResult`` dataclass，可 ``to_dict()`` 序列化为
    ``{ok, type, error, message, latency_ms}``。

安全约束（务必遵守）：
- 全过程**只从 .env / 进程 env 读取凭证**，不接受命令行参数明文传 Key。
- 输出 JSON 中**不包含**凭证原文；error 字段只放错误码 / 简短消息。
- 调用方（CLI / AI）应将 stdout 视为可解析 JSON，不在终端显式回显 Key。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# 1) 加载 conversation-core 的凭证 / 健康检查模块
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
_CORE_DIR = _ROOT / "capabilities" / "conversation-core"

if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

# 延迟导入：供 verify-credentials.py 在 .env 已加载之后调用
def _imports():
    from src.credentials import (  # type: ignore  # noqa: WPS433
        LlmCredential,
        TencentCloudCredential,
        TrtcCredential,
        load_from_env,
    )
    from src.health import (  # type: ignore  # noqa: WPS433
        check_llm,
        check_tencent_cloud,
        check_trtc,
    )

    return {
        "LlmCredential": LlmCredential,
        "TencentCloudCredential": TencentCloudCredential,
        "TrtcCredential": TrtcCredential,
        "load_from_env": load_from_env,
        "check_llm": check_llm,
        "check_tencent_cloud": check_tencent_cloud,
        "check_trtc": check_trtc,
    }


# ---------------------------------------------------------------------------
# 2) 错误码 → AI 应答提示（与 SKILL.md §7.5 对照表对齐）
# ---------------------------------------------------------------------------
_ERROR_HINTS: Dict[str, str] = {
    "E001": "腾讯云 SecretId/SecretKey 验证失败（AuthFailure / 账号未开通 STS）。",
    "E002": "TRTC 应用凭据验证失败（SDKAppID 不属于本账号 / SDKSecretKey 不匹配）。",
    "E003": "LLM 验证失败（鉴权 401/403 或返回非 200）。",
    "E004": "网络不可达 / 超时（请检查代理 / 防火墙）。",
    "E000": "凭证未配置或为空。",
}


# ---------------------------------------------------------------------------
# 3) 统一返回结构
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    """单把 Key 的验证结果，序列化后即 verify-credentials.py 的 stdout JSON。"""

    ok: bool
    type: str  # "tencent" | "trtc" | "llm" | "all"
    error: str = ""           # 错误码（E000~E004 或空字符串）
    message: str = ""         # 人类可读说明（不含 Key 原文）
    latency_ms: int = 0

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok,
            "type": self.type,
            "error": self.error,
            "message": self.message,
            "latency_ms": self.latency_ms,
        }


@dataclass
class BatchResult:
    """整体验证结果（type=all 时使用）。"""

    ok: bool
    items: List[ValidationResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "ok": self.ok,
            "type": "all",
            "items": [r.to_dict() for r in self.items],
        }


# ---------------------------------------------------------------------------
# 4) .env 加载（独立于 dotenv，避免引入额外依赖）
# ---------------------------------------------------------------------------
def load_dotenv(env_path: Optional[Path] = None) -> Dict[str, str]:
    """读 ``.env`` 到 ``os.environ``，返回新增/覆盖的键值对。

    路径优先级：参数 > capabilities/conversation-core/.env > 仓库根 .env。
    不抛异常；找不到文件时返回空字典。
    """
    candidates: List[Path] = []
    if env_path is not None:
        candidates.append(Path(env_path))
    candidates.append(_CORE_DIR / ".env")
    candidates.append(_ROOT / ".env")

    seen: Dict[str, str] = {}
    for c in candidates:
        if not c.exists() or not c.is_file():
            continue
        try:
            text = c.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in seen:
                seen[k] = v
                # 不覆盖已存在的进程级环境变量（CI / 容器优先）
                os.environ.setdefault(k, v)
        # 找到第一个就够；不再往下找以避免覆盖
        if seen:
            break
    return seen


# ---------------------------------------------------------------------------
# 5) 单把 Key 验证函数
# ---------------------------------------------------------------------------
def validate_tencent() -> ValidationResult:
    """验证腾讯云 API SecretId/SecretKey。"""
    mods = _imports()
    creds = mods["load_from_env"]()
    tc = creds.tencent_cloud
    if not tc.configured:
        return ValidationResult(
            ok=False,
            type="tencent",
            error="E000",
            message="TENCENT_CLOUD_SECRET_ID / TENCENT_CLOUD_SECRET_KEY 未配置",
        )
    r = mods["check_tencent_cloud"](tc)
    return ValidationResult(
        ok=r.ok,
        type="tencent",
        error="" if r.ok else (r.error_code or "E001"),
        message=r.detail if not r.ok else f"sts/GetFederationToken ok (region={tc.region})",
        latency_ms=r.latency_ms,
    )


def validate_trtc(deep: bool = True) -> ValidationResult:
    """验证 TRTC SDKAppId / SDKSecretKey。

    deep=True 时若腾讯云 API 凭据已配置，会调用 ``DescribeTRTCRealTimeQualityData``
    做归属校验；否则仅做本地 UserSig 自洽检查。
    """
    mods = _imports()
    creds = mods["load_from_env"]()
    trtc = creds.trtc
    tc = creds.tencent_cloud if deep else None
    if not trtc.configured:
        return ValidationResult(
            ok=False,
            type="trtc",
            error="E000",
            message="TRTC_SDK_APP_ID / TRTC_SDK_SECRET_KEY 未配置",
        )
    r = mods["check_trtc"](trtc, tencent=tc if (tc and tc.configured) else None)
    return ValidationResult(
        ok=r.ok,
        type="trtc",
        error="" if r.ok else (r.error_code or "E002"),
        message=r.detail or ("usersig/openapi ok" if r.ok else "trtc check failed"),
        latency_ms=r.latency_ms,
    )


def validate_llm() -> ValidationResult:
    """验证 LLM API Key（OpenAI 兼容协议）。"""
    mods = _imports()
    creds = mods["load_from_env"]()
    llm = creds.llm
    if not llm.configured:
        return ValidationResult(
            ok=False,
            type="llm",
            error="E000",
            message="LLM_API_KEY / LLM_API_URL / LLM_MODEL 未配置",
        )
    r = mods["check_llm"](llm)
    return ValidationResult(
        ok=r.ok,
        type="llm",
        error="" if r.ok else (r.error_code or "E003"),
        message=r.detail or (f"chat/completions 200 ok (model={llm.model})" if r.ok else "llm failed"),
        latency_ms=r.latency_ms,
    )


def validate_all() -> BatchResult:
    """依次验证三把 Key；任一失败 → ok=False。"""
    items = [validate_tencent(), validate_trtc(deep=True), validate_llm()]
    return BatchResult(ok=all(i.ok for i in items), items=items)


# ---------------------------------------------------------------------------
# 6) 错误码 → 提示（供 CLI 在非 --json 模式下打印，AI 不读这段）
# ---------------------------------------------------------------------------
def hint(error_code: str) -> str:
    return _ERROR_HINTS.get(error_code, "")


# ---------------------------------------------------------------------------
# 7) 自检：让 `python -m scripts.lib.credential_validators` 可独立运行
# ---------------------------------------------------------------------------
def _self_test() -> int:
    load_dotenv()
    out = validate_all()
    print(json.dumps(out.to_dict(), ensure_ascii=False, indent=2))
    return 0 if out.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_self_test())
