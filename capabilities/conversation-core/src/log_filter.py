"""日志脱敏过滤器（P0 安全项落地）。

按 manifest.yaml security.log_redaction.patterns 中声明的关键词，
对凭证字段在日志记录前执行不可逆掩码处理。
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

# 默认匹配的敏感字段名（与 manifest.yaml security.log_redaction.patterns 对齐）
_DEFAULT_PATTERNS = (
    "secret_id",
    "secret_key",
    "api_key",
    "app_key",
    "token",
    "usersig",
    "credential",
    "authorization",
)


def _build_regex(patterns: Iterable[str]) -> re.Pattern[str]:
    # 命中 key=value / "key": "value" / key: value 三种常见格式
    keys = "|".join(re.escape(p) for p in patterns)
    pattern = (
        r"(?i)(?P<key>" + keys + r")"
        r"(?P<sep>\s*[:=]\s*\"?)"
        r"(?P<val>[A-Za-z0-9_\-\.\+/=]{4,})"
    )
    return re.compile(pattern)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


class RedactingFilter(logging.Filter):
    """对日志 message / args 中的敏感字段执行掩码。"""

    def __init__(self, patterns: Iterable[str] = _DEFAULT_PATTERNS) -> None:
        super().__init__()
        self._regex = _build_regex(patterns)

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = self._regex.sub(
                    lambda m: f"{m.group('key')}{m.group('sep')}{_mask(m.group('val'))}",
                    record.msg,
                )
            if record.args:
                record.args = tuple(
                    self._regex.sub(
                        lambda m: f"{m.group('key')}{m.group('sep')}{_mask(m.group('val'))}",
                        str(a),
                    )
                    if isinstance(a, str)
                    else a
                    for a in record.args
                )
        except Exception:  # 脱敏失败不能影响日志主流程
            pass
        return True


def install_redacting_filter(logger: logging.Logger | None = None) -> None:
    """将脱敏过滤器挂载到指定 Logger（默认根 Logger）。"""
    target = logger or logging.getLogger()
    if any(isinstance(f, RedactingFilter) for f in target.filters):
        return
    target.addFilter(RedactingFilter())
