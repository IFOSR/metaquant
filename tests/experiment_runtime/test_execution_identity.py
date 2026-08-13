from __future__ import annotations

from quant_platform.experiment_runtime.catalog import (
    ExecutionIdentity,
    _execution_code_sha,
)


def test_resolved_derives_placeholder_content_hashes() -> None:
    identity = ExecutionIdentity.resolved(
        code_sha="0" * 40,
        image_digest="sha256:" + "0" * 64,
        dependency_lock_hash="0" * 64,
        executor_version="factor-executor/v1",
        config_hash="0" * 64,
    )

    assert identity.code_sha != "0" * 40
    assert len(identity.code_sha) == 64
    assert identity.dependency_lock_hash != "0" * 64
    assert len(identity.dependency_lock_hash) == 64
    assert identity.config_hash != "0" * 64
    assert len(identity.config_hash) == 64
    # identifiers are passed through unchanged
    assert identity.image_digest == "sha256:" + "0" * 64
    assert identity.executor_version == "factor-executor/v1"


def test_resolved_keeps_explicit_values() -> None:
    identity = ExecutionIdentity.resolved(
        code_sha="a" * 40,
        image_digest="sha256:" + "b" * 64,
        dependency_lock_hash="c" * 64,
        executor_version="custom/v2",
        config_hash="d" * 64,
    )

    assert identity.code_sha == "a" * 40
    assert identity.dependency_lock_hash == "c" * 64
    assert identity.config_hash == "d" * 64


def test_execution_code_sha_is_stable() -> None:
    assert len(_execution_code_sha()) == 64
    assert _execution_code_sha() == _execution_code_sha()
