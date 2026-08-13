from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar


class MarketId(StrEnum):
    CN_A = "CN_A"
    CN_COMMODITY_FUTURES = "CN_COMMODITY_FUTURES"


class Frequency(StrEnum):
    DAILY = "1d"
    FIVE_MINUTE = "5m"


class DatasetPurpose(StrEnum):
    RESEARCH = "RESEARCH"
    DERIVED_FACTOR = "DERIVED_FACTOR"
    BACKTEST = "BACKTEST"
    REPORT = "REPORT"
    PAPER = "PAPER"
    LIVE = "LIVE"


class SourceClass(StrEnum):
    EXPLORATION = "EXPLORATION"
    FORMAL_VENDOR = "FORMAL_VENDOR"
    OFFICIAL = "OFFICIAL"

    @property
    def is_formal(self) -> bool:
        return self is not SourceClass.EXPLORATION


class AvailabilityQuality(StrEnum):
    DERIVED = "DERIVED"
    VENDOR_REPORTED = "VENDOR_REPORTED"
    SOURCE_REPORTED = "SOURCE_REPORTED"


class RawExport(StrEnum):
    NONE = "NONE"
    INTERNAL_ONLY = "INTERNAL_ONLY"
    ALLOWED = "ALLOWED"


class DerivedExport(StrEnum):
    PROHIBITED = "PROHIBITED"
    AGGREGATED = "AGGREGATED"
    ALLOWED = "ALLOWED"


class LlmEgress(StrEnum):
    PROHIBITED = "PROHIBITED"
    APPROVED_PRIVATE_ENDPOINT = "APPROVED_PRIVATE_ENDPOINT"
    ALLOWED = "ALLOWED"


class Retention(StrEnum):
    TERM_ONLY = "TERM_ONLY"
    AUDIT_RETENTION = "AUDIT_RETENTION"
    PERPETUAL = "PERPETUAL"


class LifecycleState(StrEnum):
    SEALED = "SEALED"
    REVOKED = "REVOKED"


class RuleCategory(StrEnum):
    CALENDAR = "CALENDAR"
    SESSIONS = "SESSIONS"
    AUCTION = "AUCTION"
    TRADE_DATE_ASSIGNMENT = "TRADE_DATE_ASSIGNMENT"
    PRICE_LIMIT = "PRICE_LIMIT"
    TICK_SIZE = "TICK_SIZE"
    LOT_SIZE = "LOT_SIZE"
    CONTRACT_MULTIPLIER = "CONTRACT_MULTIPLIER"
    FEE_SCHEDULE = "FEE_SCHEDULE"
    STAMP_DUTY = "STAMP_DUTY"
    MARGIN_SCHEDULE = "MARGIN_SCHEDULE"
    SETTLEMENT = "SETTLEMENT"
    TRADABILITY = "TRADABILITY"
    POSITION_LIMIT = "POSITION_LIMIT"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    HISTORICAL_UNIVERSE = "HISTORICAL_UNIVERSE"
    DELIVERY = "DELIVERY"
    ROLL_POLICY = "ROLL_POLICY"


def _require_identifier(value: str, label: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty normalized identifier")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest") from exc
    if value != value.lower():
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")


