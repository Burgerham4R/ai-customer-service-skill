"""knowledge-base core models.

定义统一的领域模型：
- FaqEntry  知识条目（id / question / answer / keywords / source）
- SearchHit 检索命中项（含得分）
- KbStats   知识库统计信息（条目数 / 数据源类型 / 加载时间）

所有 adapter 必须使用本模块的数据结构作为传输对象。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FaqEntry:
    """单条 FAQ 知识条目。"""

    id: str
    question: str
    answer: str
    keywords: List[str] = field(default_factory=list)
    # 可选：标注条目来源（local_json / remote_api / user_uploaded 等），便于看板显示
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "keywords": list(self.keywords),
            **({"source": self.source} if self.source else {}),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "FaqEntry":
        return cls(
            id=str(raw.get("id") or raw.get("question", ""))[:64] or "auto",
            question=str(raw.get("question", "")).strip(),
            answer=str(raw.get("answer", "")).strip(),
            keywords=[
                str(k).strip()
                for k in (raw.get("keywords") or [])
                if str(k).strip()
            ],
            source=raw.get("source"),
        )


@dataclass
class SearchHit:
    """检索命中。"""

    entry: FaqEntry
    score: float

    def to_dict(self) -> dict:
        return {"entry": self.entry.to_dict(), "score": round(float(self.score), 4)}


@dataclass
class KbStats:
    """知识库统计（看板用）。"""

    backend: str                    # "local_json" / "remote_api" / "mock" / "user_custom"
    entry_count: int
    loaded_at: Optional[float] = None
    data_source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "entry_count": self.entry_count,
            "loaded_at": self.loaded_at,
            "data_source": self.data_source,
        }
