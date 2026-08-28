"""Parse uploaded research attachments (PDF / Word / plain text) into text.

The extracted text feeds the same agent pipeline as a pasted report: the
agent reads it as the research material and proposes a factor.
"""

from __future__ import annotations

import base64
import html as html_module
import io
import os
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
    if lower.endswith((".txt", ".md", ".markdown", ".csv")):
        return content.decode("utf-8", errors="replace").strip()
    raise AttachmentParseError(
        f"unsupported attachment type: {filename} "
        "(supported: .pdf, .docx, .txt, .md, .csv)"
    )


def extract_attachment(filename: str, content: bytes) -> tuple[str, str]:
    """把上传附件抽取成 (kind, extracted_text)。

    文本（PDF/DOCX/TXT/MD/CSV）直接抽取纯文本；图片交给多模态视觉模型
    「看图理解」（DeepSeek vision / Kimi K3 / Zhipu glm-4v），失败降级为空串
    （图片仍以 object_key 引用随对话留存）。
    """
    if _looks_like_image(filename, content):
        return "image", _extract_image_text(filename, content)
    try:
        return "text", parse_attachment(filename, content)
    except AttachmentParseError as exc:
        # 解析失败不阻断对话：把错误作为抽取文本交给 Agent 自行判断。
        return "text", f"[附件解析失败：{exc}]"


def _looks_like_image(filename: str, content: bytes) -> bool:
    lower = filename.lower()
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
        return True
    # 无扩展名或未知扩展名时，用魔数嗅探（PNG/JPEG/GIF）。
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if content.startswith(b"\xff\xd8\xff"):
        return True
    return content.startswith((b"GIF87a", b"GIF89a"))


def _guess_media_type(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".bmp"):
        return "image/bmp"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return "image/png"


_VISION_PROMPT = (
    "你是一个量化研究助理。请仔细阅读这张图片，提取其中与量化研究相关的全部"
    "信息：文字、表格数据、图表数值与结论。用简洁的中文输出提取到的内容，保留"
    "关键数字与单位；如果是图表，描述横纵轴含义与大致趋势。只输出提取到的内容，"
    "不要添加你的评价或建议。"
)


def _openai_vision(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    content: bytes,
    media_type: str,
    prompt: str,
) -> str:
    """OpenAI 兼容的多模态 chat/completions 请求：base64 图片 + 文本 prompt。"""
    data_url = f"data:{media_type};base64,{base64.b64encode(content).decode()}"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0,
    }
    response = httpx.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    try:
        message = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AttachmentParseError("unexpected vision response shape") from exc
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = [
            str(part.get("text", ""))
            for part in message
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    raise AttachmentParseError("unexpected vision response shape")


def _deepseek_vision(content: bytes, media_type: str, prompt: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise AttachmentParseError("DEEPSEEK_API_KEY is not configured")
    model = (
        os.environ.get("DEEPSEEK_VISION_MODEL", "").strip()
        or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()
    )
    return _openai_vision(
        endpoint="https://api.deepseek.com/chat/completions",
        api_key=api_key,
        model=model,
        content=content,
        media_type=media_type,
        prompt=prompt,
    )


def _moonshot_vision(content: bytes, media_type: str, prompt: str) -> str:
    api_key = os.environ.get("MOONSHOT_API_KEY", "").strip()
    if not api_key:
        raise AttachmentParseError("MOONSHOT_API_KEY is not configured")
    model = os.environ.get("MOONSHOT_MODEL", "kimi-k3").strip()
    base = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1").strip()
    return _openai_vision(
        endpoint=f"{base.rstrip('/')}/chat/completions",
        api_key=api_key,
        model=model,
        content=content,
        media_type=media_type,
        prompt=prompt,
    )


def _zhipu_vision(content: bytes, media_type: str, prompt: str) -> str:
    api_key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not api_key:
        raise AttachmentParseError("ZHIPU_API_KEY is not configured")
    return _openai_vision(
        endpoint="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        api_key=api_key,
        model=os.environ.get("ZHIPU_VISION_MODEL", "glm-4v-plus").strip(),
        content=content,
        media_type=media_type,
        prompt=prompt,
    )


def _extract_image_text(filename: str, content: bytes) -> str:
    """图片 → 文本：优先多模态视觉模型「看图理解」，逐供应商降级。

    顺序：DeepSeek vision → Kimi (Moonshot) K3 → Zhipu glm-4v；任一失败降级
    到下一家，全部失败返回空串（图片仍以 object_key 引用留存，不阻断对话）。
    """
    media_type = _guess_media_type(filename, content)
    providers = (_deepseek_vision, _moonshot_vision, _zhipu_vision)
    for provider in providers:
        try:
            text = provider(content, media_type, _VISION_PROMPT).strip()
        except (AttachmentParseError, httpx.HTTPError, ValueError):
            continue
        if text:
            return text
    return ""


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
