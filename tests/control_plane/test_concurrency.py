import pytest

from quant_platform.control_plane import (
    ProblemError,
    format_etag,
    parse_strong_etag,
    require_if_match,
)


def test_strong_etag_round_trip() -> None:
    assert format_etag("17") == '"17"'
    assert parse_strong_etag('"17"') == "17"


@pytest.mark.parametrize("value", ['W/"17"', "17", '"17","18"', ""])
def test_weak_or_ambiguous_etag_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        parse_strong_etag(value)


def test_existing_aggregate_mutation_requires_if_match() -> None:
    with pytest.raises(ProblemError) as error:
        require_if_match(None, "17", request_id="req-42")

    assert error.value.problem.status == 428
    assert error.value.problem.current_version == "17"


def test_stale_aggregate_mutation_reports_current_version() -> None:
    with pytest.raises(ProblemError) as error:
        require_if_match('"16"', "17", request_id="req-42")

    assert error.value.problem.code == "ETAG_MISMATCH"
    assert error.value.problem.status == 412
    assert error.value.problem.current_version == "17"


def test_current_aggregate_version_is_accepted() -> None:
    require_if_match('"17"', "17", request_id="req-42")
