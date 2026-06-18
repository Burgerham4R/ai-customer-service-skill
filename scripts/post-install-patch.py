#!/usr/bin/env python3
"""post-install-patch.py — 装能力包后的兜底补丁脚本。

何时调用
--------
    SKILL.md §5 路径 A Step 2.5（add-capability 之后、UI overlay 之前）

它会做什么
----------
1. **修旧版扩展点错位注入**
   早期版本的 `conversation-core/manifest.yaml` 把 `agent.before_push_text`
   位置写成 `before:push_text`，被 add-capability.py 解释为 "在 def push_text
   行之前同缩进插入"，结果落到了类作用域，引用 `session_id`/`text` 局部变量
   抛 NameError。
   新版改用 sentinel anchor `_ext_before_push_text_`（push_text 方法体内）。
   本补丁会扫描已部署的 agent.py，把可能存在的"类作用域错位注入块"挪到方法
   体内的正确位置；如果代码已经在方法体内，则跳过（幂等）。
   同样的逻辑也覆盖 `_ext_after_start_`。

2. **自动写 .env 默认能力包变量**
   recipe.yaml 的 ui_overlay / capability adapter 默认值（KB_ADAPTER=mock /
   HH_ADAPTER=local_queue 等）以前需要用户手动写到 .env；本补丁在 .env 已存在
   的前提下追加缺失项，不覆盖已有值。

3. **server.py StaticFiles html=True 校验**
   保证 `/static/admin/`、`/static/dev/` 等子目录访问能 fallback 到 index.html。

输出
----
    JSON 行（结构化）；返回码 0 表示全部 OK 或仅做幂等跳过；非 0 表示发现需要
    人工介入的异常情况。

仅修改以下白名单内的文件：
    capabilities/conversation-core/src/agent.py
    capabilities/conversation-core/src/server.py
    capabilities/conversation-core/.env
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_PY = ROOT / "capabilities" / "conversation-core" / "src" / "agent.py"
SERVER_PY = ROOT / "capabilities" / "conversation-core" / "src" / "server.py"
ENV_FILE = ROOT / "capabilities" / "conversation-core" / ".env"

# .env 默认值（与 scenarios/customer-service/recipe.yaml 对齐）
ENV_DEFAULTS = {
    "KB_ADAPTER": "mock",
    "KB_TOP_K": "3",
    "KB_MIN_SCORE": "0.05",
    "HH_ADAPTER": "local_queue",
}

# 已知 capability 注入块的 marker（按 capability 名）
CAP_MARKERS = ("human-handoff", "tool-calling", "session-summary", "knowledge-base")


# --------------------------------------------------------------------------- #
# 1. agent.py 错位注入修正
# --------------------------------------------------------------------------- #
def _patch_agent_py(report: dict) -> None:
    if not AGENT_PY.exists():
        report["agent_py"] = {"ok": False, "skipped": True, "reason": "agent.py not found"}
        return

    src = AGENT_PY.read_text(encoding="utf-8")

    # 检查每一个 cap 的 marker 是否仍以 4 空格缩进出现在类作用域
    # （正确位置是 8+ 空格 = 在方法体内）
    misplaced: list[str] = []
    for cap in CAP_MARKERS:
        marker = f"# [{cap}]"
        # 类作用域 4 空格 + marker
        if re.search(rf"^    {re.escape(marker)}", src, re.MULTILINE):
            misplaced.append(cap)

    if not misplaced:
        report["agent_py"] = {"ok": True, "patched": [], "note": "no misplaced capability injections"}
        return

    # 对每一个错位 cap，把它从类作用域剥离 → 移动到对应方法体的 sentinel 之前
    new_src = src
    moved: list[str] = []
    failures: list[dict] = []
    for cap in misplaced:
        marker = f"# [{cap}]"
        # 抽取以 marker 开头的、4 空格缩进的连续块
        block_re = re.compile(
            rf"(?:^    {re.escape(marker)}[^\n]*\n(?:^    [^\n]*\n)+)",
            re.MULTILINE,
        )
        m = block_re.search(new_src)
        if not m:
            failures.append({"capability": cap, "reason": "marker found but block extract failed"})
            continue
        block_text = m.group(0)
        # 把 4 空格缩进升级为 8 空格（method body）
        rebased = "\n".join(
            ("    " + line) if line.startswith("    ") else line
            for line in block_text.splitlines()
        ) + "\n"
        # 选择 sentinel：human-handoff before_push_text 用 _ext_before_push_text_；
        # 同 cap 的 after_start 用 _ext_after_start_。
        # 简化策略：哪个 sentinel 先出现就插哪个；以 cap 是否引用 `text` 决定。
        sentinel = (
            "_ext_before_push_text_"
            if "maybe_handoff(session_id, text" in block_text
            or "maybe_dispatch(text" in block_text
            or "record_user_turn(session_id, text" in block_text
            else "_ext_after_start_"
        )
        # 在 sentinel 注释行前插入 rebased
        sentinel_re = re.compile(
            rf"^([ \t]*)# {re.escape(sentinel)}\b[^\n]*$",
            re.MULTILINE,
        )
        s_match = sentinel_re.search(new_src)
        if not s_match:
            failures.append({"capability": cap, "reason": f"sentinel {sentinel} not found in agent.py"})
            continue
        # 构造插入文本（缩进对齐到 sentinel 同级即 8 空格）
        # rebased 已是 8 空格缩进
        # 先在 new_src 中删掉旧的错位块
        without_old = new_src[: m.start()] + new_src[m.end():]
        # 重新查找 sentinel 行（位置可能变化）
        s_match2 = re.compile(
            rf"^([ \t]*)# {re.escape(sentinel)}\b[^\n]*$",
            re.MULTILINE,
        ).search(without_old)
        if not s_match2:
            failures.append({"capability": cap, "reason": f"sentinel {sentinel} lost after stripping old block"})
            continue
        new_src = (
            without_old[: s_match2.start()]
            + rebased
            + without_old[s_match2.start():]
        )
        moved.append(cap)

    if new_src != src:
        AGENT_PY.write_text(new_src, encoding="utf-8")

    report["agent_py"] = {
        "ok": not failures,
        "patched": moved,
        "failed": failures,
    }


# --------------------------------------------------------------------------- #
# 2. server.py StaticFiles html=True 校验
# --------------------------------------------------------------------------- #
def _patch_server_py(report: dict) -> None:
    if not SERVER_PY.exists():
        report["server_py"] = {"ok": False, "skipped": True, "reason": "server.py not found"}
        return
    src = SERVER_PY.read_text(encoding="utf-8")
    if "StaticFiles(directory=str(_DEMO_DIR), html=False)" in src:
        new_src = src.replace(
            "StaticFiles(directory=str(_DEMO_DIR), html=False)",
            "StaticFiles(directory=str(_DEMO_DIR), html=True)",
        )
        SERVER_PY.write_text(new_src, encoding="utf-8")
        report["server_py"] = {"ok": True, "patched": ["StaticFiles html=True"]}
    elif "StaticFiles(directory=str(_DEMO_DIR), html=True)" in src:
        report["server_py"] = {"ok": True, "patched": [], "note": "already html=True"}
    else:
        report["server_py"] = {"ok": True, "patched": [], "note": "no matching StaticFiles mount"}


# --------------------------------------------------------------------------- #
# 3. .env 默认值追加（不覆盖已有）
# --------------------------------------------------------------------------- #
def _patch_env(report: dict) -> None:
    if not ENV_FILE.exists():
        report["env"] = {"ok": True, "skipped": True, "reason": ".env not present yet (run setup-credentials first)"}
        return
    text = ENV_FILE.read_text(encoding="utf-8")
    existing_keys = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    appended = []
    additions = [
        f"{k}={v}" for k, v in ENV_DEFAULTS.items() if k not in existing_keys
    ]
    if additions:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n# Added by post-install-patch.py (capability adapter defaults)\n"
        text += "\n".join(additions) + "\n"
        ENV_FILE.write_text(text, encoding="utf-8")
        appended = [a.split("=", 1)[0] for a in additions]
    report["env"] = {"ok": True, "appended": appended}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    report: dict = {}
    try:
        _patch_agent_py(report)
        _patch_server_py(report)
        _patch_env(report)
    except Exception as exc:  # noqa: BLE001
        report["fatal"] = repr(exc)
        print(json.dumps(report, ensure_ascii=False))
        return 2
    overall_ok = all(
        v.get("ok", False) or v.get("skipped", False) for v in report.values()
    )
    report["ok"] = overall_ok
    print(json.dumps(report, ensure_ascii=False))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