def _json_value(value: Any) -> Any:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, frozenset | set):
        return sorted(_json_value(item) for item in value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        _json_value(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketDefinition:
    market_id: MarketId
    exchanges: tuple[str, ...]
    enabled_frequencies: tuple[Frequency, ...]
    clock_id: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.exchanges or len(set(self.exchanges)) != len(self.exchanges):
            raise ValueError("exchanges must be non-empty and unique")
        _require_identifier(self.clock_id, "clock_id")
        self._assert_g0_frequencies(self.enabled_frequencies)

    @staticmethod
    def _assert_g0_frequencies(frequencies: tuple[Frequency, ...]) -> None:
        if frequencies != (Frequency.DAILY,):
            raise ValueError("G0 only enables 1d formal research")

    def with_frequencies(
        self,
        frequencies: tuple[Frequency, ...],
    ) -> MarketDefinition:
        self._assert_g0_frequencies(frequencies)
        return replace(self, enabled_frequencies=frequencies)


def initial_market_definitions() -> tuple[MarketDefinition, ...]:
    return (
        MarketDefinition(
            market_id=MarketId.CN_A,
            exchanges=("SSE", "SZSE"),
            enabled_frequencies=(Frequency.DAILY,),
            clock_id="CN_A_DAILY_V1",
        ),
        MarketDefinition(
            market_id=MarketId.CN_COMMODITY_FUTURES,
            exchanges=("SHFE", "INE", "DCE", "CZCE", "GFEX"),
            enabled_frequencies=(Frequency.DAILY,),
            clock_id="CN_COMMODITY_FUTURES_DAILY_V1",
        ),
    )


@dataclass(frozen=True, slots=True)
class LicensePolicy:
    allowed_purposes: frozenset[DatasetPurpose]
    raw_export: RawExport
    derived_export: DerivedExport
    llm_egress: LlmEgress
    retention: Retention
    approved_regions: tuple[str, ...]

    _RAW_ORDER: ClassVar[tuple[RawExport, ...]] = (
        RawExport.NONE,
        RawExport.INTERNAL_ONLY,
        RawExport.ALLOWED,
    )
    _DERIVED_ORDER: ClassVar[tuple[DerivedExport, ...]] = (
        DerivedExport.PROHIBITED,
        DerivedExport.AGGREGATED,
        DerivedExport.ALLOWED,
    )
    _LLM_ORDER: ClassVar[tuple[LlmEgress, ...]] = (
        LlmEgress.PROHIBITED,
        LlmEgress.APPROVED_PRIVATE_ENDPOINT,
        LlmEgress.ALLOWED,
    )
    _RETENTION_ORDER: ClassVar[tuple[Retention, ...]] = (
        Retention.TERM_ONLY,
        Retention.AUDIT_RETENTION,
        Retention.PERPETUAL,
    )

    def __post_init__(self) -> None:
        if len(set(self.approved_regions)) != len(self.approved_regions):
            raise ValueError("approved_regions must be unique")
        if any(
            not region or region.strip() != region for region in self.approved_regions
        ):
            raise ValueError("approved_regions must contain normalized labels")

    @classmethod
    def for_lineage(cls, policies: Iterable[LicensePolicy]) -> LicensePolicy:
        lineage = tuple(policies)
        if not lineage:
            raise ValueError("license lineage must not be empty")

        purposes = frozenset.intersection(
            *(policy.allowed_purposes for policy in lineage)
        )
        approved = set(lineage[0].approved_regions)
        for policy in lineage[1:]:
            approved.intersection_update(policy.approved_regions)

        return cls(
            allowed_purposes=purposes,
            raw_export=min(
                (policy.raw_export for policy in lineage),
                key=cls._RAW_ORDER.index,
            ),
            derived_export=min(
                (policy.derived_export for policy in lineage),
                key=cls._DERIVED_ORDER.index,
            ),
            llm_egress=min(
                (policy.llm_egress for policy in lineage),
                key=cls._LLM_ORDER.index,
            ),
            retention=min(
                (policy.retention for policy in lineage),
                key=cls._RETENTION_ORDER.index,
            ),
            approved_regions=tuple(
                region for region in lineage[0].approved_regions if region in approved
            ),
        )

    def assert_allows(self, purpose: DatasetPurpose) -> None:
        if purpose not in self.allowed_purposes:
            raise PermissionError(f"license does not allow {purpose.value}")


@dataclass(frozen=True, slots=True)
class DatasetContract:
    contract_id: str
    market: MarketId
    source_id: str
    source_class: SourceClass
    fields: tuple[str, ...]
    temporal_fields: tuple[str, ...]
    availability_quality: AvailabilityQuality
    license_policy: LicensePolicy
    effective_from: date
    effective_to: date | None = None
    state: LifecycleState = LifecycleState.SEALED
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    REQUIRED_TEMPORAL_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"event_time", "available_time", "ingested_at", "revision_id"}
    )

    def __post_init__(self) -> None:
        _require_identifier(self.contract_id, "contract_id")
        _require_identifier(self.source_id, "source_id")
        if not self.fields or len(set(self.fields)) != len(self.fields):
            raise ValueError("fields must be non-empty and unique")
        if not self.REQUIRED_TEMPORAL_FIELDS.issubset(self.temporal_fields):
            raise ValueError("temporal fields must include all PIT timestamps")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        _validate_revocation(self.state, self.revoked_at, self.revocation_reason)

    @property
    def fingerprint(self) -> str:
        return _stable_hash(
            {
                "contract_id": self.contract_id,
                "market": self.market,
                "source_id": self.source_id,
                "source_class": self.source_class,
                "fields": self.fields,
                "temporal_fields": self.temporal_fields,
                "availability_quality": self.availability_quality,
                "license_policy": {
                    "allowed_purposes": self.license_policy.allowed_purposes,
                    "raw_export": self.license_policy.raw_export,
                    "derived_export": self.license_policy.derived_export,
                    "llm_egress": self.license_policy.llm_egress,
                    "retention": self.license_policy.retention,
                    "approved_regions": self.license_policy.approved_regions,
                },
                "effective_from": self.effective_from,
                "effective_to": self.effective_to,
            }
        )

    def assert_formal_use(
        self,
        purpose: DatasetPurpose,
        at: datetime,
    ) -> None:
        _require_aware(at, "formal-use time")
        if self.state is LifecycleState.REVOKED:
            raise PermissionError("dataset contract is revoked")
        if not self.source_class.is_formal:
            raise PermissionError("exploration source cannot be used formally")
        if at.date() < self.effective_from or (
            self.effective_to is not None and at.date() > self.effective_to
        ):
            raise PermissionError("dataset contract is not effective")
        self.license_policy.assert_allows(purpose)

    def revoke(self, reason: str, at: datetime) -> DatasetContract:
        _validate_revoke_request(self.state, reason, at)
        return replace(
            self,
            state=LifecycleState.REVOKED,
            revoked_at=at,
            revocation_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    snapshot_id: str
    contract_id: str
    contract_fingerprint: str
    market: MarketId
    content_hash: str
    schema_hash: str
    row_count: int
    as_of: datetime
    sealed_at: datetime
    license_policy: LicensePolicy
    state: LifecycleState = LifecycleState.SEALED
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.snapshot_id, "snapshot_id")
        _require_identifier(self.contract_id, "contract_id")
        _require_sha256(self.contract_fingerprint, "contract_fingerprint")
        _require_sha256(self.content_hash, "content_hash")
        _require_sha256(self.schema_hash, "schema_hash")
        if self.row_count < 0:
            raise ValueError("row_count must be non-negative")
        _require_aware(self.as_of, "as_of")
        _require_aware(self.sealed_at, "sealed_at")
        if self.as_of > self.sealed_at:
            raise ValueError("as_of must not be after sealed_at")
        _validate_revocation(self.state, self.revoked_at, self.revocation_reason)

    @classmethod
    def seal(
        cls,
        snapshot_id: str,
        contract: DatasetContract,
        market: MarketId,
        content_hash: str,
        schema_hash: str,
        row_count: int,
        as_of: datetime,
        sealed_at: datetime,
    ) -> DatasetSnapshot:
        if contract.state is LifecycleState.REVOKED:
            raise PermissionError("dataset contract is revoked")
        if market is not contract.market:
            raise ValueError("snapshot market must match contract market")
        return cls(
            snapshot_id=snapshot_id,
            contract_id=contract.contract_id,
            contract_fingerprint=contract.fingerprint,
            market=market,
            content_hash=content_hash,
            schema_hash=schema_hash,
            row_count=row_count,
            as_of=as_of,
            sealed_at=sealed_at,
            license_policy=contract.license_policy,
        )

    def assert_formal_use(
        self,
        contract: DatasetContract,
        purpose: DatasetPurpose,
        at: datetime,
    ) -> None:
        if self.state is LifecycleState.REVOKED:
            raise PermissionError("dataset snapshot is revoked")
        if contract.state is LifecycleState.REVOKED:
            raise PermissionError("dataset contract is revoked")
        if (
            contract.contract_id != self.contract_id
            or contract.market is not self.market
        ):
            raise ValueError("dataset snapshot does not match contract")
        if contract.fingerprint != self.contract_fingerprint:
            raise ValueError("dataset contract payload differs from sealed snapshot")
        contract.assert_formal_use(purpose, at)
        self.license_policy.assert_allows(purpose)

    def revoke(self, reason: str, at: datetime) -> DatasetSnapshot:
        _validate_revoke_request(self.state, reason, at)
        return replace(
            self,
            state=LifecycleState.REVOKED,
            revoked_at=at,
            revocation_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class TradingRuleVersion:
    rule_id: str
    market: MarketId
    category: RuleCategory
    instrument_scope: tuple[str, ...]
    effective_from: date
    effective_to: date | None
    source_ref: str
    source_hash: str
    payload_hash: str
    sealed_at: datetime
    state: LifecycleState = LifecycleState.SEALED
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.rule_id, "rule_id")
        if not self.instrument_scope or len(set(self.instrument_scope)) != len(
            self.instrument_scope
        ):
            raise ValueError("instrument_scope must be non-empty and unique")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        _require_identifier(self.source_ref, "source_ref")
        _require_sha256(self.source_hash, "source_hash")
        _require_sha256(self.payload_hash, "payload_hash")
        _require_aware(self.sealed_at, "sealed_at")
        _validate_revocation(self.state, self.revoked_at, self.revocation_reason)

    @classmethod
    def seal(
        cls,
        rule_id: str,
        market: MarketId,
        category: RuleCategory,
        instrument_scope: tuple[str, ...],
        effective_from: date,
        effective_to: date | None,
        source_ref: str,
        source_hash: str,
        payload_hash: str,
        sealed_at: datetime,
    ) -> TradingRuleVersion:
        return cls(
            rule_id=rule_id,
            market=market,
            category=category,
            instrument_scope=instrument_scope,
            effective_from=effective_from,
            effective_to=effective_to,
            source_ref=source_ref,
            source_hash=source_hash,
            payload_hash=payload_hash,
            sealed_at=sealed_at,
        )

    @property
    def fingerprint(self) -> str:
        return _stable_hash(
            {
                "rule_id": self.rule_id,
                "market": self.market,
                "category": self.category,
                "instrument_scope": self.instrument_scope,
                "effective_from": self.effective_from,
                "effective_to": self.effective_to,
                "source_ref": self.source_ref,
                "source_hash": self.source_hash,
                "payload_hash": self.payload_hash,
            }
        )

    def applies_to(self, instrument_id: str, on: date) -> bool:
        in_scope = (
            "*" in self.instrument_scope or instrument_id in self.instrument_scope
        )
        in_time = on >= self.effective_from and (
            self.effective_to is None or on <= self.effective_to
        )
        return self.state is LifecycleState.SEALED and in_scope and in_time

    def revoke(self, reason: str, at: datetime) -> TradingRuleVersion:
        _validate_revoke_request(self.state, reason, at)
        return replace(
            self,
            state=LifecycleState.REVOKED,
            revoked_at=at,
            revocation_reason=reason,
        )


