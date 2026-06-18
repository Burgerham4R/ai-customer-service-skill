# knowledge-base 接口适配 SOP

> 当用户已有的知识库 / FAQ / 检索系统接口与本能力包默认契约不一致时，按本文档分场景操作。
> 推荐统一通过 `python scripts/contract-adapt.py knowledge-base` 自动生成，本文档为手工兜底。

---

## 1. 默认契约速览

本能力包**调用**用户知识库的接口（outbound）：

| 契约名 | 方法 | 路径 | 用途 |
|---|---|---|---|
| `faq.search`  | POST   | `/faq/search`        | 关键词检索 |
| `faq.list`    | GET    | `/faq`               | 列出全部条目 |
| `faq.upsert`  | POST   | `/faq`               | 新增 / 更新 |
| `faq.delete`  | DELETE | `/faq/{entry_id}`    | 删除条目 |

完整字段定义见 `manifest.yaml` 的 `business_contract.external_apis`。

---

## 2. 三层防御机制

| 层级 | 落点 | 适用场景 |
|---|---|---|
| **L1 字段映射** | 仅字段名 / 简单类型差异 | 90% 的常见情况 |
| **L2 适配子类** | 鉴权 / 路径 / 错误码差异 | 用户自有 KB 系统 |
| **L3 完整自定义实现** | 协议级差异（向量库 / GraphQL / gRPC） | 非 REST 协议 |

均落到 `capabilities/knowledge-base/src/adapters/user_custom.py`，并通过 `KB_ADAPTER=user_custom` 启用。

---

## 3. L1 字段映射（最常见）

### 3.1 适用判定

- 用户接口仍是 REST + JSON
- 仅字段名差异（在 `adapter_slots` 范围内）

### 3.2 操作步骤

**Step 1**：贴出用户的 curl 或 OpenAPI

```bash
curl -X POST https://kb.example.com/api/v3/search \
  -H 'X-Api-Key: xxx' \
  -d '{
    "keyword": "退款",
    "limit": 3
  }'
# 响应:
# {
#   "results": [
#     { "doc_id": "k001", "title": "如何退款", "content": "...", "tags": ["退款"], "relevance": 0.92 }
#   ]
# }
```

**Step 2**：写映射表 `capabilities/knowledge-base/src/adapters/user_custom_mapping.yaml`

```yaml
faq.search:
  request:
    query:  keyword              # 字段名映射
    top_k:  limit
  response:
    # response 是数组形式，转换器需要把 results[] 映射到 hits[]
    hits:   results
    "hits[].entry.id":       "results[].doc_id"
    "hits[].entry.question": "results[].title"
    "hits[].entry.answer":   "results[].content"
    "hits[].entry.keywords": "results[].tags"
    "hits[].score":          "results[].relevance"

faq.list:
  response:
    items: data                  # 用户用 data 不用 items
    "items[].id":       "data[].doc_id"
    "items[].question": "data[].title"
    "items[].answer":   "data[].content"
    "items[].keywords": "data[].tags"
```

**Step 3**：生成 adapter

```bash
python scripts/contract-adapt.py knowledge-base \
  --base-url https://kb.example.com \
  --auth-header "X-Api-Key" \
  --mapping capabilities/knowledge-base/src/adapters/user_custom_mapping.yaml
```

**Step 4**：启用

```bash
export KB_ADAPTER=user_custom
export KB_REST_BASE_URL=https://kb.example.com
export KB_REST_TOKEN=<your-api-key>
```

---

## 4. L2 适配子类（认证 / 路径风格差异）

### 4.1 适用判定

- 鉴权方式非 Bearer（如 `X-Api-Key`、签名鉴权）
- 路径模板不同
- 响应包装层级不同（如 `{ code, msg, data: { ... } }`）

### 4.2 模板代码

