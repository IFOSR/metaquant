"""Tests for attachment parsing (text paths; PDF/DOCX need the real libs)."""

from __future__ import annotations

import pytest
from pytest import MonkeyPatch

from quant_platform.research.attachment import (
    AttachmentParseError,
    parse_attachment,
    resolve_material,
)


def test_parse_plain_text() -> None:
    assert parse_attachment("report.txt", b"hello world") == "hello world"


def test_parse_markdown() -> None:
    assert parse_attachment("report.md", b"# title\nbody") == "# title\nbody"


def test_reject_unsupported_type() -> None:
    with pytest.raises(AttachmentParseError):
        parse_attachment("report.xlsx", b"data")


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
