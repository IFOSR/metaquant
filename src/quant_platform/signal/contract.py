"""信号契约：Signal / SignalSpec / load_signal_spec。

信号代码是一个受限 Python 文件，只含两个顶层名：``INDICATORS``（声明式指标
清单）与 ``compute_signal(ctx) -> Signal``（纯函数）。它在注入式命名空间里
exec：不暴露 import、危险内置与 dunder 逃逸，只注入 ``math`` / ``Signal``。
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Signal:
    target_qty: int = 0
    stop_price: float | None = None
    take_profit: float | None = None


@dataclass
class SignalSpec:
    indicators: list[dict]
    compute_signal: Callable[[Any], Signal]


_FORBIDDEN_NAMES = frozenset(
    {
        "open",
        "__import__",
        "eval",
        "exec",
        "compile",
        "input",
        "globals",
        "locals",
        "vars",
        "breakpoint",
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "importlib",
    }
)

_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "str": str,
    "True": True,
    "False": False,
    "None": None,
}


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _validate_ast(code: str) -> None:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("signal code must not import modules")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise ValueError(f"forbidden name: {node.id}")
        if isinstance(node, ast.Attribute) and _is_dunder(node.attr):
            raise ValueError(f"forbidden dunder access: {node.attr}")


def load_signal_spec(code: str) -> SignalSpec:
    """编译并校验信号代码，返回 SignalSpec（INDICATORS + compute_signal）。"""
    _validate_ast(code)
    namespace: dict[str, Any] = {
        "math": math,
        "Signal": Signal,
        "__builtins__": _SAFE_BUILTINS,
    }
    exec(compile(code, "<signal>", "exec"), namespace)  # noqa: S102
    indicators = namespace.get("INDICATORS")
    compute = namespace.get("compute_signal")
    if not isinstance(indicators, list):
        raise ValueError("signal code must define INDICATORS as a list")
    if not callable(compute):
        raise ValueError("signal code must define compute_signal(ctx)")
    return SignalSpec(indicators=indicators, compute_signal=compute)
