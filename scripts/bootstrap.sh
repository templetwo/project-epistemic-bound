#!/usr/bin/env bash
# S0 workspace bootstrap (BUILD_SPEC §4; matrix BOOT-01 / BOOT-02). Seat 1/3.
#
#   scripts/bootstrap.sh init       [reviewed paths to stage...]   # §4.1 guards + rename + git init -b main + first commit
#   scripts/bootstrap.sh worktrees                                 # §4.3 three lane worktrees (after the S1 contract commit)
#   scripts/bootstrap.sh inspect                                   # print the observed state; changes nothing
#
# Paths come from the environment so a test can run this against temporary directories:
#   PEB_SRC  (default $HOME/Desktop/untitled)                      the folder Anthony dropped the spec into
#   PEB_ROOT (default $HOME/Desktop/project-epistemic-bound)       the intended repository
#   PEB_WT   (default $HOME/Desktop/project-epistemic-bound-worktrees)
# Every unexpected state STOPs with exit 1 before anything is moved, initialized or staged. Nothing here ever
# overwrites, force-adds, deletes, creates a remote, or retries destructively. A rerun on an established repo
# inspects and reuses it.
set -euo pipefail
SRC="${PEB_SRC:-$HOME/Desktop/untitled}"
ROOT="${PEB_ROOT:-$HOME/Desktop/project-epistemic-bound}"
WT="${PEB_WT:-$HOME/Desktop/project-epistemic-bound-worktrees}"
cmd="${1:-inspect}"; shift || true

stop() { printf 'STOP: %s\n' "$*"; exit 1; }
in_repo() { git -C "$1" rev-parse --show-toplevel >/dev/null 2>&1; }

inspect() {
  printf 'SRC=%s exists=%s symlink=%s in_repo=%s\n' "$SRC" "$([ -d "$SRC" ] && echo yes || echo no)" \
    "$([ -L "$SRC" ] && echo yes || echo no)" "$( [ -d "$SRC" ] && in_repo "$SRC" && echo yes || echo no)"
  printf 'ROOT=%s exists=%s symlink=%s repo=%s remotes=%s\n' "$ROOT" "$([ -e "$ROOT" ] && echo yes || echo no)" \
    "$([ -L "$ROOT" ] && echo yes || echo no)" "$( [ -d "$ROOT/.git" ] && echo yes || echo no)" \
    "$( [ -d "$ROOT/.git" ] && git -C "$ROOT" remote | wc -l | tr -d ' ' || echo 0)"
  if [ -d "$ROOT/.git" ]; then git -C "$ROOT" status --short --branch | head -5; git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -c '^worktree ' | sed 's/^/worktrees=/'; fi
}

init() {
  if [ -d "$ROOT/.git" ] && ! [ -L "$ROOT" ]; then
    printf '%s\n' "established repo found at $ROOT; reusing it (no rename, no init, no staging)"; inspect; return 0
  fi
  [ -d "$SRC" ] || stop "expected source directory missing: $SRC"
  [ ! -L "$SRC" ] || stop "source is a symlink: $SRC"
  { [ ! -e "$ROOT" ] && [ ! -L "$ROOT" ]; } || stop "destination already exists; inspect it, do not overwrite: $ROOT"
  [ -f "$SRC/BUILD_SPEC.md" ] || stop "BUILD_SPEC.md not found in $SRC"
  if in_repo "$SRC"; then stop "source is already in a Git repository; preserve and inspect it: $SRC"; fi
  mv -n -- "$SRC" "$ROOT"
  { [ -d "$ROOT" ] && [ ! -e "$SRC" ]; } || stop "rename did not produce the expected state"
  git -C "$ROOT" init -q -b main
  if [ ! -f "$ROOT/.gitignore" ]; then
    cat > "$ROOT/.gitignore" <<'IGN'
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.peb/
state/
runs/
artifacts/
.env
.env.*
!.env.example
*.sqlite
*.sqlite3
*.db
*.db-wal
*.db-shm
*.docx
*.pdf
_sources/private/
.DS_Store
IGN
  fi
  # Stage ONLY reviewed paths (§4.2): never `git add .`; private documents stay untracked by the ignore rules
  # and by never being named here. Refuse to stage anything the ignore rules cover.
  # Validate EVERY reviewed path before staging ANY of them, so a refusal leaves the index empty.
  for p in .gitignore "$@"; do
    [ -e "$ROOT/$p" ] || stop "reviewed path does not exist: $p"
    if git -C "$ROOT" check-ignore -q -- "$p"; then stop "refusing to stage an ignored (private) path: $p"; fi
  done
  staged=0
  for p in .gitignore "$@"; do git -C "$ROOT" add -- "$p"; staged=$((staged + 1)); done
  git -C "$ROOT" commit -q -m "S0: bootstrap workspace (reviewed paths only; private documents untracked; no remote)"
  [ "$(git -C "$ROOT" remote | wc -l | tr -d ' ')" = "0" ] || stop "a remote exists; the bootstrap must not create one"
  printf 'ROOT=%s staged=%s commit=%s\n' "$(cd "$ROOT" && pwd -P)" "$staged" "$(git -C "$ROOT" rev-parse --short HEAD)"
}

worktrees() {
  [ -d "$ROOT/.git" ] || stop "no repository at $ROOT; run init first"
  git -C "$ROOT" rev-parse --verify -q main >/dev/null || stop "main has no commits yet"
  mkdir -p "$WT"
  for pair in "build/claude-core:claude" "build/grok-boundary:grok" "build/codex-workroom:codex"; do
    br="${pair%%:*}"; dir="$WT/${pair##*:}"
    if git -C "$ROOT" rev-parse --verify -q "refs/heads/$br" >/dev/null; then
      if [ -d "$dir" ] && git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null | grep -qx "$br"; then
        printf 'worktree %s already at %s; reusing\n' "$br" "$dir"; continue
      fi
      stop "branch $br exists but $dir is not its worktree; inspect, do not --force"
    fi
    [ ! -e "$dir" ] || stop "path exists without its branch; inspect, do not --force: $dir"
    git -C "$ROOT" worktree add -q -b "$br" "$dir" main
  done
  git -C "$ROOT" worktree list --porcelain
}

case "$cmd" in
  inspect) inspect ;;
  init) init "$@" ;;
  worktrees) worktrees ;;
  *) stop "unknown command: $cmd (inspect|init|worktrees)" ;;
esac
