from collections.abc import Callable

from fastapi.testclient import TestClient

from quant_platform.api.app import create_app


def make_client(probe: Callable[[], dict[str, bool]]) -> TestClient:
    return TestClient(create_app(readiness_probe=probe))


def test_liveness_reports_running_service() -> None:
    client = make_client(lambda: {"postgres": False, "minio": False})

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "service": "quant-platform-api",
        "status": "ok",
    }


def test_readiness_reports_all_dependencies() -> None:
    client = make_client(lambda: {"postgres": True, "minio": True})

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "checks": {"minio": "ok", "postgres": "ok"},
        "status": "ok",
    }


def test_readiness_returns_503_when_a_dependency_is_unavailable() -> None:
    client = make_client(lambda: {"postgres": True, "minio": False})

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "checks": {"minio": "failed", "postgres": "ok"},
        "status": "degraded",
    }
