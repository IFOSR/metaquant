"""Tests for attachment parsing (text paths; PDF/DOCX need the real libs)."""

from __future__ import annotations

import pytest
from pytest import MonkeyPatch

from quant_platform.research.attachment import (
    AttachmentParseError,
    extract_attachment,
    parse_attachment,
    resolve_material,
)


def test_parse_plain_text() -> None:
    assert parse_attachment("report.txt", b"hello world") == "hello world"


def test_parse_markdown() -> None:
    assert parse_attachment("report.md", b"# title\nbody") == "# title\nbody"


def test_parse_csv() -> None:
    assert parse_attachment("data.csv", b"a,b\n1,2\n") == "a,b\n1,2"


def test_reject_unsupported_type() -> None:
    with pytest.raises(AttachmentParseError):
        parse_attachment("report.xlsx", b"data")


def test_extract_attachment_text() -> None:
    kind, text = extract_attachment("report.txt", b"buy on cross")
    assert kind == "text"
    assert text == "buy on cross"


def test_extract_attachment_image_reference() -> None:
    """图片附件：记录引用，抽取文本为降级空串（无供应商时）。"""
    kind, text = extract_attachment("chart.png", b"\x89PNG\r\n\x1a\n" + b"x" * 16)
    assert kind == "image"
    assert text == ""


def test_extract_attachment_sniffs_image_magic() -> None:
    """无扩展名但魔数为 PNG 的附件按图片处理。"""
    kind, _text = extract_attachment("chart", b"\x89PNG\r\n\x1a\n" + b"x" * 16)
    assert kind == "image"


def test_extract_image_text_uses_vision_provider(monkeypatch: MonkeyPatch) -> None:
    """图片交给多模态视觉模型「看图理解」，返回抽取文本。"""
    import quant_platform.research.attachment as attachment

    def fake_vision(content: bytes, media_type: str, prompt: str) -> str:
        assert media_type == "image/png"
        assert prompt
        return "图：600000 均线金叉信号"

    monkeypatch.setattr(attachment, "_deepseek_vision", fake_vision)
    kind, text = extract_attachment("chart.png", b"\x89PNG\r\n\x1a\n" + b"x" * 16)
    assert kind == "image"
    assert text == "图：600000 均线金叉信号"


def test_extract_image_text_falls_back_across_providers(
    monkeypatch: MonkeyPatch,
) -> None:
    """第一家失败降级到第二家；全部失败返回空串。"""
    import quant_platform.research.attachment as attachment

    calls: list[str] = []

    from collections.abc import Callable

    def boom(name: str) -> Callable[[bytes, str, str], str]:
        def _provider(content: bytes, media_type: str, prompt: str) -> str:
            calls.append(name)
            raise attachment.AttachmentParseError("no key")

        return _provider

    monkeypatch.setattr(attachment, "_deepseek_vision", boom("deepseek"))
    monkeypatch.setattr(attachment, "_moonshot_vision", boom("moonshot"))
    monkeypatch.setattr(attachment, "_zhipu_vision", boom("zhipu"))
    kind, text = extract_attachment("chart.png", b"\x89PNG\r\n\x1a\n" + b"x" * 16)
    assert kind == "image"
    assert text == ""
    assert calls == ["deepseek", "moonshot", "zhipu"]


def test_extract_attachment_degrades_on_parse_error() -> None:
    """解析失败不阻断：抽取为可读错误文本。"""
    kind, text = extract_attachment("bad.xlsx", b"data")
    assert kind == "text"
    assert "解析失败" in text


def test_reject_oversized() -> None:
    oversized = b"x" * (20 * 1024 * 1024 + 1)
    with pytest.raises(AttachmentParseError):
        parse_attachment("report.txt", oversized)


def test_resolve_material_fetches_url_in_paper(monkeypatch: MonkeyPatch) -> None:
    def fake_fetch(url: str) -> str:
        return "Fetched body about momentum"

    monkeypatch.setattr(
        "quant_platform.research.attachment.fetch_url_text",
        fake_fetch,
    )
    material, prompt = resolve_material("https://example.com/report", "extract")
    assert material == "Fetched body about momentum"
    assert prompt == "extract"


def test_resolve_material_fetches_url_in_prompt(monkeypatch: MonkeyPatch) -> None:
    def fake_fetch(url: str) -> str:
        return "Fetched body"

    monkeypatch.setattr(
        "quant_platform.research.attachment.fetch_url_text",
        fake_fetch,
    )
    material, prompt = resolve_material("", "请看 https://example.com/report 提取因子")
    assert "Fetched body" in material
    assert prompt is not None and prompt.startswith("请看")
