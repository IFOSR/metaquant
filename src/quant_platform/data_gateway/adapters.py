from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, time

from quant_platform.data_gateway.gateway import PITDataGateway
from quant_platform.data_gateway.models import (
    ActualFuturesContract,
    QueryPurpose,
    SnapshotQuery,
)


def _event_time(on: date) -> datetime:
    return datetime.combine(on, time.min, tzinfo=UTC)


def _payload(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("market master row value must be an object")
    return value


def _date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    return date.fromisoformat(value)


def _effective(payload: Mapping[str, object], trade_date: date) -> bool:
    effective_from = _date(payload["effective_from"], "effective_from")
    effective_to_raw = payload.get("effective_to")
    effective_to = (
        None if effective_to_raw is None else _date(effective_to_raw, "effective_to")
    )
    return effective_from <= trade_date and (
        effective_to is None or trade_date < effective_to
    )


class SecurityStatusUnavailableError(LookupError):
    """Raised when a formal PIT query cannot establish a security status."""


class ASharePITAdapter:
    def __init__(self, gateway: PITDataGateway) -> None:
        self._gateway = gateway

    def members(
        self,
        *,
        snapshot_id: str,
        index_id: str,
        trade_date: date,
        decision_time: datetime,
        purpose: QueryPurpose,
        allowed_license_tags: frozenset[str],
    ) -> frozenset[str]:
        result = self._gateway.query(
            SnapshotQuery(
                snapshot_id=snapshot_id,
                dataset_id="cn_a_master",
                fields=("index_membership",),
                decision_time=decision_time,
                purpose=purpose,
                allowed_license_tags=allowed_license_tags,
            )
        )
        return frozenset(
            item.instrument_id
            for item in result.rows
            if item.event_time <= _event_time(trade_date)
            and (payload := _payload(item.value)).get("index_id") == index_id
            and payload.get("member") is True
            and _effective(payload, trade_date)
        )

    def security_status(
        self,
        *,
        snapshot_id: str,
        instrument_id: str,
        trade_date: date,
        decision_time: datetime,
        purpose: QueryPurpose,
        allowed_license_tags: frozenset[str],
    ) -> str:
        result = self._gateway.query(
            SnapshotQuery(
                snapshot_id=snapshot_id,
                dataset_id="cn_a_master",
                fields=("security_status",),
                decision_time=decision_time,
                purpose=purpose,
                allowed_license_tags=allowed_license_tags,
            )
        )
        candidates = [
            item
            for item in result.rows
            if item.instrument_id == instrument_id
            and item.event_time <= _event_time(trade_date)
            and _effective(_payload(item.value), trade_date)
        ]
        if not candidates:
            raise SecurityStatusUnavailableError(
                "no point-in-time security status is available for "
                f"{instrument_id} on {trade_date.isoformat()} "
                f"at decision_time {decision_time.isoformat()}"
            )
        selected = max(candidates, key=lambda item: item.event_time)
        status = _payload(selected.value).get("status")
        if not isinstance(status, str) or not status:
            raise ValueError("security status must be a non-empty string")
        return status


class FuturesContractChainAdapter:
    def __init__(self, gateway: PITDataGateway) -> None:
        self._gateway = gateway

    def actual_contracts(
        self,
        *,
        snapshot_id: str,
        product: str,
        trade_date: date,
        decision_time: datetime,
        purpose: QueryPurpose,
        allowed_license_tags: frozenset[str],
    ) -> tuple[ActualFuturesContract, ...]:
        result = self._gateway.query(
            SnapshotQuery(
                snapshot_id=snapshot_id,
                dataset_id="futures_master",
                fields=("actual_contract",),
                decision_time=decision_time,
                purpose=purpose,
                allowed_license_tags=allowed_license_tags,
            )
        )
        contracts: list[ActualFuturesContract] = []
        for item in result.rows:
            payload = _payload(item.value)
            listed_on = _date(payload["listed_on"], "listed_on")
            last_trade_date = _date(
                payload["last_trade_date"],
                "last_trade_date",
            )
            if (
                payload.get("product") != product
                or payload.get("tradable") is not True
                or payload.get("continuous") is True
                or not listed_on <= trade_date <= last_trade_date
                or item.event_time > _event_time(trade_date)
            ):
                continue
            exchange = payload.get("exchange")
            if not isinstance(exchange, str) or not exchange:
                raise ValueError("exchange must be a non-empty string")
            contracts.append(
                ActualFuturesContract(
                    instrument_id=item.instrument_id,
                    product=product,
                    exchange=exchange,
                    listed_on=listed_on,
                    last_trade_date=last_trade_date,
                )
            )
        return tuple(sorted(contracts, key=lambda item: item.last_trade_date))
