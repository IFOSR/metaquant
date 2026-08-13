"""Authentication providers and actor injection boundaries.

OIDC/JWT verification is intentionally an adapter boundary.  The platform
does not accept client-supplied actor fields and does not implement a second
token parser beside the selected identity provider.
"""

from collections.abc import Callable, Mapping
from typing import Protocol

from quant_platform.security.models import (
    AuthenticationError,
    AuthenticationMethod,
    Principal,
)


class PrincipalProvider(Protocol):
    def authenticate(self, authorization: str | None) -> Principal:
        """Resolve an Authorization header into a trusted principal."""


PrincipalVerifier = Callable[[str], Principal]


class StaticBearerPrincipalProvider:
    """Deterministic provider for tests and local service-to-service checks."""

    def __init__(self, principals: Mapping[str, Principal]) -> None:
        if any(not token.strip() for token in principals):
            raise ValueError("Bearer token registrations must be non-empty")
        self._principals = dict(principals)

    def authenticate(self, authorization: str | None) -> Principal:
        token = _extract_bearer_token(authorization)
        try:
            return self._principals[token]
        except KeyError as exc:
            raise AuthenticationError() from exc


class BearerPrincipalProvider:
    """Provider backed by an OIDC/JWT verifier supplied by the application."""

    def __init__(self, verifier: PrincipalVerifier) -> None:
        self._verifier = verifier

    def authenticate(self, authorization: str | None) -> Principal:
        token = _extract_bearer_token(authorization)
        try:
            principal = self._verifier(token)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError() from exc
        if principal.authentication_method is AuthenticationMethod.TEST_BEARER:
            raise AuthenticationError(
                code="AUTHENTICATION_PROVIDER_MISCONFIGURED",
                detail="Production Bearer verification cannot return a test principal.",
                status=500,
            )
        return principal


class OidcPrincipalProvider(BearerPrincipalProvider):
    """Named production adapter for an OIDC issuer's verified JWTs."""


class PrincipalInjector:
    """Framework-neutral actor injection interface.

    Route handlers receive a Principal from this object and derive actor_id
    from it.  There is no method accepting an actor from request JSON.
    """

    def __init__(self, provider: PrincipalProvider) -> None:
        self._provider = provider

    def principal(self, authorization: str | None) -> Principal:
        return self._provider.authenticate(authorization)

    def actor(self, authorization: str | None) -> str:
        return self.principal(authorization).actor_id


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization:
        raise AuthenticationError()
    scheme, separator, token = authorization.partition(" ")
    if scheme != "Bearer" or not separator or not token.strip():
        raise AuthenticationError()
    return token.strip()
