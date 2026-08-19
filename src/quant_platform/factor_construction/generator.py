"""Agent-driven factor construction: report -> build spec -> code bundle.

Two non-interactive agent stages, both with an injectable runner (same backend
selection as ``research.factor_extract``: pi / DeepSeek / Zhipu):

1. ``extract_build_spec`` — translate a research report into a
   ``FactorBuildSpec`` (research intent, not a formula).
2. ``generate_code_bundle`` — translate a frozen spec into the three-file code
   bundle (model.py / train.py / infer.py) and return its content-addressed
   manifest.

The StableAlpha report is the canonical example: the prompt encodes the core
methodology (label = style-residualized forward vwap return, inverse-size sample
weighting, style neutralization against size/volatility/reversal/liquidity).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from quant_platform.factor_construction.artifacts import (
    CodeBundleError,
    build_code_bundle,
    validate_bundle_contract,
)
from quant_platform.factor_construction.spec import FactorBuildSpec, build_spec_hash
from quant_platform.research.factor_extract import (
    FactorExtractionError,
    Runner,
    _extract_json,
    default_runner,
)

_MAX_CODE_ROUNDS = 3

_SPEC_SYSTEM_PROMPT = """You are a quantitative factor researcher translating a
research report into a *model build spec* (not a factor formula). A deep-learning
factor is defined by its construction recipe, not a closed-form expression.

Return only a JSON object (no markdown fences) with exactly this shape:
{
  "factor_id": "lowercase identifier, e.g. cn_a.stable_alpha_dl",
  "factor_name": "short human-readable name",
  "market": "CN_A | CN_COMMODITY_FUTURES",
  "universe_ref": "e.g. universe://csi-all-pit/v1",
  "inputs": ["open", "high", "low", "close", "volume", "amount", "vwap"],
  "label": {
    "name": "future_21d_vwap_return",
    "price_field": "vwap",
    "horizon": 21,
    "return_type": "simple",
    "style_neutralize": ["size", "volatility", "reversal", "liquidity"]
  },
  "architecture": "MLP | LSTM | TRANSFORMER | LINEAR",
  "style_neutralize": ["size", "volatility", "reversal", "liquidity"],
  "sample_weighting": "EQUAL | INVERSE_SIZE | CAP_WEIGHTED",
  "expected_direction": "POSITIVE | NEGATIVE | NON_MONOTONIC | UNKNOWN",
  "hyperparameters": {},
  "evidence_ref_ids": []
}

Rules:
- Use the report's actual construction recipe; do not invent one.
- label.price_field must appear in inputs.
- If the report residualizes the training label against styles, put those styles
  in label.style_neutralize (this is the key "pure alpha" step).
- If the report down-weights small-cap / equal-weighted samples, set
  sample_weighting accordingly.
- style_neutralize (model output) lists the styles to neutralize at inference.
"""


def extract_build_spec(
    paper_text: str,
    *,
    runner: Runner | None = None,
    user_prompt: str | None = None,
) -> FactorBuildSpec:
    """Translate a report into a build spec via the agent."""
    complete = runner or default_runner(system_prompt=_SPEC_SYSTEM_PROMPT)
    material = (
        f"User request: {user_prompt}\n\nReport text:\n\n{paper_text}"
        if user_prompt
        else f"Report text:\n\n{paper_text}"
    )
    raw = complete(material)
    try:
        return _parse_spec(raw)
    except (FactorExtractionError, ValidationError):
        raw = complete(
            "Your previous JSON failed validation. Return only valid JSON matching "
            "the build-spec schema.\n\nPrevious output: " + raw[:2000]
        )
        return _parse_spec(raw)


def _parse_spec(raw: str) -> FactorBuildSpec:
    data = _extract_json(raw)
    return FactorBuildSpec.model_validate(dict(data))


_CODE_SYSTEM_PROMPT = """You are a PyTorch model builder. Generate exactly three
Python files from a build spec. Output them in this exact format, no extra text:

# file: model.py
```python
def build_model(hyperparams: dict):
    # returns a PyTorch nn.Module (or equivalent) with .forward(x)
    ...
```

