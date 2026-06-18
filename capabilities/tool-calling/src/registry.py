"""ToolRegistry 加载器。

YAML 声明示例：
    priority: alpha            # alpha | beta | manifest_order
    tools:
      - name: get_order
        alpha:
          module: "capabilities.tool_calling.examples.local_tools"
          function: "get_order"
          timeout_ms: 800
        beta:
          endpoint: "https://internal.example.com/api/orders"
          method: "POST"
          timeout_ms: 5000
        description: "查询订单"

加载策略：
- α 轨函数通过 ``importlib`` 动态加载；模块缺失时该工具仅保留 β 轨。
- β 轨为纯声明，调用由 dispatcher 注入 ``beta_invoker`` 完成。
"""
from __future__ import annotations

import importlib
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# 通过相对路径引入仲裁器（Phase 2 共享基础设施）
import sys
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.lib.arbitrator import (  # noqa: E402
    AlphaTool,
    BetaTool,
    ToolCallResult,
    ToolRegistry,
)

logger = logging.getLogger(__name__)

_DEFAULT_REGISTRY_FILE = Path(
    os.getenv(
        "TC_REGISTRY_FILE",
        str(Path(__file__).resolve().parent.parent / "data" / "tools.yaml"),
    )
)


class ToolRegistryLoader:
    def __init__(self, registry_file: Optional[Path] = None) -> None:
        self._lock = threading.RLock()
        self._registry_file = Path(registry_file) if registry_file else _DEFAULT_REGISTRY_FILE
        self._registry: ToolRegistry = ToolRegistry()
        self._descriptions: Dict[str, str] = {}
        if self._registry_file.exists():
            self.reload()

    @property
    def registry(self) -> ToolRegistry:
        with self._lock:
            return self._registry

    def reload(self) -> int:
        if not self._registry_file.exists():
            return 0
        raw = yaml.safe_load(self._registry_file.read_text(encoding="utf-8")) or {}
        priority = (raw.get("priority") or "alpha").strip()
        new_reg = ToolRegistry(default_priority=priority)
        descriptions: Dict[str, str] = {}
        for tool_def in raw.get("tools") or []:
            name = str(tool_def.get("name") or "").strip()
            if not name:
                continue
            descriptions[name] = str(tool_def.get("description", ""))
            alpha_def = tool_def.get("alpha")
            beta_def = tool_def.get("beta")
            if alpha_def:
                func = self._load_callable(alpha_def)
                if func is not None:
                    new_reg.register_alpha(
                        AlphaTool(
                            name=name,
                            func=func,
                            timeout_ms=int(alpha_def.get("timeout_ms", 1000)),
                            description=descriptions[name],
                        )
                    )
            if beta_def and beta_def.get("endpoint"):
                new_reg.register_beta(
                    BetaTool(
                        name=name,
                        endpoint=str(beta_def["endpoint"]),
                        method=str(beta_def.get("method", "POST")),
                        timeout_ms=int(beta_def.get("timeout_ms", 5000)),
                        headers=dict(beta_def.get("headers") or {}),
                        description=descriptions[name],
                    )
                )
        with self._lock:
            self._registry = new_reg
            self._descriptions = descriptions
        return len(descriptions)

    def list_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._registry.list_tools()

    def call(
        self,
        name: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        priority: Optional[str] = None,
    ) -> ToolCallResult:
        return self._registry.call(
            name,
            params,
            priority=priority,
            beta_invoker=_default_beta_invoker,
        )

    @staticmethod
    def _load_callable(alpha_def: Dict[str, Any]):
        mod_name = alpha_def.get("module")
        func_name = alpha_def.get("function")
        if not mod_name or not func_name:
            return None
        module = None
        try:
            module = importlib.import_module(mod_name)
        except ImportError:
            # 兜底：能力包目录名是连字符（tool-calling），标准 import 解析不到
            # capabilities.tool_calling.* —— 改为按文件路径加载（registry 知道自身位置）。
            module = ToolRegistryLoader._load_module_by_path(mod_name)
        if module is None:
            logger.warning("alpha tool module not loadable: %s", mod_name)
            return None
        return getattr(module, func_name, None)

    @staticmethod
    def _load_module_by_path(mod_name: str):
        """把点分模块名映射到能力包内文件路径并加载。

        约定：模块名形如 ``capabilities.tool_calling.examples.local_tools``，
        取 ``examples`` 段及之后部分作为相对 ``<capability_root>`` 的路径。
        """
        import importlib.util

        cap_root = Path(__file__).resolve().parent.parent  # capabilities/tool-calling/
        parts = mod_name.split(".")
        # 去掉前缀 capabilities.<cap>（无论下划线 / 连字符），保留 examples/... 尾部
        tail: List[str] = []
        seen_examples = False
        for p in parts:
            if p == "examples":
                seen_examples = True
            if seen_examples:
                tail.append(p)
        if not tail:
            tail = parts[-2:]  # 退而求其次：取最后两段
        file_path = cap_root.joinpath(*tail).with_suffix(".py")
        if not file_path.is_file():
            return None
        qual = "_tc_local_" + "_".join(tail)
        cached = sys.modules.get(qual)
        if cached is not None:
            return cached
        spec = importlib.util.spec_from_file_location(qual, file_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[qual] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            sys.modules.pop(qual, None)
            logger.warning("alpha tool file load failed %s: %s", file_path, exc)
            return None
        return module


# ---------------------------------------------------------------------------
# β 轨默认实现：requests 同步 POST / GET
# ---------------------------------------------------------------------------
def _default_beta_invoker(tool: BetaTool, params: Dict[str, Any]) -> Any:
    import requests  # 已在骨架 requirements 中

    if not tool.endpoint.startswith("https://") and not tool.endpoint.startswith("http://localhost"):
        # 安全：除本机调试外，β 轨强制 HTTPS（manifest.security.network.enforce_https）
        raise RuntimeError(f"β endpoint must use HTTPS: {tool.endpoint}")
    headers = {"Content-Type": "application/json", **tool.headers}
    timeout = max(tool.timeout_ms, 100) / 1000.0
    method = tool.method.upper()
    if method == "GET":
        resp = requests.get(tool.endpoint, params=params, headers=headers, timeout=timeout)
    else:
        resp = requests.request(
            method, tool.endpoint, json=params, headers=headers, timeout=timeout
        )
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "")
    if "application/json" in ctype:
        return resp.json()
    return resp.text


# ---------------------------------------------------------------------------
# 全局单例（供 dispatcher / router 引用）
# ---------------------------------------------------------------------------
_global_loader = ToolRegistryLoader()


def get_loader() -> ToolRegistryLoader:
    return _global_loader
