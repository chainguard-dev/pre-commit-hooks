#!/bin/bash

# Areas of possible improvement:
# Check the git remotes to see if this is a package repo
# Exclude certain filenames like "pombump-deps.yaml", related. Probably could be done in the hook config or in the loop.

# Check for at least one argument
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 path_to_yaml_file"
    exit 1
fi

epoch_grep() {
    grep -E '^[[:space:]]+epoch:'
}

epoch_sed() {
    sed -r 's/^[[:space:]]+epoch:[[:space:]]+([0-9]+).*$/\1/'
}

for yaml_file in "$@"; do
    echo "Checking $yaml_file:"

    # Extract the epoch from the current file using grep and sed
    # (not assuming `yq` is available)
    epoch_line="$(epoch_grep < "$yaml_file")"
    epoch_local="$(echo "$epoch_line" | epoch_sed)"
    if [ -z "$epoch_local" ]; then
        echo "Warning: 'epoch' field not found in $yaml_file"
        echo ""
        continue
    fi

    # Extract the epoch from the file on the main branch using git show
    epoch_main_line="$(git show main:"$yaml_file" 2>/dev/null | epoch_grep)"
    epoch_main="$(echo "$epoch_main_line" | epoch_sed)"
    if [ -z "$epoch_main" ]; then
        echo "Warning: 'epoch' field not found in $yaml_file on branch 'main'"
        echo ""
        continue
    fi

    # Compare the two epoch values (assumed to be integers)
    if (( epoch_local > epoch_main )); then
        echo "✅ Epoch has been increased compared to main: $epoch_local > $epoch_main"
    else
        echo "⚠️ Epoch HAS NOT been increased compared to main: $epoch_local <= $epoch_main"
    fi

done
