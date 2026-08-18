from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from minio import Minio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from quant_platform import __version__
from quant_platform.artifacts import MinioArtifactStore
from quant_platform.config import get_settings
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.data_gateway.provisioning import DataProvisioning
from quant_platform.experiment_runtime import (
    ExecutionIdentity,
    JsonFormalSnapshotCatalog,
    SqlAlchemyExperimentRepository,
    build_experiment_router,
)
from quant_platform.health import ReadinessProbe, build_readiness_probe
from quant_platform.research.api import (
    ResearchPrincipal,
    ResearchPrincipalProvider,
    adapt_security_principal_provider,
    build_research_router,
    install_problem_handlers,
)
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.security import (
    AuthenticationMethod,
    Capability,
    Environment,
    Market,
    Principal,
    Scope,
    StaticBearerPrincipalProvider,
)
from quant_platform.validation import (
    JsonLabelSnapshotCatalog,
    JsonPromotionPolicyCatalog,
    JsonValidationPolicyCatalog,
)


def _default_principal_provider(token: str) -> ResearchPrincipal | None:
    capability_names = (
        # 后端授权检查使用的能力
        "research.jobs.read",
        "research.jobs.write",
        "research.jobs.manage",
        "research.briefs.write",
        "research.briefs.freeze",
        "research.experiments.read",
        "research.experiments.preregister",
        "research.experiments.run",
        "research.strategy.read",
        "research.governance.approve",
        # 前端导航与操作边界使用的能力
        "research.jobs.propose",
        "strategy.read",
        "execution.read",
        "approval.read",
    )
    scopes = [
        Scope(project_id="local", market=market, environment=environment)
        for environment in (Environment.RESEARCH, Environment.PAPER, Environment.LIVE)
        for market in (Market.CN_A, Market.CN_COMMODITY_FUTURES)
    ]
    capabilities = frozenset(
        Capability(name=name, scope=scope)
        for scope in scopes
        for name in capability_names
    )
    provider = StaticBearerPrincipalProvider(
        {
            "local-researcher": Principal(
                subject="local-researcher",
                display_name="Local Researcher",
                authentication_method=AuthenticationMethod.TEST_BEARER,
                authenticated_at=datetime.now(UTC),
                roles=frozenset({"Researcher"}),
                capabilities=capabilities,
            )
        }
    )
    return adapt_security_principal_provider(provider)(token)


def create_app(
    readiness_probe: ReadinessProbe | None = None,
    research_repository: SqlAlchemyResearchRepository | None = None,
    experiment_repository: SqlAlchemyExperimentRepository | None = None,
    research_principal_provider: ResearchPrincipalProvider | None = None,
) -> FastAPI:
    settings = get_settings()
    probe = readiness_probe or build_readiness_probe(settings)
    repository = research_repository or SqlAlchemyResearchRepository(
        create_engine(str(settings.database_url), pool_pre_ping=True)
    )
    provisioning: DataProvisioning | None = None
    if experiment_repository is None:
        engine = create_engine(str(settings.database_url), pool_pre_ping=True)
        minio_endpoint = settings.minio_endpoint.removeprefix("http://").removeprefix(
            "https://"
        )
        experiment_repository = SqlAlchemyExperimentRepository(
            engine,
            research_repository=repository,
            artifact_store=MinioArtifactStore(
                Minio(
                    minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key.get_secret_value(),
                    secure=settings.minio_secure
                    or settings.minio_endpoint.startswith("https://"),
                ),
                bucket=settings.minio_bucket,
            ),
            snapshot_catalog=JsonFormalSnapshotCatalog.from_path(
                Path(settings.formal_snapshot_catalog_path)
            ),
            execution_identity=ExecutionIdentity.resolved(
                code_sha=settings.execution_code_sha,
                image_digest=settings.execution_image_digest,
                dependency_lock_hash=settings.execution_dependency_lock_hash,
                executor_version=settings.execution_executor_version,
                config_hash=settings.execution_config_hash,
                config_path=Path(settings.formal_snapshot_catalog_path),
            ),
            policy_catalog=JsonValidationPolicyCatalog.from_path(
                Path(settings.validation_policy_catalog_path)
            ),
            label_snapshot_catalog=JsonLabelSnapshotCatalog.from_path(
                Path(settings.label_snapshot_catalog_path)
            ),
            promotion_policy_catalog=JsonPromotionPolicyCatalog.from_path(
                Path(settings.promotion_policy_catalog_path)
            ),
        )
        provisioning = DataProvisioning(SqlAlchemyPitStore(sessionmaker(engine)))
    principal_provider = research_principal_provider or _default_principal_provider
    application = FastAPI(
        title="Quant Platform API",
        version=__version__,
    )
    install_problem_handlers(application)
    application.include_router(build_research_router(repository, principal_provider))
    application.include_router(
        build_experiment_router(experiment_repository, principal_provider, provisioning)
    )

    @application.get("/health/live", tags=["health"])
    def liveness() -> dict[str, str]:
        return {"service": settings.app_name, "status": "ok"}

    @application.get("/health/ready", tags=["health"])
    def readiness() -> JSONResponse:
        results = probe()
        ready = all(results.values())
        content = {
            "status": "ok" if ready else "degraded",
            "checks": {
                name: "ok" if available else "failed"
                for name, available in results.items()
            },
        }
        return JSONResponse(status_code=200 if ready else 503, content=content)

    return application


app = create_app()
