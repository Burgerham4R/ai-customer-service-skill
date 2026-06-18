"""骨架核心链路单元测试。

验证目标：
  - 三把 Key 配置封装从环境变量正确加载
  - I/O 模态的通道选择与降级策略生效
  - 日志脱敏过滤器对常见敏感字段执行掩码
  - UserSig 生成器在合法输入下产出非空、长度合理的签名
  - 骨架源码不含业务硬编码（FAQ / 行业 prompt 等）
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent
sys.path.insert(0, str(_CORE))

from src.credentials import load_from_env  # noqa: E402
from src.log_filter import RedactingFilter  # noqa: E402
from src.modality import Channel, IoModality, from_dict  # noqa: E402
from src.usersig import gen_user_sig  # noqa: E402


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------
def test_credentials_from_env(monkeypatch):
    monkeypatch.setenv("TENCENT_CLOUD_SECRET_ID", "AKID_xxx")
    monkeypatch.setenv("TENCENT_CLOUD_SECRET_KEY", "secret_xxx")
    monkeypatch.setenv("TRTC_SDK_APP_ID", "1400000000")
    monkeypatch.setenv("TRTC_SDK_SECRET_KEY", "trtc_secret")
    monkeypatch.setenv("LLM_API_KEY", "sk-xxx")

    cred = load_from_env()
    assert cred.fully_configured is True
    assert cred.tencent_cloud.secret_id == "AKID_xxx"
    assert cred.trtc.sdk_app_id == 1400000000
    assert cred.llm.model == "gpt-4o-mini"  # default
    assert cred.missing() == []


def test_credentials_missing(monkeypatch):
    for k in (
        "TENCENT_CLOUD_SECRET_ID", "TENCENT_CLOUD_SECRET_KEY",
        "TRTC_SDK_APP_ID", "TRTC_SDK_SECRET_KEY", "LLM_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    cred = load_from_env()
    assert cred.fully_configured is False
    assert set(cred.missing()) == {"tencent_cloud", "trtc", "llm"}


# ---------------------------------------------------------------------------
# modality
# ---------------------------------------------------------------------------
def test_modality_default_resolve():
    mod = IoModality()
    assert mod.resolve_input_channel(voice_available=True) == Channel.VOICE_INPUT
    assert mod.resolve_output_channel(voice_available=True) == Channel.VOICE_OUTPUT


def test_modality_fallback_to_text_when_voice_unavailable():
    mod = IoModality()
    assert mod.resolve_input_channel(voice_available=False) == Channel.TEXT_INPUT
    assert mod.resolve_output_channel(voice_available=False) == Channel.TEXT_OUTPUT


def test_modality_text_only_scenario():
    mod = from_dict(
        {
            "voice_input": {"enabled": False},
            "voice_output": {"enabled": False},
            "text_input": {"enabled": True},
            "text_output": {"enabled": True},
        }
    )
    assert mod.resolve_input_channel(voice_available=True) == Channel.TEXT_INPUT
    assert mod.resolve_output_channel(voice_available=True) == Channel.TEXT_OUTPUT


def test_modality_all_disabled_raises():
    mod = from_dict(
        {
            "voice_input": {"enabled": False},
            "voice_output": {"enabled": False},
            "text_input": {"enabled": False},
            "text_output": {"enabled": False},
        }
    )
    with pytest.raises(RuntimeError):
        mod.resolve_input_channel(voice_available=False)


# ---------------------------------------------------------------------------
# log redaction (P0 security)
# ---------------------------------------------------------------------------
def test_log_redacting_filter():
    rec = logging.LogRecord(
        name="t", level=logging.INFO, pathname="", lineno=1,
        msg="boot with secret_key=ABCDEFGHIJKLMNOP and api_key: sk-1234567890abcdef",
        args=(), exc_info=None,
    )
    flt = RedactingFilter()
    assert flt.filter(rec) is True
    masked = rec.getMessage()
    assert "ABCDEFGHIJKLMNOP" not in masked
    assert "sk-1234567890abcdef" not in masked
    assert "secret_key" in masked  # 字段名保留
    assert "api_key" in masked


# ---------------------------------------------------------------------------
# usersig
# ---------------------------------------------------------------------------
def test_usersig_basic():
    sig = gen_user_sig(
        sdk_app_id=1400000000,
        sdk_secret_key="dummy_secret_for_unit_test",
        user_id="user_123",
        expire_seconds=60,
    )
    assert isinstance(sig, str) and len(sig) > 32
    # base64url 字符集（TRTC 自定义 + -> *、/ -> -、= -> _）
    allowed = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*-_"
    )
    assert all(c in allowed for c in sig)


def test_usersig_input_validation():
    with pytest.raises(ValueError):
        gen_user_sig(0, "k", "user")
    with pytest.raises(ValueError):
        gen_user_sig(1400000000, "", "user")
    with pytest.raises(ValueError):
        gen_user_sig(1400000000, "k", "")


# ---------------------------------------------------------------------------
# 骨架纯净性：源码不应包含行业关键词（电商/订单/餐厅/订位等）。
# 检查目标：剥离注释与 docstring 之后的"实际代码"中不得出现业务硬编码。
# ---------------------------------------------------------------------------
import ast
import io
import tokenize


def _strip_comments_and_docstrings(source: str) -> str:
    """返回剥离注释与 docstring 后的代码片段。"""
    # 1) 去掉 # 注释
    out_tokens = []
    g = tokenize.generate_tokens(io.StringIO(source).readline)
    for tok_type, tok_val, *_ in g:
        if tok_type == tokenize.COMMENT:
            continue
        out_tokens.append((tok_type, tok_val))
    no_comments = tokenize.untokenize(out_tokens)
    # 2) 去掉 docstring：用 AST 重写为不含 Expr(Constant(str)) 的版本
    try:
        tree = ast.parse(no_comments)
    except SyntaxError:
        return no_comments

    class _DocstringRemover(ast.NodeTransformer):
        def _strip(self, node):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:] or [ast.Pass()]
            return node

        def visit_Module(self, node):
            self.generic_visit(node)
            return self._strip(node)

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            return self._strip(node)

        def visit_AsyncFunctionDef(self, node):
            self.generic_visit(node)
            return self._strip(node)

        def visit_ClassDef(self, node):
            self.generic_visit(node)
            return self._strip(node)

    cleaned = _DocstringRemover().visit(tree)
    ast.fix_missing_locations(cleaned)
    return ast.unparse(cleaned)


def test_skeleton_purity_no_business_keywords():
    forbidden = [
        "电商", "订单", "物流", "餐厅", "订位", "金融", "医疗", "保险",
        "FAQ",
    ]
    src_dir = _CORE / "src"
    offenders = []
    for py in src_dir.glob("*.py"):
        raw = py.read_text(encoding="utf-8")
        code_only = _strip_comments_and_docstrings(raw)
        for kw in forbidden:
            if kw in code_only:
                offenders.append((py.name, kw))
    assert offenders == [], f"骨架包含业务关键词: {offenders}"
