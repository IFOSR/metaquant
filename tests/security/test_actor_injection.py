from datetime import UTC, datetime

import pytest

from quant_platform.security import (
    AuthenticationError,
    AuthenticationMethod,
    BearerPrincipalProvider,
    Principal,
    PrincipalInjector,
    StaticBearerPrincipalProvider,
)


def principal(method: AuthenticationMethod) -> Principal:
    return Principal(
        subject="user-17",
        display_name="Research User",
        authentication_method=method,
        authenticated_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def test_actor_is_derived_from_the_authenticated_principal() -> None:
    injector = PrincipalInjector(
        StaticBearerPrincipalProvider(
            {"test-token-value": principal(AuthenticationMethod.TEST_BEARER)}
        )
    )

    assert injector.actor("Bearer test-token-value") == "user-17"


def test_production_provider_uses_verified_principal() -> None:
    provider = BearerPrincipalProvider(
        lambda token: principal(AuthenticationMethod.OIDC)
    )

    authenticated = provider.authenticate("Bearer signed-jwt")

    assert authenticated.actor_id == "user-17"


def test_production_provider_rejects_test_principal() -> None:
    provider = BearerPrincipalProvider(
        lambda token: principal(AuthenticationMethod.TEST_BEARER)
    )

    with pytest.raises(AuthenticationError) as error:
        provider.authenticate("Bearer signed-jwt")

    assert error.value.code == "AUTHENTICATION_PROVIDER_MISCONFIGURED"
    assert error.value.status == 500
