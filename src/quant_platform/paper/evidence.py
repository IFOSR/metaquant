"""Paper reproduction evidence contracts (G13-001).

Page-level extraction of claims, formulas, and variable mappings from a frozen
PDF. Every artifact is locatable to a page (and optionally a bounding box), so
a conclusion can be traced back to the exact page that supports it.
"""

from __future__ import annotations

from dataclasses import dataclass

from quant_platform.experiments import canonical_hash

_HEX_DIGITS = frozenset("0123456789abcdef")
_VALID_MAPPING_KINDS = frozenset({"exact", "derived", "proxy", "unavailable"})


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError(f"{name} must be a 64-character hex digest")


@dataclass(frozen=True, slots=True)
class PaperClaim:
    claim_id: str
    page: int
    text: str
    bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.claim_id, "claim_id")
        if self.page < 1:
            raise ValueError("page must be positive")
        if not self.text:
            raise ValueError("claim text must not be empty")
        if self.bbox is not None and (
            len(self.bbox) != 4
            or self.bbox[2] < self.bbox[0]
            or self.bbox[3] < self.bbox[1]
        ):
            raise ValueError("bbox must be (x0, y0, x1, y1) with x1 >= x0 and y1 >= y0")

    def payload(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "page": self.page,
            "text": self.text,
            "bbox": list(self.bbox) if self.bbox is not None else None,
        }


@dataclass(frozen=True, slots=True)
class ExtractedFormula:
    formula_id: str
    page: int
    latex: str
    variables: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.formula_id, "formula_id")
        if self.page < 1:
            raise ValueError("page must be positive")
        if not self.latex:
            raise ValueError("latex must not be empty")
        if not self.variables:
            raise ValueError("variables must not be empty")

    def payload(self) -> dict[str, object]:
        return {
            "formula_id": self.formula_id,
            "page": self.page,
            "latex": self.latex,
            "variables": list(self.variables),
        }


@dataclass(frozen=True, slots=True)
class VariableMapping:
    variable: str
    mapping_kind: str
    target_field: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.variable, "variable")
        if self.mapping_kind not in _VALID_MAPPING_KINDS:
            raise ValueError(
                f"mapping_kind must be one of {sorted(_VALID_MAPPING_KINDS)}"
            )
        if self.mapping_kind == "unavailable":
            if self.target_field is not None:
                raise ValueError("unavailable mapping must not have a target field")
        elif self.target_field is None:
            raise ValueError("non-unavailable mapping requires a target field")

    def is_available(self) -> bool:
        return self.mapping_kind in {"exact", "derived", "proxy"}

    def payload(self) -> dict[str, object]:
        return {
            "variable": self.variable,
            "mapping_kind": self.mapping_kind,
            "target_field": self.target_field,
        }


@dataclass(frozen=True, slots=True)
class PaperEvidence:
    paper_id: str
    source: str
    sha256: str
    claims: tuple[PaperClaim, ...]
    formulas: tuple[ExtractedFormula, ...]
    mappings: tuple[VariableMapping, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.paper_id, "paper_id")
        _require_identifier(self.source, "source")
        _require_sha256(self.sha256, "sha256")
        claim_ids = [item.claim_id for item in self.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("claim ids must be unique")
        formula_ids = [item.formula_id for item in self.formulas]
        if len(set(formula_ids)) != len(formula_ids):
            raise ValueError("formula ids must be unique")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "paper-evidence/v1",
            "paper_id": self.paper_id,
            "source": self.source,
            "sha256": self.sha256,
            "claims": [item.payload() for item in self.claims],
            "formulas": [item.payload() for item in self.formulas],
            "mappings": [item.payload() for item in self.mappings],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
