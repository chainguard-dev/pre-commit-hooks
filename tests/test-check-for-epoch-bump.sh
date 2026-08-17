#!/usr/bin/env bash
# Tests for scripts/check-for-epoch-bump.sh
#
# Builds a throwaway repo with a real `origin` remote so the two refs can
# disagree, which is the situation that matters: in package repos nobody checks
# out `main` locally, so the local branch rots while `origin/main` stays current.
#
# Run: tests/test-check-for-epoch-bump.sh [path-to-script]
# Exits non-zero on the first failing case and leaves the scratch repo in place
# for inspection.
set -uo pipefail

SCRIPT="${1:-$(cd "$(dirname "$0")/.." && pwd)/scripts/check-for-epoch-bump.sh}"
ROOT=/tmp/epoch-hook-test
PKG=enterprise-packages/foo.yaml

pass=0
fail=0

say() { printf '%s\n' "$*"; }

# Scratch repos must never sign. gitsign is enabled globally on dev machines
# (gpg.format=x509, commit.gpgsign=true), so an unconfigured test repo would
# round-trip to Fulcio and Rekor for every throwaway commit: slow, offline-hostile,
# and it writes junk into the transparency log. Call this right after init/clone.
init_repo_config() {
  git config commit.gpgsign false
  git config tag.gpgsign false
  git config user.name "epoch hook test"
  git config user.email "epoch-hook-test@example.invalid"
}

# write a melange-ish yaml with the given version and epoch
write_pkg() {
  mkdir -p "$(dirname "$2")"
  cat > "$2" <<YAML
package:
  name: foo
  version: "$1"
  epoch: $3
  description: test package
YAML
}

# build_repo: origin/main ends at <ahead spec>, local main is left at <stale spec>
# args: ahead_version ahead_epoch stale_mode
#   stale_mode=behind  -> local main points one commit back (file present, older epoch)
#   stale_mode=nofile  -> local main points at a commit before the file existed
#   stale_mode=current -> local main == origin/main
build_repo() {
  local av=$1 ae=$2 mode=$3
  rm -rf "$ROOT"
  mkdir -p "$ROOT"
  git init -q --bare "$ROOT/origin.git"
  git clone -q "$ROOT/origin.git" "$ROOT/work" 2>/dev/null
  cd "$ROOT/work" || exit 1
  init_repo_config
  git symbolic-ref HEAD refs/heads/main

  echo seed > README.md
  git add README.md
  git commit -qm "seed"
  local seed
  seed=$(git rev-parse HEAD)

  write_pkg "1.0.0" "$PKG" 3
  git add "$PKG"
  git commit -qm "add foo 1.0.0-r3"
  local older
  older=$(git rev-parse HEAD)

  write_pkg "$av" "$PKG" "$ae"
  git add "$PKG"
  git commit -qm "foo $av-r$ae"
  git push -q origin main

  # Leave main before moving it: git refuses to force-update a branch that is
  # checked out in the current worktree.
  git checkout -q -b feature
  case "$mode" in
    behind)  git branch -f main "$older" ;;
    nofile)  git branch -f main "$seed" ;;
    current) : ;;
  esac

  # sanity-check that the scenario is actually set up, so a silently broken
  # harness cannot report a green run
  local local_main origin_main
  local_main=$(git rev-parse main)
  origin_main=$(git rev-parse origin/main)
  case "$mode" in
    behind|nofile)
      if [ "$local_main" = "$origin_main" ]; then
        say "  HARNESS BROKEN: local main was not made stale for mode=$mode"
        exit 1
      fi ;;
    current)
      if [ "$local_main" != "$origin_main" ]; then
        say "  HARNESS BROKEN: local main should equal origin/main for mode=current"
        exit 1
      fi ;;
  esac
}

# run_case <label> <expect: PASS|WARN|SKIP|NEW> <local version> <local epoch>
run_case() {
  local label=$1 expect=$2 lv=$3 le=$4
  write_pkg "$lv" "$PKG" "$le"
  local out
  out=$("$SCRIPT" "$PKG" 2>&1)

  local got=UNKNOWN
  case "$out" in
    *"Could not resolve a base ref"*)  got=SKIP ;;
    *"not found on"*|*"new package"*)  got=NEW ;;
    *"HAS NOT been increased"*)        got=WARN ;;
    *"has been increased"*)            got=PASS ;;
  esac

  if [ "$got" = "$expect" ]; then
    say "  ok   $label (expected $expect)"
    pass=$((pass + 1))
  else
    say "  FAIL $label: expected $expect, got $got"
    say "       ---- script output ----"
    printf '%s\n' "$out" | sed 's/^/       /'
    fail=$((fail + 1))
  fi
}

say "script under test: $SCRIPT"

say ""
say "scenario: local main one commit stale, origin/main has 1.0.0-r5"
build_repo "1.0.0" 5 behind
run_case "epoch 4 is NOT a bump over origin/main r5" WARN "1.0.0" 4
run_case "epoch 6 IS a bump over origin/main r5"     PASS "1.0.0" 6
run_case "epoch 5 equals origin/main r5"             WARN "1.0.0" 5
run_case "new version resets epoch to 0"             PASS "1.0.1" 0

say ""
say "scenario: local main predates the file, origin/main has 1.0.0-r5"
build_repo "1.0.0" 5 nofile
run_case "epoch 4 still compared against origin/main" WARN "1.0.0" 4
run_case "epoch 6 still recognised as a bump"         PASS "1.0.0" 6

say ""
say "scenario: local main == origin/main (no staleness)"
build_repo "1.0.0" 5 current
run_case "epoch 4 rejected"  WARN "1.0.0" 4
run_case "epoch 6 accepted"  PASS "1.0.0" 6

say ""
say "scenario: genuinely new package, absent from origin/main"
build_repo "1.0.0" 5 current
rm -f "$PKG"
write_pkg "2.0.0" "enterprise-packages/brand-new.yaml" 0
out=$("$SCRIPT" enterprise-packages/brand-new.yaml 2>&1)
if printf '%s' "$out" | grep -qiE 'not found on|new package'; then
  say "  ok   absent-from-main is reported explicitly, not silently compared"
  pass=$((pass + 1))
else
  say "  FAIL absent-from-main was not called out; output was:"
  printf '%s\n' "$out" | sed 's/^/       /'
  fail=$((fail + 1))
fi

say ""
say "scenario: no resolvable base ref at all"
rm -rf "$ROOT/norefs"
mkdir -p "$ROOT/norefs"
cd "$ROOT/norefs" || exit 1
git init -q .
init_repo_config
git symbolic-ref HEAD refs/heads/feature
write_pkg "1.0.0" "$PKG" 1
git add "$PKG" >/dev/null 2>&1
git commit -qm "initial" >/dev/null 2>&1
out=$("$SCRIPT" "$PKG" 2>&1)
if printf '%s' "$out" | grep -qi 'could not resolve a base ref'; then
  say "  ok   missing base ref is reported instead of passing everything"
  pass=$((pass + 1))
else
  say "  FAIL missing base ref was not reported; output was:"
  printf '%s\n' "$out" | sed 's/^/       /'
  fail=$((fail + 1))
fi

say ""
say "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ]
