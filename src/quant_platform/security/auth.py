"""Authentication providers.

OIDC/JWT verification is intentionally an adapter boundary.  The platform
does not accept client-supplied actor fields and does not implement a second
token parser beside the selected identity provider.

The local single-user deployment uses the deterministic static bearer provider;
production identity verification is reintroduced as a separately reviewed
adapter package when needed.
"""

from collections.abc import Mapping
from typing import Protocol

from quant_platform.security.models import (
    AuthenticationError,
    Principal,
)


class PrincipalProvider(Protocol):
    def authenticate(self, authorization: str | None) -> Principal:
        """Resolve an Authorization header into a trusted principal."""


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


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization:
        raise AuthenticationError()
    scheme, separator, token = authorization.partition(" ")
    if scheme != "Bearer" or not separator or not token.strip():
        raise AuthenticationError()
    return token.strip()
