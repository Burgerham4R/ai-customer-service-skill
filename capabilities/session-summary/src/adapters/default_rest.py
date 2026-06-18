"""default_rest 写回 sink —— POST 到用户真实 CRM / 工单系统。

环境变量：
    SS_REST_BASE_URL   必填，如 https://crm.example.com/api
    SS_REST_TOKEN      可选，Bearer Token
    SS_REST_TIMEOUT_MS 可选，默认 5000

对齐 manifest.business_contract.external_apis[summary.write_to_crm]：
    POST {base}/sessions/{session_id}/summary
字段对不齐时改本文件的 _build_payload，或参照 INTERFACE_ADAPT.md。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from .base import SummarySink

logger = logging.getLogger(__name__)


class DefaultRestSink(SummarySink):
    name = "default_rest"

    def __init__(self) -> None:
        self._base = (os.getenv("SS_REST_BASE_URL") or "").rstrip("/")
        self._token = os.getenv("SS_REST_TOKEN") or ""
        self._timeout = max(int(os.getenv("SS_REST_TIMEOUT_MS", "5000")), 100) / 1000.0
        if not self._base:
            raise RuntimeError("SS_REST_BASE_URL not configured for default_rest sink")
        # 安全：禁止明文 http（本机调试除外），避免凭证 / 纪要走非加密通道
        if not self._base.startswith("https://") and "localhost" not in self._base:
            raise RuntimeError(f"SS_REST_BASE_URL must use HTTPS: {self._base}")

    def _build_payload(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        summary = rec.get("summary") or {}
        return {
            "session_id": rec.get("session_id"),
            "topic": (summary.get("topics") or [None])[0],
            "outcome": summary.get("outcome", "follow_up"),
            "next_actions": summary.get("next_actions") or [],
            "full_transcript": [t.get("text", "") for t in rec.get("turns") or []],
            "structured_facts": summary,
            "finalized_at": rec.get("closed_at"),
        }

    def write(self, summary_record: Dict[str, Any]) -> Dict[str, Any]:
        import requests

        sid = summary_record.get("session_id", "")
        url = f"{self._base}/sessions/{sid}/summary"
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = requests.post(url, json=self._build_payload(summary_record),
                             headers=headers, timeout=self._timeout)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            data = {}
        return {
            "record_id": data.get("record_id", ""),
            "accepted": bool(data.get("accepted", True)),
            "sink": self.name,
        }
