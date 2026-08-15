from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from quant_platform.markets.nt.instruments import (
    equity_instrument,
    futures_contract,
)
from quant_platform.markets.nt.sessions import (
    A_SHARE_SESSIONS,
    TradingSession,
    in_sessions,
    is_night_session,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_equity_instrument_sse_venue() -> None:
    instrument = equity_instrument(symbol="600000")

    assert instrument.id.venue.value == "SSE"
    assert instrument.id.symbol.value == "600000"
    assert instrument.lot_size.as_double() == 100.0
    assert instrument.price_increment.as_double() == 0.01


def test_equity_instrument_szse_venue() -> None:
    instrument = equity_instrument(symbol="000001")

    assert instrument.id.venue.value == "SZSE"
    assert instrument.id.symbol.value == "000001"


def test_futures_contract_multiplier() -> None:
    instrument = futures_contract(
        symbol="RB2610",
        venue="SHFE",
        underlying="RB",
        price_increment="1",
        multiplier="10",
        price_precision=0,
        activation_ns=0,
        expiration_ns=1_000_000_000,
    )

    assert instrument.id.venue.value == "SHFE"
    assert instrument.multiplier.as_double() == 10.0
    assert instrument.underlying == "RB"


def test_trading_session_contains() -> None:
    session = TradingSession(time(9, 30), time(11, 30))

    assert session.contains(time(10, 0))
    assert not session.contains(time(9, 29))
    assert not session.contains(time(11, 30))


def test_trading_session_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        TradingSession(time(11, 30), time(9, 30))


def test_is_night_session() -> None:
    assert is_night_session(datetime(2026, 8, 14, 21, 0, tzinfo=SHANGHAI))
    assert not is_night_session(datetime(2026, 8, 14, 14, 0, tzinfo=SHANGHAI))


def test_in_sessions() -> None:
    moment = datetime(2026, 8, 14, 10, 0, tzinfo=SHANGHAI)
    assert in_sessions(moment, A_SHARE_SESSIONS)
    assert not in_sessions(
        datetime(2026, 8, 14, 12, 0, tzinfo=SHANGHAI), A_SHARE_SESSIONS
    )
