from collections.abc import Callable
from typing import cast
from urllib.parse import urlparse

from minio import Minio
from sqlalchemy import create_engine, text

from quant_platform.config import Settings

ReadinessProbe = Callable[[], dict[str, bool]]


def _postgres_ready(settings: Settings) -> bool:
    engine = create_engine(str(settings.database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            migration_present = connection.execute(
                text("SELECT to_regclass('public.platform_health_probe') IS NOT NULL")
            ).scalar_one()
            return bool(migration_present)
    except Exception:
        return False
    finally:
        engine.dispose()


def _minio_ready(settings: Settings) -> bool:
    parsed = urlparse(settings.minio_endpoint)
    endpoint = parsed.netloc or parsed.path
    secure = settings.minio_secure or parsed.scheme == "https"
    client = Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=secure,
    )
    try:
        return cast(bool, client.bucket_exists(settings.minio_bucket))
    except Exception:
        return False


def build_readiness_probe(settings: Settings) -> ReadinessProbe:
    def probe() -> dict[str, bool]:
        return {
            "postgres": _postgres_ready(settings),
            "minio": _minio_ready(settings),
        }

    return probe
