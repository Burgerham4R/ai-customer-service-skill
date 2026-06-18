"""结构化摘要生成器。

策略：
- 离线启发式（默认）：抽取问句 / 待办关键词 / 关键名词，本地零依赖完成。
- LLM 二次总结（可选，需 LLM_API_KEY）：把 turns 序列化后调用 OpenAI 兼容协议。

输出 JSON：
    {
      "topics":      ["..."],
      "user_intents": ["..."],
      "next_actions": ["..."],
      "highlights":  ["..."],
      "engine":      "heuristic" | "llm",
      "model":       "gpt-4o-mini" | null
    }
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

from .recorder import SessionRecord

logger = logging.getLogger(__name__)


_QUESTION_RE = re.compile(r"[^?？]+[?？]")
_ACTION_RE = re.compile(r"(我想|请帮我|帮我|need to|please)([^。.!?？!\n]+)", re.IGNORECASE)
_NOUN_RE = re.compile(r"[A-Z][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")
_STOPWORDS = {"我们", "你们", "什么", "因为", "所以", "时候", "可以", "需要"}


def _heuristic(record: SessionRecord) -> Dict[str, Any]:
    topics: List[str] = []
    intents: List[str] = []
    actions: List[str] = []
    highlights: List[str] = []
    seen_topic, seen_intent, seen_action = set(), set(), set()
    for t in record.turns:
        if t.role != "user":
            continue
        for q in _QUESTION_RE.findall(t.text):
            q = q.strip()
            if q and q not in seen_intent:
                intents.append(q[:120])
                seen_intent.add(q)
        for m in _ACTION_RE.finditer(t.text):
            phrase = (m.group(1) + m.group(2)).strip()[:120]
            if phrase and phrase not in seen_action:
                actions.append(phrase)
                seen_action.add(phrase)
        for noun in _NOUN_RE.findall(t.text):
            if noun in _STOPWORDS or len(noun) > 24:
                continue
            if noun not in seen_topic and len(topics) < 8:
                topics.append(noun)
                seen_topic.add(noun)
    if record.turns:
        highlights.append(f"{len(record.turns)} turns recorded")
    return {
        "topics": topics,
        "user_intents": intents[:5],
        "next_actions": actions[:5],
        "highlights": highlights,
        "engine": "heuristic",
        "model": None,
    }


def _llm_summarize(record: SessionRecord) -> Dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY")
    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not configured")
    import requests

    transcript = "\n".join(f"[{t.role}] {t.text}" for t in record.turns[-50:])
    prompt = (
        "你是会话纪要助理，请将以下对话总结为 JSON，键包含 topics, user_intents,"
        " next_actions, highlights，每个键值为字符串数组（不超过 5 项）。"
        "禁止包含任何敏感信息（API Key/Token 等）。\n"
        f"对话内容:\n{transcript}\n"
        "仅输出 JSON。"
    )
    resp = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"highlights": [content[:512]]}
    parsed.setdefault("topics", [])
    parsed.setdefault("user_intents", [])
    parsed.setdefault("next_actions", [])
    parsed.setdefault("highlights", [])
    parsed["engine"] = "llm"
    parsed["model"] = model
    return parsed


def summarize(record: SessionRecord, *, prefer_llm: bool = True) -> Dict[str, Any]:
    if prefer_llm and os.getenv("LLM_API_KEY"):
        try:
            return _llm_summarize(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM summarize failed, fallback to heuristic: %s", exc)
    return _heuristic(record)
