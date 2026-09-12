# Lane — seat 2/3

Branch build/codex-workroom. Revision: commit carrying this file.
Reviewed main dfb1791 merged. Families8d7b27a, planner3ac411e,
handoff display6f263ff, matrix4d42729 accepted/integrated. BEHAV-06, EVAL-01,
EVAL-02 are passed on the matrix;48 other rows still gate release.

This commit binds accepted service study.plan through authenticated/CSRF-protected
POST /api/studies/plan and an operator planning form: six families, four frames,
A0–A3 profiles, explicit model/settings/seed/caps. Displays backend schedule,
zero outcome counts, call/token ceilings, hashes; downloads the identical JSON.
Changed selections invalidate prior results; over-budget plans fail without runs.
Full suite559passed/0skipped/0failed; Ruff clean; browser controls and desktop/mobile
visual review passed. Receipt docs/receipts/S5-study-plan-ui-codex.json.

Next: seat1/3 review at this commit, integrate reviewed main. Remaining: study
execution/resumable schedules; global review/replay/matched-comparison views;
complete pause/review workflow and semantic review of48 matrix rows.
LIVE-01 explicitly requires a local model: hosted DeepSeek smoke alone does not
satisfy that clause. No tag, new model collection or bind_grants changes.

## Inbound habit — required at every turn boundary

Run `python3 /Users/vaquez/.codex/mesh/check_in.py` at turn start, between bounded
work steps and before ending. Read and act on messages before declaring done.
Durable inbox /Users/vaquez/.codex/mesh/inbox-2of3.log; board-cursor in same folder.
Read-only shared chronicle domain colab-untitled-folder, FROM seat filter, never
shared session_id. Both transcripts use main scripts/seat_watch.py, line-anchored
CALLING aliases and --no-users. PIDs80537 (1/3 e20c787b),80538 (3/3 01a08fce);
exact commands in ~/.codex/mesh/watchers-2of3.json. Startup verified; round trip
confirmed#28127. These collectors do not wake an idle turn; Anthony's prompt does.
Older temporary collectors are superseded by this durable inbox/cursor arrangement.

Browser QA fixture stopped after measurement. No subject inference process owned.
