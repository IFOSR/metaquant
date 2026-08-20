"""Runs INSIDE the sandbox image to prove the torch computational core.

Contract: this mirrors exactly what the platform executor's train_driver.py /
infer_driver.py do — write the three-file bundle, build a PITFrame + labels via
``quant_platform.ml``, call ``train(data, labels, spec)`` then
``infer(data, weights)``, and compute the cross-sectional IC.

Run (host):
    docker run --rm -v "$PWD/scripts/sandbox-torch-smoke.py:/smoke.py:ro" \
      quant-sandbox:local python /smoke.py
"""

from __future__ import annotations

import os
import random
import sys

import numpy as np

import quant_platform.ml as ml

MODEL = '''import torch\n\ndef build_model(hyperparams: dict):\n    dim = hyperparams.get("input_dim", 2)\n    hidden = hyperparams.get("hidden_dim", 8)\n    return torch.nn.Sequential(\n        torch.nn.Linear(dim, hidden),\n        torch.nn.ReLU(),\n        torch.nn.Linear(hidden, 1),\n    )\n'''

TRAIN = '''import torch\nfrom model import build_model\n\ndef train(data, labels, spec):\n    X = torch.tensor(data.data.values, dtype=torch.float32)\n    y = labels.to_numpy(dtype=float)\n    y = torch.tensor(y, dtype=torch.float32).unsqueeze(1)\n    hp = dict(spec.get("hyperparameters", {}))\n    hp.setdefault("input_dim", X.shape[1])\n    model = build_model(hp)\n    opt = torch.optim.Adam(model.parameters(), lr=1e-2)\n    loss_fn = torch.nn.MSELoss()\n    for _ in range(50):\n        opt.zero_grad()\n        loss = loss_fn(model(X), y)\n        loss.backward()\n        opt.step()\n    return {"state_dict": model.state_dict(), "hyperparameters": hp}\n'''

INFER = '''import torch\nfrom model import build_model\n\ndef infer(data, weights):\n    X = torch.tensor(data.data.values, dtype=torch.float32)\n    hp = dict(weights.get("hyperparameters", {}))\n    hp.setdefault("input_dim", X.shape[1])\n    model = build_model(hp)\n    model.load_state_dict(weights["state_dict"])\n    model.eval()\n    with torch.no_grad():\n        return model(X).squeeze(1).tolist()\n'''

SPEC = {
    "factor_id": "cn_a.stable_alpha_dl",
    "factor_name": "StableAlpha",
    "label": {"price_field": "vwap", "horizon": 5},
    "hyperparameters": {"input_dim": 2, "hidden_dim": 16},
}


def _pearson(xs, ys):
    if len(xs) < 2:
        return None
    return float(np.corrcoef(xs, ys)[0, 1])


def _spearman(xs, ys):
    if len(xs) < 2:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        for position, index in enumerate(order):
            result[index] = float(position)
        return result

    return float(np.corrcoef(ranks(xs), ranks(ys))[0, 1])


def main() -> None:
    # 1. Write the bundle into the workspace.
    for name, source in (("model.py", MODEL), ("train.py", TRAIN), ("infer.py", INFER)):
        with open(name, "w") as handle:
            handle.write(source)
    sys.path.insert(0, os.getcwd())
    import infer as infer_mod  # noqa: PLC0415
    import train as train_mod  # noqa: PLC0415

    # 2. Synthetic PIT frame + labels.
    rng = random.Random(7)
    rows = []
    labels = []
    for instrument in range(30):
        price = 10.0 + rng.random() * 5
        for day in range(30):
            price = max(1.0, price * (1.0 + rng.uniform(-0.03, 0.03)))
            event_time = f"2020-01-{(day + 1):02d}T07:00:00Z"
            rows.append(
                {
                    "instrument_id": f"STK{instrument:03d}",
                    "event_time": event_time,
                    "vwap": round(price, 4),
                    "amount": round(rng.uniform(0, 1), 4),
                }
            )
    # forward return label over horizon 5
    for instrument in range(30):
        prices = [r["vwap"] for r in rows if r["instrument_id"] == f"STK{instrument:03d}"]
        for day in range(len(prices) - 5):
            labels.append(
                {
                    "instrument_id": f"STK{instrument:03d}",
                    "event_time": f"2020-01-{(day + 1):02d}T07:00:00Z",
                    "label": prices[day + 5] / prices[day] - 1,
                }
            )

    fields = ["vwap", "amount"]
    label_series = ml._label_rows_to_series(labels)
    # Align features to labels: train only on rows that have a realized label.
    frame = ml._rows_to_frame(rows, fields)
    aligned = frame.loc[frame.index.isin(label_series.index)]
    aligned_labels = label_series.reindex(aligned.index)
    data = ml.PITFrame(data=aligned, decision_time="2020-02-01T07:00:00Z")

    # 3. Train + infer (torch).
    weights = train_mod.train(data, aligned_labels, SPEC)
    values = infer_mod.infer(data, weights)

    # 4. Align factor values with labels and compute IC.
    by_key = {
        (i, e): v for (i, e), v in zip(data.data.index, values)
    }
    label_by_key = {
        (i, e): float(v) for (i, e), v in zip(aligned_labels.index, aligned_labels.to_numpy())
    }
    common = [(by_key[k], label_by_key[k]) for k in by_key if k in label_by_key]
    xs = [p[0] for p in common]
    ys = [p[1] for p in common]

    print(f"torch: {__import__('torch').__version__}")
    print(f"features: {len(aligned)} rows x {len(fields)} fields")
    print(f"weights: {len(weights)} tensors (state_dict)")
    print(f"factor values: {len(values)}")
    print(f"aligned observations: {len(common)}")
    print(f"pearson IC: {_pearson(xs, ys):.4f}")
    print(f"spearman IC: {_spearman(xs, ys):.4f}")
    print("OK: torch code -> train -> weights -> infer -> factor values -> IC")


if __name__ == "__main__":
    main()