@dataclass(frozen=True, slots=True)
class RuleSetSnapshot:
    snapshot_id: str
    market: MarketId
    rules: tuple[TradingRuleVersion, ...]
    content_hash: str
    sealed_at: datetime
    state: LifecycleState = LifecycleState.SEALED
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    _CN_A_REQUIRED: ClassVar[tuple[RuleCategory, ...]] = (
        RuleCategory.CALENDAR,
        RuleCategory.SESSIONS,
        RuleCategory.AUCTION,
        RuleCategory.PRICE_LIMIT,
        RuleCategory.TICK_SIZE,
        RuleCategory.LOT_SIZE,
        RuleCategory.FEE_SCHEDULE,
        RuleCategory.STAMP_DUTY,
        RuleCategory.TRADABILITY,
        RuleCategory.CORPORATE_ACTION,
        RuleCategory.HISTORICAL_UNIVERSE,
    )
    _FUTURES_REQUIRED: ClassVar[tuple[RuleCategory, ...]] = (
        RuleCategory.CALENDAR,
        RuleCategory.SESSIONS,
        RuleCategory.TRADE_DATE_ASSIGNMENT,
        RuleCategory.PRICE_LIMIT,
        RuleCategory.TICK_SIZE,
        RuleCategory.LOT_SIZE,
        RuleCategory.CONTRACT_MULTIPLIER,
        RuleCategory.FEE_SCHEDULE,
        RuleCategory.MARGIN_SCHEDULE,
        RuleCategory.SETTLEMENT,
        RuleCategory.POSITION_LIMIT,
        RuleCategory.DELIVERY,
        RuleCategory.ROLL_POLICY,
    )

    def __post_init__(self) -> None:
        _require_identifier(self.snapshot_id, "snapshot_id")
        _require_sha256(self.content_hash, "content_hash")
        _require_aware(self.sealed_at, "sealed_at")
        _validate_revocation(self.state, self.revoked_at, self.revocation_reason)

    @classmethod
    def required_categories(cls, market: MarketId) -> tuple[RuleCategory, ...]:
        if market is MarketId.CN_A:
            return cls._CN_A_REQUIRED
        return cls._FUTURES_REQUIRED

    @classmethod
    def seal(
        cls,
        snapshot_id: str,
        market: MarketId,
        rules: tuple[TradingRuleVersion, ...],
        sealed_at: datetime,
    ) -> RuleSetSnapshot:
        if not rules:
            raise ValueError("rule set must not be empty")
        if any(rule.market is not market for rule in rules):
            raise ValueError("all rules must match the rule-set market")
        if any(rule.state is LifecycleState.REVOKED for rule in rules):
            raise PermissionError("revoked rules cannot enter a sealed rule set")
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ValueError("rule IDs must be unique")

        present = {rule.category for rule in rules}
        missing = set(cls.required_categories(market)) - present
        if missing:
            names = ", ".join(sorted(category.value for category in missing))
            raise ValueError(f"missing rule categories: {names}")

        content_hash = _stable_hash(
            {
                "market": market,
                "rules": tuple(
                    sorted(
                        (rule.fingerprint for rule in rules),
                    )
                ),
            }
        )
        return cls(
            snapshot_id=snapshot_id,
            market=market,
            rules=rules,
            content_hash=content_hash,
            sealed_at=sealed_at,
        )

    def assert_formal_use(self, instrument_id: str, on: date) -> None:
        if self.state is LifecycleState.REVOKED:
            raise PermissionError("rule-set snapshot is revoked")
        for category in self.required_categories(self.market):
            if not any(
                rule.category is category and rule.applies_to(instrument_id, on)
                for rule in self.rules
            ):
                raise PermissionError(
                    f"no effective {category.value} rule for {instrument_id}"
                )

    def revoke(self, reason: str, at: datetime) -> RuleSetSnapshot:
        _validate_revoke_request(self.state, reason, at)
        return replace(
            self,
            state=LifecycleState.REVOKED,
            revoked_at=at,
            revocation_reason=reason,
        )


def _validate_revocation(
    state: LifecycleState,
    revoked_at: datetime | None,
    reason: str | None,
) -> None:
    if state is LifecycleState.REVOKED:
        if revoked_at is None or not reason:
            raise ValueError("revoked objects require time and reason")
        _require_aware(revoked_at, "revoked_at")
    elif revoked_at is not None or reason is not None:
        raise ValueError("sealed objects cannot contain revocation metadata")


def _validate_revoke_request(
    state: LifecycleState,
    reason: str,
    at: datetime,
) -> None:
    if state is LifecycleState.REVOKED:
        raise ValueError("object is already revoked")
    if not reason or reason.strip() != reason:
        raise ValueError("revocation reason must be non-empty and normalized")
    _require_aware(at, "revocation time")
