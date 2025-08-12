from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")


def check_go_fips_compliance(melange_cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Check if all go-fips usages have corresponding tests.
    Returns (is_compliant, list_of_missing_tests).
    """
    issues = []

    # Check if main package uses go-fips
    main_uses_fips = False
    main_has_test = False

    # Check environment packages for any go-fips variant
    env_packages = (
        melange_cfg.get("environment", {}).get("contents", {}).get("packages", [])
    )
    for pkg in env_packages:
        if pkg.startswith("go-fips"):
            main_uses_fips = True
            break

    # Check main pipeline steps for go/build with go-package: go-fips*
    pipelines = melange_cfg.get("pipeline", [])
    for step in pipelines:
        if step.get("uses") == "go/build":
            go_package = step.get("with", {}).get("go-package", "")
            if go_package.startswith("go-fips"):
                main_uses_fips = True
                break

    # Check main test section
    test_section = melange_cfg.get("test", {})
    test_pipelines = test_section.get("pipeline", [])
    for step in test_pipelines:
        if step.get("uses") == "test/go-fips-check":
            main_has_test = True
            break

    if main_uses_fips and not main_has_test:
        issues.append("main package uses go-fips but lacks test/go-fips-check")

    # Check each subpackage
    for i, subpkg in enumerate(melange_cfg.get("subpackages", [])):
        subpkg_uses_fips = False
        subpkg_has_test = False
        subpkg_name = subpkg.get("name", f"subpackage-{i}")

        # Check subpackage pipelines for go-fips usage
        subpkg_pipelines = subpkg.get("pipeline", [])
        for step in subpkg_pipelines:
            if step.get("uses") == "go/build":
                go_package = step.get("with", {}).get("go-package", "")
                if go_package.startswith("go-fips"):
                    subpkg_uses_fips = True
                    break

        # Check subpackage test sections
        subpkg_test_section = subpkg.get("test", {})
        subpkg_test_pipelines = subpkg_test_section.get("pipeline", [])
        for step in subpkg_test_pipelines:
            if step.get("uses") == "test/go-fips-check":
                subpkg_has_test = True
                break

        if subpkg_uses_fips and not subpkg_has_test:
            issues.append(
                f"subpackage '{subpkg_name}' uses go-fips but lacks test/go-fips-check",
            )

    return len(issues) == 0, issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that packages using go-fips have corresponding go-fips tests",
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

        is_compliant, issues = check_go_fips_compliance(melange_cfg)
        if not is_compliant:
            for issue in issues:
                print(f"{filename}: {issue}")
            retval = 1

    return retval


if __name__ == "__main__":
    sys.exit(main())
