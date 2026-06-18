"""写回 sink 工厂 —— 按 env SS_ADAPTER 选择实现（与 KB/handoff factory 范式一致）。

    SS_ADAPTER=mock         默认；无外部依赖
    SS_ADAPTER=local_json   写本地 JSONL
    SS_ADAPTER=default_rest  POST 到真实 CRM（需 SS_REST_BASE_URL）

任意实现初始化失败（如 default_rest 缺 base_url）时，安全降级回 mock，
保证 finalize 流程永不因写回目标不可用而中断。
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from .base import SummarySink
from .mock import MockSink

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_instance: Optional[SummarySink] = None
_instance_key: Optional[str] = None


def _build(name: str) -> SummarySink:
    name = (name or "mock").strip().lower()
    if name == "local_json":
        from .local_json import LocalJsonSink
        return LocalJsonSink()
    if name == "default_rest":
        from .default_rest import DefaultRestSink
        return DefaultRestSink()
    return MockSink()


def get_sink() -> SummarySink:
    """返回当前配置的写回 sink（按 SS_ADAPTER 缓存；env 变化时重建）。"""
    global _instance, _instance_key
    key = (os.getenv("SS_ADAPTER", "mock") or "mock").strip().lower()
    with _lock:
        if _instance is not None and _instance_key == key:
            return _instance
        try:
            _instance = _build(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("session-summary sink '%s' init failed, fallback to mock: %s", key, exc)
            _instance = MockSink()
        _instance_key = key
        return _instance
