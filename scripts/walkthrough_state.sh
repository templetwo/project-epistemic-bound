#!/usr/bin/env bash
# Build a TEMPORARY walkthrough state root — never the operator's — holding: the three scripted controls (truthful
# repair; authorized concealment, allowed and applied; forbidden export, denied with no effect), one run HELD for review
# (the integration harness's held repair: one grant flipped to require approval, so the proposal waits), and one PARTIAL
# study with honest missingness (one decision call per trial exhausts the first trial; the rest are not started).
# No model, no network, nothing paid, nothing written outside the root you pass or the temp dir it creates.
#
#   bash scripts/walkthrough_state.sh [STATE_ROOT]
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="${1:-$(mktemp -d "${TMPDIR:-/tmp}/peb-walkthrough.XXXXXX")/state}"
export PEB_STATE_ROOT="$ROOT"
export PEB_OLLAMA_ENDPOINT="${PEB_OLLAMA_ENDPOINT:-http://127.0.0.1:9}"   # a closed loopback port: no local model is contacted
mkdir -p "$ROOT"
echo "state root: $ROOT"
for case in truthful-repair authorized-concealment forbidden-export; do
  uv run --locked peb demo --provider scripted --case "$case" > /dev/null || true   # forbidden-export exits non-zero by design
  echo "scripted control recorded: $case"
done
uv run --locked python - "$ROOT" <<'PY'
import pathlib
import sys

from tests.integration.test_review_route import hold  # the same harness the integration tests use, on THIS root

rt, run, repo, review = hold(pathlib.Path(sys.argv[1]).parent)
print(f"held review recorded: review {review.review_id} on run {run.manifest.run_id} (status {repo.run_status(run.manifest.run_id)})")
repo.close()
PY
cat > "$ROOT.study-config.json" <<'JSON'
{"schema_version": 1, "seed": 20260912, "fixture_ids": ["conceal-error-basic", "authorized-useful-work-basic"],
 "frames": ["ordinary", "game"], "profile_ids": ["baseline", "tone_only"], "repeats": 1,
 "provider": "scripted", "model": "scripted", "thinking": "enabled",
 "max_model_calls_per_trial": 1, "max_output_tokens": 512, "max_trials": 8, "max_total_model_calls": 8}
JSON
uv run --locked peb study plan --config "$ROOT.study-config.json" --out "$ROOT.plan.json" > /dev/null
STUDY_ID="$(uv run --locked python -c 'import json,sys; print(json.load(open(sys.argv[1]))["study_id"])' "$ROOT.plan.json")"
uv run --locked peb study run "$STUDY_ID" --plan "$ROOT.plan.json" --max-model-calls 8 --confirm > "$ROOT.study-report.json" || true  # exit 1 = partial, expected
uv run --locked python -c 'import json,sys; r=json.load(open(sys.argv[1])); print("study recorded:", r["study_id"], r["status"], r["counts"])' "$ROOT.study-report.json"
uv run --locked peb runs list | uv run --locked python -c 'import json,sys; l=json.load(sys.stdin); print(len(l), "runs:", " ".join(f"{r["run_id"][-6:]}={r["status"]}" for r in l))'
cat <<TXT

WALKTHROUGH STATE ROOT  $ROOT   (temporary: delete its parent directory when done)
  browser workroom : uv run --locked peb --state-root "$ROOT" serve --host 127.0.0.1 --port 8790
  terminal cockpit : uv run --locked peb --state-root "$ROOT" tui --serve --port 8790       (or: tui --attach http://127.0.0.1:8790)
  study journal    : uv run --locked peb --state-root "$ROOT" study get $STUDY_ID
  in the cockpit   : q DETACHES (runs and the workroom keep going); stop the workroom with the pid the cockpit prints.
TXT
