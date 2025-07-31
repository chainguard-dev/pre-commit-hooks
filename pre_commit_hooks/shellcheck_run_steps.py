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

# Reference by SHA for safety
DefaultShellCheckImage = "koalaman/shellcheck@sha256:652a5a714dc2f5f97e36f565d4f7d2322fea376734f3ec1b04ed54ce2a0b124f"


def do_shellcheck(
    melange_cfg: Mapping[str, Any],
    shellcheck: list[str],
    shellcheck_args: list[str],
) -> None:
    if melange_cfg == {}:
        return

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
            return
        for step, shfile in all_steps:
            shfile.write(step["runs"])
            shfile.close()
        subprocess.check_call(
            shellcheck
            + shellcheck_args
            + ["--shell=busybox", "--"]
            + [os.path.basename(f.name) for _, f in all_steps],
            cwd=os.getcwd(),
        )


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
            f"--volume={os.getcwd()}:/mnt",
            "--rm",
            "-it",
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

    melange_cfg = {}
    for filename in filenames:
        with tempfile.NamedTemporaryFile(
            "w",
            delete_on_close=False,
        ) as compiled_out:
            subprocess.check_call(
                [
                    "melange",
                    "compile",
                    "--arch=x86_64",
                    "--pipeline-dir=./pipelines",
                    filename,
                ],
                stdout=compiled_out,
            )
            compiled_out.close()
            try:
                with open(compiled_out.name) as compiled_in:
                    melange_cfg = yaml.load(compiled_in)
                    do_shellcheck(
                        melange_cfg,
                        args.shellcheck,
                        shellcheck_args,
                    )
            except ruamel.yaml.YAMLError as exc:
                print(exc)
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
