"""LiveFeed 回放器：历史价格 × 虚拟行情时钟 → PIT（paper trading 数据平面）。

用法（api 容器内）：
    python scripts/live-feed.py --instruments RB2610.SHF --speed 10

paper 节点零改动：PitBarPoller 按水位线消费新 bar，与真实实时行情同构。
"""

from __future__ import annotations

import argparse
import signal
import sys
from datetime import datetime
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from quant_platform.config import get_settings  # noqa: E402
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore  # noqa: E402
from quant_platform.paper.live_feed import ReplayFeed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--instruments", required=True, help="逗号分隔，如 RB2610.SHF,AU2610.SHF"
    )
    parser.add_argument("--market", default="CN_COMMODITY_FUTURES")
    parser.add_argument("--speed", type=float, default=10.0, help="回放倍速（1=真实速度）")
    parser.add_argument("--source-from", default=None, help="源价格序列起点（ISO 日期）")
    parser.add_argument(
        "--start-at", default=None, help="虚拟行情时钟起点（ISO 时间，默认当前）"
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(str(settings.database_url), pool_pre_ping=True)
    feed = ReplayFeed(
        store=SqlAlchemyPitStore(sessionmaker(engine)),
        instrument_ids=tuple(args.instruments.split(",")),
        market=args.market,
        speed=args.speed,
        source_from=(
            datetime.fromisoformat(args.source_from) if args.source_from else None
        ),
        start_at=datetime.fromisoformat(args.start_at) if args.start_at else None,
    )
    stop = Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    print(f"live-feed replaying {args.instruments} at {args.speed}x", flush=True)
    feed.run(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
