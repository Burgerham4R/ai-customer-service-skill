# python-backend 适配器

将 conversation-core 骨架以反向代理形式接入 Python 后端。

| 框架 | 模板 | 默认目标 |
|:---|:---|:---|
| Flask    | `flask.py.tpl`    | `voice_agent_proxy.py` (Blueprint) |
| FastAPI  | `fastapi.py.tpl`  | `voice_agent_proxy.py` (APIRouter) |
| Django   | `django.py.tpl`   | `voice_agent_proxy/views.py` (function view) |

## 配置

| 环境变量 | 默认 | 说明 |
|:---|:---|:---|
| `SKELETON_BASE_URL` | `http://localhost:3000` | 骨架地址 |
| `API_PREFIX`        | `/api/v1`             | 骨架前缀 |
| `ROUTE_PREFIX`      | `/voice-agent`         | 自身挂载路径 |

## 注意

- Django 模板使用了 `@csrf_exempt`，仅适合反向代理场景；如需 CSRF，自行接入 DRF。
- FastAPI 模板基于 `httpx.AsyncClient`，可与骨架的异步链路对齐。
