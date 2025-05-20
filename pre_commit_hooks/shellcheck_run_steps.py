from __future__ import annotations

import argparse
import subprocess
import tempfile
from collections.abc import Generator
from collections.abc import Sequence
from typing import Any
from typing import NamedTuple

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")


def _exhaust(gen: Generator[str]) -> None:
    for _ in gen:
        pass


def _parse_unsafe(*args: Any, **kwargs: Any) -> None:
    _exhaust(yaml.parse(*args, **kwargs))


def _load_all(*args: Any, **kwargs: Any) -> None:
    _exhaust(yaml.load_all(*args, **kwargs))


class Key(NamedTuple):
    multi: bool
    unsafe: bool


def do_shellcheck(melange_cfg):
    if melange_cfg == {}:
        return 0

    pkgs = [melange_cfg]
    pkgs.extend(melange_cfg.get("subpackages", []))
    pipelines = []
    for pkg in pkgs:
        pipelines.extend(pkg.get("pipeline", []))
        if "test" in pkg.keys():
            test_pipeline = pkg["test"].get("pipeline", [])
            pipelines.extend(test_pipeline)

    for step in pipelines:
        if "runs" not in step.keys():
            continue
        with tempfile.NamedTemporaryFile(mode="w") as shfile:
            shfile.write(step["runs"])
            subprocess.check_call(
                ["shellcheck", "--shell=busybox", shfile.name]
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*", help="Filenames to check.")
    args = parser.parse_args(argv)

    melange_cfg = {}
    for filename in args.filenames:
        with tempfile.NamedTemporaryFile(
            "w", delete_on_close=False
        ) as compiled_out:
            subprocess.check_call(
                [
                    "melange",
                    "compile",
                    "--arch",
                    "x86_64",
                    "--pipeline-dir",
                    "./pipelines",
                    filename,
                ],
                stdout=compiled_out,
            )
            compiled_out.close()
            try:
                with open(compiled_out.name) as compiled_in:
                    melange_cfg = yaml.load(compiled_in)
                    do_shellcheck(melange_cfg)
            except ruamel.yaml.YAMLError as exc:
                print(exc)
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
