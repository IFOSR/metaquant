"""Vendor adapter boundary (G16-006, FR-312).

Third-party vendor adapters implement ``VendorAdapter`` and always return rows
marked with a source class. Rows from exploratory sources are tagged
``EXPLORATORY`` and can never enter formal gates, strategy packages, or live
trading; only ``FORMAL`` sources feed the sealed snapshot pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from quant_platform.data_gateway.loader import RawPITRow


class VendorSourceClass(StrEnum):
    FORMAL = "FORMAL"
    EXPLORATORY = "EXPLORATORY"


@dataclass(frozen=True, slots=True)
class VendorResponse:
    source_class: VendorSourceClass
    rows: tuple[RawPITRow, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_class, VendorSourceClass):
            object.__setattr__(
                self, "source_class", VendorSourceClass(self.source_class)
            )

    @property
    def exploratory(self) -> bool:
        return self.source_class is VendorSourceClass.EXPLORATORY

    def formal_rows(self) -> tuple[RawPITRow, ...]:
        """Rows admissible to formal gates; exploratory rows are excluded."""
        if self.exploratory:
            return ()
        return self.rows


class VendorAdapter(Protocol):
    source_id: str
    source_class: VendorSourceClass

    def fetch(
        self,
        instruments: tuple[str, ...],
        start: date,
        end: date,
    ) -> VendorResponse: ...


def guard_exploratory(response: VendorResponse, context: str) -> None:
    """Fail closed when exploratory data is offered to a formal context.

    Call this at the boundary where rows enter formal gates, the strategy
    package, or live trading (FR-312).
    """
    if response.exploratory:
        raise ValueError(
            f"EXPLORATORY_SOURCE_REJECTED: {context} requires formal sources"
        )


def exploratory_response(
    rows: tuple[RawPITRow, ...] = (),
) -> VendorResponse:
    """Mark rows from a third-party exploration platform as EXPLORATORY."""
    return VendorResponse(source_class=VendorSourceClass.EXPLORATORY, rows=rows)


def formal_response(rows: tuple[RawPITRow, ...]) -> VendorResponse:
    return VendorResponse(source_class=VendorSourceClass.FORMAL, rows=rows)


def utc_now() -> datetime:
    return datetime.now().astimezone()
