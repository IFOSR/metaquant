"""Parse uploaded research attachments (PDF / Word / plain text) into text.

The extracted text feeds the same agent pipeline as a pasted report: the
agent reads it as the research material and proposes a factor.
"""

from __future__ import annotations

import io

_ATTACHMENT_LIMIT_BYTES = 20 * 1024 * 1024  # 20 MiB


class AttachmentParseError(ValueError):
    """Raised when an attachment cannot be parsed into text."""


def parse_attachment(filename: str, content: bytes) -> str:
    if len(content) > _ATTACHMENT_LIMIT_BYTES:
        raise AttachmentParseError("attachment exceeds the 20 MiB limit")
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _parse_pdf(content)
    if lower.endswith(".docx"):
        return _parse_docx(content)
    if lower.endswith((".txt", ".md", ".markdown")):
        return content.decode("utf-8", errors="replace").strip()
    raise AttachmentParseError(
        f"unsupported attachment type: {filename} "
        "(supported: .pdf, .docx, .txt, .md)"
    )


def _parse_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise AttachmentParseError("pypdf is not installed") from exc
    reader = PdfReader(io.BytesIO(content))
    parts = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(parts).strip()
    if not text:
        raise AttachmentParseError("no extractable text in PDF (scanned image?)")
    return text


def _parse_docx(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise AttachmentParseError("python-docx is not installed") from exc
    document = Document(io.BytesIO(content))
    parts = [paragraph.text for paragraph in document.paragraphs]
    text = "\n\n".join(parts).strip()
    if not text:
        raise AttachmentParseError("no extractable text in document")
    return text
