#!/usr/bin/env bash
# Local .deb build helper. The standard build path is GitHub Actions in a
# debian:12 container — this script is intended only for debugging.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v dpkg-buildpackage >/dev/null 2>&1; then
    echo "ERROR: dpkg-buildpackage is missing. Install build deps:" >&2
    echo "  sudo apt install build-essential debhelper dh-python \\" >&2
    echo "      pybuild-plugin-pyproject python3-all python3-setuptools \\" >&2
    echo "      devscripts fakeroot" >&2
    exit 1
fi

dpkg-buildpackage -us -uc -b

echo
echo "Built artifacts (sibling of repo dir):"
ls -1 ../reminders-gtk_*.deb ../reminders-gtk_*.changes 2>/dev/null || true
