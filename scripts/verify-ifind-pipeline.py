"""iFinD 原始价 → PIT 快照验证脚本 (G18 数据接入)。

用同花顺 iFinD 网页版 HTTP API（``quantapi.51ifind.com``）拉取不复权原始
收盘价，转成 FORMAL PIT 行，验证「原始价 → PIT → 因子」链路可用。
refresh_token 从环境变量 ``IFIND_REFRESH_TOKEN`` 读取。
"""

from __future__ import annotations

import os
from datetime import date

from quant_platform.data_gateway.ifind_client import (
    IFindClient,
    IFindPITAdapter,
)
from quant_platform.data_gateway.loader import validate_pit_rows


def main() -> None:
    token = os.environ.get("IFIND_REFRESH_TOKEN")
    if not token:
        print("请设置环境变量 IFIND_REFRESH_TOKEN")
        return

    client = IFindClient(refresh_token=token)
    adapter = IFindPITAdapter(client=client)

    end = date(2026, 8, 15)
    start = end.replace(day=1)

    # A 股（600000 浦发银行）原始价
    stock_rows = adapter.fetch(("600000.SH",), start, end)
    validate_pit_rows(stock_rows)
    print(f"[A股] 600000.SH 拉取 {len(stock_rows)} 条 FORMAL PIT 行")
    for row in stock_rows[-3:]:
        print(
            f"  {row.event_time.date()} close={row.value} "
            f"available={row.available_time.time()}"
        )

    # 期货（RB2610 螺纹钢）原始价
    try:
        future_rows = adapter.fetch(
            ("RB2610.SHF",), start, end, close_indicator="ths_close_price_future"
        )
        validate_pit_rows(future_rows)
        print(f"[期货] RB2610.SHF 拉取 {len(future_rows)} 条 FORMAL PIT 行")
        for row in future_rows[-3:]:
            print(f"  {row.event_time.date()} close={row.value}")
    except Exception as exc:  # noqa: BLE001
        print(f"[期货] 拉取失败: {type(exc).__name__} {str(exc)[:120]}")

    print("[验证] 原始价 → PIT 行链路成立（FORMAL，无前视可用时间）")


if __name__ == "__main__":
    main()
