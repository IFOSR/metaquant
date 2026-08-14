from __future__ import annotations

import pytest

from quant_platform.paper.evidence import (
    ExtractedFormula,
    PaperClaim,
    PaperEvidence,
    VariableMapping,
)
from quant_platform.paper.reproduction import (
    ReproductionLevel,
    ReproductionPair,
    ReproductionResult,
    ReproductionTrack,
)


def evidence() -> PaperEvidence:
    return PaperEvidence(
        paper_id="paper://momentum-1993",
        source="Jegadeesh and Titman (1993)",
        sha256="a" * 64,
        claims=(
            PaperClaim("c1", 3, "Past winners outperform past losers."),
            PaperClaim("c2", 5, "Momentum is strongest over 3-12 months."),
        ),
        formulas=(ExtractedFormula("f1", 4, "R_t = \\prod (1 + r_i)", ("R_t", "r_i")),),
        mappings=(
            VariableMapping("r_i", "exact", "market.eod.return_1d"),
            VariableMapping("sentiment", "unavailable"),
        ),
    )


def faithful(level: ReproductionLevel) -> ReproductionResult:
    return ReproductionResult(
        reproduction_id="repro-faithful",
        paper_id="paper://momentum-1993",
        track=ReproductionTrack.FAITHFUL,
        level=level,
        evidence_refs=("c1", "f1"),
        notes="faithful reproduction",
    )


def local(level: ReproductionLevel) -> ReproductionResult:
    return ReproductionResult(
        reproduction_id="repro-local",
        paper_id="paper://momentum-1993",
        track=ReproductionTrack.LOCAL,
        level=level,
        evidence_refs=("c1", "f1"),
        notes="local adaptation",
    )


def test_evidence_content_hash_is_stable() -> None:
    assert evidence().content_hash() == evidence().content_hash()


def test_evidence_rejects_duplicate_claim_ids() -> None:
    claim = PaperClaim("dup", 1, "text")
    with pytest.raises(ValueError):
        PaperEvidence(
            paper_id="p",
            source="s",
            sha256="a" * 64,
            claims=(claim, claim),
            formulas=(),
            mappings=(),
        )


def test_unavailable_mapping_has_no_target() -> None:
    mapping = VariableMapping("sentiment", "unavailable")

    assert not mapping.is_available()
    assert mapping.target_field is None


def test_available_mapping_requires_target() -> None:
    with pytest.raises(ValueError):
        VariableMapping("r_i", "exact")


def test_r2_counts_as_directional_success() -> None:
    assert faithful(ReproductionLevel.R2).directionally_reproduced()


def test_r1_does_not_count_as_directional_success() -> None:
    assert not faithful(ReproductionLevel.R1).directionally_reproduced()


def test_pair_rejects_mixed_tracks() -> None:
    with pytest.raises(ValueError):
        ReproductionPair(
            faithful=local(ReproductionLevel.R2),
            local=local(ReproductionLevel.R2),
        )


def test_pair_rejects_mismatched_paper() -> None:
    faithful_other = ReproductionResult(
        reproduction_id="r",
        paper_id="paper://other",
        track=ReproductionTrack.FAITHFUL,
        level=ReproductionLevel.R2,
        evidence_refs=(),
        notes="n",
    )
    with pytest.raises(ValueError):
        ReproductionPair(faithful=faithful_other, local=local(ReproductionLevel.R2))
