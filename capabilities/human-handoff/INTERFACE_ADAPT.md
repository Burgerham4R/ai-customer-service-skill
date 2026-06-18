# human-handoff 接口适配 SOP

> 当用户已有的工单 / 客服调度系统接口与本能力包默认契约不一致时，按本文档分场景操作。
> 推荐统一通过 `python scripts/contract-adapt.py human-handoff` 自动生成，本文档为手工兜底。

---

## 1. 默认契约速览

本能力包**调用**用户工单系统的接口（outbound）：

| 契约名 | 方法 | 路径 | 用途 |
|---|---|---|---|
| `ticket.create`        | POST | `/tickets`                          | 创建工单 |
| `ticket.status_query`  | GET  | `/tickets/{ticket_id}`              | 查工单状态 |
| `ticket.cancel`        | POST | `/tickets/{ticket_id}/cancel`       | 取消工单 |
| `ticket.status_callback` | POST | `/api/v1/handoff/callback/ticket-status` | 业务方回调（inbound） |

完整字段定义见 `manifest.yaml` 的 `business_contract.external_apis`。

---

## 2. 三层防御机制

| 层级 | 落点 | 适用场景 |
|---|---|---|
| **L1 字段映射** | 仅字段名 / 简单类型差异 | 90% 的常见情况 |
| **L2 适配子类** | 认证、传输头、错误码、URL 模板差异 | 鉴权机制不同 / 路径/路由风格不同 |
| **L3 完整自定义实现** | 协议级差异（webhook / MQ / gRPC） | 非 REST 协议 |

三层均落到 `capabilities/human-handoff/src/adapters/user_custom.py`，并通过 `HH_ADAPTER=user_custom` 启用。

---

## 3. L1 字段映射（最常见）

### 3.1 适用判定

- 用户接口仍是 REST + JSON
- 仅字段名 / 字段路径不同（在 `adapter_slots` 范围内）
- 字段类型一致（string ↔ string，int ↔ int）

### 3.2 操作步骤

**Step 1**：贴出用户的 curl 或 OpenAPI

```bash
# 用户的工单创建接口
curl -X POST https://crm.example.com/api/v2/work_orders \
  -H 'X-Auth-Token: xxx' \
  -d '{
    "customer_id": "u001",
    "title": "退款问题",
    "level": "P2",
    "messages": ["..."]
  }'
# 响应: { "id": "WO123", "rank": 5, "wait_estimate": 150 }
```

**Step 2**：写映射表 `capabilities/human-handoff/src/adapters/user_custom_mapping.yaml`

```yaml
# 字段路径映射：左 = 默认契约字段，右 = 用户实际字段
ticket.create:
  request:
    user_id:     customer_id
    subject:     title
    priority:    level                  # 值映射见下
    transcript:  messages
  response:
    ticket_id:       id
    queue_position:  rank
    eta_seconds:     wait_estimate
  # 枚举值映射
  enum_map:
    request.priority:
      low:    P3
      normal: P2
      high:   P1
      urgent: P0

ticket.status_query:
  request:
    ticket_id: id
  response:
    ticket_id: id
    status:    state
  enum_map:
    response.status:
      pending:    queued
      processing: in_progress
      closed:     done
      canceled:   cancelled
```

**Step 3**：生成 adapter（通过工具）

```bash
python scripts/contract-adapt.py human-handoff \
  --base-url https://crm.example.com \
  --auth-header "X-Auth-Token" \
  --mapping capabilities/human-handoff/src/adapters/user_custom_mapping.yaml
```

工具会按映射生成 `user_custom.py`，自动继承 `DefaultRestHandoffClient` 并覆写字段映射逻辑。

**Step 4**：启用

```bash
export HH_ADAPTER=user_custom
export HH_REST_BASE_URL=https://crm.example.com
export HH_REST_TOKEN=<your-token>     # 可选；无 token 时清空
```

---

## 4. L2 适配子类（认证 / 路径风格差异）

### 4.1 适用判定

- 鉴权方式非 Bearer（如 `X-Auth-Token`、`HMAC-SHA256` 签名、双 Token）
- 路径模板不同（如 `/tickets/{id}` vs `/work-orders/by-id/{id}`）
- 错误码不是 HTTP 标准（如返回 200 但 body 中 `code != 0`）

### 4.2 模板代码

```python
# capabilities/human-handoff/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import Ticket, TicketStatus
from .default_rest import DefaultRestHandoffClient


class UserCustomHandoffClient(DefaultRestHandoffClient):
    """用户工单系统适配器（L2）。"""

    def _headers(self) -> dict:
        # 覆写鉴权方式
        h = {"Content-Type": "application/json"}
        if self._token:
            h["X-Auth-Token"] = self._token        # 不是 Bearer
        return h

    def create_ticket(
        self,
        *,
        user_id: str,
        subject: str = "",
        description: str = "",
        priority: str = "normal",
        transcript: Optional[List[str]] = None,
    ) -> Ticket:
        # TODO 字段重映射
        payload = {
            "customer_id": user_id,
            "title": subject,
            "level": {"low": "P3", "normal": "P2", "high": "P1", "urgent": "P0"}[priority],
            "messages": list(transcript or []),
        }
        data = self._post("/api/v2/work_orders", payload)
        return Ticket(
            ticket_id=str(data["id"]),
            user_id=user_id,
            subject=subject,
            description=description,
            priority=priority,
            queue_position=int(data.get("rank", 0)),
            eta_seconds=int(data.get("wait_estimate", 0)),
            transcript=list(transcript or []),
        )

    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        # TODO 路径模板重映射
        data = self._get(f"/api/v2/work_orders/by-id/{ticket_id}", optional=True)
        if data is None:
            return None
        # TODO 状态枚举重映射
        status_map = {"queued": "pending", "in_progress": "processing", "done": "closed"}
        return TicketStatus(
            ticket_id=str(data["id"]),
            status=status_map.get(data.get("state", ""), data.get("state", "pending")),
            agent_id=data.get("operator"),
        )


def from_env() -> Optional["UserCustomHandoffClient"]:
    import os
    base = os.getenv("HH_REST_BASE_URL")
    if not base:
        return None
    return UserCustomHandoffClient(
        base_url=base,
        token=os.getenv("HH_REST_TOKEN"),
        timeout_ms=int(os.getenv("HH_REST_TIMEOUT_MS", "5000")),
    )
```

