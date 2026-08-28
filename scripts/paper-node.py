"""Run one paper account as a long-lived simulated trading node.

Usage:
    python scripts/paper-node.py --account-id pa_xxxx [--poll-interval 60]

The script verifies the account is ACTIVE, re-verifies the frozen artifact
from MinIO, then starts a NautilusTrader live-kernel node whose orders fill
against the China-market simulated exchange. Bars arrive incrementally from
the PIT store per the account's frequency; fills/positions/equity reconcile
into PostgreSQL every cycle.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from minio import Minio  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from quant_platform.artifacts.store import MinioArtifactStore  # noqa: E402
from quant_platform.config import get_settings  # noqa: E402
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore  # noqa: E402
from quant_platform.paper.artifact import (
    FrozenStrategyArtifact,  # noqa: E402
    StrategyArtifactStore,  # noqa: E402
)
from quant_platform.paper.contracts import PaperAccountError  # noqa: E402
from quant_platform.paper.data_client import PitBarPoller  # noqa: E402
from quant_platform.paper.node import PaperNodeRunner, warmup_bars_for  # noqa: E402
from quant_platform.paper.repository import SqlAlchemyPaperRepository  # noqa: E402
from quant_platform.paper.service import PaperAccountService  # noqa: E402
from quant_platform.strategy_generation.repository import (  # noqa: E402
    SqlAlchemyStrategyRepository,
)


def _minio_store(settings: object) -> StrategyArtifactStore:
    endpoint = settings.minio_endpoint.removeprefix("http://").removeprefix(  # type: ignore[attr-defined]
        "https://"
    )
    client = Minio(
        endpoint,
        access_key=settings.minio_access_key,  # type: ignore[attr-defined]
        secret_key=settings.minio_secret_key.get_secret_value(),  # type: ignore[attr-defined]
        secure=settings.minio_secure  # type: ignore[attr-defined]
        or settings.minio_endpoint.startswith("https://"),  # type: ignore[attr-defined]
    )
    return StrategyArtifactStore(
        MinioArtifactStore(client, bucket=settings.minio_bucket)  # type: ignore[attr-defined]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--poll-interval", type=int, default=60)
    parser.add_argument("--warmup-bars", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(str(settings.database_url), pool_pre_ping=True)
    repository = SqlAlchemyPaperRepository(engine)
    service = PaperAccountService(
        repository=repository,
        artifacts=_minio_store(settings),
        drafts=SqlAlchemyStrategyRepository(engine),
    )
    try:
        account = service.require_active(args.account_id)
    except (KeyError, PaperAccountError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    artifact: FrozenStrategyArtifact = service._artifacts.load(  # noqa: SLF001
        account.artifact_address
    )

    poller = PitBarPoller(
        store=SqlAlchemyPitStore(sessionmaker(engine)),
        instrument_ids=account.instrument_ids,
        frequency=account.frequency,
        warmup_bars=(
            args.warmup_bars
            if args.warmup_bars is not None
            else warmup_bars_for(account.frequency)
        ),
    )
    runner = PaperNodeRunner(
        account=account,
        code=artifact.code,
        repository=repository,
        poller=poller,
        poll_interval_seconds=args.poll_interval,
    )
    stop = asyncio.Event()

    # 注意：不要在此处预 build 节点。TradingNode 在构造时绑定当前事件循环，
    # 同步上下文里 build 会让引擎队列消费协程绑到永不运行的默认 loop，
    # 导致订单命令永远无人消费。构建（含失败落库）在 run_until 内完成。

    async def run() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):  # pragma: no cover
                loop.add_signal_handler(sig, stop.set)
        await runner.run_until(stop)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
