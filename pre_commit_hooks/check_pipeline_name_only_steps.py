from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from pre_commit_hooks.melange import iter_pipelines
from pre_commit_hooks.melange import iter_steps
from pre_commit_hooks.melange import run_check


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
    return run_check(args.filenames, check_pipeline_steps)


if __name__ == "__main__":
    sys.exit(main())
