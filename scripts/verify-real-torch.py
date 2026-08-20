"""Real-data torch end-to-end verification (runs inside the API image).

Loads the actual PIT rows from PostgreSQL (18 instruments), builds a
self-describing torch bundle, trains + infers it with the subprocess sandbox
(torch is in the API image), and reports the cross-sectional IC.

Run:
    docker compose run --rm --no-deps api python scripts/verify-real-torch.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from quant_platform.config import get_settings
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.factor_construction.data_service import PitDataService
from quant_platform.factor_construction.executor import run_infer, run_train
from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.research.models import PitObservationModel
from quant_platform.validation.model_factor import validate_model_factor

_BUNDLE = {
    "model.py": b"""import torch\n\ndef build_model(hyperparams: dict):\n    dim = hyperparams.get("input_dim", 5)\n    hidden = hyperparams.get("hidden_dim", 32)\n    return torch.nn.Sequential(\n        torch.nn.Linear(dim, hidden),\n        torch.nn.ReLU(),\n        torch.nn.Linear(hidden, hidden),\n        torch.nn.ReLU(),\n        torch.nn.Linear(hidden, 1),\n    )\n""",
    "train.py": b"""import torch\nfrom model import build_model\n\ndef train(data, labels, spec):\n    X = torch.tensor(data.data.values, dtype=torch.float32)\n    y = torch.tensor(labels.to_numpy(dtype=float), dtype=torch.float32).unsqueeze(1)\n    hp = dict(spec.get("hyperparameters", {}))\n    hp.setdefault("input_dim", X.shape[1])\n    model = build_model(hp)\n    opt = torch.optim.Adam(model.parameters(), lr=1e-2, weight_decay=1e-4)\n    loss_fn = torch.nn.MSELoss()\n    for _ in range(200):\n        opt.zero_grad()\n        loss = loss_fn(model(X), y)\n        loss.backward()\n        opt.step()\n    return {"state_dict": model.state_dict(), "hyperparameters": hp}\n""",
    "infer.py": b"""import torch\nfrom model import build_model\n\ndef infer(data, weights):\n    X = torch.tensor(data.data.values, dtype=torch.float32)\n    hp = dict(weights.get("hyperparameters", {}))\n    hp.setdefault("input_dim", X.shape[1])\n    model = build_model(hp)\n    model.load_state_dict(weights["state_dict"])\n    model.eval()\n    with torch.no_grad():\n        return model(X).squeeze(1).tolist()\n""",
}


def _main() -> None:
    settings = get_settings()
    engine = create_engine(str(settings.database_url), pool_pre_ping=True)
    sessions = sessionmaker(engine)
    with sessions() as session:
        instruments = list(
            session.scalars(
                select(PitObservationModel.instrument_id)
                .where(PitObservationModel.field.startswith("market.eod."))
                .distinct()
            ).all()
        )
        max_event = session.scalar(
            select(PitObservationModel.event_time)
            .order_by(PitObservationModel.event_time.desc())
            .limit(1)
        )
    assert max_event is not None

    store = SqlAlchemyPitStore(sessions)
    service = PitDataService(store)

    fields = ["open", "high", "low", "close", "volume"]
    spec = FactorBuildSpec.model_validate(
        {
            "factor_id": "cn_a.real_torch_demo",
            "factor_name": "RealTorchDemo",
            "market": "CN_A",
            "universe_ref": "universe://real-18/v1",
            "inputs": fields,
            "label": {"name": "future_5d_close_return", "price_field": "close", "horizon": 5},
            "architecture": "MLP",
            "sample_weighting": "INVERSE_SIZE",
        }
    )
    decision_time = max_event.astimezone(UTC) + timedelta(days=1)
    decision_time_text = decision_time.isoformat().replace("+00:00", "Z")

    frame = service.pit_frame(
        instrument_ids=tuple(instruments),
        fields=tuple(fields),
        decision_time=decision_time,
    )
    labels = service.label_frame(
        instrument_ids=tuple(instruments),
        price_field="close",
        horizon=5,
        decision_time=decision_time,
    )

    print(f"instruments: {len(instruments)} | features: {len(frame['rows'])} | labels: {len(labels['rows'])}")

    train = run_train(
        bundle_files=_BUNDLE,
        spec=spec,
        data_rows=frame["rows"],
        fields=fields,
        label_rows=labels["rows"],
        decision_time=decision_time_text,
    )
    print(f"trained weights: {train.weights_hash}")

    infer = run_infer(
        bundle_files=_BUNDLE,
        spec=spec,
        weights=train.weights,
        data_rows=frame["rows"],
        fields=fields,
        decision_time=decision_time_text,
    )
    print(f"factor values: {len(infer.observations)} (output_hash {infer.output_hash[:12]}…)")

    factor_rows = [
        {
            "instrument_id": obs.instrument_id,
            "event_time": obs.timestamp.isoformat(),
            "value": obs.value,
        }
        for obs in infer.observations
    ]
    label_rows = [
        {
            "instrument_id": row["instrument_id"],
            "event_time": row["event_time"],
            "value": row["label"],
        }
        for row in labels["rows"]
    ]
    report = validate_model_factor(factor_rows, label_rows)
    print(json.dumps(report.payload(), ensure_ascii=False, indent=2))
    print("\nOK: 真实数据 + torch 训练/推理 + IC 验证全链路跑通")


if __name__ == "__main__":
    _main()
