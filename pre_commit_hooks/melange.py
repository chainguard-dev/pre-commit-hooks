from __future__ import annotations

import re
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Sequence
from typing import Any

import ruamel.yaml

# Helpers for walking melange package configurations.
#
# Shared by the hooks that inspect package YAML before melange compiles it.
# Every accessor tolerates a key that is present with no value (YAML null),
# which melange treats the same as an absent key.

yaml = ruamel.yaml.YAML(typ="safe")


def iter_steps(steps: Any) -> Iterator[dict[str, Any]]:
    """Yield every dict step in *steps*, descending into nested ``pipeline:`` lists."""
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step
        yield from iter_steps(step.get("pipeline"))


def uses_any(steps: Any, pipelines: frozenset[str]) -> bool:
    """Whether any step in *steps*, at any depth, ``uses:`` one of *pipelines*."""
    return any(step.get("uses") in pipelines for step in iter_steps(steps))


def subpackages(melange_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``subpackages:`` entries that are mappings, in file order."""
    return [s for s in melange_cfg.get("subpackages") or [] if isinstance(s, dict)]


def build_steps(scope: dict[str, Any]) -> list[Any]:
    """Top-level steps of *scope*'s build ``pipeline:``."""
    return list(scope.get("pipeline") or [])


def test_steps(scope: dict[str, Any]) -> list[Any]:
    """Top-level steps of *scope*'s ``test.pipeline:``."""
    test = scope.get("test") or {}
    return list(test.get("pipeline") or []) if isinstance(test, dict) else []


def iter_pipelines(melange_cfg: dict[str, Any]) -> Iterator[tuple[str, list[Any]]]:
    """Yield (label, steps) for the main and every subpackage build and test pipeline."""
    scopes: list[tuple[str, dict[str, Any]]] = [("main", melange_cfg)]
    scopes += [
        (f"subpackage '{s.get('name', i)}'", s)
        for i, s in enumerate(subpackages(melange_cfg))
    ]
    for label, scope in scopes:
        yield f"{label} pipeline", build_steps(scope)
        yield f"{label} test pipeline", test_steps(scope)


_VAR_REF = re.compile(r"\$\{\{vars\.([A-Za-z0-9_.-]+)\}\}")


def resolve_vars(melange_cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *melange_cfg* with ``${{vars.NAME}}`` substituted.

    Only plain entries of the top-level ``vars:`` mapping are resolved; values
    produced by ``var-transforms`` and other template namespaces are left as
    written. That is enough to see through ``go-package: ${{vars.go-package}}``
    without running ``melange compile``.
    """
    vars_ = melange_cfg.get("vars") or {}
    if not isinstance(vars_, dict):
        return melange_cfg

    def substitute(value: Any) -> Any:
        if isinstance(value, str):
            return _VAR_REF.sub(
                lambda m: str(vars_.get(m.group(1), m.group(0))),
                value,
            )
        if isinstance(value, list):
            return [substitute(v) for v in value]
        if isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        return value

    resolved: dict[str, Any] = substitute(melange_cfg)
    return resolved


def environment_packages(scope: dict[str, Any]) -> list[Any]:
    """Packages under ``environment.contents.packages`` of *scope*.

    Works for the top-level build environment and for a ``test:`` section,
    which has the same shape.
    """
    env = scope.get("environment") or {}
    contents = (env.get("contents") or {}) if isinstance(env, dict) else {}
    packages = contents.get("packages") if isinstance(contents, dict) else None
    return list(packages or [])


def run_check(
    filenames: Sequence[str],
    check: Callable[[dict[str, Any]], list[str]],
) -> int:
    """Load each file as a melange config, print *check*'s findings per file.

    Returns 1 if any file failed to load or produced a finding, else 0.
    Files that do not parse to a mapping are skipped.
    """
    retval = 0
    for filename in filenames:
        try:
            with open(filename) as f:
                melange_cfg = yaml.load(f)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            retval = 1
            continue

        if not isinstance(melange_cfg, dict):
            continue

        for issue in check(melange_cfg):
            print(f"{filename}: {issue}")
            retval = 1

    return retval
