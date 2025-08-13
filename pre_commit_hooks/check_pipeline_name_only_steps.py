from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")


def check_pipeline_steps(melange_cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Check if any pipeline steps have only a 'name' field without 'uses' or other details.
    Returns (is_valid, list_of_issues).
    """
    issues = []

    # Check main pipeline
    pipelines = melange_cfg.get("pipeline", [])
    for i, step in enumerate(pipelines):
        if isinstance(step, dict):
            # Check if step has only 'name' and no 'uses'
            if "name" in step and "uses" not in step and len(step) == 1:
                step_name = step.get("name", f"step {i}")
                issues.append(
                    f"main pipeline step '{step_name}' has only a name with no 'uses' or other details",
                )

    # Check test pipeline
    test_section = melange_cfg.get("test", {})
    test_pipelines = test_section.get("pipeline", [])
    for i, step in enumerate(test_pipelines):
        if isinstance(step, dict):
            # Check if step has only 'name' and no 'uses'
            if "name" in step and "uses" not in step and len(step) == 1:
                step_name = step.get("name", f"step {i}")
                issues.append(
                    f"test pipeline step '{step_name}' has only a name with no 'uses' or other details",
                )

    # Check each subpackage
    for sub_idx, subpkg in enumerate(melange_cfg.get("subpackages", [])):
        subpkg_name = subpkg.get("name", f"subpackage-{sub_idx}")

        # Check subpackage pipelines
        subpkg_pipelines = subpkg.get("pipeline", [])
        for i, step in enumerate(subpkg_pipelines):
            if isinstance(step, dict):
                # Check if step has only 'name' and no 'uses'
                if "name" in step and "uses" not in step and len(step) == 1:
                    step_name = step.get("name", f"step {i}")
                    issues.append(
                        f"subpackage '{subpkg_name}' pipeline step '{step_name}' has only a name with no 'uses' or other details",
                    )

        # Check subpackage test pipelines
        subpkg_test_section = subpkg.get("test", {})
        subpkg_test_pipelines = subpkg_test_section.get("pipeline", [])
        for i, step in enumerate(subpkg_test_pipelines):
            if isinstance(step, dict):
                # Check if step has only 'name' and no 'uses'
                if "name" in step and "uses" not in step and len(step) == 1:
                    step_name = step.get("name", f"step {i}")
                    issues.append(
                        f"subpackage '{subpkg_name}' test pipeline step '{step_name}' has only a name with no 'uses' or other details",
                    )

    return len(issues) == 0, issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that pipeline steps don't have only a name without uses or other details",
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

        if not melange_cfg:
            continue

        is_valid, issues = check_pipeline_steps(melange_cfg)
        if not is_valid:
            for issue in issues:
                print(f"{filename}: {issue}")
            retval = 1

    return retval


if __name__ == "__main__":
    sys.exit(main())
