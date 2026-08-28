"""Router tests for the read-only data service (label training grant)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from quant_platform.data_gateway.models import PITRow
from quant_platform.factor_construction.data_service import (
    PitDataService,
    build_data_service_router,
)
from quant_platform.research.api import ResearchGrant, ResearchPrincipal


class _FakeStore:
    def __init__(self, rows: tuple[PITRow, ...]) -> None:
        self._rows = rows

    def load(
        self,
        *,
        instrument_ids: tuple[str, ...],
        field_prefix: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[PITRow, ...]:
        del instrument_ids, field_prefix, start, end
        return self._rows


def _row(field: str, instrument_id: str, value: float, day: int) -> PITRow:
    t = datetime(2026, 8, day, 7, 0, tzinfo=UTC)
    return PITRow(
        dataset_id="market",
        field=field,
        instrument_id=instrument_id,
        event_time=t,
        available_time=t,
        ingested_at=t,
        revision_id="rev-1",
        source_id="ifind-cn",
        license_tag="licensed-research",
        value=value,
    )


def _provider(*, train: bool) -> Callable[[str], ResearchPrincipal | None]:
    def resolve(token: str) -> ResearchPrincipal | None:
        if token != "test-researcher":
            return None
        caps = ["factor_construction.train"] if train else []
        return ResearchPrincipal(
            actor_id="researcher-1",
            grants=frozenset(
                ResearchGrant(capability=cap, project_id="local", market="CN_A")
                for cap in caps
            ),
        )

    return resolve


def _client(*, train: bool) -> TestClient:
    from fastapi import FastAPI

    from quant_platform.research.api import install_problem_handlers

    rows = tuple(
        _row("market.eod.vwap", "A", p, 1 + i)
        for i, p in enumerate([100.0, 100.0, 110.0])
    )
    service = PitDataService(_FakeStore(rows))  # type: ignore[arg-type]
    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(build_data_service_router(service, _provider(train=train)))
    return TestClient(app)


def test_label_frame_requires_training_grant() -> None:
    client = _client(train=False)
    response = client.post(
        "/v1/data/label-frame",
        json={
            "instrument_ids": ["A"],
            "price_field": "vwap",
            "horizon": 1,
            "decision_time": "2026-08-10T07:00:00Z",
        },
        headers={"Authorization": "Bearer test-researcher"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TRAINING_GRANT_REQUIRED"


def test_label_frame_with_training_grant() -> None:
    client = _client(train=True)
    response = client.post(
        "/v1/data/label-frame",
        json={
            "instrument_ids": ["A"],
            "price_field": "vwap",
            "horizon": 1,
            "decision_time": "2026-08-10T07:00:00Z",
        },
        headers={"Authorization": "Bearer test-researcher"},
    )
    assert response.status_code == 200
    assert len(response.json()["rows"]) == 2


def test_label_frame_requires_auth() -> None:
    client = _client(train=True)
    response = client.post(
        "/v1/data/label-frame",
        json={
            "instrument_ids": ["A"],
            "price_field": "vwap",
            "horizon": 1,
            "decision_time": "2026-08-10T07:00:00Z",
        },
    )
    assert response.status_code == 401
