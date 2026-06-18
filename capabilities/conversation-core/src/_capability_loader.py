"""兄弟能力包动态加载器（与 cwd / 仓库目录名 / 连字符无关）。

为什么需要这个模块？
====================
能力包目录命名采用连字符（如 ``knowledge-base``、``human-handoff``），
而 Python ``import`` 语法不能识别连字符。再加上 ``start.sh`` 进程的
工作目录是 ``capabilities/conversation-core/``，项目根并不在
``sys.path`` 中。因此 manifest.yaml 中那种::

    from capabilities.knowledge_base.src.retriever import attach_faq_to_instructions

的写法**永远不会工作**——它隐含假设了：
1. 目录名是下划线（实际是连字符）；
2. 项目根在 ``sys.path``（实际不在）。

本模块通过 ``importlib.util`` 把每一层目录主动注册为合法 Python 包，
绕过包名限制；项目根通过 ``__file__`` 反推得到，因此**仓库目录被任意
改名也不影响**。子模块内的 ``from .x import y`` 等相对导入也能正常工作。

用法
----
    from ._capability_loader import load_capability

    retriever = load_capability("knowledge-base", "src/retriever.py")
    new_text = retriever.attach_faq_to_instructions(text)

    router_mod = load_capability("knowledge-base", "src/router.py")
    app.include_router(router_mod.router, prefix="/api/v1/kb")
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径解析：__file__ 反推 repo_root，不依赖 cwd / 仓库目录名
# 该文件位于 <repo_root>/capabilities/conversation-core/src/_capability_loader.py
# parents[3] = <repo_root>
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
_CAPABILITIES_ROOT = _REPO_ROOT / "capabilities"

_CAPS_NAMESPACE = "_capabilities"

_lock = RLock()
_module_cache: dict[str, ModuleType] = {}


def repo_root() -> Path:
    """返回仓库根目录（含 ``capabilities/`` 子目录的那一层）。"""
    return _REPO_ROOT


def capabilities_root() -> Path:
    return _CAPABILITIES_ROOT


def _safe_name(part: str) -> str:
    """把目录段转成合法 Python identifier（连字符 → 下划线）。"""
    return part.replace("-", "_")


def _ensure_namespace_root() -> ModuleType:
    """注册 ``_capabilities`` 顶层命名空间包到 ``sys.modules``。"""
    mod = sys.modules.get(_CAPS_NAMESPACE)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_loader(_CAPS_NAMESPACE, loader=None, is_package=True)
    if spec is None:
        raise RuntimeError("failed to build namespace spec")
    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [str(_CAPABILITIES_ROOT)]  # 让 importlib 能在该目录下查找子包
    sys.modules[_CAPS_NAMESPACE] = mod
    return mod


def _ensure_package(qualified_name: str, dir_path: Path) -> ModuleType:
    """把 ``dir_path`` 注册为名为 ``qualified_name`` 的 Python 包。

    若同名 ``__init__.py`` 存在则正常 exec，否则按命名空间包处理。
    幂等：已在 ``sys.modules`` 中则直接返回。
    """
    cached = sys.modules.get(qualified_name)
    if cached is not None:
        return cached

    init_file = dir_path / "__init__.py"
    if init_file.is_file():
        spec = importlib.util.spec_from_file_location(
            qualified_name,
            init_file,
            submodule_search_locations=[str(dir_path)],
        )
    else:
        spec = importlib.util.spec_from_loader(qualified_name, loader=None, is_package=True)
    if spec is None:
        raise ModuleNotFoundError(f"failed to build spec for package: {qualified_name}")

    pkg = importlib.util.module_from_spec(spec)
    if not hasattr(pkg, "__path__"):
        pkg.__path__ = [str(dir_path)]  # type: ignore[attr-defined]
    sys.modules[qualified_name] = pkg

    if init_file.is_file() and spec.loader is not None:
        try:
            spec.loader.exec_module(pkg)
        except Exception:
            sys.modules.pop(qualified_name, None)
            raise
    return pkg


def load_capability(cap_name: str, module_rel: str) -> ModuleType:
    """加载指定能力包下的某个 Python 文件并返回 module 对象。

    Parameters
    ----------
    cap_name
        能力包目录名，例如 ``"knowledge-base"``（带连字符）。
    module_rel
        相对能力包根的 Python 文件路径，例如 ``"src/retriever.py"``。

    Returns
    -------
    ModuleType
        已执行的模块对象。失败时抛出 :class:`ModuleNotFoundError`。

    备注
    ----
    - 进程内缓存：相同 ``(cap_name, module_rel)`` 仅加载一次。
    - 模块完整名形如 ``_capabilities.<cap_safe>.<dir>.<basename>``，
      因此能力包内部 ``from .x import y`` 等相对导入可以正常工作。
    """
    cache_key = f"{cap_name}::{module_rel}"
    with _lock:
        cached = _module_cache.get(cache_key)
        if cached is not None:
            return cached

    cap_dir = _CAPABILITIES_ROOT / cap_name
    file_path = cap_dir / module_rel
    if not file_path.is_file():
        raise ModuleNotFoundError(
            f"capability '{cap_name}' module '{module_rel}' not found at {file_path}"
        )

    # 1) 顶层命名空间 _capabilities.*
    _ensure_namespace_root()

    # 2) 能力包包名 _capabilities.<cap_safe>
    cap_safe = _safe_name(cap_name)
    cap_qual = f"{_CAPS_NAMESPACE}.{cap_safe}"
    _ensure_package(cap_qual, cap_dir)

    # 3) 中间目录每一层都注册为子包
    rel_parts = Path(module_rel).parts
    *dir_parts, leaf = rel_parts
    parent_qual = cap_qual
    parent_dir = cap_dir
    for part in dir_parts:
        parent_dir = parent_dir / part
        parent_qual = f"{parent_qual}.{_safe_name(part)}"
        _ensure_package(parent_qual, parent_dir)

    # 4) 叶子模块加载
    leaf_basename = Path(leaf).stem
    leaf_qual = f"{parent_qual}.{_safe_name(leaf_basename)}"

    cached_leaf = sys.modules.get(leaf_qual)
    if cached_leaf is not None:
        with _lock:
            _module_cache[cache_key] = cached_leaf
        return cached_leaf

    spec = importlib.util.spec_from_file_location(leaf_qual, file_path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            f"failed to build spec for capability '{cap_name}' / '{module_rel}'"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[leaf_qual] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(leaf_qual, None)
        raise

    with _lock:
        _module_cache[cache_key] = module
    logger.debug("capability loaded: %s -> %s", leaf_qual, file_path)
    return module


def try_load_capability(
    cap_name: str, module_rel: str
) -> Optional[ModuleType]:
    """与 :func:`load_capability` 相同，但失败时返回 ``None`` 而不抛异常。

    适合"能力包可选安装"的场景：找不到时静默降级，不影响骨架运行。
    """
    try:
        return load_capability(cap_name, module_rel)
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "capability '%s' module '%s' not loaded (skipped): %s",
            cap_name, module_rel, exc,
        )
        return None
