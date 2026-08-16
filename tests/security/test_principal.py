from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quant_platform.security import (
    AuthenticationMethod,
    Capability,
    Environment,
    Market,
    Principal,
    Scope,
)


def test_principal_exposes_only_scoped_capabilities() -> None:
    scope = Scope(
        project_id="project-alpha",
        market=Market.CN_A,
        environment=Environment.RESEARCH,
    )
    principal = Principal(
        subject="user-42",
        display_name="Researcher",
        authentication_method=AuthenticationMethod.TEST_BEARER,
        authenticated_at=datetime(2026, 8, 11, tzinfo=UTC),
        roles=frozenset({"Researcher"}),
        capabilities=frozenset(
            {
                Capability(name="research.jobs.read", scope=scope),
                Capability(name="research.jobs.create", scope=scope),
            }
        ),
    )

    assert principal.actor_id == "user-42"
    assert principal.can("research.jobs.read", scope)
    assert not principal.can(
        "research.jobs.read",
        Scope(
            project_id="project-beta",
            market=Market.CN_A,
            environment=Environment.RESEARCH,
        ),
    )


@pytest.mark.parametrize("environment", [Environment.PAPER, Environment.LIVE])
def test_capabilities_are_allowed_outside_research(
    environment: Environment,
) -> None:
    capability = Capability(
        name="approvals.decide",
        scope=Scope(
            project_id="project-alpha",
            market=Market.CN_A,
            environment=environment,
        ),
    )
    assert capability.scope.environment is environment


def test_principal_requires_an_authenticated_subject() -> None:
    with pytest.raises(ValidationError):
        Principal(
            subject=" ",
            display_name="Nobody",
            authentication_method=AuthenticationMethod.TEST_BEARER,
            authenticated_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
