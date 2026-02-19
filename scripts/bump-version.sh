#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 0.1.3"
    exit 1
fi

NEW="$1"

if ! [[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: version must be in X.Y.Z format (got: $NEW)"
    exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"

# pyproject.toml
sed -i "s/^version = \".*\"/version = \"$NEW\"/" "$ROOT/pyproject.toml"

# PKGBUILD
sed -i "s/^pkgver=.*/pkgver=$NEW/" "$ROOT/PKGBUILD"

# window.py (About dialog)
sed -i "s/version=\"[0-9]\+\.[0-9]\+\.[0-9]\+\"/version=\"$NEW\"/" "$ROOT/src/monique/window.py"

# README.md badge cache-bust
sed -i "s/v=[0-9]\+\.[0-9]\+\.[0-9]\+/v=$NEW/g" "$ROOT/README.md"

echo "Updated to $NEW:"
echo "  - pyproject.toml"
echo "  - PKGBUILD"
echo "  - src/monique/window.py"
echo "  - README.md (badges)"
echo ""

git -C "$ROOT" add pyproject.toml PKGBUILD src/monique/window.py README.md
git -C "$ROOT" commit -m "Bump version to $NEW"
git -C "$ROOT" tag "v$NEW"

echo ""
echo "Done! Run: git push && git push --tags"
