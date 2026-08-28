"""Tests for on-demand strategy data provisioning (G19-P4)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.research.models import Base
from quant_platform.strategy_generation import provisioning
from quant_platform.strategy_generation.provisioning import (
    SHANGHAI,
    StrategyDataProvisioner,
    StrategyProvisionError,
    _clamp_eod_end,
    _ifind_stock_code,
)

TS = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def _row(instrument: str, field: str) -> RawPITRow:
    return RawPITRow(
        source_id="ifind-cn",
        dataset_id="market-eod",
        field=field,
        instrument_id=instrument,
        event_time=TS,
        available_time=TS,
        ingested_at=TS,
        revision_id="r1",
        license_tag="formal",
        value_type="decimal",
        value="10.0",
    )


def make_provisioner() -> StrategyDataProvisioner:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return StrategyDataProvisioner(sessionmaker(engine))


def test_ifind_stock_code_mapping() -> None:
    assert _ifind_stock_code("600000.SSE") == "600000.SH"
    assert _ifind_stock_code("000001.SZSE") == "000001.SZ"


def test_clamp_eod_end_before_market_close() -> None:
    """15:20 前「今天」的日线尚未可用，终点收敛到上一交易日。"""
    before_close = datetime(2026, 8, 24, 5, 0, tzinfo=SHANGHAI)
    assert _clamp_eod_end(date(2026, 8, 24), now=before_close) == date(2026, 8, 23)


def test_clamp_eod_end_after_market_close() -> None:
    """15:20 后今天的日线已可用，终点保持今天。"""
    after_close = datetime(2026, 8, 24, 16, 0, tzinfo=SHANGHAI)
    assert _clamp_eod_end(date(2026, 8, 24), now=after_close) == date(2026, 8, 24)


def test_clamp_eod_end_historical_window_untouched() -> None:
    """显式历史终点不被收敛。"""
    before_close = datetime(2026, 8, 24, 5, 0, tzinfo=SHANGHAI)
    assert _clamp_eod_end(date(2026, 8, 20), now=before_close) == date(2026, 8, 20)


def test_clamp_eod_end_future_window_capped() -> None:
    """显式未来终点收敛到最后一个可用交易日。"""
    before_close = datetime(2026, 8, 24, 5, 0, tzinfo=SHANGHAI)
    assert _clamp_eod_end(date(2026, 9, 1), now=before_close) == date(2026, 8, 23)


def test_provision_daily_stock_persists_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_daily(
        self: StrategyDataProvisioner,
        symbol: str,
        venue: str,
        db_id: str,
        start: date,
        end: date,
    ) -> list[RawPITRow]:
        return [
            _row(db_id, f"market.eod.{field}")
            for field in ("open", "high", "low", "close", "volume")
        ]

    monkeypatch.setattr(StrategyDataProvisioner, "_daily", fake_daily)
    provisioner = make_provisioner()
    result = provisioner.provision(instrument_ids=("600000.SH",), frequency="1d")
    assert result.rows == 5
    assert result.instrument_ids == ("600000.SSE",)
    # 数据入库后，data_status 应该就绪
    from quant_platform.strategy_generation.service import StrategyBacktestService

    status = StrategyBacktestService(provisioner._store._sessions).data_status(
        instrument_ids=("600000.SH",), frequencies=("1d",)
    )
    assert status["ready"] is True


def test_provision_raises_when_nothing_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        StrategyDataProvisioner,
        "_minute",
        lambda self, symbol, venue, db_id, frequency, start, end: [],
    )
    provisioner = make_provisioner()
    with pytest.raises(StrategyProvisionError):
        provisioner.provision(instrument_ids=("AU2610.SHF",), frequency="5m")


def test_provision_rejects_bad_frequency() -> None:
    provisioner = make_provisioner()
    with pytest.raises(StrategyProvisionError):
        provisioner.provision(instrument_ids=("600000.SH",), frequency="1m")


def test_provisioning_module_exports() -> None:
    assert provisioning.StrategyDataProvisioner is not None
