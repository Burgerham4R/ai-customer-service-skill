"""文本注入拦截：从对话流中识别 "/tool" 调用。

约定文本格式：
    /tool <name> {json_params}

示例：
    /tool get_order {"order_id": "A1234"}

Dispatcher 解析后调用 ToolRegistry，将结果以结构化字符串返回，
由 conversation-core 的注入点继续推送给 LLM。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .registry import get_loader

_TOOL_RE = re.compile(r"^\s*/tool\s+([A-Za-z0-9_\-]{1,64})\s*(\{.*\})?\s*$", re.DOTALL)
_MAX_TEXT_LEN = 4096


def maybe_dispatch(text: str) -> Optional[str]:
    """识别 "/tool" 触发，返回带工具结果的新文本；无触发返回 None。"""
    if not text or len(text) > _MAX_TEXT_LEN:
        return None
    m = _TOOL_RE.match(text)
    if not m:
        return None
    name = m.group(1)
    raw_params = m.group(2) or "{}"
    try:
        params = json.loads(raw_params)
        if not isinstance(params, dict):
            params = {}
    except json.JSONDecodeError:
        params = {}
    result = get_loader().call(name, params)
    payload = {
        "tool": result.tool,
        "track": result.track,
        "ok": result.ok,
        "output": result.output,
        "error": result.error,
        "latency_ms": result.latency_ms,
        "fallback_chain": result.fallback_chain,
    }
    # 用约定块返回，便于 LLM 系统提示识别工具结果
    return (
        f"[tool_result name={result.tool} track={result.track} ok={result.ok}]\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n[/tool_result]"
    )
