from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from quant_platform.data_gateway.ifind_client import (
    HttpPost,
    IFindClient,
    IFindPITAdapter,
    close_series_to_pit_rows,
    fetch_close_series,
    parse_date_sequence,
)


def fake_post(responses: dict[str, dict[str, object]]) -> HttpPost:
    def post(
        path: str, body: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        assert path in responses, f"unexpected path {path}"
        return responses[path]

    return post


def test_get_access_token_exchanges_refresh_token() -> None:
    post = fake_post(
        {"/api/v1/get_access_token": {"errorcode": 0, "access_token": "at-123"}}
    )
    client = IFindClient("refresh-1", post=post)

    assert client.get_access_token() == "at-123"


def test_get_access_token_is_cached() -> None:
    calls: list[str] = []

    def post(
        path: str, body: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        calls.append(path)
        return {"errorcode": 0, "access_token": "at-1"}

    client = IFindClient("refresh-1", post=post)
    client.get_access_token()
    client.get_access_token()

    assert calls == ["/api/v1/get_access_token"]


def test_fetch_daily_bars_builds_request() -> None:
    captured: dict[str, object] = {}

    def post(
        path: str, body: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        captured["path"] = path
        captured["body"] = body
        captured["headers"] = headers
        return {"errorcode": 0, "tables": []}

    client = IFindClient(access_token="at-9", post=post)
    client.fetch_daily_bars(
        ("300033.SZ",),
        ("ths_close_price_stock",),
        "20250113",
        "20250113",
    )

    assert captured["path"] == "/api/v1/basic_data_service"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["access_token"] == "at-9"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["codes"] == "300033.SZ"
    indipara = body["indipara"]
    assert (
        isinstance(indipara, list)
        and indipara[0]["indicator"] == "ths_close_price_stock"
    )


def test_fetch_daily_bars_requires_codes() -> None:
    client = IFindClient(access_token="at-1")
    with pytest.raises(ValueError):
        client.fetch_daily_bars((), ("ths_close_price_stock",), "20250101", "20250102")


def test_error_code_raises() -> None:
    client = IFindClient(
        "refresh-1",
        post=fake_post(
            {
                "/api/v1/get_access_token": {
                    "errorcode": -1301,
                    "errmsg": "Refresh_Token is expired or illegal.",
                }
            }
        ),
    )
    with pytest.raises(RuntimeError, match="get_access_token"):
        client.get_access_token()


def test_client_requires_token() -> None:
    with pytest.raises(ValueError, match="refresh_token"):
        IFindClient()


def test_fetch_date_sequence_builds_request() -> None:
    captured: dict[str, object] = {}

    def post(
        path: str, body: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        captured["path"] = path
        captured["body"] = body
        return {"errorcode": 0}

    client = IFindClient(access_token="at-2", post=post)
    client.fetch_date_sequence(
        ("AAPL.O",), ("ths_pre_close_uss",), "20250101", "20250113"
    )

    assert captured["path"] == "/api/v1/date_sequence"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["startdate"] == "20250101"


def test_parse_date_sequence() -> None:
    payload = {
        "errorcode": 0,
        "tables": [
            {
                "thscode": "300033.SZ",
                "time": ["2026-08-10", "2026-08-11"],
                "table": {"ths_close_price_stock": [238.51, 235.99]},
            }
        ],
    }

    parsed = parse_date_sequence(payload)

    assert parsed["300033.SZ"]["2026-08-10"]["ths_close_price_stock"] == 238.51
    assert parsed["300033.SZ"]["2026-08-11"]["ths_close_price_stock"] == 235.99


def test_fetch_close_series_parses_response() -> None:
    def post(
        path: str, body: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        assert path == "/api/v1/date_sequence"
        return {
            "errorcode": 0,
            "tables": [
                {
                    "thscode": "300033.SZ",
                    "time": ["2026-08-10", "2026-08-11"],
                    "table": {"ths_close_price_stock": [238.51, 235.99]},
                }
            ],
        }

    client = IFindClient(access_token="at-3", post=post)
    series = fetch_close_series(client, ("300033.SZ",), "20260810", "20260811")

    assert series["300033.SZ"]["2026-08-10"] == 238.51
    assert series["300033.SZ"]["2026-08-11"] == 235.99


def test_close_series_to_pit_rows_formal() -> None:
    series: dict[str, dict[str, object]] = {"600000.SH": {"2026-08-14": 9.29}}

    rows = close_series_to_pit_rows(
        series,
        source_id="ifind-cn",
        ingested_at=datetime(2026, 8, 15, tzinfo=UTC),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.license_tag == "formal"
    assert row.value == "9.29"
    assert row.instrument_id == "600000.SH"
    assert row.available_time > row.event_time
    assert row.available_time.minute == 20  # 收盘后 20 分钟


def test_ifind_pit_adapter_fetches() -> None:
    class FakeClient:
        def fetch_date_sequence(
            self,
            codes: tuple[str, ...],
            indicators: tuple[str, ...],
            start_date: str,
            end_date: str,
        ) -> dict[str, object]:
            return {
                "errorcode": 0,
                "tables": [
                    {
                        "thscode": "600000.SH",
                        "time": ["2026-08-14"],
                        "table": {"ths_close_price_stock": [9.29]},
                    }
                ],
            }

    adapter = IFindPITAdapter(
        client=FakeClient(),  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 8, 15, tzinfo=UTC),
    )
    rows = adapter.fetch(("600000.SH",), date(2026, 8, 14), date(2026, 8, 14))

    assert len(rows) == 1
    assert rows[0].license_tag == "formal"
    assert rows[0].value == "9.29"
