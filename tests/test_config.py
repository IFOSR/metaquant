import pytest

from quant_platform.config import Settings


def test_settings_read_runtime_dependencies_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:secret@postgres:5432/platform",
    )
    monkeypatch.setenv("MINIO_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "local-access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "local-secret")
    monkeypatch.setenv("MINIO_BUCKET", "artifacts")

    settings = Settings(_env_file=None)

    assert settings.database_url.hosts()[0]["host"] == "postgres"
    assert settings.minio_endpoint == "http://minio:9000"
    assert settings.minio_bucket == "artifacts"
