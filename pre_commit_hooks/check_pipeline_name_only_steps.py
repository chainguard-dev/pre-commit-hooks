from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from collections.abc import Sequence
from typing import Any

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")


def iter_pipelines(melange_cfg: dict[str, Any]) -> Iterator[tuple[str, list[Any]]]:
    """Yield (label, steps) for every pipeline in a melange config.

    Covers the main build and test pipelines and each subpackage's build and
    test pipelines. A ``pipeline:`` key with no value (YAML null) yields an
    empty list, matching how melange treats it.
    """
    scopes: list[tuple[str, dict[str, Any]]] = [("main", melange_cfg)]
    for i, subpkg in enumerate(melange_cfg.get("subpackages") or []):
        if isinstance(subpkg, dict):
            scopes.append((f"subpackage '{subpkg.get('name', i)}'", subpkg))
    for label, scope in scopes:
        yield f"{label} pipeline", scope.get("pipeline") or []
        test = scope.get("test") or {}
        if isinstance(test, dict):
            yield f"{label} test pipeline", test.get("pipeline") or []


def iter_steps(steps: list[Any]) -> Iterator[dict[str, Any]]:
    """Yield every dict step in *steps*, descending into nested ``pipeline:`` lists."""
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        yield from iter_steps(step.get("pipeline") or [])


def check_pipeline_steps(melange_cfg: dict[str, Any]) -> list[str]:
    """Return a message for every step that consists of nothing but a ``name``.

    melange runs such a step as a no-op, so it is either a typo for ``uses:``
    or a heading that was meant to sit on the step that follows it.
    """
    issues = []
    for label, steps in iter_pipelines(melange_cfg):
        for step in iter_steps(steps):
            if set(step) == {"name"}:
                issues.append(
                    f"{label} step '{step['name']}' has only a name and does "
                    "nothing; use 'uses:' for a pipeline, or fold the name into "
                    "the next step",
                )
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that no melange pipeline step consists of only a name",
    )
    parser.add_argument("filenames", nargs="*", help="Filenames to check")
    args = parser.parse_args(argv)

    retval = 0

    for filename in args.filenames:
        try:
            with open(filename) as f:
                melange_cfg = yaml.load(f)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            retval = 1
            continue

        if not isinstance(melange_cfg, dict):
            continue

        for issue in check_pipeline_steps(melange_cfg):
            print(f"{filename}: {issue}")
            retval = 1

    return retval


if __name__ == "__main__":
    sys.exit(main())
