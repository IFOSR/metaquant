"""Three-file code bundle (code-bundle/v1).

The agent's second-stage artifact: ``model.py`` / ``train.py`` / ``infer.py``,
each content-addressed, plus a bundle manifest that pins the generating spec.
The bundle is the unit of freezing: once written, it is immutable.

The contract is enforced here, not at run time: each file must parse and expose
its required top-level symbol, so a malformed bundle is rejected before it ever
reaches the sandbox.
"""

from __future__ import annotations

import ast
import hashlib
import json
from typing import Any

BUNDLE_SCHEMA = "code-bundle/v1"

REQUIRED_FILES: frozenset[str] = frozenset({"model.py", "train.py", "infer.py"})

_REQUIRED_SYMBOLS: dict[str, frozenset[str]] = {
    "model.py": frozenset({"build_model"}),
    "train.py": frozenset({"train"}),
    "infer.py": frozenset({"infer"}),
}


class CodeBundleError(ValueError):
    """Raised when generated code violates the three-file contract."""


def content_hash(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def validate_bundle_contract(files: dict[str, bytes]) -> None:
    """Reject a bundle that is not exactly three contract-conformant files."""
    if set(files) != REQUIRED_FILES:
        missing = sorted(REQUIRED_FILES - set(files))
        extra = sorted(set(files) - REQUIRED_FILES)
        raise CodeBundleError(
            f"bundle must contain exactly {sorted(REQUIRED_FILES)} "
            f"(missing={missing}, extra={extra})"
        )
    for name, payload in files.items():
        try:
            tree = ast.parse(payload, filename=name)
        except SyntaxError as exc:
            raise CodeBundleError(f"{name} failed to parse: {exc}") from exc
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        required = _REQUIRED_SYMBOLS[name]
        missing_symbols = required - defined
        if missing_symbols:
            raise CodeBundleError(
                f"{name} must define {sorted(required)}, "
                f"missing {sorted(missing_symbols)}"
            )


def build_code_bundle(files: dict[str, bytes], *, spec_hash: str) -> dict[str, Any]:
    """Produce the content-addressed manifest for a validated code bundle."""
    validate_bundle_contract(files)
    if not spec_hash.startswith("sha256:") or len(spec_hash) != 71:
        raise CodeBundleError("spec_hash must be a sha256:<hex> address")
    return {
        "schema_version": BUNDLE_SCHEMA,
        "spec_hash": spec_hash,
        "files": {
            name: {
                "sha256": content_hash(payload),
                "size_bytes": len(payload),
                "media_type": "text/x-python",
            }
            for name, payload in sorted(files.items())
        },
    }


def bundle_hash(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
