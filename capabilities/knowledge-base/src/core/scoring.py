"""分词 + 评分工具：从原 retriever.py 迁入。

不引入任何外部依赖，纯 Python：
- 中文按字 2-gram 切分
- 英文按 word 切分
- TF-IDF 评分（关键词加权 3 倍）
"""
from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List

from .models import FaqEntry


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> List[str]:
    """混合中英文分词。"""
    if not text:
        return []
    text = text.lower()
    tokens: List[str] = []
    tokens.extend(_WORD_RE.findall(text))
    for blob in _CN_RE.findall(text):
        if len(blob) == 1:
            tokens.append(blob)
        else:
            tokens.extend(blob[i : i + 2] for i in range(len(blob) - 1))
    return tokens


def doc_tokens(entry: FaqEntry) -> List[str]:
    """生成单条目用于评分的 token 列表（关键词加权 3 倍）。"""
    toks = tokenize(entry.question) + tokenize(entry.answer)
    for kw in entry.keywords:
        toks.extend(tokenize(kw) * 3)
    return toks


def build_df(entries: Iterable[FaqEntry]) -> Dict[str, int]:
    """构建文档频率表。"""
    df: Dict[str, int] = {}
    for e in entries:
        for t in set(doc_tokens(e)):
            df[t] = df.get(t, 0) + 1
    return df


def tfidf_score(
    entry: FaqEntry,
    q_tokens: List[str],
    *,
    df: Dict[str, int],
    n_docs: int,
) -> float:
    """TF-IDF 评分（归一化到 [0, 1]）。"""
    d_tokens = doc_tokens(entry)
    if not d_tokens:
        return 0.0
    tf: Dict[str, int] = {}
    for t in d_tokens:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for t in q_tokens:
        if t not in tf:
            continue
        idf = math.log((n_docs + 1) / (1 + df.get(t, 0))) + 1
        score += (tf[t] / len(d_tokens)) * idf
    return max(0.0, min(score, 1.0))
