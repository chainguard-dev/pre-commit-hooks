from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from collections.abc import Sequence
from typing import Any

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")

# Go toolchain packages that imply a FIPS build, matched as prefixes against
# environment packages and `go-package:` inputs (go-fips, go-fips-md5-1.25, ...).
FIPS_GO_PREFIXES = ("go-fips",)

# Pipelines that install the toolchain named by their `go-package` input.
GO_PIPELINES_WITH_TOOLCHAIN_INPUT = frozenset({"go/build", "go/install"})
# Pipelines that build with whatever `go` the build environment provides.
GO_PIPELINES_FROM_ENVIRONMENT = frozenset({"go/build/v2"})
# `runs:` blocks that call the compiler directly also use the environment's go.
GO_BUILD_COMMAND = re.compile(r"\bgo\s+(build|install)\b")

FIPS_TEST = "test/go-fips-check"
EMPTY_PACKAGE_TESTS = frozenset({"test/emptypackage", "test/tw/emptypackage"})
# Moves the main package's binaries into a subpackage, which then owns the test.
SPLIT_BIN = "split/bin"


def iter_steps(steps: Any) -> Iterator[dict[str, Any]]:
    """Yield every dict step in *steps*, descending into nested ``pipeline:`` lists."""
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step
        yield from iter_steps(step.get("pipeline"))


def uses_any(steps: Any, pipelines: frozenset[str]) -> bool:
    return any(step.get("uses") in pipelines for step in iter_steps(steps))


def is_fips_toolchain(package: Any) -> bool:
    return isinstance(package, str) and package.startswith(FIPS_GO_PREFIXES)


def environment_packages(scope: dict[str, Any]) -> list[Any]:
    """Packages listed under ``environment.contents.packages`` of *scope*."""
    env = scope.get("environment") or {}
    contents = (env.get("contents") or {}) if isinstance(env, dict) else {}
    packages = contents.get("packages") if isinstance(contents, dict) else None
    return list(packages or [])


def test_steps(scope: dict[str, Any]) -> list[Any]:
    test = scope.get("test") or {}
    return list(test.get("pipeline") or []) if isinstance(test, dict) else []


def builds_with_fips(steps: Any, env_has_fips_go: bool) -> bool:
    """Whether *steps* compile Go with a FIPS toolchain.

    `go/build` and `go/install` say so explicitly through `go-package`.
    `go/build/v2` and hand-written `go build` lines use the environment's go,
    so they count only when the environment provides a FIPS toolchain.
    """
    for step in iter_steps(steps):
        uses = step.get("uses")
        if uses in GO_PIPELINES_WITH_TOOLCHAIN_INPUT:
            inputs = step.get("with") or {}
            if is_fips_toolchain(inputs.get("go-package")):
                return True
        elif uses in GO_PIPELINES_FROM_ENVIRONMENT:
            if env_has_fips_go:
                return True
        elif env_has_fips_go and isinstance(step.get("runs"), str):
            if GO_BUILD_COMMAND.search(step["runs"]):
                return True
    return False


def installed_in_main_test(melange_cfg: dict[str, Any], subpkg_name: str) -> bool:
    """Whether the main test environment installs *subpkg_name*.

    Names are compared before template expansion. For range subpackages the
    part before ``${{range.key}}`` is matched as a prefix, so a main test that
    installs ``${{package.name}}-controller`` covers
    ``${{package.name}}-${{range.key}}``.
    """
    test = melange_cfg.get("test") or {}
    packages = environment_packages(test) if isinstance(test, dict) else []
    if subpkg_name in packages:
        return True
    prefix, sep, _ = subpkg_name.partition("${{range.key}}")
    return bool(sep and prefix) and any(
        isinstance(p, str) and p.startswith(prefix) for p in packages
    )


def check_go_fips_compliance(melange_cfg: dict[str, Any]) -> list[str]:
    """Return a message for every package or subpackage that builds Go with a
    FIPS toolchain and has no test/go-fips-check covering it.

    Coverage is the scope's own test pipeline, an empty-package test (nothing
    to check), or for subpackages the main test pipeline when it both runs
    test/go-fips-check and installs the subpackage.
    """
    issues = []
    env_has_fips_go = any(
        is_fips_toolchain(p) for p in environment_packages(melange_cfg)
    )
    subpackages = [
        s for s in melange_cfg.get("subpackages") or [] if isinstance(s, dict)
    ]

    main_test = test_steps(melange_cfg)
    main_has_fips_test = uses_any(main_test, frozenset({FIPS_TEST}))
    main_builds_fips = builds_with_fips(melange_cfg.get("pipeline"), env_has_fips_go)
    # split/bin in a subpackage moves the main package's binaries there: the
    # subpackage inherits the obligation and the main package is left with none.
    split_off = [
        s for s in subpackages if uses_any(s.get("pipeline"), frozenset({SPLIT_BIN}))
    ]

    if (
        main_builds_fips
        and not split_off
        and not main_has_fips_test
        and not uses_any(main_test, EMPTY_PACKAGE_TESTS)
    ):
        issues.append(
            f"main package builds with a FIPS Go toolchain but lacks {FIPS_TEST}",
        )

    for i, subpkg in enumerate(subpackages):
        name = str(subpkg.get("name", f"#{i}"))
        builds_fips = builds_with_fips(subpkg.get("pipeline"), env_has_fips_go) or (
            main_builds_fips and any(s is subpkg for s in split_off)
        )
        if not builds_fips:
            continue
        sub_test = test_steps(subpkg)
        if uses_any(sub_test, frozenset({FIPS_TEST})) or uses_any(
            sub_test,
            EMPTY_PACKAGE_TESTS,
        ):
            continue
        if main_has_fips_test and installed_in_main_test(melange_cfg, name):
            continue
        issues.append(
            f"subpackage '{name}' builds with a FIPS Go toolchain but lacks "
            f"{FIPS_TEST} (in its own test, or in the main test with the "
            "subpackage installed)",
        )

    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that packages built with a FIPS Go toolchain "
        f"have a {FIPS_TEST} test",
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

        for issue in check_go_fips_compliance(melange_cfg):
            print(f"{filename}: {issue}")
            retval = 1

    return retval


if __name__ == "__main__":
    sys.exit(main())
