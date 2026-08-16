"""Authentication principals and authorization capabilities.

Principals may be scoped to research, paper, or live environments.  The
local single-user deployment grants the demo identity every environment;
production rollouts are expected to reintroduce gating in a separately
reviewed policy package.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Market(str, Enum):
    CN_A = "CN_A"
    CN_COMMODITY_FUTURES = "CN_COMMODITY_FUTURES"


class Environment(str, Enum):
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    LIVE = "LIVE"


class AuthenticationMethod(str, Enum):
    OIDC = "OIDC"
    BEARER_JWT = "BEARER_JWT"
    TEST_BEARER = "TEST_BEARER"


class Scope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str = Field(min_length=1)
    market: Market
    environment: Environment = Environment.RESEARCH

    @field_validator("project_id")
    @classmethod
    def project_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project_id must not be blank")
        return value


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    scope: Scope

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("capability name must not be blank")
        return value


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    authentication_method: AuthenticationMethod
    authenticated_at: datetime
    roles: frozenset[str] = frozenset()
    capabilities: frozenset[Capability] = frozenset()

    @field_validator("subject", "display_name")
    @classmethod
    def identity_fields_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity fields must not be blank")
        return value

    @property
    def actor_id(self) -> str:
        """Return the immutable server-side actor identifier."""

        return self.subject

    def can(self, capability_name: str, scope: Scope) -> bool:
        return any(
            capability.name == capability_name and capability.scope == scope
            for capability in self.capabilities
        )

    def has_role(self, role: str) -> bool:
        return role in self.roles


class AuthenticationError(Exception):
    """Stable authentication failure suitable for an API problem response."""

    def __init__(
        self,
        code: str = "AUTHENTICATION_REQUIRED",
        detail: str = "A valid Bearer credential is required.",
        *,
        status: int = 401,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.retryable = False
