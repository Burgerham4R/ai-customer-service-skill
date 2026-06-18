# knowledge-base · FAQ 检索能力包

> 给 conversation-core 骨架追加最简 FAQ 检索能力，零外部依赖。

## 安装

```bash
# 在仓库根目录
python scripts/add-capability.py knowledge-base
```

## 配置

| 环境变量 | 默认 | 说明 |
|:---|:---|:---|
| `KB_DATA_FILE` | `capabilities/knowledge-base/data/faq.json` | FAQ 数据文件 |
| `KB_TOP_K`    | `3`   | 单次检索最多回填条数 |
| `KB_MIN_SCORE`| `0.1` | 命中阈值（低于则不注入） |

## REST API

| 方法 | 路径 | 用途 |
|:---|:---|:---|
| GET  | `/api/v1/kb/list`    | 列出所有条目 |
| POST | `/api/v1/kb/search`  | 关键词检索 |
| POST | `/api/v1/kb/upsert`  | 新增 / 更新 |
| DELETE | `/api/v1/kb/{id}`  | 删除 |
| POST | `/api/v1/kb/reload`  | 从文件热重载 |

## 注入策略

- `agent.before_start`：把检索到的 FAQ 拼接到 LLM `instructions` 末尾。
- `server.router_extension`：挂载 `/api/v1/kb/*` 子路由。

## 数据格式

```json
[
  {
    "id": "faq_xxx",
    "question": "What ...?",
    "answer": "...",
    "keywords": ["alias1", "alias2"]
  }
]
```

## 安全

- 写入条目时自动剥离 HTML 标签（XSS 防御）。
- 长度上限 `question ≤ 1024`、`answer ≤ 4096`、`query ≤ 256`。
