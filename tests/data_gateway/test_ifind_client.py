from __future__ import annotations

import pytest

from quant_platform.data_gateway.ifind_client import HttpPost, IFindClient


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
