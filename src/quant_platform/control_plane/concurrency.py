"""Strong ETag and If-Match concurrency helpers."""

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.control_plane.contracts import Problem, ProblemError


class ETag(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)

    @property
    def header_value(self) -> str:
        return format_etag(self.version)


def format_etag(version: str) -> str:
    if not version.strip() or '"' in version or version.startswith("W/"):
        raise ValueError("ETag version must be a non-empty strong token")
    return f'"{version}"'


def parse_strong_etag(value: str) -> str:
    if not value or value.startswith("W/") or len(value) < 3:
        raise ValueError("If-Match must contain a strong ETag")
    if not (value.startswith('"') and value.endswith('"')):
        raise ValueError("If-Match must contain a quoted strong ETag")
    version = value[1:-1]
    if not version or '"' in version or "," in version:
        raise ValueError("If-Match must contain one strong ETag")
    return version


def matches_if_match(if_match: str, current_version: str) -> bool:
    try:
        return parse_strong_etag(if_match) == current_version
    except ValueError:
        return False


def require_if_match(
    if_match: str | None,
    current_version: str,
    *,
    request_id: str,
) -> None:
    if if_match is None:
        raise ProblemError(
            Problem(
                title="If-Match required",
                status=428,
                detail="Mutating an existing aggregate requires its strong ETag.",
                code="PRECONDITION_REQUIRED",
                request_id=request_id,
                retryable=True,
                current_version=current_version,
            )
        )
    try:
        supplied_version = parse_strong_etag(if_match)
    except ValueError as exc:
        raise ProblemError(
            Problem(
                title="Invalid If-Match",
                status=400,
                detail=str(exc),
                code="INVALID_IF_MATCH",
                request_id=request_id,
                retryable=False,
                current_version=current_version,
            )
        ) from exc
    if supplied_version != current_version:
        raise ProblemError(
            Problem(
                title="Resource version conflict",
                status=412,
                detail="The aggregate changed before this command was applied.",
                code="ETAG_MISMATCH",
                request_id=request_id,
                retryable=True,
                current_version=current_version,
            )
        )
