# sample-data —— 默认演示数据

`faq-sample.json` 是 5 条中性行业 FAQ，结构与 `capabilities/knowledge-base/src/core/models.py.FaqEntry` 一致：

```json
{
  "id":       "string，主键",
  "question": "string",
  "answer":   "string",
  "keywords": "string[]",
  "source":   "string，可选；用于看板显示数据出处"
}
```

**顶层是数组**（与 `LocalJsonKbClient.reload()` 期望的格式对齐）。

## 启用方式

把 KB 切到 `local_json` adapter 并指向本文件：

```env
# capabilities/conversation-core/.env
KB_ADAPTER=local_json
KB_DATA_FILE=scenarios/customer-service/sample-data/faq-sample.json
```

或在路径 A 演示阶段，保留默认 `KB_ADAPTER=mock` 即可（mock adapter 内置等价的 5 条 demo FAQ）。

## 上线前

1. 用真实业务 FAQ 替换本文件内容（或新建一个文件并指向 `KB_DATA_FILE`）；
2. 也可改用 `default_rest` adapter 接外部 FAQ 服务，按 `capabilities/knowledge-base/INTERFACE_ADAPT.md` 配置即可，不再需要本目录。
