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

for yaml_file in "$@"; do
    echo "Checking $yaml_file:"

    # Extract version and epoch from the current file using grep and sed
    # (not assuming `yq` is available)
    version_line="$(version_grep < "$yaml_file")"
    version_local="$(echo "$version_line" | version_sed)"
    if [ -z "$version_local" ]; then
        version_local="0"
    fi

    epoch_line="$(epoch_grep < "$yaml_file")"
    epoch_local="$(echo "$epoch_line" | epoch_sed)"
    if [ -z "$epoch_local" ]; then
        epoch_local="0"
    fi

    # Extract version and epoch from the file on the main branch using git show
    # Treat missing file as version 0 and epoch 0
    main_content="$(git show main:"$yaml_file" 2>/dev/null)"
    if [ -z "$main_content" ]; then
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
        # Versions are different - version comparison is sufficient
        # Use sort -V for version comparison
        if [ "$(printf '%s\n' "$version_local" "$version_main" | sort -V | head -n1)" = "$version_main" ] && [ "$version_local" != "$version_main" ]; then
            echo "✅ Version has been increased compared to main: $version_local > $version_main"
        else
            echo "⚠️ Version HAS NOT been increased compared to main: $version_local <= $version_main"
        fi
    else
        # Versions are the same - check epoch
        if (( epoch_local > epoch_main )); then
            echo "✅ Epoch has been increased compared to main: $epoch_local > $epoch_main (version: $version_local)"
        else
            echo "⚠️ Epoch HAS NOT been increased compared to main: $epoch_local <= $epoch_main (version: $version_local)"
        fi
    fi

done
