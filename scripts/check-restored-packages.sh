#!/bin/bash
set -e

# Check if restored-packages.txt is being modified
if ! git diff --cached --name-only | grep -q "restored-packages.txt"; then
    exit 0
fi

if [ ! -f "withdrawn-packages.txt" ] || [ ! -f "restored-packages.txt" ]; then
    exit 0
fi

# Get the new lines being added to restored-packages.txt
NEW_PACKAGES=$(git diff --cached "restored-packages.txt" | grep "^+" | grep -v "^+++" | sed 's/^+//' | grep -v '^$' | grep -v '^#')

if [ -z "$NEW_PACKAGES" ]; then
    exit 0
fi

# Check if any new packages are in withdrawn-packages.txt
CONFLICTS=""
while IFS= read -r package; do
    if [ -n "$package" ]; then
        if grep -Fxq "$package" "withdrawn-packages.txt"; then
            CONFLICTS="${CONFLICTS}${package}\n"
        fi
    fi
done <<< "$NEW_PACKAGES"

if [ -n "$CONFLICTS" ]; then
    echo "ERROR: The following packages are being added to restored-packages.txt but are still present in withdrawn-packages.txt:"
    echo -e "$CONFLICTS"
    echo "Please remove these packages from withdrawn-packages.txt first, then commit again."
    exit 1
fi

exit 0
