from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from quant_platform.data_gateway.akshare_vendor import AkShareVendorAdapter
from quant_platform.data_gateway.vendor import VendorSourceClass


class FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.columns = list(rows[0].keys()) if rows else []
        self.empty = not rows

    def iterrows(self) -> list[tuple[int, FakeRow]]:
        return [(index, FakeRow(row)) for index, row in enumerate(self._rows)]


class FakeRow:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def get(self, key: str) -> object:
        return self._data.get(key)

    def __getitem__(self, key: str) -> object:
        return self._data[key]


def fake_module() -> SimpleNamespace:
    def stock_zh_a_hist(**kwargs: object) -> FakeFrame:
        return FakeFrame(
            [
                {"date": date(2026, 8, 3), "close": "10.5"},
                {"date": date(2026, 8, 4), "close": "11.0"},
            ]
        )

    def futures_zh_daily_sina(symbol: str) -> FakeFrame:
        return FakeFrame(
            [
                {"date": date(2026, 8, 3), "close": "4000"},
                {"date": date(2026, 8, 4), "close": "4100"},
            ]
        )

    return SimpleNamespace(
        stock_zh_a_hist=stock_zh_a_hist,
        futures_zh_daily_sina=futures_zh_daily_sina,
    )


def adapter() -> AkShareVendorAdapter:
    return AkShareVendorAdapter(
        module=fake_module(),
        clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )


def test_akshare_adapter_marks_rows_exploratory() -> None:
    response = adapter().fetch(("600000",), date(2026, 8, 1), date(2026, 8, 31))

    assert response.source_class is VendorSourceClass.EXPLORATORY
    assert response.exploratory
    assert response.formal_rows() == ()


def test_akshare_adapter_fetches_stock_daily_bars() -> None:
    response = adapter().fetch(("600000",), date(2026, 8, 1), date(2026, 8, 31))

    assert len(response.rows) == 2
    assert response.rows[0].instrument_id == "600000"
    assert response.rows[0].field == "market.eod.close"
    assert response.rows[0].value == "10.5"
    assert response.rows[1].value == "11.0"


def test_akshare_adapter_routes_futures_symbols() -> None:
    response = adapter().fetch(("RB2510",), date(2026, 8, 1), date(2026, 8, 31))

    assert len(response.rows) == 2
    assert response.rows[0].instrument_id == "RB2510"
    assert response.rows[0].value == "4000.0"


def test_akshare_adapter_rows_have_pit_contract() -> None:
    response = adapter().fetch(("600000",), date(2026, 8, 1), date(2026, 8, 31))

    row = response.rows[0]
    assert row.event_time <= row.available_time
    assert row.ingested_at >= row.available_time
    assert row.revision_id.startswith("akshare-")
    assert row.license_tag == "exploratory"


def test_akshare_adapter_ignores_missing_symbol() -> None:
    def no_data(**kwargs: object) -> FakeFrame:
        raise ValueError("no data")

    module = SimpleNamespace(
        stock_zh_a_hist=no_data,
        futures_zh_daily_sina=lambda symbol: no_data(),
    )
    adapter_missing = AkShareVendorAdapter(
        module=module,
        clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )

    response = adapter_missing.fetch(("NOPE",), date(2026, 8, 1), date(2026, 8, 31))

    assert response.rows == ()
