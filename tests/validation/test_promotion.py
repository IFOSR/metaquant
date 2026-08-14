from __future__ import annotations

import pytest

from quant_platform.validation.policy import ICSign
from quant_platform.validation.promotion import (
    CandidateEvidence,
    PromotionDisposition,
    PromotionPolicy,
    evaluate_promotion,
)


def policy() -> PromotionPolicy:
    return PromotionPolicy(
        policy_id="policy://cn-a-promotion/v1",
        market="CN_A",
        min_coverage=0.8,
        min_observations=100,
        min_oos_ic=0.02,
        fdr_bound=0.1,
        min_capacity=1_000_000.0,
    )


def strong_evidence() -> CandidateEvidence:
    return CandidateEvidence(
        coverage=0.95,
        observations=300,
        oos_ic=0.05,
        expected_direction=ICSign.POSITIVE,
        fdr_qvalue=0.03,
        capacity_aum=5_000_000.0,
        sharpe=1.2,
        effect_score=0.8,
        stability_score=0.7,
        independence_score=0.9,
        cost_value_score=0.6,
        interpretability_score=0.5,
    )


def test_promotes_strong_candidate() -> None:
    decision = evaluate_promotion(strong_evidence(), policy())

    assert decision.disposition is PromotionDisposition.PROMOTE
    assert decision.total_score is not None
    assert decision.total_score >= 0.6


def test_rejects_on_failed_hard_gate() -> None:
    base = strong_evidence()
    evidence = CandidateEvidence(
        coverage=0.5,  # below min_coverage 0.8
        observations=base.observations,
        oos_ic=base.oos_ic,
        expected_direction=base.expected_direction,
        fdr_qvalue=base.fdr_qvalue,
        capacity_aum=base.capacity_aum,
        sharpe=base.sharpe,
        effect_score=base.effect_score,
        stability_score=base.stability_score,
        independence_score=base.independence_score,
        cost_value_score=base.cost_value_score,
        interpretability_score=base.interpretability_score,
    )

    decision = evaluate_promotion(evidence, policy())

    assert decision.disposition is PromotionDisposition.REJECT
    assert any(
        gate.name == "data_quality.coverage" and not gate.passed
        for gate in decision.gates
    )


def test_quarantines_suspiciously_strong_ic() -> None:
    base = strong_evidence()
    evidence = CandidateEvidence(
        coverage=base.coverage,
        observations=base.observations,
        oos_ic=0.3,  # above quarantine_ic 0.2
        expected_direction=base.expected_direction,
        fdr_qvalue=base.fdr_qvalue,
        capacity_aum=base.capacity_aum,
        sharpe=base.sharpe,
        effect_score=base.effect_score,
        stability_score=base.stability_score,
        independence_score=base.independence_score,
        cost_value_score=base.cost_value_score,
        interpretability_score=base.interpretability_score,
    )

    decision = evaluate_promotion(evidence, policy())

    assert decision.disposition is PromotionDisposition.QUARANTINE


def test_rejects_wrong_direction() -> None:
    base = strong_evidence()
    evidence = CandidateEvidence(
        coverage=base.coverage,
        observations=base.observations,
        oos_ic=-0.05,  # expected POSITIVE but IC is negative
        expected_direction=ICSign.POSITIVE,
        fdr_qvalue=base.fdr_qvalue,
        capacity_aum=base.capacity_aum,
        sharpe=base.sharpe,
        effect_score=base.effect_score,
        stability_score=base.stability_score,
        independence_score=base.independence_score,
        cost_value_score=base.cost_value_score,
        interpretability_score=base.interpretability_score,
    )

    decision = evaluate_promotion(evidence, policy())

    assert decision.disposition is PromotionDisposition.REJECT
    assert any(
        gate.name == "oos.direction" and not gate.passed for gate in decision.gates
    )


def test_rejects_below_pass_line() -> None:
    evidence = CandidateEvidence(
        coverage=0.95,
        observations=300,
        oos_ic=0.05,
        expected_direction=ICSign.POSITIVE,
        fdr_qvalue=0.03,
        capacity_aum=5_000_000.0,
        sharpe=1.2,
        effect_score=0.1,
        stability_score=0.1,
        independence_score=0.1,
        cost_value_score=0.1,
        interpretability_score=0.1,
    )

    decision = evaluate_promotion(evidence, policy())

    assert decision.disposition is PromotionDisposition.REJECT
    assert decision.total_score == pytest.approx(0.1)


def test_policy_rejects_unbalanced_weights() -> None:
    with pytest.raises(ValueError):
        PromotionPolicy(
            policy_id="policy://bad/v1",
            market="CN_A",
            min_coverage=0.8,
            min_observations=100,
            min_oos_ic=0.02,
            fdr_bound=0.1,
            min_capacity=1_000_000.0,
            effect_weight=0.5,
        )


def test_decision_is_deterministic() -> None:
    first = evaluate_promotion(strong_evidence(), policy())
    second = evaluate_promotion(strong_evidence(), policy())

    assert first == second
    assert first.content_hash() == second.content_hash()
