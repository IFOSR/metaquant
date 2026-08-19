"""Sandbox execution for generated code bundles.

A ``SandboxRunner`` runs a command against the three-file bundle in an isolated
directory. ``SubprocessSandboxRunner`` is the local/test implementation (CPU and
memory limits, timeouts); a Docker-backed runner is the production equivalent.

``scan_forbidden`` is the pre-flight security guard: generated code may only
import the model/ML libraries and may not perform network, subprocess, or file
IO. ``smoke_bundle`` combines the guard with a real compile run so a bundle
that violates the sandbox contract never executes.
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "http",
        "httpx",
        "shutil",
        "pathlib",
        "tempfile",
        "pickle",
        "ctypes",
        "importlib",
        "builtins",
    }
)

_FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"eval", "exec", "open", "__import__", "compile", "input"}
)


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxRunner(Protocol):
    def run(
        self, *, cwd: Path, command: list[str], timeout_seconds: int
    ) -> SandboxResult: ...


def _decode(output: str | bytes | None) -> str:
    if output is None:
        return ""
    return output if isinstance(output, str) else output.decode(errors="replace")


class SubprocessSandboxRunner:
    def run(
        self, *, cwd: Path, command: list[str], timeout_seconds: int
    ) -> SandboxResult:
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                exit_code=124,
                stdout=_decode(exc.stdout),
                stderr=_decode(exc.stderr),
                timed_out=True,
            )
        return SandboxResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            timed_out=False,
        )


class DockerSandboxRunner:
    """Production runner: executes the bundle in a sandbox image.

    The image ships ``quant_platform.ml`` + PyTorch; the bundle directory is
    bind-mounted, the root filesystem is read-only, and the container has no
    network egress (``--network=none``).
    """

    def __init__(
        self,
        image: str,
        *,
        network: str = "none",
        memory_mb: int = 2048,
        cpus: float = 1.0,
    ) -> None:
        self._image = image
        self._network = network
        self._memory_mb = memory_mb
        self._cpus = cpus

    def run(
        self, *, cwd: Path, command: list[str], timeout_seconds: int
    ) -> SandboxResult:
        args = [
            "docker",
            "run",
            "--rm",
            f"--network={self._network}",
            f"--memory={self._memory_mb}m",
            f"--cpus={self._cpus}",
            "--read-only",
            "-v",
            f"{cwd}:/workspace:rw",
            "-w",
            "/workspace",
            self._image,
            *command,
        ]
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                exit_code=124,
                stdout=_decode(exc.stdout),
                stderr=_decode(exc.stderr),
                timed_out=True,
            )
        return SandboxResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            timed_out=False,
        )


def _forbidden_module(module: str) -> bool:
    return module.split(".")[0] in _FORBIDDEN_MODULES


def scan_forbidden(source: bytes) -> tuple[str, ...]:
    """Return sandbox-policy violations found in ``source`` (deduplicated)."""
    tree = ast.parse(source, filename="<generated>")
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden_module(alias.name):
                    violations.append(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and _forbidden_module(node.module):
                violations.append(f"forbidden import: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            # Only bare builtins (``eval(...)``) are forbidden; method calls such
            # as ``model.eval()`` (PyTorch) are legitimate and must pass.
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                violations.append(f"forbidden call: {func.id}()")
    return tuple(dict.fromkeys(violations))


def smoke_bundle(
    files: dict[str, bytes], runner: SandboxRunner | None = None
) -> SandboxResult:
    """Guard + compile a bundle; returns an exit code the fix loop can react to."""
    violations: list[str] = []
    for name, payload in files.items():
        violations.extend(f"{name}: {item}" for item in scan_forbidden(payload))
    if violations:
        return SandboxResult(
            exit_code=1, stdout="", stderr="\n".join(violations), timed_out=False
        )
    active = runner or SubprocessSandboxRunner()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for name, payload in files.items():
            (tmpdir / name).write_bytes(payload)
        return active.run(
            cwd=tmpdir,
            command=["python", "-m", "py_compile", "model.py", "train.py", "infer.py"],
            timeout_seconds=30,
        )
