"""Tests for runtime monitoring: staleness + kill switch binding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from quant_platform.paper.monitor import PaperMonitor, kill_switch_tripped
from quant_platform.research.models import Base, ExecutionStateModel


def _monitor(**kwargs: int) -> PaperMonitor:
    return PaperMonitor(account_id="pa_1", expected_interval_seconds=60, **kwargs)


def test_healthy_when_cycle_recent() -> None:
    monitor = _monitor()
    now = datetime.now(UTC)
    monitor.record_cycle(at=now)
    monitor.record_bars(count=1, at=now)
    assert monitor.is_stale(now=now + timedelta(seconds=120)) is False
    assert monitor.health_payload(now=now + timedelta(seconds=120))["stale"] is False


def test_stale_when_no_bar_within_window() -> None:
    monitor = _monitor()
    now = datetime.now(UTC)
    monitor.record_cycle(at=now)
    monitor.record_bars(count=1, at=now)
    later = now + timedelta(seconds=181)  # 60s × 3 multiplier + ε
    assert monitor.is_stale(now=later) is True


def test_stale_when_never_received_bars() -> None:
    monitor = _monitor()
    now = datetime.now(UTC)
    monitor.record_cycle(at=now)
    later = now + timedelta(seconds=181)
    assert monitor.is_stale(now=later) is True
    assert monitor.is_stale(now=now + timedelta(seconds=60)) is False


def test_not_stale_before_first_cycle() -> None:
    monitor = _monitor()
    assert monitor.is_stale() is False


def test_error_is_surfaced() -> None:
    monitor = _monitor()
    monitor.record_error("boom")
    assert monitor.health_payload()["last_error"] == "boom"


def test_kill_switch_read() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    assert kill_switch_tripped(sessions) is False  # 缺行 = 未触发

    with sessions.begin() as session:
        session.add(
            ExecutionStateModel(
                state_id="cn-a",
                kill_switch_state="TRIPPED",
                tripped_by="tester",
                reason="drill",
                shadow_positions={},
                paper_positions={},
                updated_at=datetime.now(UTC),
            )
        )
    assert kill_switch_tripped(sessions) is True
