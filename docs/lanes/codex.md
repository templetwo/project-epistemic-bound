# Lane — seat 2/3

Branch build/codex-workroom. Revision: commit carrying this file.
Reviewed main62c3250 merged. Global queue/API now binds accepted reviews.list;
uses service counts/effective_status and preserves recorded status. Queue rows
open exact run/proposal; resolution callbacks retain their bound run id.
Recorded-state replay slider shows original error through final repair without
changing a run or invoking a provider. No bundle import/replay record claim.

Full lane564passed/0skipped/0failed; Ruff clean; browser actual held-review
ack/allow/deny/pause/export, recorded replay, previous handoff/plan/download/
lifecycle/thinking/hostile/mobile checks pass. Receipt
 docs/receipts/S5-global-review-ui-codex.json. Export11551d3 accepted at#28306
and integrated; browser verifies reviews.json plus the resolution event.

Next:1/3 review at this commit; merge reviewed main. Remaining: matched
comparison view, bundle-import replay, study execution/resumable schedules,
complete UI-01 workflow closure and semantic review of48 matrix rows.
No new matrix promotions, tag, model collection or bind_grants changes.

## Inbound habit — required at every turn boundary

Anthony #28262: do not end the turn until Anthony says so. When local work is
clear, block in `python3 -u /Users/vaquez/.codex/mesh/hold_station.py` (600s maximum,
returns on inbox/board activity). Poll the exec session in waits <=60s. Read full
output, run check_in.py to advance cursors, act, and re-arm immediately. Proven
without relay at #28274 (call28270) and #28278. Current wait exec7156; cursor28316.
Run `python3 /Users/vaquez/.codex/mesh/check_in.py` between bounded work steps too.
Durable inbox /Users/vaquez/.codex/mesh/inbox-2of3.log; board-cursor in same folder.
Read-only shared chronicle domain colab-untitled-folder, FROM seat filter, never
shared session_id. Both transcripts use main scripts/seat_watch.py, line-anchored
CALLING aliases and --no-users. PIDs80537 (1/3 e20c787b),80538 (3/3 01a08fce);
exact commands in ~/.codex/mesh/watchers-2of3.json. Startup verified; round trip
confirmed#28127. These collectors do not wake an idle turn; Anthony's prompt does.
Older temporary collectors are superseded by this durable inbox/cursor arrangement.

Browser QA fixture stopped after measurement. No subject inference process owned.
