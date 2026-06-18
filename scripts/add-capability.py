#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""能力包叠加 CLI。

用法
----
    # 列出已发现的能力包及拓扑序
    python scripts/add-capability.py --list

    # 添加能力包到当前项目（默认在 conversation-core 内注入扩展）
    python scripts/add-capability.py knowledge-base
    python scripts/add-capability.py knowledge-base tool-calling --dry-run

    # 在外部用户项目中渲染前端 / 后端适配器
    python scripts/add-capability.py knowledge-base \
        --target-project /path/to/user/repo \
        --tech-stack react

    # 输出能力包依赖图（DOT）
    python scripts/add-capability.py --graph

行为
----
1. 扫描 capabilities/ 下全部 manifest，校验拓扑序、循环依赖、版本兼容
2. 对要安装的能力包执行 manifest.extensions 注入到骨架（默认 dry-run）
3. 若 --target-project 提供，按 tech_stack 检测结果调用 auto_adapters 三级降级渲染
4. 输出诊断 JSON，便于 Agent 解析
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from scripts.lib import manifest_resolver as mr
from scripts.lib import stack_detector as sd
from scripts.lib import degrader as dg
from scripts.lib import injector as ij


CAPS_ROOT = _ROOT / "capabilities"
ADAPTERS_ROOT = _ROOT / "auto_adapters"
SKELETON_NAME = "conversation-core"


# ---------------------------------------------------------------------------
# 模板渲染
# ---------------------------------------------------------------------------
_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def render_template(text: str, variables: Dict[str, str]) -> str:
    def _sub(m: re.Match) -> str:
        return variables.get(m.group(1), m.group(0))

    return _VAR_RE.sub(_sub, text)


def load_yaml(path: Path) -> Dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# 安装 / 注入
# ---------------------------------------------------------------------------
@dataclass
class InstallReport:
    capability: str
    skeleton_injection: List[Dict[str, Any]]
    adapter: Optional[Dict[str, Any]] = None
    degrade: Optional[Dict[str, Any]] = None
    errors: List[str] = None         # type: ignore[assignment]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "skeleton_injection": self.skeleton_injection,
            "adapter": self.adapter,
            "degrade": self.degrade,
            "errors": self.errors or [],
        }


def inject_into_skeleton(
    skeleton: mr.Manifest,
    cap: mr.Manifest,
    *,
    dry_run: bool,
) -> List[Dict[str, Any]]:
    """把 cap.extensions 注入到骨架对应文件。"""
    skeleton_root = skeleton.path.parent if skeleton.path else CAPS_ROOT / SKELETON_NAME
    cap_root = cap.path.parent if cap.path else CAPS_ROOT / cap.name
    plans = ij.plan(
        skeleton_root,
        skeleton.injection_points,
        [(cap_root, cap.extensions)],
    )
    results = ij.apply_plans(plans, dry_run=dry_run)
    out = []
    for r in results:
        out.append(
            {
                "capability": cap.name,
                "inject_at": r.plan.extension.inject_at,
                "target": str(r.plan.target_abs_path.relative_to(_ROOT))
                if r.plan.target_abs_path.is_relative_to(_ROOT)
                else str(r.plan.target_abs_path),
                "op": r.plan.op,
                "anchor": r.plan.anchor,
                "applied": r.applied,
                "dry_run": r.dry_run,
                "error": r.error,
                "diff_preview": r.diff_preview[:200] if r.diff_preview else "",
            }
        )
    return out


def render_adapter(
    cap: mr.Manifest,
    target_project: Path,
    tech_stack: Optional[str],
    *,
    dry_run: bool,
) -> Dict[str, Any]:
    """对外部用户项目执行 auto_adapters 三级降级渲染。"""
    integration = cap.integration or {}
    auto_adapters = integration.get("auto_adapters") or []
    fallback = integration.get("fallback") or {}

    # 检测技术栈（若未传入则自动识别）
    detected = sd.detect(target_project) if not tech_stack else None
    primary = tech_stack or (detected.primary if detected else None)
    adapter_name = sd.match_adapter(primary or "", auto_adapters) if primary else None

    artifacts: List[Dict[str, Any]] = []
    code_gen_ok = False
    code_gen_error = ""

    if adapter_name:
        adapter_dir = ADAPTERS_ROOT / adapter_name
        if adapter_dir.exists():
            try:
                adapter_mf = load_yaml(adapter_dir / "manifest.yaml")
                tpl_def = (adapter_mf.get("templates") or {}).get(primary)
                if not tpl_def:
                    code_gen_error = f"adapter '{adapter_name}' has no template for '{primary}'"
                else:
                    variables = _merge_variables(adapter_mf, primary)
                    src_tpl = adapter_dir / tpl_def["file"]
                    target_path = Path(
                        render_template(tpl_def["target_path"], variables)
                    )
                    abs_target = target_project / target_path
                    rendered = render_template(
                        src_tpl.read_text(encoding="utf-8"), variables
                    )
                    if abs_target.exists() and not dry_run:
                        # 路径冲突 → 视为代码生成失败 → 降级 L2
                        code_gen_error = (
                            f"target file already exists: {abs_target}, refuse to overwrite"
                        )
                    else:
                        if not dry_run:
                            abs_target.parent.mkdir(parents=True, exist_ok=True)
                            abs_target.write_text(rendered, encoding="utf-8")
                        artifacts.append(
                            {
                                "type": "rendered_file",
                                "path": str(abs_target),
                                "size": len(rendered),
                                "dry_run": dry_run,
                            }
                        )
                        code_gen_ok = True
                        # 输出 install_hint
                        artifacts.append(
                            {
                                "type": "install_hint",
                                "content": tpl_def.get("install_hint", "").strip(),
                                "package_dependencies": tpl_def.get("package_dependencies") or [],
                            }
                        )
            except Exception as exc:  # noqa: BLE001
                code_gen_error = f"{type(exc).__name__}: {exc}"

    decision = dg.decide(
        primary, adapter_name, code_gen_ok,
        fallback=fallback,
        code_gen_error=code_gen_error,
    )

    return {
        "tech_stack_detected": detected.to_dict() if detected else None,
        "tech_stack_used": primary,
        "adapter": adapter_name,
        "artifacts": artifacts,
        "degrade": decision.to_dict(),
    }


