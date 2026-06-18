"""capabilities 命名空间根。

子目录为短横线命名（manifest 风格），但 Python 模块需用下划线命名，
本文件在导入时按需建立别名（仅当对应目录存在）。

例如：
    capabilities.knowledge-base/  →  import capabilities.knowledge_base
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

# 短横线目录 → 下划线模块别名
_ALIASES = {
    "knowledge-base": "knowledge_base",
    "tool-calling": "tool_calling",
    "human-handoff": "human_handoff",
    "session-summary": "session_summary",
    "digital-human": "digital_human",
}


def _install_alias(dirname: str, modname: str) -> None:
    full_dir = _ROOT / dirname
    if not full_dir.exists():
        return
    full_name = f"{__name__}.{modname}"
    if full_name in sys.modules:
        return
    # 注册一个可被子模块继续 import 的命名空间包
    import types

    pkg = types.ModuleType(full_name)
    pkg.__path__ = [str(full_dir)]  # type: ignore[attr-defined]
    sys.modules[full_name] = pkg


for _d, _m in _ALIASES.items():
    _install_alias(_d, _m)
