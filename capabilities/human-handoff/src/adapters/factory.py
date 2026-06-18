"""adapter 工厂：根据环境变量挑选 HandoffClient 实现。

环境变量 `HH_ADAPTER`：
    local_queue   默认本地内存队列（生产可用，零依赖）
    mock          演示数据（包含若干预置工单，用于录视频）
    default_rest  按 business_contract 默认契约调用远程工单系统
    user_custom   用户接入向导（contract-adapt.py）生成的实现

未设置或值非法时，回退到 local_queue（保留与 Phase 2 的行为兼容）。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from ..ports.handoff_client import HandoffClient


logger = logging.getLogger(__name__)


_VALID = ("local_queue", "mock", "default_rest", "user_custom")


def _build(name: str) -> Optional[HandoffClient]:
    if name == "local_queue":
        from .local_queue import from_env as build_local
        return build_local()
    if name == "mock":
        from .mock import from_env as build_mock
        return build_mock()
    if name == "default_rest":
        from .default_rest import from_env as build_rest
        c = build_rest()
        if c is None:
            logger.warning(
                "HH_ADAPTER=default_rest but HH_REST_BASE_URL is empty; "
                "falling back to local_queue"
            )
        return c
    if name == "user_custom":
        try:
            from .user_custom import from_env as build_custom  # type: ignore
        except ImportError:
            logger.warning(
                "HH_ADAPTER=user_custom but src/adapters/user_custom.py is missing; "
                "run scripts/contract-adapt.py human-handoff to generate it"
            )
            return None
        return build_custom()
    return None


def build_default() -> HandoffClient:
    """按环境变量构建默认 client；非法配置回落到 local_queue。"""
    name = (os.getenv("HH_ADAPTER") or "local_queue").strip().lower()
    if name not in _VALID:
        logger.warning("HH_ADAPTER=%s is not recognised; using local_queue", name)
        name = "local_queue"
    client = _build(name)
    if client is None:
        from .local_queue import from_env as build_local
        client = build_local()
    return client


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_singleton: Optional[HandoffClient] = None


def get_client() -> HandoffClient:
    global _singleton
    if _singleton is None:
        _singleton = build_default()
    return _singleton


def set_client(client: HandoffClient) -> None:
    """仅供测试用：注入自定义 client。"""
    global _singleton
    _singleton = client


def reset_client() -> None:
    global _singleton
    _singleton = None
