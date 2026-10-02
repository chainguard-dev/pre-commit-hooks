# Test data for pre-commit hooks

Sample melange YAML files for exercising the hooks in this repository by hand.

## Running a hook against a test file

From the root of this repository:

```bash
pre-commit try-repo . check-pipeline-name-only-steps --files test-data/pipeline-name-only-bad.yaml
```

`pre-commit try-repo` accepts any path to a checkout of this repository, so the
same command works from another repo by replacing `.` with that path.

## Files

### pipeline-name-only-bad.yaml

- Hook: `check-pipeline-name-only-steps`
- Expected: fails with five findings, one each in the main pipeline, the main
  test pipeline, a subpackage pipeline, a nested `pipeline:` inside a
  subpackage step, and a subpackage test pipeline.

### pipeline-name-only-good.yaml

- Hook: `check-pipeline-name-only-steps`
- Expected: passes. Every step has `uses:` or `runs:` alongside any `name:`,
  and the last subpackage has an empty `pipeline:` key, which melange allows
  and the hook must not trip over.
