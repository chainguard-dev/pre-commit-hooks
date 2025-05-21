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


def do_shellcheck(
    melange_cfg: Mapping[str, Any],
    shellcheck: list[str],
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
        for step, shfile in all_steps:
            shfile.write(step["runs"])
            shfile.close()
        subprocess.check_call(
            ["/usr/bin/shellcheck"]
            + ["--shell=busybox", "--"]
            + [os.path.basename(f.name) for _, f in all_steps],
            cwd=os.getcwd(),
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*", help="Filenames to check.")
    parser.add_argument(
        "--shellcheck",
        default=[
            "docker",
            "run",
            f"--volume={os.getcwd()}:/mnt",
            "--rm",
            "-it",
            "koalaman/shellcheck:latest",
        ],
        nargs="*",
        help="shellcheck command",
    )
    args = parser.parse_args(argv)

    melange_cfg = {}
    for filename in args.filenames:
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
                    do_shellcheck(melange_cfg, args.shellcheck)
            except ruamel.yaml.YAMLError as exc:
                print(exc)
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
