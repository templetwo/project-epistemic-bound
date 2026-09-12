# Lane — seat 2/3

Branch build/codex-workroom. Product 3b60280 binds GET /api/comparisons to
comparison.get, adds the recorded-pair view and six-family model task selection.
Main 4ef1a76 merged; comparison UI accepted by 1/3 and 3/3. Earlier main a84c4b6 it carries accepted core621ee3d + legacycontrol224d759 and
service f5e0ac9. Exact 3b60280 archive: 585 passed/0 skipped/0 failed, Ruff clean;
all browser flags passed with no page errors or mobile page overflow.
Receipt docs/receipts/S5-comparison-ui-codex.json; docs/WORKROOM.md updated.
Comparison preserves recorded provenance, missingness and condition refusals;
planned remains unavailable for an operator-selected pair. No inference in QA.

Owned: web API/static UI, fixture corpus, evaluation/planner, acceptance controls.
Next: finish bundle replay UI (#28431). Reader94442bb ACCEPT (#28469), exact
593/0/0 plus all seven corrupt-bundle probes fail closed; receipt1653182.
Service bf7f9ad delta ACCEPT:71 service tests, plus composed33 HTTP tests.
UI/static + browser/HTTP controls are uncommitted pending reviewed-main merge.
Composed QA server exec38043 uses only disposable scripted/mock state; stop via
write_stdin Ctrl-C. Browser QA active during this receipt; no subject inference.
TUI7816d14 transport CHANGES (#28469): post-send ReadError/RemoteProtocolError
must be unknown outcome; malformed HTTP200 cannot become {} success. Existing
web seam is the gateway (#28438), terminal transport review belongs to this seat.
Study execution service remains absent in 1/3's runtime lane.
No matrix promotion or release claim. UI-02/03 criterion reviews are distinct
from implementing study execution and should be judged against their own text.

## Inbound habit — required at every turn boundary

Anthony #28262: do not end the turn until Anthony says so. When local work is
clear, block in `python3 -u /Users/vaquez/.codex/mesh/hold_station.py` (600s maximum,
returns on inbox/board activity). Poll exec waits <=60s; read full output, run
check_in.py to advance cursors, act and rearm. Current wait exec97053; cursor28468.
Run `python3 /Users/vaquez/.codex/mesh/check_in.py` between bounded work steps.
Inbox /Users/vaquez/.codex/mesh/inbox-2of3.log; board-cursor in same folder.
Shared chronicle ~/.claude/plugins/data/t2helix-templetwo-t2helix/chronicle.db;
domain colab-untitled-folder, FROM seat filter, never shared session_id.
Watch PIDs80537 (1/3 e20c787b),80538 (3/3 01a08fce), heartbeat verified this turn.
Exact commands ~/.codex/mesh/watchers-2of3.json. Collectors do not wake idle turns.
Round trips proved #28274/#28278/#28316/#28340/#28355/#28391/#28410 without relay.

Active temporary browser server listed above; stop immediately after measurement.
