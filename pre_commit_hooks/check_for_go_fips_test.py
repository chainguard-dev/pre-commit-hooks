from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from typing import Any

from pre_commit_hooks.melange import build_steps
from pre_commit_hooks.melange import environment_packages
from pre_commit_hooks.melange import iter_steps
from pre_commit_hooks.melange import resolve_vars
from pre_commit_hooks.melange import run_check
from pre_commit_hooks.melange import subpackages
from pre_commit_hooks.melange import test_steps
from pre_commit_hooks.melange import uses_any

# Go toolchain packages that imply a FIPS build, matched as prefixes against
# environment packages and `go-package:` inputs. One entry per toolchain family
# test/go-fips-check knows how to verify:
#   go-fips, go-fips-md5  Microsoft-patched Go with the OpenSSL backend; at 1.27
#                         these are meta packages pointing at go-msft-1.27
#   go-msft               the same toolchain under its own name (systemcrypto)
#   go-geomys             Geomys Go with the native FIPS 140 module
#   go-openssl            unpatched golang-fips/go
FIPS_GO_PREFIXES = ("go-fips", "go-msft", "go-geomys", "go-openssl")

# Pipelines that install the toolchain named by their `go-package` input.
GO_PIPELINES_WITH_TOOLCHAIN_INPUT = frozenset({"go/build", "go/install"})
# Pipelines that build with whatever `go` the build environment provides.
GO_PIPELINES_FROM_ENVIRONMENT = frozenset({"go/build/v2"})
# `runs:` blocks that call the compiler directly also use the environment's go.
GO_BUILD_COMMAND = re.compile(r"\bgo\s+(build|install)\b")

FIPS_TEST = frozenset({"test/go-fips-check"})
EMPTY_PACKAGE_TESTS = frozenset({"test/emptypackage", "test/tw/emptypackage"})
# Moves the main package's binaries into a subpackage, which then owns the test.
SPLIT_BIN = frozenset({"split/bin"})


def is_fips_toolchain(package: Any) -> bool:
    return isinstance(package, str) and package.startswith(FIPS_GO_PREFIXES)


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
    # Toolchain names are often templated (`go-package: ${{vars.go-package}}`);
    # resolve what can be resolved without a melange compile.
    melange_cfg = resolve_vars(melange_cfg)
    env_has_fips_go = any(
        is_fips_toolchain(p) for p in environment_packages(melange_cfg)
    )
    subs = subpackages(melange_cfg)

    main_test = test_steps(melange_cfg)
    main_has_fips_test = uses_any(main_test, FIPS_TEST)
    main_builds_fips = builds_with_fips(build_steps(melange_cfg), env_has_fips_go)
    # split/bin in a subpackage moves the main package's binaries there: the
    # subpackage inherits the obligation and the main package is left with none.
    split_off = [s for s in subs if uses_any(build_steps(s), SPLIT_BIN)]

    if (
        main_builds_fips
        and not split_off
        and not main_has_fips_test
        and not uses_any(main_test, EMPTY_PACKAGE_TESTS)
    ):
        issues.append(
            "main package builds with a FIPS Go toolchain but lacks test/go-fips-check",
        )

    for i, subpkg in enumerate(subs):
        name = str(subpkg.get("name", f"#{i}"))
        builds_fips = builds_with_fips(build_steps(subpkg), env_has_fips_go) or (
            main_builds_fips and any(s is subpkg for s in split_off)
        )
        if not builds_fips:
            continue
        sub_test = test_steps(subpkg)
        if uses_any(sub_test, FIPS_TEST) or uses_any(sub_test, EMPTY_PACKAGE_TESTS):
            continue
        if main_has_fips_test and installed_in_main_test(melange_cfg, name):
            continue
        issues.append(
            f"subpackage '{name}' builds with a FIPS Go toolchain but lacks "
            "test/go-fips-check (in its own test, or in the main test with the "
            "subpackage installed)",
        )

    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check that packages built with a FIPS Go toolchain "
        "have a test/go-fips-check test",
    )
    parser.add_argument("filenames", nargs="*", help="Filenames to check")
    args = parser.parse_args(argv)
    return run_check(args.filenames, check_go_fips_compliance)


if __name__ == "__main__":
    sys.exit(main())
