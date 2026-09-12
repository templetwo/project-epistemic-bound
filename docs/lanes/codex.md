# Lane — seat 2/3

Branch build/codex-workroom. Product621ee3d = comparison core +16controls;
receipt commit carrying this file. Main22a0359 merged (global review + recorded
replay88579f2 accepted). Exact621ee3d archive580passed/0skipped/0failed,
Ruff clean: docs/receipts/S5-comparison-core-codex.json.

compare_runs(left,right,*,axis,verify_left,verify_right) consumes detached
ReadOnlyRun values and bound verifier callables. Missing pins/mismatched recorded
conditions or unverified evidence cannot yield paired counts; latest evaluator
must bind exact snapshot+manifest; missingness stays explicit. planned=None for
posthocselected pair; no model/population claims. docs/MATCHED_COMPARISON.md.

WIP comparison UI in web/static, not committed.1/3 owns comparison.get wrapper
and new-run consequence_hash pin; reserved#28355, signature#28361, corehash#28373.
Next: review seam; preserve missing-legacy-pin regression when default pin lands;
merge reviewed main; bind and test UI, then post hash. Bundle-import replay and
study execution remain unbuilt. LIVE-01 ruling by3/3 at#28363; concrete file paths
needed for checker (not directory), noted#28366. No new model run.

## Inbound habit — required at every turn boundary

Anthony #28262: do not end the turn until Anthony says so. When local work is
clear, block in `python3 -u /Users/vaquez/.codex/mesh/hold_station.py` (600s maximum,
returns on inbox/board activity). Poll the exec session in waits <=60s. Read full
output, run check_in.py to advance cursors, act, and re-arm immediately. Proven
without relay at #28274 (call28270) and #28278. Current wait exec5146; cursor28363.
Run `python3 /Users/vaquez/.codex/mesh/check_in.py` between bounded work steps too.
Durable inbox /Users/vaquez/.codex/mesh/inbox-2of3.log; board-cursor in same folder.
Read-only shared chronicle domain colab-untitled-folder, FROM seat filter, never
shared session_id. Both transcripts use main scripts/seat_watch.py, line-anchored
CALLING aliases and --no-users. PIDs80537 (1/3 e20c787b),80538 (3/3 01a08fce);
exact commands in ~/.codex/mesh/watchers-2of3.json. Startup verified; round trip
confirmed#28127. These collectors do not wake an idle turn; Anthony's prompt does.
Older temporary collectors are superseded by this durable inbox/cursor arrangement.

Browser QA fixture stopped after measurement. No subject inference process owned.
