from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SeriesKind(str, Enum):
    SCALAR_SERIES = "ScalarSeries"
    CROSS_SECTION = "CrossSection"
    EVENT_SERIES = "EventSeries"
    LABEL_SERIES = "LabelSeries"
    UNIVERSE_MASK = "UniverseMask"
    EXPOSURE_MATRIX = "ExposureMatrix"


@dataclass(frozen=True)
class ValueType:
    kind: SeriesKind
    unit: str


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    path: str


class FactorIRCompileError(ValueError):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("compile error requires at least one diagnostic")
        self.diagnostics = diagnostics
        summary = "; ".join(
            f"{item.code} at {item.path}: {item.message}" for item in diagnostics
        )
        super().__init__(summary)


@dataclass(frozen=True)
class RefNode:
    alias: str


@dataclass(frozen=True)
class LiteralNode:
    value: int | float | bool
    unit: str


@dataclass(frozen=True)
class CallNode:
    operator: str
    args: tuple[ExpressionNode, ...]
    params: tuple[tuple[str, Any], ...]


ExpressionNode = RefNode | LiteralNode | CallNode


@dataclass(frozen=True)
class PostprocessStep:
    operator: str
    params: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class CompiledFactorIR:
    factor_id: str
    canonical_json: str
    canonical_expression_json: str
    expression_hash: str
    ir_hash: str
    ast: ExpressionNode
    output_type: ValueType
    lookback: int
    available_time: str
    operator_names: tuple[str, ...]
    input_aliases: tuple[str, ...]
    postprocess_steps: tuple[PostprocessStep, ...]
