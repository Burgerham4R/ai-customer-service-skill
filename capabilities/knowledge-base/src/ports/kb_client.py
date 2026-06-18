"""knowledge-base 抽象端口（Port）。

与 manifest.yaml.business_contract.external_apis 对齐：
- search   -> faq.search
- list_all -> faq.list
- upsert   -> faq.upsert
- delete   -> faq.delete

所有具体实现（local_json / default_rest / mock / user_custom）必须继承本 ABC。
core 层只依赖本接口。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..core.models import FaqEntry, KbStats, SearchHit


class KnowledgeBaseClient(ABC):
    """知识库后端的统一接口契约。"""

    # ------------------------------------------------------------------
    # 与 business_contract 对齐
    # ------------------------------------------------------------------
    @abstractmethod
    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchHit]:
        """检索匹配的 FAQ。对应 business_contract.faq.search。"""

    @abstractmethod
    def list_all(self) -> List[FaqEntry]:
        """列出所有条目。对应 business_contract.faq.list。"""

    @abstractmethod
    def upsert(self, entry: FaqEntry) -> FaqEntry:
        """新增或更新单条。对应 business_contract.faq.upsert。"""

    @abstractmethod
    def delete(self, entry_id: str) -> bool:
        """删除单条。对应 business_contract.faq.delete。"""

    # ------------------------------------------------------------------
    # 看板辅助方法（默认实现：远程后端可不覆写）
    # ------------------------------------------------------------------
    def stats(self) -> KbStats:
        """返回统计信息（默认基于 list_all 实时计算）。"""
        items = self.list_all()
        return KbStats(
            backend=type(self).__name__,
            entry_count=len(items),
        )

    def reload(self) -> int:
        """从外部源重载数据。默认 no-op；本地实现可覆写为重读文件。"""
        return len(self.list_all())
