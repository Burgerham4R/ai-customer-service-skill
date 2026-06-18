"""session-summary 写回适配层。

与 knowledge-base / human-handoff 一致的「三档 adapter + factory」范式：
    mock          —— 默认；纪要只打日志 + 返回 mock record_id，无需任何外部系统，
                     便于本地 / 路径 A 演示时立刻看到"写回成功"效果。
    local_json    —— 追加写到本地 JSONL（data/_writeback.jsonl），可离线核对。
    default_rest  —— POST 到用户真实 CRM / 工单系统（SS_REST_BASE_URL）。

对外契约见 manifest.business_contract.external_apis[summary.write_to_crm]。
接口字段对不齐时，参照 INTERFACE_ADAPT.md 做 request/response 映射。
"""
from __future__ import annotations

import abc
from typing import Any, Dict


class SummarySink(abc.ABC):
    """会话纪要写回目标的统一抽象。"""

    name: str = "base"

    @abc.abstractmethod
    def write(self, summary_record: Dict[str, Any]) -> Dict[str, Any]:
        """把一条 finalize 后的纪要写回目标系统。

        Returns
        -------
        dict: {"record_id": str, "accepted": bool, "sink": str}
        """
        raise NotImplementedError
