from datetime import UTC, datetime

import pytest

from quant_platform.security import (
    AuthenticationError,
    AuthenticationMethod,
    Principal,
    StaticBearerPrincipalProvider,
)


def make_principal() -> Principal:
    return Principal(
        subject="service:test-suite",
        display_name="Test Suite",
        authentication_method=AuthenticationMethod.TEST_BEARER,
        authenticated_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def test_static_bearer_provider_authenticates_registered_test_token() -> None:
    principal = make_principal()
    provider = StaticBearerPrincipalProvider({"test-token": principal})

    assert provider.authenticate("Bearer test-token") is principal


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc", "Bearer", "Bearer unknown", "bearer test-token"],
)
def test_static_bearer_provider_rejects_missing_or_invalid_credentials(
    authorization: str | None,
) -> None:
    provider = StaticBearerPrincipalProvider({"test-token": make_principal()})

    with pytest.raises(AuthenticationError) as error:
        provider.authenticate(authorization)

    assert error.value.code == "AUTHENTICATION_REQUIRED"
    assert error.value.status == 401


def test_static_bearer_provider_refuses_empty_token_registration() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        StaticBearerPrincipalProvider({"": make_principal()})
