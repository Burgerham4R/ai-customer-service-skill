"""adapter 工厂：根据环境变量挑选 KnowledgeBaseClient 实现。

环境变量 `KB_ADAPTER`：
    local_json    默认本地 JSON 文件检索（生产可用，零依赖）
    mock          内置示例 FAQ（用于 Recipe 录视频）
    default_rest  按 business_contract 默认契约调用远程 FAQ 服务
    user_custom   用户接入向导生成的实现

未设置或值非法时，回退到 local_json（保留与 Phase 2 的行为兼容）。
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from ..ports.kb_client import KnowledgeBaseClient


logger = logging.getLogger(__name__)


_VALID = ("local_json", "mock", "default_rest", "user_custom")


def _build(name: str) -> Optional[KnowledgeBaseClient]:
    if name == "local_json":
        from .local_json import from_env as build_local
        return build_local()
    if name == "mock":
        from .mock import from_env as build_mock
        return build_mock()
    if name == "default_rest":
        from .default_rest import from_env as build_rest
        c = build_rest()
        if c is None:
            logger.warning(
                "KB_ADAPTER=default_rest but KB_REST_BASE_URL is empty; "
                "falling back to local_json"
            )
        return c
    if name == "user_custom":
        try:
            from .user_custom import from_env as build_custom  # type: ignore
        except ImportError:
            logger.warning(
                "KB_ADAPTER=user_custom but src/adapters/user_custom.py is missing; "
                "run scripts/contract-adapt.py knowledge-base to generate it"
            )
            return None
        return build_custom()
    return None


def build_default() -> KnowledgeBaseClient:
    name = (os.getenv("KB_ADAPTER") or "local_json").strip().lower()
    if name not in _VALID:
        logger.warning("KB_ADAPTER=%s is not recognised; using local_json", name)
        name = "local_json"
    client = _build(name)
    if client is None:
        from .local_json import from_env as build_local
        client = build_local()
    return client


# ---------------------------------------------------------------------------
_singleton: Optional[KnowledgeBaseClient] = None


def get_client() -> KnowledgeBaseClient:
    global _singleton
    if _singleton is None:
        _singleton = build_default()
    return _singleton


def set_client(client: KnowledgeBaseClient) -> None:
    """仅供测试用：注入自定义 client。"""
    global _singleton
    _singleton = client


def reset_client() -> None:
    global _singleton
    _singleton = None
