"""Parse uploaded research attachments (PDF / Word / plain text) into text.

The extracted text feeds the same agent pipeline as a pasted report: the
agent reads it as the research material and proposes a factor.
"""

from __future__ import annotations

import html as html_module
import io
import re
from urllib.parse import urlparse

import httpx

_ATTACHMENT_LIMIT_BYTES = 20 * 1024 * 1024  # 20 MiB
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


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


def fetch_url_text(url: str) -> str:
    """Fetch a URL and extract its readable text (HTML tags stripped)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AttachmentParseError(f"invalid URL: {url}")
    try:
        response = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (quant-research)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AttachmentParseError(f"failed to fetch URL: {exc}") from exc
    text = _html_to_text(response.text)
    if len(text) < 200:
        raise AttachmentParseError("URL returned too little text")
    return text


def resolve_material(
    paper_text: str,
    user_prompt: str | None,
) -> tuple[str, str | None]:
    """If the input contains a URL, fetch its body as the research material.

    Returns ``(material, prompt)`` where ``material`` is the text the agent
    should read.  The user's prompt is preserved unchanged.
    """
    trimmed = paper_text.strip()
    if trimmed.startswith(("http://", "https://")) and " " not in trimmed:
        return fetch_url_text(trimmed), user_prompt
    if user_prompt:
        urls = _URL_PATTERN.findall(user_prompt)
        if urls:
            fetched: list[str] = []
            for url in urls:
                try:
                    fetched.append(fetch_url_text(url.rstrip(".,;:!?)")))
                except AttachmentParseError:
                    continue
            if fetched:
                base = trimmed if trimmed else ""
                joined = "\n\n".join(fetched)
                return f"{base}\n\n{joined}".strip(), user_prompt
    return paper_text, user_prompt


def _html_to_text(html_text: str) -> str:
    without_blocks = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>",
        " ",
        html_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    without_tags = re.sub(r"<[^>]+>", " ", without_blocks)
    unescaped = html_module.unescape(without_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


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
