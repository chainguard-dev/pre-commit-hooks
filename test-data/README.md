# Test Data for Pre-commit Hooks

This directory contains sample YAML files that can be used to test the pre-commit hooks in this repository.

## Testing hooks locally

To test a specific hook against a test file, use the `pre-commit try-repo` command:

```bash
# From any directory with YAML files to test:
pre-commit try-repo /path/to/this/repo HOOK_ID --files FILE_TO_TEST

# Example for check-pipeline-name-only-steps:
pre-commit try-repo /home/amber-arcadia/Documents/GitRepos/pre-commit-hooks \
  check-pipeline-name-only-steps \
  --files test-data/pipeline-name-only-bad.yaml
```

## Test files

### pipeline-name-only-bad.yaml
- **Tests**: `check-pipeline-name-only-steps`
- **Expected**: Should FAIL
- **Issues**: Contains pipeline steps that have only a `name` field without `uses` or other details

### pipeline-name-only-good.yaml
- **Tests**: `check-pipeline-name-only-steps`
- **Expected**: Should PASS
- **Issues**: None - all pipeline steps are properly formatted