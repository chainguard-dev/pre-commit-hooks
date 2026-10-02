from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import tempfile
from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

import ruamel.yaml

yaml = ruamel.yaml.YAML(typ="safe")

# Please provide the output of `grype koalaman/shellcheck@sha256:<newhash>`
# in your PR when bumping. Referenced by SHA for safety.
DefaultShellCheckImage = "koalaman/shellcheck@sha256:652a5a714dc2f5f97e36f565d4f7d2322fea376734f3ec1b04ed54ce2a0b124f"
# Tracks the latest melange; docker_image_outdated() below refreshes a stale
# local copy so new config fields (e.g. `test-resources`) compile.
MelangeImage = "cgr.dev/chainguard/melange:latest"
# How old the local melange image may get before `docker run` re-pulls it.
# Override per repo with `args: [--max-image-age-days=N]`.
DefaultMaxImageAgeDays = 7

# `docker image inspect --format {{.Created}}` prints RFC 3339 with up to
# nanosecond precision, e.g. 2025-07-31T02:42:03.371039353Z. Python < 3.11
# datetime.fromisoformat() accepts only 0, 3 or 6 fractional digits, so the
# fraction is dropped before parsing; day-level age does not need it.
_FRACTIONAL_SECONDS = re.compile(r"\.\d+(?=(?:Z|[+-]\d{2}:\d{2})$)")

# Pipeline directories per package tier, matching stereo's dirToPipelineDirs.
# Paths are relative to the repo root (the Docker /work mount).
PIPELINE_DIRS: dict[str, list[str]] = {
    "os/": ["./os/pipelines/"],
    "extra-packages/": ["./extra-packages/pipelines/", "./pipelines/os"],
    "enterprise-packages/": [
        "./enterprise-packages/pipelines/",
        "./pipelines/",
        "./pipelines/os",
    ],
}


def _pipeline_dirs_for(filename: str) -> list[str]:
    """Return the --pipeline-dirs flag appropriate for *filename*.

    `melange compile` reads only the last of repeated --pipeline-dir flags,
    so the directories go in a single comma-separated --pipeline-dirs.
    """
    for prefix, dirs in PIPELINE_DIRS.items():
        if filename.startswith(prefix):
            return [f"--pipeline-dirs={','.join(dirs)}"]
    # Fallback: derive from the file's own directory (original behaviour).
    return [f"--pipeline-dirs=./{os.path.dirname(filename)}/pipelines"]


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


def parse_docker_timestamp(created: str) -> datetime:
    """Parse a docker `.Created` value into an aware datetime."""
    created = _FRACTIONAL_SECONDS.sub("", created.strip())
    if created.endswith("Z"):
        created = created[:-1] + "+00:00"
    return datetime.fromisoformat(created)


def docker_image_outdated(image: str, max_age: timedelta) -> bool:
    """Return True if *image* is absent locally or was created more than *max_age* ago.

    The caller turns this into `docker run --pull=always`, so there is a single
    pull code path and a missing image is handled the same way as a stale one.
    If docker itself is unusable the later `docker run` reports that with its
    own error, so this only answers the age question.
    """
    result = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Created}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return True
    try:
        created = parse_docker_timestamp(result.stdout)
    except ValueError as exc:
        print(f"Warning: cannot parse creation time of {image}: {exc}")
        return False
    age = datetime.now(timezone.utc) - created
    if age > max_age:
        # flush so the line lands before docker's own pull output
        print(f"{image} is {age.days} days old; refreshing it", flush=True)
        return True
    return False


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
    parser.add_argument(
        "--max-image-age-days",
        type=int,
        default=DefaultMaxImageAgeDays,
        metavar="DAYS",
        help="refresh the melange image when the local copy is older than this "
        "many days (default: %(default)s; 0 refreshes on every run)",
    )
    args = parser.parse_args(argv)
    try:
        idx = args.filenames.index("--")
        shellcheck_args = args.filenames[:idx]
        filenames = args.filenames[idx + 1 :]
    except ValueError:
        shellcheck_args = []
        filenames = args.filenames

    # Decided once per invocation, after argument parsing so that `--help`
    # never touches docker. The first `docker run` below performs the refresh.
    pull_policy = "missing"
    if docker_image_outdated(MelangeImage, timedelta(days=args.max_image_age_days)):
        pull_policy = "always"

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
                    f"--pull={pull_policy}",
                    f"--volume={os.getcwd()}:/work:Z",
                    "--rm",
                    MelangeImage,
                    "compile",
                    f"--arch={arch}",
                    *_pipeline_dirs_for(filename),
                    filename,
                ],
                stdout=compiled_out,
            )
            # One refresh per invocation is enough.
            pull_policy = "missing"
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
