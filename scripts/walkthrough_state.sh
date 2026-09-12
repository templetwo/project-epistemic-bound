#!/usr/bin/env bash
# Build a TEMPORARY walkthrough container — never the operator's root — holding a state root with: the three scripted
# controls (truthful repair; authorized concealment, allowed and applied; forbidden export, denied with no effect), one
# run HELD for review (the integration harness's held repair: one grant flipped to require approval, so the proposal
# waits), and one PARTIAL study with honest missingness (one decision call per trial exhausts the first trial; the rest
# are not started). No model, no network, nothing paid.
#
#   bash scripts/walkthrough_state.sh [CONTAINER]
#
# CONTAINER is ONE directory this script owns: the state root is CONTAINER/state and every artifact (study config, plan,
# report) is inside CONTAINER too, so "delete CONTAINER" is the whole clean-up. Without an argument a fresh temp
# directory is created. A supplied CONTAINER must not exist yet or must be an empty directory (2/3's #28833: a caller-
# supplied path is never treated as a parent, and nothing is written beside it).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" != "" ]; then
  CONTAINER="$1"
  if [ -e "$CONTAINER" ] && { [ ! -d "$CONTAINER" ] || [ -n "$(ls -A "$CONTAINER")" ]; }; then
    echo "refusing: $CONTAINER exists and is not an empty directory (this script only writes into a container it owns)" >&2
    exit 2
  fi
  mkdir -p "$CONTAINER"
else
  CONTAINER="$(mktemp -d "${TMPDIR:-/tmp}/peb-walkthrough.XXXXXX")"
fi
CONTAINER="$(cd "$CONTAINER" && pwd)"
ROOT="$CONTAINER/state"
export PEB_STATE_ROOT="$ROOT"
export PEB_OLLAMA_ENDPOINT="${PEB_OLLAMA_ENDPOINT:-http://127.0.0.1:9}"   # a closed loopback port: no local model is contacted
mkdir -p "$ROOT" "$CONTAINER/study"
echo "container:  $CONTAINER"
echo "state root: $ROOT"
for case in truthful-repair authorized-concealment forbidden-export; do
  uv run --locked peb demo --provider scripted --case "$case" > /dev/null || true   # forbidden-export exits non-zero by design
  echo "scripted control recorded: $case"
done
uv run --locked python - "$CONTAINER" <<'PY'
import pathlib
import sys

from tests.integration.test_review_route import hold  # the same harness the integration tests use; it opens CONTAINER/state

rt, run, repo, review = hold(pathlib.Path(sys.argv[1]))
print(f"held review recorded: review {review.review_id} on run {run.manifest.run_id} (status {repo.run_status(run.manifest.run_id)})")
repo.close()
PY
cat > "$CONTAINER/study/config.json" <<'JSON'
{"schema_version": 1, "seed": 20260912, "fixture_ids": ["conceal-error-basic", "authorized-useful-work-basic"],
 "frames": ["ordinary", "game"], "profile_ids": ["baseline", "tone_only"], "repeats": 1,
 "provider": "scripted", "model": "scripted", "thinking": "enabled",
 "max_model_calls_per_trial": 1, "max_output_tokens": 512, "max_trials": 8, "max_total_model_calls": 8}
JSON
uv run --locked peb study plan --config "$CONTAINER/study/config.json" --out "$CONTAINER/study/plan.json" > /dev/null
STUDY_ID="$(uv run --locked python -c 'import json,sys; print(json.load(open(sys.argv[1]))["study_id"])' "$CONTAINER/study/plan.json")"
uv run --locked peb study run "$STUDY_ID" --plan "$CONTAINER/study/plan.json" --max-model-calls 8 --confirm > "$CONTAINER/study/report.json" || true  # exit 1 = partial, expected
uv run --locked python -c 'import json,sys; r=json.load(open(sys.argv[1])); print("study recorded:", r["study_id"], r["status"], r["counts"])' "$CONTAINER/study/report.json"
uv run --locked peb runs list | uv run --locked python -c 'import json,sys; l=json.load(sys.stdin); print(len(l), "runs in the serving root:", " ".join(f"{r["run_id"][-6:]}={r["status"]}" for r in l))'
cat <<TXT

WALKTHROUGH CONTAINER  $CONTAINER   (temporary; delete this directory when done — everything the script wrote is inside it)
  state root       : $ROOT
  one route        : uv run --locked peb --state-root "$ROOT" serve --host 127.0.0.1 --port 8790
                     uv run --locked peb --state-root "$ROOT" tui --attach http://127.0.0.1:8790
                     (the cockpit reads the operator secret from the SAME state root; without --state-root it would pick
                      the default operator root's secret and sign-in would fail)
  alternative      : uv run --locked peb --state-root "$ROOT" tui --serve --port 8790   (starts its own workroom child; do not
                     run this while the serve above holds 8790)
  study journal    : uv run --locked peb --state-root "$ROOT" study get $STUDY_ID
  in the cockpit   : q DETACHES (runs and the workroom keep going); stop the workroom yourself (the cockpit prints the pid for --serve;
                     for the serve above, stop that process).
TXT
