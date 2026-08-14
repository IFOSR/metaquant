"""Paper reproduction grading contracts (G13-002).

Faithful reproduction (following the paper exactly) and local adaptation
(adapted to the platform's markets) are graded separately and never mixed.
Completion is graded R0-R4; only R2 and above count as directional success.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quant_platform.experiments import canonical_hash


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


class ReproductionTrack(StrEnum):
    FAITHFUL = "FAITHFUL"
    LOCAL = "LOCAL"


class ReproductionLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


_DIRECTIONAL_LEVELS = frozenset(
    {ReproductionLevel.R2, ReproductionLevel.R3, ReproductionLevel.R4}
)


@dataclass(frozen=True, slots=True)
class ReproductionResult:
    reproduction_id: str
    paper_id: str
    track: ReproductionTrack
    level: ReproductionLevel
    evidence_refs: tuple[str, ...]
    notes: str

    def __post_init__(self) -> None:
        _require_identifier(self.reproduction_id, "reproduction_id")
        _require_identifier(self.paper_id, "paper_id")
        if not isinstance(self.track, ReproductionTrack):
            object.__setattr__(self, "track", ReproductionTrack(self.track))
        if not isinstance(self.level, ReproductionLevel):
            object.__setattr__(self, "level", ReproductionLevel(self.level))
        if not self.notes:
            raise ValueError("notes must not be empty")

    def directionally_reproduced(self) -> bool:
        """R2 and above count as directional success."""
        return self.level in _DIRECTIONAL_LEVELS

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "reproduction-result/v1",
            "reproduction_id": self.reproduction_id,
            "paper_id": self.paper_id,
            "track": self.track.value,
            "level": self.level.value,
            "evidence_refs": list(self.evidence_refs),
            "notes": self.notes,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


@dataclass(frozen=True, slots=True)
class ReproductionPair:
    """A faithful and a local result for the same paper, never mixed."""

    faithful: ReproductionResult
    local: ReproductionResult

    def __post_init__(self) -> None:
        if self.faithful.track is not ReproductionTrack.FAITHFUL:
            raise ValueError("faithful result must use the FAITHFUL track")
        if self.local.track is not ReproductionTrack.LOCAL:
            raise ValueError("local result must use the LOCAL track")
        if self.faithful.paper_id != self.local.paper_id:
            raise ValueError("faithful and local results must share a paper_id")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "reproduction-pair/v1",
            "faithful": self.faithful.payload(),
            "local": self.local.payload(),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
