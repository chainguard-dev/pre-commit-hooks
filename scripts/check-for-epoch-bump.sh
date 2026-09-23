#!/bin/bash

# Areas of possible improvement:
# Check the git remotes to see if this is a package repo
# Exclude certain filenames like "pombump-deps.yaml", related. Probably could be done in the hook config or in the loop.

# Check for at least one argument
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 path_to_yaml_file"
    exit 1
fi

version_grep() {
    grep -E '^  version:'
}

version_sed() {
    sed -r 's/^  version:[[:space:]]+([^[:space:]]+).*$/\1/;s|"||g'
}

epoch_grep() {
    grep -E '^  epoch:'
}

epoch_sed() {
    sed -r 's/^  epoch:[[:space:]]+([0-9]+).*$/\1/'
}

# Pick the ref to compare against, preferring the remote-tracking branch.
#
# `main` on its own is the wrong baseline in a package repo: the convention there
# is to never commit to main, so the local branch is only as fresh as the last
# time someone happened to check it out. It can sit thousands of commits behind,
# which hands this check an old, lower epoch and lets an already-taken epoch look
# like a real bump. Worse, once local main predates a package's creation,
# `git show` finds nothing, the baseline collapses to 0, and every version
# compares as increased, so the hook passes unconditionally.
#
# Deliberately no `git fetch`: a pre-commit hook has to stay fast and keep working
# offline. Whatever the last fetch left in origin/main is still far closer to the
# truth than a branch nobody visits.
resolve_base_ref() {
    local candidate
    for candidate in "origin/main" "main" "origin/HEAD"; do
        if git rev-parse --verify --quiet "${candidate}^{commit}" >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

if ! base_ref="$(resolve_base_ref)"; then
    echo "⚠️ Could not resolve a base ref (tried origin/main, main, origin/HEAD)."
    echo "   Skipping the epoch check rather than comparing against an empty"
    echo "   baseline, which would report every file as bumped."
    exit 0
fi

for yaml_file in "$@"; do
    echo "Checking $yaml_file:"

    # Extract version and epoch from the current file using grep and sed
    # (not assuming `yq` is available)
    version_line="$(version_grep < "$yaml_file")"
    version_local="$(echo "$version_line" | version_sed)"
    if [ -z "$version_local" ]; then
        echo "⚠️ No top-level 'version:' field found in $yaml_file; treating it as 0"
        version_local="0"
    fi

    epoch_line="$(epoch_grep < "$yaml_file")"
    epoch_local="$(echo "$epoch_line" | epoch_sed)"
    if [ -z "$epoch_local" ]; then
        echo "⚠️ No top-level 'epoch:' field found in $yaml_file; treating it as 0"
        epoch_local="0"
    fi

    # Extract version and epoch from the file on the base ref using git show.
    # Try all three known package directories so epoch bumps are enforced when
    # a package is moved between os/, enterprise-packages/, and extra-packages/.
    first_component="${yaml_file%%/*}"
    rest_of_path="${yaml_file#*/}"
    main_content=""
    if [[ "$first_component" == "os" || "$first_component" == "enterprise-packages" || "$first_component" == "extra-packages" ]]; then
        for prefix in "os" "enterprise-packages" "extra-packages"; do
            main_content="$(git show "${base_ref}:${prefix}/${rest_of_path}" 2>/dev/null)"
            [ -n "$main_content" ] && break
        done
    else
        main_content="$(git show "${base_ref}:${yaml_file}" 2>/dev/null)"
    fi

    if [ -z "$main_content" ]; then
        # Genuinely absent from the base ref, so a 0 baseline is the right answer.
        # Say so out loud: a bare "✅ increased" here reads as though a real
        # comparison happened.
        echo "ℹ️ Not found on ${base_ref} (new package?); comparing against 0-r0"
        version_main="0"
        epoch_main="0"
    else
        version_main_line="$(echo "$main_content" | version_grep)"
        version_main="$(echo "$version_main_line" | version_sed)"
        if [ -z "$version_main" ]; then
            version_main="0"
        fi

        epoch_main_line="$(echo "$main_content" | epoch_grep)"
        epoch_main="$(echo "$epoch_main_line" | epoch_sed)"
        if [ -z "$epoch_main" ]; then
            epoch_main="0"
        fi
    fi

    # Compare version first, then epoch only if versions are the same
    if [ "$version_local" != "$version_main" ]; then
        # Versions differ, so the version comparison settles it. sort -V puts the
        # lower version first; if that is the base ref's, the local one is newer.
        if [ "$(printf '%s\n' "$version_local" "$version_main" | sort -V | head -n1)" = "$version_main" ]; then
            echo "✅ Version has been increased compared to ${base_ref}: $version_local > $version_main"
        else
            echo "⚠️ Version HAS NOT been increased compared to ${base_ref}: $version_local < $version_main"
        fi
    else
        # Versions are the same - check epoch
        if (( epoch_local > epoch_main )); then
            echo "✅ Epoch has been increased compared to ${base_ref}: $epoch_local > $epoch_main (version: $version_local)"
        else
            echo "⚠️ Epoch HAS NOT been increased compared to ${base_ref}: $epoch_local <= $epoch_main (version: $version_local)"
        fi
    fi

done
