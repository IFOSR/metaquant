from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from yaml.constructor import ConstructorError  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = ROOT / "docs/ui/control-plane-mock/openapi.yaml"
EVENT_FIXTURE_PATH = (
    ROOT / "docs/ui/control-plane-mock/examples/research-job-events.json"
)


class UniqueKeyLoader(yaml.SafeLoader):  # type: ignore[misc]
    """Reject duplicate YAML keys instead of silently keeping the last value."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: Any, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_spec() -> dict[str, Any]:
    parsed = yaml.load(OPENAPI_PATH.read_text(), Loader=UniqueKeyLoader)
    assert isinstance(parsed, dict)
    return parsed


def _operation_by_id(spec: dict[str, Any], operation_id: str) -> dict[str, Any]:
    for path_item in spec["paths"].values():
        for operation in path_item.values():
            if (
                isinstance(operation, dict)
                and operation.get("operationId") == operation_id
            ):
                return operation
    raise AssertionError(f"operationId not found: {operation_id}")


def _parameter_refs(operation: dict[str, Any]) -> set[str]:
    return {
        parameter["$ref"]
        for parameter in operation.get("parameters", [])
        if "$ref" in parameter
    }


def test_openapi_has_unique_keys_and_global_authentication() -> None:
    spec = _load_spec()
    schemes = spec["components"]["securitySchemes"]

    assert {"oidc": []} in spec["security"]
    assert {"bearerAuth": []} in spec["security"]
    assert schemes["oidc"]["type"] == "openIdConnect"
    assert schemes["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }


def test_actor_is_derived_from_authenticated_session() -> None:
    schemas = _load_spec()["components"]["schemas"]
    metadata = schemas["CommandMetadata"]

    assert "actor" not in metadata["required"]
    assert "actor" not in metadata["properties"]
    assert metadata["additionalProperties"] is False


def test_mutating_operations_define_idempotency_and_concurrency() -> None:
    spec = _load_spec()
    write_operations = {
        operation["operationId"]: operation
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method in {"post", "put", "patch", "delete"}
    }

    for operation_id, operation in write_operations.items():
        assert "#/components/parameters/IdempotencyKey" in _parameter_refs(operation), (
            operation_id
        )

    concurrent_operations = set(write_operations) - {"createResearchJob"}
    for operation_id in concurrent_operations:
        assert "#/components/parameters/IfMatch" in _parameter_refs(
            write_operations[operation_id]
        ), operation_id


def test_object_authorization_does_not_disclose_existence() -> None:
    spec = _load_spec()
    for path, path_item in spec["paths"].items():
        if "{" not in path:
            continue
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert "403" not in operation.get("responses", {}), (
                path,
                method,
            )


def test_g0_market_scope_frequencies_and_futures_constraints_are_required() -> None:
    schemas = _load_spec()["components"]["schemas"]
    create_schema = schemas["CreateResearchJobCommand"]
    futures_rule = create_schema["allOf"][0]

    assert schemas["FrequencyId"]["enum"] == ["1d", "1m", "5m", "15m", "30m", "60m"]
    assert set(futures_rule["then"]["required"]) >= {
        "settlement_clock",
        "exchange_scope",
        "contract_selection",
        "roll_policy",
    }
    assert futures_rule["if"]["properties"]["market"]["const"] == (
        "CN_COMMODITY_FUTURES"
    )


def test_research_brief_has_draft_version_and_freeze_contract() -> None:
    spec = _load_spec()
    schemas = spec["components"]["schemas"]
    version_fields = schemas["ResearchBriefVersion"]["allOf"][1]

    assert set(version_fields["required"]) >= {
        "id",
        "job_id",
        "version",
        "status",
        "content_hash",
    }
    assert schemas["ResearchBriefVersionState"]["enum"] == [
        "DRAFT",
        "FROZEN",
        "SUPERSEDED",
    ]
    for operation_id in {
        "listResearchBriefVersions",
        "createResearchBriefVersion",
        "getResearchBriefVersion",
        "updateResearchBriefVersion",
        "freezeResearchBriefVersion",
    }:
        _operation_by_id(spec, operation_id)


def test_workflows_use_distinct_state_machines() -> None:
    schemas = _load_spec()["components"]["schemas"]

    for state_schema in {
        "ResearchJobState",
        "ExperimentSpecState",
        "ExperimentRunState",
        "AttemptState",
        "ReplicationState",
        "PackageReleaseState",
        "DeploymentRunState",
    }:
        assert state_schema in schemas

    assert schemas["ResearchJob"]["properties"]["state"]["$ref"].endswith(
        "/ResearchJobState"
    )
    assert schemas["Attempt"]["properties"]["state"]["$ref"].endswith("/AttemptState")
    assert schemas["Experiment"]["properties"]["spec_state"]["$ref"].endswith(
        "/ExperimentSpecState"
    )


def test_candidates_include_executable_research_constraints() -> None:
    candidate = _load_spec()["components"]["schemas"]["Candidate"]

    assert set(candidate["required"]) >= {
        "expected_direction",
        "lookback",
        "failure_conditions",
    }


def test_reports_and_lineage_carry_complete_provenance() -> None:
    schemas = _load_spec()["components"]["schemas"]
    report = schemas["ResearchReport"]
    evidence = schemas["EvidenceRef"]
    lineage_node = schemas["LineageNode"]

    assert set(report["required"]) >= {
        "experiment_spec_id",
        "experiment_run_id",
        "code_sha",
        "image_digest",
        "run_fingerprint",
        "policy_version_ids",
        "approval_ids",
        "evidence_catalog",
    }
    assert set(evidence["properties"]) >= {
        "artifact_id",
        "content_hash",
        "page",
        "bbox",
        "row_selector",
    }
    assert set(lineage_node["required"]) >= {
        "content_hash",
        "schema_version",
        "produced_by_run_id",
    }


def test_strategy_package_payload_is_immutable_and_approval_is_attestation() -> None:
    schemas = _load_spec()["components"]["schemas"]
    payload = schemas["StrategyPackagePayload"]
    attestation = schemas["PackageAttestation"]

    assert payload["additionalProperties"] is False
    assert "status" not in payload["properties"]
    assert "approved" not in payload["properties"]
    assert set(attestation["required"]) >= {
        "package_content_hash",
        "environment",
        "decision",
        "approved_by",
    }


def test_reconnect_fixture_requires_authoritative_snapshot_refetch() -> None:
    fixture = json.loads(EVENT_FIXTURE_PATH.read_text())

    assert fixture["must_refetch_snapshot"] is True