```python
# capabilities/knowledge-base/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import FaqEntry, SearchHit
from .default_rest import DefaultRestKbClient


class UserCustomKbClient(DefaultRestKbClient):
    """用户自有 KB 系统适配器（L2）。"""

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["X-Api-Key"] = self._token       # 不是 Bearer
        return h

    def search(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> List[SearchHit]:
        if not query.strip():
            return []
        payload = {
            "keyword": query,                  # 字段重映射
            "limit": int(top_k or 3),
        }
        # 用户接口路径不同
        data = self._post("/api/v3/search", payload)
        results = data.get("results", []) if isinstance(data, dict) else (data or [])
        hits: List[SearchHit] = []
        for r in results:
            hits.append(
                SearchHit(
                    entry=FaqEntry(
                        id=str(r.get("doc_id", "")),
                        question=str(r.get("title", "")),
                        answer=str(r.get("content", "")),
                        keywords=list(r.get("tags") or []),
                        source="remote_api",
                    ),
                    score=float(r.get("relevance", 0.0)),
                )
            )
        return hits

    def list_all(self) -> List[FaqEntry]:
        data = self._get("/api/v3/docs")
        items = data.get("data", []) if isinstance(data, dict) else (data or [])
        return [
            FaqEntry(
                id=str(it.get("doc_id", "")),
                question=str(it.get("title", "")),
                answer=str(it.get("content", "")),
                keywords=list(it.get("tags") or []),
                source="remote_api",
            )
            for it in items
        ]


def from_env() -> Optional["UserCustomKbClient"]:
    import os
    base = os.getenv("KB_REST_BASE_URL")
    if not base:
        return None
    return UserCustomKbClient(
        base_url=base,
        token=os.getenv("KB_REST_TOKEN"),
        timeout_ms=int(os.getenv("KB_REST_TIMEOUT_MS", "5000")),
    )
```

---

## 5. L3 完整自定义（向量库 / GraphQL / gRPC）

### 5.1 适用判定

- 用户使用向量数据库（Milvus / Pinecone / Qdrant）做语义检索
- 用户使用 GraphQL 而非 REST
- 用户使用 gRPC

### 5.2 模板代码（向量库示例）

```python
# capabilities/knowledge-base/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import FaqEntry, KbStats, SearchHit
from ..ports.kb_client import KnowledgeBaseClient


class UserCustomKbClient(KnowledgeBaseClient):
    """向量库适配器示例（L3：直接实现 KnowledgeBaseClient）。"""

    def __init__(self, **kwargs):
        # TODO 初始化向量库 client：
        # self._milvus = MilvusClient(uri=...)
        # self._embedder = SentenceTransformer(...)
        ...

    def search(self, query, *, top_k=None, min_score=None) -> List[SearchHit]:
        # TODO 调用 embedder + 向量检索
        # vec = self._embedder.encode(query)
        # results = self._milvus.search(vec, top_k=top_k or 3)
        results = []
        return [
            SearchHit(
                entry=FaqEntry(id=r["id"], question=r["q"], answer=r["a"]),
                score=float(r["distance"]),
            )
            for r in results
        ]

    def list_all(self) -> List[FaqEntry]:
        # TODO 向量库不一定支持枚举；返回空或抛 NotSupported
        return []

    def upsert(self, entry: FaqEntry) -> FaqEntry:
        # TODO 写入向量
        return entry

    def delete(self, entry_id: str) -> bool:
        # TODO
        return False

    def stats(self) -> KbStats:
        return KbStats(backend="vector_db", entry_count=-1)


def from_env():
    import os
    return UserCustomKbClient(
        endpoint=os.getenv("KB_VECTOR_ENDPOINT", ""),
        api_key=os.getenv("KB_VECTOR_TOKEN", ""),
    )
```

---

## 6. 切换 / 验证

### 6.1 启用 user_custom

```bash
export KB_ADAPTER=user_custom
# 重启服务后生效
```

### 6.2 单元自检

```bash
python -c "
from capabilities.knowledge_base.src.adapters.factory import build_default
c = build_default()
print('adapter:', type(c).__name__)
hits = c.search('退款')
for h in hits:
    print(' ', h.score, h.entry.question)
"
```

### 6.3 端到端

```bash
curl -X POST http://localhost:3000/api/v1/kb/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"退款","top_k":3}'
```

---

## 7. 安全清单

- [ ] `KB_REST_BASE_URL` 必须使用 https://（localhost 例外）
- [ ] 默认拒绝私网地址
- [ ] 鉴权 token 仅来自环境变量
- [ ] 用户上传 FAQ 内容时通过 `_strip_html` 清洗（router 已内置）
- [ ] 远程异常不打印响应体
