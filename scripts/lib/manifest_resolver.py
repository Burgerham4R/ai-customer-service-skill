"""能力包 manifest 加载 / 依赖图 / 拓扑排序 / 循环依赖检测。

对应风险：
- P1 manifest 依赖解析边界未覆盖：通过拓扑排序检测循环依赖；
  semver 主版本不兼容时阻止安装。

约定：
- 每个能力包目录下必须有 ``manifest.yaml``。
- ``type`` 字段为 ``skeleton`` | ``capability``，骨架包必须存在且唯一。
- ``dependencies`` 元素形如 ``{name: conversation-core, version: ">=1.0.0,<2.0.0"}``。
- ``injection_points`` 与 ``extensions[*].inject_at`` 通过 ``id`` 字段对齐。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------
class ManifestError(RuntimeError):
    """manifest 加载或校验失败。"""


class CircularDependencyError(ManifestError):
    """检测到循环依赖。"""


class VersionConflictError(ManifestError):
    """semver 主版本不兼容。"""


class UnknownInjectionPointError(ManifestError):
    """能力包引用了骨架未声明的注入点。"""


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DependencySpec:
    name: str
    version: str = "*"  # semver range，如 ">=1.0.0,<2.0.0"


@dataclass
class Manifest:
    name: str
    version: str
    type: str  # skeleton | capability
    description: str = ""
    dependencies: List[DependencySpec] = field(default_factory=list)
    injection_points: List[Dict] = field(default_factory=list)
    extensions: List[Dict] = field(default_factory=list)
    config: Dict = field(default_factory=dict)
    integration: Dict = field(default_factory=dict)
    security: Dict = field(default_factory=dict)
    endpoints: List[Dict] = field(default_factory=list)
    path: Optional[Path] = None  # 加载时回填

    @property
    def is_skeleton(self) -> bool:
        return self.type == "skeleton"


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------
def _coerce_dep(raw) -> DependencySpec:
    if isinstance(raw, str):
        return DependencySpec(name=raw)
    if isinstance(raw, dict):
        if "name" not in raw:
            raise ManifestError(f"dependency missing 'name': {raw}")
        return DependencySpec(name=raw["name"], version=str(raw.get("version", "*")))
    raise ManifestError(f"unsupported dependency form: {raw!r}")


def load_manifest(manifest_path: Path) -> Manifest:
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ManifestError(f"{manifest_path}: top-level must be mapping")
    for key in ("name", "version", "type"):
        if key not in raw:
            raise ManifestError(f"{manifest_path}: missing required field '{key}'")
    if raw["type"] not in ("skeleton", "capability"):
        raise ManifestError(
            f"{manifest_path}: invalid type '{raw['type']}', expected skeleton|capability"
        )
    deps = [_coerce_dep(d) for d in (raw.get("dependencies") or [])]
    return Manifest(
        name=str(raw["name"]),
        version=str(raw["version"]),
        type=str(raw["type"]),
        description=str(raw.get("description", "")),
        dependencies=deps,
        injection_points=list(raw.get("injection_points") or []),
        extensions=list(raw.get("extensions") or []),
        config=dict(raw.get("config") or {}),
        integration=dict(raw.get("integration") or {}),
        security=dict(raw.get("security") or {}),
        endpoints=list(raw.get("endpoints") or []),
        path=manifest_path,
    )


def discover_manifests(capabilities_root: Path) -> List[Manifest]:
    """扫描 capabilities/ 下的所有能力包 manifest。"""
    manifests: List[Manifest] = []
    if not capabilities_root.exists():
        return manifests
    for child in sorted(capabilities_root.iterdir()):
        if not child.is_dir():
            continue
        mf = child / "manifest.yaml"
        if mf.exists():
            manifests.append(load_manifest(mf))
    return manifests


# ---------------------------------------------------------------------------
# semver 兼容性
# ---------------------------------------------------------------------------
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _parse_version(v: str) -> Tuple[int, int, int]:
    m = _SEMVER_RE.match(v.strip())
    if not m:
        raise ManifestError(f"invalid semver: {v!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


_RANGE_RE = re.compile(r"^\s*(>=|<=|>|<|=|\^|~)?\s*(\d+(?:\.\d+){0,2})\s*$")


def _check_single(actual: Tuple[int, int, int], spec: str) -> bool:
    spec = spec.strip()
    if spec in ("", "*"):
        return True
    m = _RANGE_RE.match(spec)
    if not m:
        # 无法解析的范围视为通过（保守策略，记录于日志由调用方负责）
        return True
    op = m.group(1) or "="
    parts = [int(p) for p in m.group(2).split(".")]
    while len(parts) < 3:
        parts.append(0)
    target = (parts[0], parts[1], parts[2])
    if op == "=":
        return actual == target
    if op == ">":
        return actual > target
    if op == ">=":
        return actual >= target
    if op == "<":
        return actual < target
    if op == "<=":
        return actual <= target
    if op == "^":  # 主版本兼容
        return actual >= target and actual[0] == target[0]
    if op == "~":  # 次版本兼容
        return actual >= target and actual[:2] == target[:2]
    return True


def satisfies(actual_version: str, spec: str) -> bool:
    """判断 actual 是否落入 spec（支持 ',' 拼接的 AND 关系）。"""
    if not spec or spec == "*":
        return True
    actual = _parse_version(actual_version)
    return all(_check_single(actual, part) for part in spec.split(","))


# ---------------------------------------------------------------------------
# 拓扑排序 / 循环依赖检测
# ---------------------------------------------------------------------------
@dataclass
class ResolvedGraph:
    order: List[str]               # 拓扑序后的能力包名列表
    manifests: Dict[str, Manifest]
    skeleton: Manifest


def resolve(manifests: Sequence[Manifest]) -> ResolvedGraph:
    """构建依赖图、校验版本兼容并返回拓扑序。

    Raises
    ------
    ManifestError
        无骨架 / 多个骨架 / 引用未知能力包 / 版本不兼容。
    CircularDependencyError
        检测到环。
    """
    # 1) 唯一性 + 骨架定位
    by_name: Dict[str, Manifest] = {}
    for m in manifests:
        if m.name in by_name:
            raise ManifestError(f"duplicate capability name: {m.name}")
        by_name[m.name] = m
    skeletons = [m for m in manifests if m.is_skeleton]
    if len(skeletons) == 0:
        raise ManifestError("no skeleton capability found (expected conversation-core)")
    if len(skeletons) > 1:
        raise ManifestError(
            f"multiple skeleton capabilities found: {[s.name for s in skeletons]}"
        )
    skeleton = skeletons[0]

    # 2) 引用 + 版本校验
    for m in manifests:
        for dep in m.dependencies:
            if dep.name not in by_name:
                raise ManifestError(
                    f"{m.name} depends on unknown capability '{dep.name}'"
                )
            target = by_name[dep.name]
            if not satisfies(target.version, dep.version):
                raise VersionConflictError(
                    f"{m.name} requires {dep.name}@{dep.version} but found "
                    f"{target.version}"
                )

    # 3) 注入点引用校验（仅校验注入到骨架的）
    skeleton_ids = {p.get("id") for p in skeleton.injection_points if p.get("id")}
    for m in manifests:
        for ext in m.extensions:
            inject_id = ext.get("inject_at")
            if not inject_id:
                continue
            # 允许引用其他能力包暴露的注入点（前缀 cap:能力名/注入点id）
            if ":" in inject_id:
                continue
            if inject_id not in skeleton_ids:
                raise UnknownInjectionPointError(
                    f"{m.name} references unknown injection point '{inject_id}' "
                    f"(skeleton declares: {sorted(skeleton_ids)})"
                )

    # 4) 拓扑排序（Kahn 算法）
    indeg: Dict[str, int] = {n: 0 for n in by_name}
    adj: Dict[str, List[str]] = {n: [] for n in by_name}
    for m in manifests:
        for dep in m.dependencies:
            adj[dep.name].append(m.name)
            indeg[m.name] += 1
    queue = sorted([n for n, d in indeg.items() if d == 0])
    order: List[str] = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for nxt in sorted(adj[n]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(by_name):
        remaining = [n for n, d in indeg.items() if d > 0]
        raise CircularDependencyError(
            f"circular dependency detected among: {remaining}"
        )

    # 骨架必须排在最前
    if skeleton.name not in order or order[0] != skeleton.name:
        order = [skeleton.name] + [n for n in order if n != skeleton.name]
    return ResolvedGraph(order=order, manifests=by_name, skeleton=skeleton)


# ---------------------------------------------------------------------------
# 工具：导出依赖图 DOT
# ---------------------------------------------------------------------------
def to_dot(graph: ResolvedGraph) -> str:
    lines = ["digraph capabilities {", "  rankdir=LR;"]
    for name, mf in graph.manifests.items():
        shape = "box" if mf.is_skeleton else "ellipse"
        lines.append(f'  "{name}" [shape={shape}, label="{name}\\n{mf.version}"];')
    for name, mf in graph.manifests.items():
        for dep in mf.dependencies:
            lines.append(f'  "{name}" -> "{dep.name}";')
    lines.append("}")
    return "\n".join(lines)
