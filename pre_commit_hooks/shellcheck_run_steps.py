from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import tempfile
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")

# Please provide the output of `grype koalaman/shellcheck@sha256:<newhash>`
# in your PR when bumping. Referenced by SHA for safety.
DefaultShellCheckImage = "koalaman/shellcheck@sha256:652a5a714dc2f5f97e36f565d4f7d2322fea376734f3ec1b04ed54ce2a0b124f"
# 0.31.6 pinning to resolve var-transforms linting error
MelangeImage = "cgr.dev/chainguard/melange@sha256:f90bc7ef37f080cd9e0919d8ff96163a57551de515c6e8c7c228157176a0436b"


# Returns False if shellcheck reports issues
def do_shellcheck(
    melange_cfg: Mapping[str, Any],
    shellcheck: list[str],
    shellcheck_args: list[str],
) -> bool:
    if melange_cfg == {}:
        return True

    pkgs = [melange_cfg]
    pkgs.extend(melange_cfg.get("subpackages", []))
    pipelines: list[Mapping[str, Any]] = []
    for pkg in pkgs:
        pipelines.extend(pkg.get("pipeline", []))
        if "test" in pkg.keys():
            test_pipeline = pkg["test"].get("pipeline", [])
            pipelines.extend(test_pipeline)
    name = melange_cfg["package"]["name"]
    all_steps = []
    with contextlib.ExitStack() as stack:
        for step in pipelines:
            if "runs" not in step.keys():
                continue
            all_steps.append(
                (
                    step,
                    stack.enter_context(
                        tempfile.NamedTemporaryFile(
                            mode="w",
                            prefix=name,
                            dir=os.getcwd(),
                            delete_on_close=False,
                        ),
                    ),
                ),
            )
        if len(all_steps) == 0:
            return True
        for step, shfile in all_steps:
            shfile.write(step["runs"])
            shfile.close()
        try:
            subprocess.check_call(
                shellcheck
                + shellcheck_args
                + ["--shell=busybox", "--"]
                + [os.path.basename(f.name) for _, f in all_steps],
                cwd=os.getcwd(),
            )
        except subprocess.CalledProcessError:
            return False

    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "filenames",
        nargs="*",
        metavar="[-- SHELLCHECK ARGS -- ] FILENAMES",
    )
    parser.add_argument(
        "--shellcheck",
        default=[
            "docker",
            "run",
            f"--volume={os.getcwd()}:/mnt:Z",
            "--rm",
            DefaultShellCheckImage,
        ],
        nargs="*",
        help="shellcheck command",
    )
    args = parser.parse_args(argv)
    try:
        idx = args.filenames.index("--")
        shellcheck_args = args.filenames[:idx]
        filenames = args.filenames[idx + 1 :]
    except ValueError:
        shellcheck_args = []
        filenames = args.filenames

    fail_cnt = 0
    melange_cfg = {}
    for filename in filenames:
        with tempfile.NamedTemporaryFile(
            "w",
            delete_on_close=False,
        ) as compiled_out:
            with open(filename) as precompiled_in:
                melange_cfg = yaml.load(precompiled_in)
                arch = melange_cfg["package"].get("target-architecture", ["x86_64"])[0]
            subprocess.check_call(
                [
                    "docker",
                    "run",
                    f"--volume={os.getcwd()}:/work:Z",
                    "--rm",
                    MelangeImage,
                    "compile",
                    f"--arch={arch}",
                    "--pipeline-dir=./pipelines",
                    filename,
                ],
                stdout=compiled_out,
            )
            compiled_out.close()
            try:
                with open(compiled_out.name) as compiled_in:
                    melange_cfg = yaml.load(compiled_in)
                    if not do_shellcheck(
                        melange_cfg,
                        args.shellcheck,
                        shellcheck_args,
                    ):
                        fail_cnt += 1
            except ruamel.yaml.YAMLError as exc:
                print(exc)
                fail_cnt += 1

    return fail_cnt


if __name__ == "__main__":
    fail_cnt = main()
    exit_code = 0
    if fail_cnt != 0:
        exit_code = 1

    raise SystemExit(exit_code)
