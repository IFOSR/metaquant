"""Sandbox execution of generated ``train.py`` / ``infer.py``.

The executor writes the bundle, a trusted driver script, and the feature/label
payloads into an isolated directory, then runs the driver via a
``SandboxRunner``.  The driver does *all* IO (loading ``PITFrame``/labels and
serializing weights), so the generated code is pure computation::

    train.py:  def train(data, labels, spec) -> weights
    infer.py:  def infer(data, weights) -> list[float]   (aligned to data index)

Weights are content-addressed bytes (the sandbox image uses ``torch.save``; the
local driver pickles the returned object). Factor values are canonicalized to
``factor-observations/v1`` via the shared ``canonical_observations`` helper.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from quant_platform.factor_construction.artifacts import content_hash
from quant_platform.factor_construction.runner import (
    SandboxResult,
    SandboxRunner,
    SubprocessSandboxRunner,
)
from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.factor_executor.model import (
    FactorObservation,
    canonical_observations,
)


class FactorBuildExecutionError(RuntimeError):
    """Raised when a sandbox run fails or produces no output."""


_TRAIN_DRIVER = """\
import json, os, pickle, sys
from pathlib import Path
sys.path.insert(0, os.getcwd())
import quant_platform.ml as ml
import train as train_mod

spec = json.loads(Path(sys.argv[1]).read_text())
payload = json.loads(Path(sys.argv[2]).read_text())
label_payload = json.loads(Path(sys.argv[3]).read_text())

data = ml.PITFrame(
    data=ml._rows_to_frame(payload["rows"], payload["fields"]),
    decision_time=payload["decision_time"],
)
labels = (
    ml._label_rows_to_series(label_payload["rows"])
    if label_payload["rows"]
    else None
)

weights = train_mod.train(data, labels, spec)
Path(sys.argv[4]).write_bytes(pickle.dumps(weights))
"""

_INFER_DRIVER = """\
import json, os, pickle, sys
from pathlib import Path
sys.path.insert(0, os.getcwd())
import quant_platform.ml as ml
import infer as infer_mod

weights = pickle.loads(Path(sys.argv[1]).read_bytes())
payload = json.loads(Path(sys.argv[2]).read_text())

data = ml.PITFrame(
    data=ml._rows_to_frame(payload["rows"], payload["fields"]),
    decision_time=payload["decision_time"],
)
values = infer_mod.infer(data, weights)

rows = []
for (instrument_id, event_time), value in zip(data.data.index, values):
    if value is None:
        continue
    rows.append({
        "instrument_id": str(instrument_id),
        "event_time": str(event_time),
        "value": value,
    })
Path(sys.argv[3]).write_text(json.dumps({"rows": rows}))
"""


@dataclass(frozen=True, slots=True)
class TrainOutcome:
    weights: bytes
    weights_hash: str


@dataclass(frozen=True, slots=True)
class InferOutcome:
    observations: tuple[FactorObservation, ...]
    canonical_json: str
    output_hash: str


def _write_bundle(directory: Path, files: dict[str, bytes]) -> None:
    for name, payload in files.items():
        (directory / name).write_bytes(payload)


def _data_payload(
    rows: list[dict[str, Any]], fields: list[str], decision_time: str
) -> dict[str, Any]:
    return {"rows": rows, "fields": fields, "decision_time": decision_time}


def _require_success(result: SandboxResult) -> None:
    if result.timed_out:
        raise FactorBuildExecutionError("sandbox run timed out")
    if result.exit_code != 0:
        raise FactorBuildExecutionError(
            f"sandbox run failed (exit {result.exit_code}): {result.stderr.strip()}"
        )


def run_train(
    *,
    bundle_files: dict[str, bytes],
    spec: FactorBuildSpec,
    data_rows: list[dict[str, Any]],
    fields: list[str],
    label_rows: list[dict[str, Any]],
    decision_time: str,
    sandbox: SandboxRunner | None = None,
) -> TrainOutcome:
    """Run the bundle's ``train`` and return content-addressed weights."""
    active = sandbox or SubprocessSandboxRunner()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _write_bundle(directory, bundle_files)
        (directory / "train_driver.py").write_text(_TRAIN_DRIVER)
        (directory / "spec.json").write_text(
            json.dumps(spec.model_dump(mode="json"), ensure_ascii=False)
        )
        (directory / "data.json").write_text(
            json.dumps(_data_payload(data_rows, fields, decision_time))
        )
        (directory / "labels.json").write_text(json.dumps({"rows": label_rows}))
        result = active.run(
            cwd=directory,
            command=[
                "python",
                "train_driver.py",
                "spec.json",
                "data.json",
                "labels.json",
                "weights.pkl",
            ],
            timeout_seconds=300,
        )
        _require_success(result)
        weights = (directory / "weights.pkl").read_bytes()
    return TrainOutcome(weights=weights, weights_hash=content_hash(weights))


def run_infer(
    *,
    bundle_files: dict[str, bytes],
    spec: FactorBuildSpec,
    weights: bytes,
    data_rows: list[dict[str, Any]],
    fields: list[str],
    decision_time: str,
    sandbox: SandboxRunner | None = None,
) -> InferOutcome:
    """Run the bundle's ``infer`` and return canonical factor observations."""
    del spec
    active = sandbox or SubprocessSandboxRunner()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _write_bundle(directory, bundle_files)
        (directory / "infer_driver.py").write_text(_INFER_DRIVER)
        (directory / "weights.pkl").write_bytes(weights)
        (directory / "data.json").write_text(
            json.dumps(_data_payload(data_rows, fields, decision_time))
        )
        result = active.run(
            cwd=directory,
            command=[
                "python",
                "infer_driver.py",
                "weights.pkl",
                "data.json",
                "out.json",
            ],
            timeout_seconds=300,
        )
        _require_success(result)
        payload = json.loads((directory / "out.json").read_text())
    observations = tuple(
        FactorObservation(
            timestamp=datetime.fromisoformat(row["event_time"].replace("Z", "+00:00")),
            instrument_id=row["instrument_id"],
            value=row["value"],
        )
        for row in payload["rows"]
    )
    canonical, output_hash = canonical_observations(observations, "factor")
    return InferOutcome(
        observations=observations, canonical_json=canonical, output_hash=output_hash
    )
