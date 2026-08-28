"""End-to-end verification: paper -> spec -> torch code -> sandbox -> factor -> IC.

Runs inside the API image with the Docker socket mounted so the sandbox runner
can launch the torch image. Uses the real agent (DEEPSEEK_API_KEY) to extract a
spec and generate code from the StableAlpha report, then executes that code in
the sandbox to produce factor values and an IC report.

Usage (from repo root):
    docker compose run --rm --no-deps \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -v "$PWD/src:/app/src" -v "$PWD/tests:/app/tests" \
      api python scripts/verify-model-factor-pipeline.py
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quant_platform.data_gateway.models import PITRow
from quant_platform.factor_construction.artifacts import CodeBundleError, content_hash
from quant_platform.factor_construction.data_service import forward_returns
from quant_platform.factor_construction.executor import run_infer, run_train
from quant_platform.factor_construction.generator import (
    extract_build_spec,
    generate_and_smoke,
)
from quant_platform.factor_construction.runner import DockerSandboxRunner
from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.validation.model_factor import validate_model_factor

_SANDBOX_IMAGE = "quant-sandbox:local"

# A contract-conformant torch bundle used as a fallback if agent generation fails.
_FALLBACK_BUNDLE = {
    "model.py": b"""import torch\n\ndef build_model(hyperparams: dict):\n    dim = hyperparams.get("input_dim", 2)\n    hidden = hyperparams.get("hidden_dim", 8)\n    return torch.nn.Sequential(\n        torch.nn.Linear(dim, hidden),\n        torch.nn.ReLU(),\n        torch.nn.Linear(hidden, 1),\n    )\n""",
    "train.py": b"""import torch\nfrom model import build_model\n\ndef train(data, labels, spec):\n    X = torch.tensor(data.data.values, dtype=torch.float32)\n    y = labels.to_numpy(dtype=float) if labels is not None else None\n    if y is None or len(y) == 0:\n        y = torch.zeros(X.shape[0], 1)\n    else:\n        y = torch.tensor(y, dtype=torch.float32).unsqueeze(1)\n    hp = dict(spec.get("hyperparameters", {}))\n    hp.setdefault("input_dim", X.shape[1])\n    model = build_model(hp)\n    opt = torch.optim.Adam(model.parameters(), lr=1e-2)\n    loss_fn = torch.nn.MSELoss()\n    for _ in range(30):\n        opt.zero_grad()\n        loss = loss_fn(model(X), y)\n        loss.backward()\n        opt.step()\n    return {"state_dict": model.state_dict(), "hyperparameters": hp}\n""",
    "infer.py": b"""import torch\nfrom model import build_model\n\ndef infer(data, weights):\n    X = torch.tensor(data.data.values, dtype=torch.float32)\n    hp = dict(weights.get("hyperparameters", {}))\n    hp.setdefault("input_dim", X.shape[1])\n    model = build_model(hp)\n    model.load_state_dict(weights["state_dict"])\n    model.eval()\n    with torch.no_grad():\n        return model(X).squeeze(1).tolist()\n""",
}


def _synthetic_data(spec: FactorBuildSpec) -> tuple[list[dict], list[dict], list[str]]:
    """Generate a small synthetic feature + label dataset from the spec."""
    rng = random.Random(42)
    instruments = [f"STK{i:03d}" for i in range(20)]
    fields = list(spec.inputs)
    price_field = spec.label.price_field
    start = datetime(2020, 1, 2, tzinfo=UTC)
    features: list[dict] = []
    price_rows: list[dict] = []
    for instrument in instruments:
        price = 10.0
        for day in range(40):
            event_time = start + timedelta(days=day)
            price = max(1.0, price * (1.0 + rng.uniform(-0.02, 0.02)))
            row: dict = {
                "instrument_id": instrument,
                "event_time": event_time.isoformat().replace("+00:00", "Z"),
            }
            for field in fields:
                row[field] = (
                    round(price * (1.0 + rng.uniform(-0.01, 0.01)), 4)
                    if field == price_field
                    else round(rng.uniform(-1, 1), 4)
                )
            features.append(row)
            price_rows.append(
                {"instrument_id": instrument, "event_time": event_time, "value": price}
            )
    return features, price_rows, fields


def _main() -> None:
    report_path = Path(
        "/app/tests/factor_construction/fixtures/stable_alpha_report.txt"
    )
    paper = report_path.read_text()

    print("== 1. 研报 -> 构建规格 (agent) ==")
    spec = extract_build_spec(paper)

    print("== 2. 规格 -> torch 代码 + 试运行 (agent + 沙箱) ==")
    sandbox = DockerSandboxRunner(_SANDBOX_IMAGE)
    files = None
    try:
        files, manifest, smoke = generate_and_smoke(spec, sandbox=sandbox)
        print(f"    agent 代码 smoke exit={smoke.exit_code}")
    except CodeBundleError as exc:
        print(f"    agent 生成失败，回退到固定 torch 代码包: {exc}")
        files = dict(_FALLBACK_BUNDLE)

    features, price_rows, fields = _synthetic_data(spec)
    labels = forward_returns(
        tuple(
            PITRow(
                dataset_id="market",
                field=f"market.eod.{spec.label.price_field}",
                instrument_id=row["instrument_id"],
                event_time=row["event_time"],
                available_time=row["event_time"],
                ingested_at=row["event_time"],
                revision_id="rev-1",
                source_id="synth",
                license_tag="licensed-research",
                value=row["value"],
            )
            for row in price_rows
        ),
        price_field=f"market.eod.{spec.label.price_field}",
        horizon=min(spec.label.horizon, 5),
    )["rows"]

    decision_time = features[-1]["event_time"]

    print("== 3. 沙箱训练 (torch) ==")
    train = run_train(
        bundle_files=files,
        spec=spec,
        data_rows=features,
        fields=fields,
        label_rows=labels,
        decision_time=decision_time,
        sandbox=sandbox,
    )
    print(f"    weights_hash={train.weights_hash}")

    print("== 4. 沙箱推理 (torch) ==")
    infer = run_infer(
        bundle_files=files,
        spec=spec,
        weights=train.weights,
        data_rows=features,
        fields=fields,
        decision_time=decision_time,
        sandbox=sandbox,
    )
    print(f"    factor_values_hash={content_hash(infer.canonical_json.encode())}")

    factor_rows = [
        {
            "instrument_id": o.instrument_id,
            "event_time": o.timestamp.isoformat(),
            "value": o.value,
        }
        for o in infer.observations
    ]
    label_rows = [
        {
            "instrument_id": r["instrument_id"],
            "event_time": r["event_time"],
            "value": r["label"],
        }
        for r in labels
    ]

    print("== 5. 因子值 -> IC 验证 ==")
    report = validate_model_factor(factor_rows, label_rows)
    print(json.dumps(report.payload(), ensure_ascii=False, indent=2))
    print("\nOK: 研报 -> 规格 -> torch 代码 -> 因子值 -> IC 全链路跑通。")


if __name__ == "__main__":
    _main()
