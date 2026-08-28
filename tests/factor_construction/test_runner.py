"""Tests for the sandbox runner, security guard, and smoke loop."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from quant_platform.factor_construction.generator import generate_and_smoke
from quant_platform.factor_construction.runner import (
    DockerSandboxRunner,
    SandboxResult,
    SubprocessSandboxRunner,
    scan_forbidden,
    smoke_bundle,
)
from quant_platform.factor_construction.spec import FactorBuildSpec

_VALID_FILES = {
    "model.py": b"def build_model(hyperparams: dict):\n    return None\n",
    "train.py": b"def train(data, spec: dict):\n    return None\n",
    "infer.py": b"def infer(data, weights):\n    return None\n",
}


def _spec() -> FactorBuildSpec:
    return FactorBuildSpec.model_validate(
        {
            "factor_id": "cn_a.stable_alpha_dl",
            "factor_name": "StableAlpha",
            "market": "CN_A",
            "universe_ref": "u",
            "inputs": ["vwap"],
            "label": {
                "name": "future_21d_vwap_return",
                "price_field": "vwap",
                "horizon": 21,
            },
            "architecture": "MLP",
        }
    )


class _RecordingRunner:
    def __init__(self, result: SandboxResult) -> None:
        self._result = result
        self.calls: list[tuple[Path, list[str]]] = []

    def run(
        self, *, cwd: Path, command: list[str], timeout_seconds: int
    ) -> SandboxResult:
        self.calls.append((cwd, command))
        return self._result


def test_scan_forbidden_detects_os_import() -> None:
    violations = scan_forbidden(b"import os\nx = 1\n")
    assert any("os" in item for item in violations)


def test_scan_forbidden_detects_open_call() -> None:
    violations = scan_forbidden(b"def f():\n    return open('x')\n")
    assert any("open()" in item for item in violations)


def test_scan_forbidden_allows_torch_and_ml() -> None:
    source = (
        b"import torch\nimport numpy as np\n"
        b"from quant_platform.ml import load_pit_frame\n"
        b"def build_model(h):\n    return torch.nn.Linear(7, 1)\n"
    )
    assert scan_forbidden(source) == ()


def test_scan_forbidden_allows_method_named_eval() -> None:
    # ``model.eval()`` (PyTorch) must not be confused with the builtin ``eval``.
    source = b"def infer(data, weights):\n    model.eval()\n    return None\n"
    assert scan_forbidden(source) == ()


def test_smoke_bundle_rejects_forbidden_before_running() -> None:
    recording = _RecordingRunner(SandboxResult(0, "", ""))
    files = dict(_VALID_FILES)
    files["train.py"] = b"import socket\n\ndef train(data, spec):\n    return None\n"
    result = smoke_bundle(files, recording)
    assert result.exit_code != 0
    assert "socket" in result.stderr
    assert recording.calls == []


def test_smoke_bundle_compiles_valid_files() -> None:
    result = smoke_bundle(_VALID_FILES, SubprocessSandboxRunner())
    assert result.exit_code == 0
    assert not result.timed_out


def test_subprocess_runner_times_out() -> None:
    runner = SubprocessSandboxRunner()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = runner.run(
            cwd=Path(tmp),
            command=["python", "-c", "import time; time.sleep(3)"],
            timeout_seconds=1,
        )
    assert result.timed_out
    assert result.exit_code == 124


def test_docker_runner_builds_sandbox_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args: list[str], **kwargs: Any) -> _Completed:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    docker = DockerSandboxRunner("quant-sandbox:latest", memory_mb=1024, cpus=0.5)
    with tempfile.TemporaryDirectory() as tmp:
        result = docker.run(
            cwd=Path(tmp), command=["python", "train_driver.py"], timeout_seconds=60
        )
    assert result.exit_code == 0
    args = captured["args"]
    assert isinstance(args, list)
    assert args[0] == "docker"
    assert "--network=none" in args
    assert "--read-only" in args
    assert "quant-sandbox:latest" in args


def _code_ok(_prompt: str) -> str:
    return (
        "# file: model.py\n```python\n"
        "def build_model(hyperparams: dict):\n    return None\n```\n"
        "# file: train.py\n```python\n"
        "def train(data, spec: dict):\n    return None\n```\n"
        "# file: infer.py\n```python\n"
        "def infer(data, weights):\n    return None\n```\n"
    )


def test_generate_and_smoke_passes_valid_code() -> None:
    files, manifest, result = generate_and_smoke(
        _spec(), agent_runner=_code_ok, max_rounds=2
    )
    assert set(files) == {"model.py", "train.py", "infer.py"}
    assert manifest["schema_version"] == "code-bundle/v1"
    assert result.exit_code == 0


def test_generate_and_smoke_retries_on_forbidden_code() -> None:
    calls: list[str] = []

    def forbidden_then_ok(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return _code_ok("").replace(
                "def train(data, spec: dict):",
                "import os\ndef train(data, spec: dict):",
            )
        return _code_ok("")

    files, _manifest, result = generate_and_smoke(
        _spec(), agent_runner=forbidden_then_ok, max_rounds=2
    )
    assert b"import os" not in files["train.py"]
    assert result.exit_code == 0
    assert len(calls) == 2
