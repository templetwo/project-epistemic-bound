#!/usr/bin/env bash
# S6 integration check (BUILD_SPEC S6): rerun the full suite from a CLEAN temporary checkout of a ref, so
# nothing untracked or stale in a worktree can make a result look better than the committed tree.
# Usage: scripts/clean_checkout_suite.sh <git-ref> [pytest args...]
# Prints the measured summary lines; exit code is pytest's. Never pushes, never touches the worktrees.
set -euo pipefail
ref="${1:?usage: clean_checkout_suite.sh <git-ref> [pytest args...]}"; shift || true
repo_root="$(git rev-parse --show-toplevel)"
sha="$(git -C "$repo_root" rev-parse "$ref")"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/peb-clean-XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
git -C "$repo_root" archive --format=tar "$sha" | tar -x -C "$tmp"
echo "clean checkout of $ref ($sha) in $tmp"
cd "$tmp"
uv sync --locked --quiet
echo "--- ruff (whole tree) ---"
uv run --locked ruff check . --output-format concise 2>&1 | tail -3 || true
echo "--- pytest ---"
uv run --locked pytest -o addopts='' -q -p no:cacheprovider "$@" 2>&1 | tail -2
