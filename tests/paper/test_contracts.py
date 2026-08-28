"""Tests for paper account contracts and the lifecycle state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quant_platform.paper.contracts import (
    PaperAccount,
    PaperAccountError,
    PaperAccountState,
    next_state,
)


def _account(state: PaperAccountState = PaperAccountState.ACTIVE) -> PaperAccount:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return PaperAccount(
        id="pa_1",
        owner="tester",
        draft_id="sd_1",
        artifact_address="abc123",
        content_hash="def456",
        market="CN_A",
        instrument_ids=("600000.SH",),
        frequency="1d",
        initial_cash=Decimal("1000000"),
        state=state,
        created_at=now,
        updated_at=now,
    )


def test_state_machine_happy_path() -> None:
    assert next_state(PaperAccountState.ACTIVE, "pause") is PaperAccountState.PAUSED
    assert next_state(PaperAccountState.PAUSED, "resume") is PaperAccountState.ACTIVE
    assert next_state(PaperAccountState.PAUSED, "close") is PaperAccountState.CLOSED


def test_close_is_terminal() -> None:
    with pytest.raises(PaperAccountError):
        next_state(PaperAccountState.CLOSED, "resume")


def test_unknown_action_rejected() -> None:
    with pytest.raises(PaperAccountError):
        next_state(PaperAccountState.ACTIVE, "rebalance")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"market": "US"}, "unsupported market"),
        ({"frequency": "1m"}, "unsupported frequency"),
        ({"instrument_ids": ()}, "at least one instrument"),
        ({"initial_cash": Decimal("0")}, "initial_cash must be positive"),
    ],
)
def test_account_validation(kwargs: dict[str, object], message: str) -> None:
    base = {
        "id": "pa_1",
        "owner": "t",
        "draft_id": "sd_1",
        "artifact_address": "a",
        "content_hash": "h",
        "market": "CN_A",
        "instrument_ids": ("600000.SH",),
        "frequency": "1d",
        "initial_cash": Decimal("100"),
        "state": PaperAccountState.ACTIVE,
        "created_at": datetime(2026, 8, 22, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 22, tzinfo=UTC),
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        PaperAccount(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("frequency", ["1d", "5m", "15m", "30m", "60m"])
def test_account_accepts_supported_frequencies(frequency: str) -> None:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    account = PaperAccount(
        id="pa_2",
        owner="t",
        draft_id="sd_1",
        artifact_address="a",
        content_hash="h",
        market="CN_A",
        instrument_ids=("600000.SH",),
        frequency=frequency,
        initial_cash=Decimal("100"),
        state=PaperAccountState.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    assert account.frequency == frequency


def test_payload_round_trip_fields() -> None:
    payload = _account().payload()
    assert payload["market"] == "CN_A"
    assert payload["state"] == "ACTIVE"
    assert payload["initial_cash"] == 1000000.0
