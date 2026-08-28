"""Static security scan for LLM-generated strategy code (G19 review P0-1).

Generated strategies run inside the API process, so the source must be
constrained before it is compiled. The policy is an import **allowlist**
(``nautilus_trader`` plus a small set of harmless stdlib modules), a
forbidden-call blacklist, and a dunder-access ban that closes the usual
``obj.__class__`` / ``__builtins__`` escape hatches.

Residual risk (obfuscated access such as ``getattr(x, "__class__")`` with a
computed string) is documented and accepted for the local MVP; the Docker
sandbox path (``SANDBOX_USE_DOCKER``) is the hard boundary for shared
deployments.
"""

from __future__ import annotations

import ast

ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        "nautilus_trader",
        "math",
        "decimal",
        "datetime",
        "typing",
        "dataclasses",
        "enum",
        "collections",
        "functools",
        "itertools",
        "statistics",
    }
)

FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "open",
        "__import__",
        "compile",
        "input",
        "globals",
        "locals",
        "vars",
        "breakpoint",
    }
)

# super().__init__() is the mandated NT skeleton line and grants no escape
# capability; every other dunder attribute stays banned.
_ALLOWED_DUNDER_ATTRS: frozenset[str] = frozenset({"__init__"})


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _top_level(module: str) -> str:
    return module.split(".")[0]


def scan_strategy_source(source: str) -> tuple[str, ...]:
    """Return deduplicated policy violations found in generated strategy code."""
    try:
        tree = ast.parse(source, filename="<strategy>")
    except SyntaxError as exc:
        return (f"syntax error: {exc}",)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _top_level(alias.name) not in ALLOWED_MODULES:
                    violations.append(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            top = _top_level(node.module or "")
            if top and top not in ALLOWED_MODULES:
                violations.append(f"forbidden import: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            # Bare builtins only; method calls such as indicator.update(...) pass.
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                violations.append(f"forbidden call: {func.id}()")
        elif isinstance(node, ast.Attribute):
            if _is_dunder(node.attr) and node.attr not in _ALLOWED_DUNDER_ATTRS:
                violations.append(f"forbidden attribute access: .{node.attr}")
        elif isinstance(node, ast.Name) and _is_dunder(node.id):
            violations.append(f"forbidden name reference: {node.id}")
    return tuple(dict.fromkeys(violations))