# file: train.py
```python
def train(data, spec: dict):
    # data is a PITFrame; train and return serializable weights (e.g. state_dict)
    ...
```

# file: infer.py
```python
def infer(data, weights):
    # data is a PITFrame; return a list/array of factor values aligned to rows
    ...
```

Hard rules:
- model.py MUST define top-level `def build_model(hyperparams)`.
- train.py MUST define top-level `def train(data, spec)`.
- infer.py MUST define top-level `def infer(data, weights)`.
- Features come only from `data.data` (a DataFrame returned by
  quant_platform.ml.load_pit_frame); labels come only from
  quant_platform.ml.load_label_frame.
- No network imports, no subprocess, no os, no file writing.
"""


def _code_prompt(spec: FactorBuildSpec) -> str:
    spec_payload = json.dumps(
        spec.model_dump(mode="json"), ensure_ascii=False, indent=2
    )
    return f"{_CODE_SYSTEM_PROMPT}\n\nBuild spec:\n{spec_payload}"


def _generate_once(
    spec: FactorBuildSpec,
    complete: Runner,
    *,
    hint: str = "",
) -> tuple[dict[str, bytes], dict[str, Any]]:
    suffix = f"\n\nPrevious attempt failed: {hint}" if hint else ""
    raw = complete(_code_prompt(spec) + suffix)
    files = _parse_code_files(raw)
    validate_bundle_contract(files)
    manifest = build_code_bundle(files, spec_hash=build_spec_hash(spec))
    return files, manifest


def generate_code_bundle(
    spec: FactorBuildSpec,
    *,
    runner: Runner | None = None,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Translate a build spec into a validated three-file code bundle."""
    complete = runner or default_runner(
        system_prompt=_CODE_SYSTEM_PROMPT, json_mode=False
    )
    last_error = ""
    for _ in range(_MAX_CODE_ROUNDS):
        try:
            return _generate_once(spec, complete, hint=last_error)
        except (CodeBundleError, ValueError) as exc:
            last_error = str(exc)
    raise CodeBundleError(
        f"code generation failed after {_MAX_CODE_ROUNDS} rounds: {last_error}"
    )


def generate_and_smoke(
    spec: FactorBuildSpec,
    *,
    agent_runner: Runner | None = None,
    sandbox: Any | None = None,
    max_rounds: int = _MAX_CODE_ROUNDS,
) -> tuple[dict[str, bytes], dict[str, Any], Any]:
    """Generate a bundle and smoke-run it, feeding errors back to the agent."""
    from quant_platform.factor_construction.runner import (
        SubprocessSandboxRunner,
        smoke_bundle,
    )

    complete = agent_runner or default_runner(
        system_prompt=_CODE_SYSTEM_PROMPT, json_mode=False
    )
    active_sandbox = sandbox or SubprocessSandboxRunner()
    last_error = ""
    for _ in range(max_rounds):
        try:
            files, manifest = _generate_once(spec, complete, hint=last_error)
        except (CodeBundleError, ValueError) as exc:
            last_error = str(exc)
            continue
        result = smoke_bundle(files, active_sandbox)
        if result.exit_code == 0 and not result.timed_out:
            return files, manifest, result
        last_error = (
            f"smoke run failed (exit {result.exit_code}): "
            f"{result.stderr.strip()[:2000]}"
        )
    raise CodeBundleError(
        f"generate + smoke failed after {max_rounds} rounds: {last_error}"
    )


_CODE_FILE_RE = re.compile(
    r"# file:\s*(?P<name>[A-Za-z0-9_.\-]+)\s*\n"
    r"```(?:python)?\s*\n(?P<body>.*?)```",
    re.DOTALL,
)


def _parse_code_files(raw: str) -> dict[str, bytes]:
    """Parse ``# file: X`` fenced blocks into a filename -> bytes mapping."""
    matches = list(_CODE_FILE_RE.finditer(raw))
    if not matches:
        raise ValueError(
            "no code files found: expected '# file: model.py' + python fences"
        )
    files: dict[str, bytes] = {}
    for match in matches:
        name = match.group("name")
        body = match.group("body").strip() + "\n"
        if name in files:
            raise ValueError(f"duplicate file block: {name}")
        files[name] = body.encode()
    return files
