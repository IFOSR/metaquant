from functools import lru_cache

from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "quant-platform-api"
    environment: str = "local"
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+psycopg://quant_app:quant_app_dev@localhost:55432/quant_platform"
    )
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "quant_minio"
    minio_secret_key: SecretStr = SecretStr("quant_minio_dev")
    minio_bucket: str = "artifacts"
    minio_secure: bool = False
    formal_snapshot_catalog_path: str = "/app/config/formal-snapshots.json"
    label_snapshot_catalog_path: str = "/app/config/label-snapshots.json"
    validation_policy_catalog_path: str = "/app/config/validation-policies.json"
    promotion_policy_catalog_path: str = "/app/config/promotion-policies.json"
    execution_code_sha: str = "0" * 40
    execution_image_digest: str = "sha256:" + "0" * 64
    execution_dependency_lock_hash: str = "0" * 64
    execution_executor_version: str = "factor-executor/v1"
    execution_config_hash: str = "0" * 64
    sandbox_image: str = "quant-sandbox:local"
    sandbox_use_docker: bool = False
    # pi Agent（非交互）基座模型配置：仅对本项目调用生效，不写 pi 全局配置。
    pi_provider: str = ""
    pi_model: str = ""
    pi_api_key: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
