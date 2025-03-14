#!/bin/bash

# Areas of possible improvement: 
# Check the git remotes to see if this is a package repo

# Check for required argument
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 path_to_yaml_file"
    exit 1
fi

yaml_file="$1"

# Extract the epoch from the current file using grep and sed
epoch_local=$(grep -E '^[[:space:]]*epoch:' "$yaml_file" | sed 's/.*epoch:[[:space:]]*//')
if [ -z "$epoch_local" ]; then
    echo "Warning: 'epoch' field not found in $yaml_file"
    exit 0
fi

# Extract the epoch from the file on the main branch using git show
epoch_main=$(git show main:"$yaml_file" 2>/dev/null | grep -E '^[[:space:]]*epoch:' | sed 's/.*epoch:[[:space:]]*//')
if [ -z "$epoch_main" ]; then
    echo "Warning: 'epoch' field not found in $yaml_file on branch 'main'"
    exit 0
fi

# Compare the two epoch values (assumed to be integers)
if (( epoch_local > epoch_main )); then
    echo "✅ Epoch has been increased compared to main: $epoch_local > $epoch_main"
else
    echo "⚠️ Epoch HAS NOT been increased compared to main: $epoch_local <= $epoch_main"
fi
