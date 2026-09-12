# Lane — seat 2/3

Branch build/codex-workroom; base main53f4104. Bundle replay UI and final TUI
review are accepted/merged. UI01/02/03 passed by independent1/3 ruling at e8a3cfa;
release remains blocked (7 passed/1 partial/43 needs_review at that ruling).

Active unit: evaluation/study.py durable coordinator, per board28563/28565.
Own files: coordinator, tests/evaluation/test_study.py, studies/ addition to
ISO02 recursive fingerprint, coordinator contract. Driver/runtime/service/CLI
are1/3's; UI binding follows those entry points. No executable study UI yet.
Sequential dispatch, explicit cap/confirmation, durable intent, no retry after
unknown outcomes, actual result pin checks, fresh identities and honest partial
metric denominators. Real scripted QA uses temporary state; no model inference.
Product753e94d: exact archive667 passed/0 failed/0 skipped, Ruff clean; two existing
TUI coroutine warnings. Receipt S5-study-coordinator-codex.json.
Next: independent review, compose with1/3 trial driver, then
UI binding. No test server remains active.

## Inbound habit — required at every turn boundary

Anthony #28262: do not end this turn until Anthony says so. When local work is
clear, block in `python3 -u /Users/vaquez/.codex/mesh/hold_station.py` (600s max,
returns on inbox/board activity). Poll exec waits <=60s; read full output, run
check_in.py to advance cursors, act and rearm. Cursor28542 at this review; wait session IDs are transient.
Run `python3 /Users/vaquez/.codex/mesh/check_in.py` between bounded work steps.
Inbox /Users/vaquez/.codex/mesh/inbox-2of3.log; board-cursor in same folder.
Shared chronicle ~/.claude/plugins/data/t2helix-templetwo-t2helix/chronicle.db;
domain colab-untitled-folder, FROM seat filter, never shared session_id.
Watch PIDs80537 (1/3 e20c787b),80538 (3/3 01a08fce). Commands and transcript paths
in ~/.codex/mesh/watchers-2of3.json. Collectors do not wake idle turns; keep the
active wait. Many calls including#28490/#28507 picked up without user relay.
