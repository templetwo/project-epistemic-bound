# Lane — seat 2/3

Branch build/codex-workroom, synced to main a5a95db at closure (#28856).
All current units are accepted by both reviewers and merged: coordinator753e94d,
runtime driver/preview19d6d28, study UI64e4290, wording follow-up9a57144.
TUI pass 2 product 056edda and corrected walkthrough d72daea are now merged too.
Seat 2/3 receipts 1c70bb3 (browser ACCEPT, initial walkthrough CHANGES) and
7d934ae (corrected walkthrough ACCEPT) are carried by main a5a95db.
No product edit, review verdict or integration request is pending from this lane.

Latest own review evidence: exact 84b2ad1 passed 145 web/TUI/runtime-service
checks (zero failures/skips), scoped Ruff clean, real Chromium verified that
verified_head passes through HTTP and renders literally with the existing fields
preserved and no page errors. Exact d72daea custom-container demonstration:
five runs in the serving root, partial study 8 planned / 1 dispatched / 1 recorded;
all artifacts contained; reuse refused exit 2 without file changes; attach root
explicit. Product/tests unchanged in d72daea; no redundant suite rerun claimed.
1/3 reports integrated 5064bd5 measured 706 passed, zero failures/skips; a5a95db
adds integration documentation. Browser limits at board #28802 remain: delayed
verification lacks a selection guard; separate event payloads are not a linked
inspector; uncertain review responses require operator reconciliation.

Exact9a57144 measured699passed/0failed/0skipped, whole-tree Ruff clean, study
browser passed with no page errors/mobile overflow. Exact64e4290 additionally
passed all five browser flags. Receipts S5-study-coordinator-codex.json,
S5-study-execution-ui-codex.json, S5-study-missingness-wording-codex.json.
Two pre-existing TUI unawaited-refresh coroutine warnings remain documented.
All study launches in QA were scripted; hosted preview only, no paid/model run.
No temporary test server remains active. Release rows remain7passed/1partial/
43needs_review; no tag. Operator-root studies and paid studies await Anthony's
own direction. Next action: remain in the active inbound wait and handle calls.

## Inbound habit — required at every turn boundary

Anthony #28262: do not end this turn until Anthony says so. When local work is
clear, block in `python3 -u /Users/vaquez/.codex/mesh/hold_station.py` (600s max,
returns on inbox/board activity). Poll exec waits <=60s; read full output, run
check_in.py to advance cursors, act and rearm. Cursor 28856 at this update; wait session IDs are transient.
Run `python3 /Users/vaquez/.codex/mesh/check_in.py` between bounded work steps.
Inbox /Users/vaquez/.codex/mesh/inbox-2of3.log; board-cursor in same folder.
Shared chronicle ~/.claude/plugins/data/t2helix-templetwo-t2helix/chronicle.db;
domain colab-untitled-folder, FROM seat filter, never shared session_id.
Watch PIDs80537 (1/3 e20c787b),80538 (3/3 01a08fce). Commands and transcript paths
in ~/.codex/mesh/watchers-2of3.json. Collectors do not wake idle turns; keep the
active wait. Many calls including#28490/#28507 picked up without user relay.
