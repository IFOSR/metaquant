from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from quant_platform.markets.contracts import (
    AvailabilityQuality,
    DatasetContract,
    DatasetPurpose,
    DatasetSnapshot,
    DerivedExport,
    Frequency,
    LicensePolicy,
    LifecycleState,
    LlmEgress,
    MarketId,
    RawExport,
    Retention,
    RuleCategory,
    RuleSetSnapshot,
    SourceClass,
    TradingRuleVersion,
    initial_market_definitions,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
NOW = datetime(2026, 8, 11, 9, tzinfo=UTC)


def _license(*purposes: DatasetPurpose) -> LicensePolicy:
    return LicensePolicy(
        allowed_purposes=frozenset(purposes),
        raw_export=RawExport.INTERNAL_ONLY,
        derived_export=DerivedExport.AGGREGATED,
        llm_egress=LlmEgress.PROHIBITED,
        retention=Retention.AUDIT_RETENTION,
        approved_regions=("CN",),
    )


def _contract() -> DatasetContract:
    return DatasetContract(
        contract_id="contract-fixture-v1",
        market=MarketId.CN_A,
        source_id="accepted-source-fixture",
        source_class=SourceClass.FORMAL_VENDOR,
        fields=("close", "volume"),
        temporal_fields=(
            "event_time",
            "available_time",
            "ingested_at",
            "revision_id",
        ),
        availability_quality=AvailabilityQuality.VENDOR_REPORTED,
        license_policy=_license(
            DatasetPurpose.RESEARCH,
            DatasetPurpose.DERIVED_FACTOR,
            DatasetPurpose.BACKTEST,
        ),
        effective_from=date(2026, 1, 1),
    )


def test_initial_markets_are_independent_and_daily_only() -> None:
    markets = {item.market_id: item for item in initial_market_definitions()}

    assert set(markets) == {MarketId.CN_A, MarketId.CN_COMMODITY_FUTURES}
    assert markets[MarketId.CN_A].enabled_frequencies == (Frequency.DAILY,)
    assert markets[MarketId.CN_A].exchanges == ("SSE", "SZSE")
    assert markets[MarketId.CN_COMMODITY_FUTURES].exchanges == (
        "SHFE",
        "INE",
        "DCE",
        "CZCE",
        "GFEX",
    )
    assert markets[MarketId.CN_A].clock_id != (
        markets[MarketId.CN_COMMODITY_FUTURES].clock_id
    )


def test_market_definition_rejects_frequency_outside_g0() -> None:
    market = initial_market_definitions()[0]

    with pytest.raises(ValueError, match="G0 only enables 1d"):
        market.with_frequencies((Frequency.FIVE_MINUTE,))


def test_dataset_contract_requires_all_pit_time_fields() -> None:
    with pytest.raises(ValueError, match="temporal fields"):
        DatasetContract(
            contract_id="incomplete",
            market=MarketId.CN_A,
            source_id="fixture",
            source_class=SourceClass.FORMAL_VENDOR,
            fields=("close",),
            temporal_fields=("event_time", "available_time"),
            availability_quality=AvailabilityQuality.VENDOR_REPORTED,
            license_policy=_license(DatasetPurpose.RESEARCH),
            effective_from=date(2026, 1, 1),
        )


def test_exploration_contract_cannot_be_used_formally() -> None:
    contract = DatasetContract(
        contract_id="exploration",
        market=MarketId.CN_A,
        source_id="public-aggregator-fixture",
        source_class=SourceClass.EXPLORATION,
        fields=("close",),
        temporal_fields=(
            "event_time",
            "available_time",
            "ingested_at",
            "revision_id",
        ),
        availability_quality=AvailabilityQuality.DERIVED,
        license_policy=_license(DatasetPurpose.RESEARCH),
        effective_from=date(2026, 1, 1),
    )

    with pytest.raises(PermissionError, match="formal"):
        contract.assert_formal_use(DatasetPurpose.RESEARCH, NOW)


def test_license_policy_propagates_most_restrictive_lineage() -> None:
    research = _license(DatasetPurpose.RESEARCH, DatasetPurpose.REPORT)
    backtest = LicensePolicy(
        allowed_purposes=frozenset({DatasetPurpose.RESEARCH, DatasetPurpose.BACKTEST}),
        raw_export=RawExport.NONE,
        derived_export=DerivedExport.PROHIBITED,
        llm_egress=LlmEgress.APPROVED_PRIVATE_ENDPOINT,
        retention=Retention.TERM_ONLY,
        approved_regions=("CN", "SG"),
    )

    effective = LicensePolicy.for_lineage((research, backtest))

    assert effective.allowed_purposes == frozenset({DatasetPurpose.RESEARCH})
    assert effective.raw_export is RawExport.NONE
    assert effective.derived_export is DerivedExport.PROHIBITED
    assert effective.llm_egress is LlmEgress.PROHIBITED
    assert effective.retention is Retention.TERM_ONLY
    assert effective.approved_regions == ("CN",)


def test_dataset_snapshot_seals_immutably_and_revocation_blocks_formal_use() -> None:
    contract = _contract()
    snapshot = DatasetSnapshot.seal(
        snapshot_id="dataset-snapshot-v1",
        contract=contract,
        market=MarketId.CN_A,
        content_hash=HASH_A,
        schema_hash=HASH_B,
        row_count=12,
        as_of=NOW,
        sealed_at=NOW,
    )

    snapshot.assert_formal_use(contract, DatasetPurpose.BACKTEST, NOW)
    assert snapshot.state is LifecycleState.SEALED
    with pytest.raises(FrozenInstanceError):
        snapshot.row_count = 13  # type: ignore[misc]

    revoked = snapshot.revoke("source revision dispute", NOW)
    with pytest.raises(PermissionError, match="revoked"):
        revoked.assert_formal_use(contract, DatasetPurpose.BACKTEST, NOW)


def test_revoked_contract_blocks_an_existing_sealed_snapshot() -> None:
    contract = _contract()
    snapshot = DatasetSnapshot.seal(
        snapshot_id="dataset-snapshot-v1",
        contract=contract,
        market=MarketId.CN_A,
        content_hash=HASH_A,
        schema_hash=HASH_B,
        row_count=12,
        as_of=NOW,
        sealed_at=NOW,
    )

    with pytest.raises(PermissionError, match="contract is revoked"):
        snapshot.assert_formal_use(
            contract.revoke("license expired", NOW),
            DatasetPurpose.RESEARCH,
            NOW,
        )


def _sealed_rule(
    market: MarketId,
    category: RuleCategory,
    suffix: str,
) -> TradingRuleVersion:
    return TradingRuleVersion.seal(
        rule_id=f"{market.value.lower()}-{category.value.lower()}-{suffix}",
        market=market,
        category=category,
        instrument_scope=("*",),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_ref=f"official-fixture://{suffix}",
        source_hash=HASH_A,
        payload_hash=HASH_B,
        sealed_at=NOW,
    )


@pytest.mark.parametrize("market", list(MarketId))
def test_rule_set_requires_complete_market_specific_categories(
    market: MarketId,
) -> None:
    rules = tuple(
        _sealed_rule(market, category, str(index))
        for index, category in enumerate(RuleSetSnapshot.required_categories(market))
    )

    snapshot = RuleSetSnapshot.seal(
        snapshot_id=f"{market.value.lower()}-rules-v1",
        market=market,
        rules=rules,
        sealed_at=NOW,
    )

    assert snapshot.state is LifecycleState.SEALED
    assert snapshot.content_hash

    with pytest.raises(ValueError, match="missing rule categories"):
        RuleSetSnapshot.seal(
            snapshot_id="incomplete",
            market=market,
            rules=rules[:-1],
            sealed_at=NOW,
        )


def test_rule_set_rejects_revoked_or_cross_market_rules() -> None:
    market = MarketId.CN_A
    rules = [
        _sealed_rule(market, category, str(index))
        for index, category in enumerate(RuleSetSnapshot.required_categories(market))
    ]
    rules[0] = rules[0].revoke("superseded evidence", NOW)

    with pytest.raises(PermissionError, match="revoked"):
        RuleSetSnapshot.seal("revoked-rules", market, tuple(rules), NOW)

    cross_market = list(rules)
    cross_market[0] = _sealed_rule(
        MarketId.CN_COMMODITY_FUTURES,
        RuleCategory.CALENDAR,
        "cross-market",
    )
    with pytest.raises(ValueError, match="market"):
        RuleSetSnapshot.seal("mixed-rules", market, tuple(cross_market), NOW)
