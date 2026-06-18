"""Best-effort 联动 session-summary（可选能力）。

当转人工建单时，自动为该 session 生成一份会话纪要并挂到工单上，
让坐席在工单详情里立刻看到客户问题上下文，无需手动点"生成纪要"。

设计原则：
- 软依赖：session-summary 未安装时静默 no-op，不影响转人工主流程。
- 不阻塞：默认走启发式摘要（本地零延迟），不在建单链路里调用 LLM。
- 解耦：通过 conversation-core 的 _capability_loader 动态加载，
  human-handoff 不对 session-summary 产生静态 import 依赖。
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_loader: Optional[Any] = None
_loader_resolved = False


def _get_loader() -> Optional[Any]:
    """动态加载 conversation-core 的 _capability_loader（自身无相对导入，可独立加载）。"""
    global _loader, _loader_resolved
    if _loader_resolved:
        return _loader
    _loader_resolved = True
    try:
        # <root>/capabilities/human-handoff/src/summary_link.py → parents[3] = <root>
        repo_root = Path(__file__).resolve().parents[3]
        loader_path = (
            repo_root / "capabilities" / "conversation-core" / "src" / "_capability_loader.py"
        )
        if not loader_path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("_hh_capability_loader", loader_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _loader = mod
    except Exception as exc:  # noqa: BLE001
        logger.info("session-summary link unavailable: %s", exc)
        _loader = None
    return _loader


def attach_summary_to_ticket(ticket: Any) -> None:
    """为工单对应的 session 生成纪要并写入 ticket.extra['session_summary']。

    session-summary 未安装 / 任何异常 → 静默跳过（不影响建单主流程）。
    """
    loader = _get_loader()
    if loader is None:
        return
    try:
        recorder_mod = loader.try_load_capability("session-summary", "src/recorder.py")
        summarizer_mod = loader.try_load_capability("session-summary", "src/summarizer.py")
        if recorder_mod is None or summarizer_mod is None:
            return
        session_id = ticket.user_id
        recorder = recorder_mod.get_recorder()
        rec = recorder.get(session_id)
        if rec is None:
            return  # 该会话没有记录（如看板手工插入的测试工单），跳过
        # 建单链路走启发式摘要（本地、零延迟），避免 LLM 调用阻塞转人工；
        # 坐席如需更精炼的版本，可在看板里点"重新生成"走 LLM。
        summary = summarizer_mod.summarize(rec, prefer_llm=False)
        recorder.finalize(session_id, summary)
        ticket.extra["session_summary"] = summary
    except Exception as exc:  # noqa: BLE001
        logger.info("attach session summary skipped: %s", exc)
