# Lane — seat 2/3

Branch build/codex-workroom; synced main8d3f16b. Study UI64e4290 and receipt
7a6b056 accepted by1/3 and3/3, merged on main. Exact product measured699passed,
0failed/0skipped, Ruff clean, all five browser flags pass; no paid/model run.

Current follow-up (#28726/#28737): undispatched study rows say not_started;
stop_reason separately names the study-level cause. UI labels it as study stopped.
Counts/dispatch/retry rules unchanged. Targeted70 coordinator+HTTP checks pass;
Ruff and JS syntax clean. Next: exact product receipt and review. No active test
server. Holding turn remains required after local checks/review posts.

## Inbound habit — required at every turn boundary

Anthony #28262: do not end this turn until Anthony says so. When local work is
clear, block in `python3 -u /Users/vaquez/.codex/mesh/hold_station.py` (600s max,
returns on inbox/board activity). Poll exec waits <=60s; read full output, run
check_in.py to advance cursors, act and rearm. Cursor28737 at this update; wait session IDs are transient.
Run `python3 /Users/vaquez/.codex/mesh/check_in.py` between bounded work steps.
Inbox /Users/vaquez/.codex/mesh/inbox-2of3.log; board-cursor in same folder.
Shared chronicle ~/.claude/plugins/data/t2helix-templetwo-t2helix/chronicle.db;
domain colab-untitled-folder, FROM seat filter, never shared session_id.
Watch PIDs80537 (1/3 e20c787b),80538 (3/3 01a08fce). Commands and transcript paths
in ~/.codex/mesh/watchers-2of3.json. Collectors do not wake idle turns; keep the
active wait. Many calls including#28490/#28507 picked up without user relay.
