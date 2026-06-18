# Q1 —— 业务描述（自由文本）

> 路径 B 第 1 题。AI 用 `ask_followup_question` 单独提问，**不带 options**，让用户自由输入。
>
> AI 把用户答复保存到内部变量 `business_desc`，将来用于：
> 1. 渲染 `scenarios/customer-service/system-prompt.template.md` 中的 `{{business_desc}}`
> 2. 写入 `<workspace>/recipe.yaml` 的 `agent_runtime.system_prompt.variables.business_desc`
>
> AI **不要**自己脑补行业；用户没说的字段保持空白，等 Q4 之后再做兜底。

---

## AI 应该说

> 第 1 题（共 4 题）：你的客服机器人是为什么业务做的？
> 用一两句话告诉我**业务范围**和**典型问题**就行。例如：
>
> - "我们做家用智能小家电的电商，主营空气炸锅 / 扫地机 / 加湿器，用户通常问保修、退换、物流"
> - "我是一家 SaaS HR 系统的客户支持，常见问题是登录失败、组织架构同步、套餐升级"
> - "餐厅外送，用户主要问订单状态、退款、菜单库存、配送费"
>
> 业务越具体，最终生成的 system prompt 越贴合你的真实场景。

---

## 收到答复后的校验

- 长度 ≥ 8 字符且 ≤ 600 字符。过短追问"业务范围太短，请补充一下典型问题或行业关键词"
- 包含至少一个名词性短语（如行业名、产品名、用户类型）；纯感叹词或闲聊则**重新提问**
- 不要要求用户提供品牌名 / 公司名（如要使用，模板里会用占位符 `{{business_name | default('我们')}}`）

---

## 答复回写

```yaml
# 渲染到 <workspace>/recipe.yaml
agent_runtime:
  system_prompt:
    variables:
      business_desc: |
        <用户原文>
```
