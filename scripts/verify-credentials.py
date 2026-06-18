#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三把 Key 无参数验证脚本（Phase 3 阶段 5 新增）。

设计目标
--------
**AI 主导的 Key 配置流程的"原子工具"**：
1. 由 AI 把用户粘贴的 Key 通过 ``write_to_file`` 写入 ``.env``
2. 由 AI 调 ``python scripts/verify-credentials.py [--type tencent|trtc|llm]``
3. 本脚本**只**从 .env / 环境变量读取，**不**接受任何 Key 作为命令行参数
4. 输出**结构化 JSON** 到 stdout，AI 据此判断 ok / 失败并按 SKILL.md §7.5 应答

输出格式（始终是合法 JSON）::

    单项: {"ok": true,  "type": "tencent", "error": "",     "message": "...", "latency_ms": 320}
    单项: {"ok": false, "type": "trtc",    "error": "E002", "message": "...", "latency_ms": 0}
    全量: {"ok": true,  "type": "all", "items": [ ... ]}

退出码：``0`` 表示全部通过；非零表示有任意失败（便于 shell 判断）。

用法
----
    python3 scripts/verify-credentials.py                  # 验证全部三把
    python3 scripts/verify-credentials.py --type tencent   # 仅腾讯云
    python3 scripts/verify-credentials.py --type trtc      # 仅 TRTC
    python3 scripts/verify-credentials.py --type llm       # 仅 LLM
    python3 scripts/verify-credentials.py --no-deep        # TRTC 跳过 OpenAPI 深度校验

安全约束（红线）
----------------
- 严禁通过命令行参数传递任何 Key（无 --secret-id / --api-key 等参数）
- 严禁在 stdout / stderr 中回显凭证原文
- ``.env`` 由调用方在写入时自行设置权限 600（本脚本不再二次处理）
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

# 抑制第三方库（如 urllib3 / NotOpenSSLWarning）发到 stderr 的告警，
# 保证 stdout 纯 JSON、stderr 静默——AI 解析时无干扰
warnings.filterwarnings("ignore")

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lib import credential_validators as cv  # noqa: E402


def _print_json(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify-credentials",
        description="无参数验证三把 Key（仅从 .env 读取，输出结构化 JSON）",
    )
    parser.add_argument(
        "--type",
        choices=["tencent", "trtc", "llm", "all"],
        default="all",
        help="只验证指定一把 Key；默认 all",
    )
    parser.add_argument(
        "--no-deep",
        action="store_true",
        help="TRTC 跳过 OpenAPI 深度校验，仅做本地 UserSig 自洽",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="可选：指定 .env 路径（默认查找 capabilities/conversation-core/.env）",
    )
    args = parser.parse_args(argv)

    cv.load_dotenv(Path(args.env_file) if args.env_file else None)

    if args.type == "tencent":
        result = cv.validate_tencent()
        _print_json(result.to_dict())
        return 0 if result.ok else 1

    if args.type == "trtc":
        result = cv.validate_trtc(deep=not args.no_deep)
        _print_json(result.to_dict())
        return 0 if result.ok else 1

    if args.type == "llm":
        result = cv.validate_llm()
        _print_json(result.to_dict())
        return 0 if result.ok else 1

    # all
    batch = cv.validate_all()
    _print_json(batch.to_dict())
    return 0 if batch.ok else 1


if __name__ == "__main__":
    sys.exit(main())
