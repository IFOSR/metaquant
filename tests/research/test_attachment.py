"""Tests for attachment parsing (text paths; PDF/DOCX need the real libs)."""

from __future__ import annotations

import pytest

from quant_platform.research.attachment import (
    AttachmentParseError,
    parse_attachment,
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
