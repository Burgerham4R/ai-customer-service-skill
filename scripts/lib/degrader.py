"""三级降级策略决策机。

输入：技术栈检测结果 + 适配器执行结果。
输出：降级级别（L1 / L2 / L3）+ 用户引导内容路径。

| 级别 | 触发条件                                  | Agent 行为                                |
|:----:|:------------------------------------------|:------------------------------------------|
| L1   | tech_stack 命中 adapter 且代码生成成功    | 直接写入用户项目                           |
| L2   | tech_stack 命中但代码生成失败/有冲突      | 输出 INTEGRATION_GUIDE.md 模板 + 模板代码 |
| L3   | tech_stack 未识别或不在支持列表           | 输出通用 REST API 文档 + SDK 包安装命令   |
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class DegradeLevel(str, Enum):
    L1_AUTO = "L1"
    L2_GUIDED = "L2"
    L3_MANUAL = "L3"


@dataclass
class DegradeDecision:
    level: DegradeLevel
    reason: str
    adapter: Optional[str] = None
    tech_stack: Optional[str] = None
    artifacts: List[str] = None        # type: ignore[assignment]
    remediation: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "reason": self.reason,
            "tech_stack": self.tech_stack,
            "adapter": self.adapter,
            "artifacts": self.artifacts or [],
            "remediation": self.remediation,
        }


def decide(
    tech_stack: Optional[str],
    adapter: Optional[str],
    code_gen_ok: bool,
    *,
    fallback: Optional[Dict] = None,
    code_gen_error: str = "",
) -> DegradeDecision:
    """根据上游信号产出降级决策。

    Parameters
    ----------
    tech_stack
        stack_detector.detect() 的 ``primary`` 字段。
    adapter
        manifest.integration.auto_adapters 中匹配到的适配器名。None 表示不支持。
    code_gen_ok
        L1 阶段实际尝试生成代码后的成功标志。
    fallback
        manifest.integration.fallback 节点内容（提供 guided_templates / manual_api）。
    code_gen_error
        L1 失败时的错误描述（写入 reason）。
    """
    fb = fallback or {}
    if tech_stack and adapter and code_gen_ok:
        return DegradeDecision(
            level=DegradeLevel.L1_AUTO,
            reason="tech stack matched and code generation succeeded",
            tech_stack=tech_stack,
            adapter=adapter,
            artifacts=[],
            remediation="",
        )
    if tech_stack and adapter and not code_gen_ok:
        templates = list(fb.get("guided_templates") or [])
        return DegradeDecision(
            level=DegradeLevel.L2_GUIDED,
            reason=code_gen_error
            or "tech stack matched but code generation failed; provide manual guide",
            tech_stack=tech_stack,
            adapter=adapter,
            artifacts=templates,
            remediation=(
                "Agent 输出 INTEGRATION_GUIDE.md：包含模板代码 + 注入位置说明，"
                "用户按文档手工完成集成"
            ),
        )
    # L3：未识别或无适配器
    manual = fb.get("manual_api") or {}
    artifacts = []
    if manual.get("rest_endpoint"):
        artifacts.append(f"rest_endpoint:{manual['rest_endpoint']}")
    for sdk in manual.get("sdk_packages") or []:
        for ecos, pkg in sdk.items():
            artifacts.append(f"sdk:{ecos}:{pkg}")
    return DegradeDecision(
        level=DegradeLevel.L3_MANUAL,
        reason=(
            "tech stack not recognised or not in supported list"
            if not tech_stack
            else f"no adapter for tech_stack={tech_stack}"
        ),
        tech_stack=tech_stack,
        adapter=None,
        artifacts=artifacts,
        remediation=(
            "Agent 输出通用 REST API 接入文档（基础地址 /api/v1）"
            " + SDK 包安装命令，由集成方手动接入。"
        ),
    )


# ---------------------------------------------------------------------------
# I/O 模态降级矩阵：4 通道独立开关 → 16 种组合，确保每种组合都有可用路径
# ---------------------------------------------------------------------------
def channel_combinations_matrix() -> List[Dict]:
    """返回 16 种通道组合的降级路径（供文档与测试使用）。"""
    rows: List[Dict] = []
    channels = ["voice_input", "text_input", "voice_output", "text_output"]
    for mask in range(16):
        state = {c: bool(mask & (1 << i)) for i, c in enumerate(channels)}
        usable_in = state["voice_input"] or state["text_input"]
        usable_out = state["voice_output"] or state["text_output"]
        if not usable_in and not usable_out:
            verdict = "silent_wait"  # 上层进入静默等待
        elif not usable_in:
            verdict = "output_only_broadcast"
        elif not usable_out:
            verdict = "input_only_logging"
        else:
            primary_in = "voice_input" if state["voice_input"] else "text_input"
            primary_out = "voice_output" if state["voice_output"] else "text_output"
            verdict = f"primary={primary_in}->{primary_out}"
        rows.append({"state": state, "verdict": verdict})
    return rows