def _merge_variables(adapter_mf: Dict[str, Any], tech_stack: str) -> Dict[str, str]:
    # 优先级：env > adapters/manifest.yaml.default_variables > adapter.defaults
    top = load_yaml(ADAPTERS_ROOT / "manifest.yaml")
    out = {}
    out.update(top.get("default_variables") or {})
    out.update(adapter_mf.get("defaults") or {})
    for k in list(out.keys()):
        if os.getenv(k):
            out[k] = os.getenv(k, "")
    # 强制类型为 str
    return {k: str(v) for k, v in out.items()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_list() -> Dict[str, Any]:
    mfs = mr.discover_manifests(CAPS_ROOT)
    graph = mr.resolve(mfs)
    return {
        "skeleton": graph.skeleton.name,
        "topo_order": graph.order,
        "capabilities": [
            {
                "name": m.name,
                "version": m.version,
                "type": m.type,
                "dependencies": [{"name": d.name, "version": d.version} for d in m.dependencies],
                "extensions_count": len(m.extensions),
            }
            for m in mfs
        ],
    }


def cmd_graph() -> str:
    mfs = mr.discover_manifests(CAPS_ROOT)
    graph = mr.resolve(mfs)
    return mr.to_dot(graph)


def cmd_install(
    cap_names: List[str],
    *,
    target_project: Optional[Path],
    tech_stack: Optional[str],
    dry_run: bool,
) -> Dict[str, Any]:
    mfs = mr.discover_manifests(CAPS_ROOT)
    graph = mr.resolve(mfs)
    name_set = set(cap_names)
    unknown = [n for n in name_set if n not in graph.manifests]
    if unknown:
        raise SystemExit(f"unknown capabilities: {unknown}")
    install_order = [n for n in graph.order if n in name_set]
    reports: List[Dict[str, Any]] = []
    for n in install_order:
        cap = graph.manifests[n]
        sk_inj = inject_into_skeleton(graph.skeleton, cap, dry_run=dry_run)
        adapter_info = None
        if target_project is not None:
            adapter_info = render_adapter(
                cap, target_project, tech_stack, dry_run=dry_run
            )
        reports.append(
            InstallReport(
                capability=n,
                skeleton_injection=sk_inj,
                adapter=adapter_info,
                degrade=adapter_info["degrade"] if adapter_info else None,
            ).to_dict()
        )
    return {
        "skeleton": graph.skeleton.name,
        "install_order": install_order,
        "dry_run": dry_run,
        "reports": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="能力包叠加 CLI")
    parser.add_argument("capabilities", nargs="*", help="待安装的能力包名")
    parser.add_argument("--list", action="store_true", help="列出已发现的能力包")
    parser.add_argument("--graph", action="store_true", help="输出依赖图 DOT")
    parser.add_argument(
        "--target-project", type=Path, default=None,
        help="外部用户项目根目录（启用 auto_adapters 渲染）",
    )
    parser.add_argument("--tech-stack", default=None, help="覆盖自动识别的技术栈")
    parser.add_argument("--apply", action="store_true", help="真实写入（默认 dry-run）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 便于 Agent 解析")
    args = parser.parse_args()

    if args.list:
        out = cmd_list()
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else _pretty_list(out))
        return
    if args.graph:
        print(cmd_graph())
        return
    if not args.capabilities:
        parser.print_help()
        return

    out = cmd_install(
        args.capabilities,
        target_project=args.target_project,
        tech_stack=args.tech_stack,
        dry_run=not args.apply,
    )
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(_pretty_install(out))


def _pretty_list(out: Dict[str, Any]) -> str:
    lines = [f"skeleton: {out['skeleton']}", f"topo_order: {' -> '.join(out['topo_order'])}", ""]
    for c in out["capabilities"]:
        deps = ", ".join(f"{d['name']}@{d['version']}" for d in c["dependencies"]) or "-"
        lines.append(f"  · {c['name']} {c['version']} [{c['type']}]  deps={deps}  extensions={c['extensions_count']}")
    return "\n".join(lines)


def _pretty_install(out: Dict[str, Any]) -> str:
    lines = [
        f"skeleton: {out['skeleton']}",
        f"install_order: {' -> '.join(out['install_order'])}",
        f"dry_run: {out['dry_run']}",
        "",
    ]
    for r in out["reports"]:
        lines.append(f"[{r['capability']}]")
        for inj in r["skeleton_injection"]:
            mark = "✓" if inj["applied"] else ("·" if not inj["error"] else "✗")
            lines.append(
                f"  {mark} {inj['inject_at']} -> {inj['target']} ({inj['op']}:{inj['anchor']})"
                + (f"  err={inj['error']}" if inj["error"] else "")
            )
        if r.get("adapter"):
            lines.append(
                f"  adapter={r['adapter']['adapter']} stack={r['adapter']['tech_stack_used']} "
                f"degrade={r['adapter']['degrade']['level']}"
            )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
