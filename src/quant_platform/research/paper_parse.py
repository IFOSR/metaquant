"""Parse a research paper into a structured brief draft (LLM-assisted).

The parser is an amplifier, not an authority: it translates free-form paper
text into the structured ``BriefContent`` contract so the researcher does not
have to know the schema.  The researcher must still review and freeze the
result.  It never writes to the deterministic kernel.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from quant_platform.research.schemas import BriefContent

_SYSTEM_PROMPT = """You extract testable factor-research hypotheses
from quantitative-finance papers.

Output a single JSON object matching this schema:
{
  "hypothesis": "one sentence: the factor and its predicted effect",
  "economic_mechanism": "why the effect should exist (behavioral or structural)",
  "expected_direction": "POSITIVE | NEGATIVE | NON_MONOTONIC | UNKNOWN",
  "falsification_conditions": ["what result would prove the hypothesis wrong"],
  "allowed_data_domains": ["data domains allowed, e.g. formal.market.eod"],
  "forbidden_data_domains": ["data domains forbidden"],
  "constraints": ["universe or timing constraints"],
  "evidence_ref_ids": [],
  "uncertainties": ["known weaknesses or regime dependence"]
}

Rules:
- Use the paper's actual factor definition; do not invent a new factor.
- expected_direction must be one of POSITIVE, NEGATIVE, NON_MONOTONIC, UNKNOWN.
- falsification_conditions must be concrete and measurable
  (e.g. "mean rank IC is not significantly positive").
- Keep enum and data-domain values as literal strings.
"""

_Complete = Callable[[str, str | None], str]


class PaperParseError(RuntimeError):
    """Raised when the paper cannot be translated into a brief draft."""


def parse_paper_to_brief(
    paper_text: str,
    *,
    complete: _Complete | None = None,
) -> BriefContent:
    """Translate free-form paper text into a structured brief draft.

    ``complete`` is injectable for tests; it defaults to the DeepSeek REST
    client and receives (paper_text, hint).
    """
    runner = complete or _deepseek_complete
    raw = runner(paper_text, None)
    data = _extract_json(raw)
    try:
        return BriefContent.model_validate(data)
    except Exception as first_error:  # pydantic.ValidationError
        raw = runner(
            paper_text,
            f"Your previous output failed validation: {first_error}. "
            "Return only valid JSON matching the schema.",
        )
        data = _extract_json(raw)
        return BriefContent.model_validate(data)


def _deepseek_complete(paper_text: str, hint: str | None) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise PaperParseError(
            "DEEPSEEK_API_KEY is not configured; cannot parse papers"
        )
    user_prompt = f"Paper text:\n\n{paper_text}"
    if hint:
        user_prompt += f"\n\n{hint}"
    payload = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        response = httpx.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PaperParseError(f"DeepSeek request failed: {exc}") from exc
    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PaperParseError("unexpected DeepSeek response shape") from exc
    if not isinstance(content, str):
        raise PaperParseError("unexpected DeepSeek response shape")
    return content


def _extract_json(raw: str) -> Mapping[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").rstrip("`").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PaperParseError(f"model returned invalid JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise PaperParseError("model output must be a JSON object")
    return data
