from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")


def uses_go_fips(melange_cfg: dict[str, Any]) -> bool:
    """Check if package uses go-fips."""
    # Check environment packages
    env_packages = melange_cfg.get("environment", {}).get("contents", {}).get("packages", [])
    if "go-fips" in env_packages:
        return True
    
    # Check pipeline steps for go/build with go-package: go-fips
    pipelines = melange_cfg.get("pipeline", [])
    for step in pipelines:
        if step.get("uses") == "go/build":
            if step.get("with", {}).get("go-package") == "go-fips":
                return True
    
    # Check subpackage pipelines
    for subpkg in melange_cfg.get("subpackages", []):
        subpkg_pipelines = subpkg.get("pipeline", [])
        for step in subpkg_pipelines:
            if step.get("uses") == "go/build":
                if step.get("with", {}).get("go-package") == "go-fips":
                    return True
    
    return False


def has_go_fips_test(melange_cfg: dict[str, Any]) -> bool:
    """Check if package has go-fips test."""
    test_section = melange_cfg.get("test", {})
    test_pipelines = test_section.get("pipeline", [])
    
    for step in test_pipelines:
        if step.get("uses") == "test/go-fips-check":
            return True
    
    return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that packages using go-fips have corresponding go-fips tests"
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
            
        if uses_go_fips(melange_cfg):
            if not has_go_fips_test(melange_cfg):
                print(
                    f"{filename}: Package uses go-fips but does not have "
                    "a corresponding go-fips test (add '- uses: test/go-fips-check' to test pipeline)"
                )
                retval = 1
    
    return retval


if __name__ == "__main__":
    sys.exit(main())