### 4.3 启用

```bash
export HH_ADAPTER=user_custom
export HH_REST_BASE_URL=https://crm.example.com
export HH_REST_TOKEN=<your-token>
```

---

## 5. L3 完整自定义（协议差异）

### 5.1 适用判定

- 业务方使用 webhook（你方推消息过去，业务方再异步回调）
- 业务方使用消息队列（Kafka / RocketMQ / RabbitMQ）
- 业务方使用 gRPC / gRPC-Web
- 用户体系完全自研，不存在"通用工单接口"概念

### 5.2 模板代码

```python
# capabilities/human-handoff/src/adapters/user_custom.py
from typing import List, Optional

from ..core.models import OverallStatus, Ticket, TicketStatus, TicketStatusEnum, now_ts
from ..ports.handoff_client import HandoffClient


class UserCustomHandoffClient(HandoffClient):
    """用户自研协议适配器（L3：直接实现 HandoffClient）。"""

    def __init__(self, **kwargs):
        # TODO 初始化你的客户端：Kafka producer / gRPC channel / webhook poster 等
        ...

    def create_ticket(self, *, user_id, subject="", description="",
                      priority="normal", transcript=None) -> Ticket:
        # TODO 用你自己的协议发送创建工单消息
        # 例：self._kafka.send("ticket.create", {...})
        ticket_id = Ticket.new_id()
        return Ticket(
            ticket_id=ticket_id,
            user_id=user_id,
            subject=subject,
            description=description,
            priority=priority,
            status=TicketStatusEnum.PENDING.value,
            transcript=list(transcript or []),
            created_at=now_ts(),
        )

    def query_status(self, ticket_id: str) -> Optional[TicketStatus]:
        # TODO 从你的存储 / API 查询状态
        ...

    def cancel_ticket(self, ticket_id: str, reason: str = "") -> Optional[Ticket]:
        # TODO
        ...

    def overall_status(self) -> OverallStatus:
        return OverallStatus(
            agent_pool_size=-1, available_agents=-1, waiting=-1, connected=-1, capacity=-1
        )

    def list_tickets(self, *, limit=50, status=None) -> List[Ticket]:
        # 看板可用；远程后端如不支持枚举可返回空
        return []


def from_env():
    return UserCustomHandoffClient(
        broker=__import__("os").getenv("HH_BROKER_URL", ""),
    )
```

---

## 6. inbound 回调对接（`ticket.status_callback`）

如果用户工单系统支持主动回调，建议启用 inbound 模式：

### 6.1 我方暴露的回调端点

```
POST /api/v1/handoff/callback/ticket-status
Content-Type: application/json
{
  "ticket_id": "WO123",
  "status": "processing",
  "agent_id": "alice"
}
```

返回 `{"code": 0, "message": "ok"}`。

> **注意**：本期 router.py **未实现**该 inbound 端点；使用 inbound 模式需在 user_custom.py 注册 FastAPI route 并自行实现，或在 Phase 4 由 contract-adapt.py 自动生成。

### 6.2 入站字段映射（用户回调字段名不同）

如果用户系统回调时字段名为 `id` / `state` / `operator`，需在 user_custom.py 中加入入站映射：

```python
# 在 router 注册回调端点后调用本方法转换 payload
def _map_inbound(payload: dict) -> dict:
    return {
        "ticket_id": payload.get("id") or payload.get("ticket_id"),
        "status": {"queued": "pending", "in_progress": "processing"}.get(
            payload.get("state"), payload.get("status")
        ),
        "agent_id": payload.get("operator") or payload.get("agent_id"),
    }
```

---

## 7. 切换 / 验证

### 7.1 启用 user_custom

```bash
export HH_ADAPTER=user_custom
# 重启服务后生效
```

### 7.2 单元自检

```bash
python -c "
from capabilities.human_handoff.src.adapters.factory import build_default
c = build_default()
print('adapter:', type(c).__name__)
t = c.create_ticket(user_id='u_test', subject='ping')
print('created:', t.to_dict())
print('queried:', c.query_status(t.ticket_id))
"
```

### 7.3 端到端

```bash
curl -X POST http://localhost:3000/api/v1/handoff/request \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"u_test","reason":"我要投诉"}'
```

---

## 8. 安全清单

- [ ] `HH_REST_BASE_URL` 必须使用 https://（localhost 例外）
- [ ] 默认拒绝私网地址（9.* / 10.* / 172.16-31.* / 192.168.* / 169.254.*）
- [ ] 鉴权 token 仅来自环境变量，**禁止**硬编码到 user_custom.py
- [ ] 远程异常不打印响应体（可能含 PII）
- [ ] 日志中 `Authorization` / `X-Auth-Token` 头自动脱敏（由骨架 `log_redaction` 负责）
