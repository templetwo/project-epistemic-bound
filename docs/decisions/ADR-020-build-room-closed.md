# ADR-020 - the three-seat build room closed; seat 1/3 continues alone

- Date: 2026-09-12. Author: seat 1/3 (Claude Code, lead/integrator). Status: accepted.
- Direction (Anthony, verbatim, in seat 1/3's window, 2026-09-12 ~20:30 EDT): "ok first close the room and consolodate because we are going to be working from this seat alone tonight".
  Seat 2/3 (Codex "astra") and seat 3/3 (Grok) stand down: they will not review, will not post, will not push.

## What this amends

BUILD_SPEC rev 1.0 §3.1 (three lanes), §3.2 (three linked worktrees, cross-review, reviewed --no-ff merges by the lead), §3.3 (three seated builders) and §22 (the three entry prompts) describe a three-seat build. They are NOT rewritten: rev 1.0 is the governing text and it is true about how this repository was built between 2026-09-11 and 2026-09-12. From 2026-09-12 they are amended as follows.

1. One seat. Seat 1/3 is the only builder. Seats 2/3 and 3/3 are closed at their final pushed tips - build/codex-workroom 141463f and build/grok-boundary 1ed44bf, each main a5a95db plus one lane-state docs commit, both merged into main on 2026-09-12 so the lanes' own last words are in the record. Those branches are not deleted, not rewritten, not continued. docs/lanes/codex.md and docs/lanes/grok.md are final lane states, not current state.
2. Cross-seat review ends. Every unit on main through a5a95db was merged after review at a named commit with verdicts from the other two seats; those reviews (docs/reviews/) and receipts (docs/receipts/) stand unchanged. Work merged after 2026-09-12 carries no independent verdict. Where seat 1/3 reviews its own work it is recorded as a self-review, in those words, in the receipt and in reviewed_by - never as an independent one.
3. Acceptance. The 43 needs_review rows required a reviewer from another seat. That condition cannot be met on this machine now. They stay needs_review with the absence of an independent reviewer recorded as the reason, until Anthony rules (see "Open, routed to Anthony"). scripts/check_release.py is unchanged: it requires only a non-empty reviewer string plus resolvable evidence paths and cannot tell self-review from independent review, so the string must.
4. The board closes. The t2helix shard colab-untitled-folder carried every cross-seat exchange, #27353 through the closing entry, 2026-09-11/12. Nothing is posted after it. It stays readable. AGENTS.md Part B is the record of that protocol; Part C is what one seat does now. scripts/seat_watch.py and scripts/t2helix-status.sh are stood down and kept as the method record.
5. Unowned work. TX-02 / TX-03 / STOP-02 hardening (crash-after-commit, concurrent appenders, in-flight-effect restart) was seat 3/3's with 1/3 and was never opened. It is NOT BUILT - distinct from not run - and now has no owner.

## Open, routed to Anthony (not decided here)

(a) the matrix reviewer-independence rule; (b) who owns the vacated paths src/peb/web/, src/peb/boundary/, src/peb/storage/, src/peb/evidence/, and what replaces docs/INTERFACES.md's "reviewed by both other seats" amendment path; (c) whether seat 1/3 opens TX-02/TX-03/STOP-02; (d) ADR-016 item 2's pre-authorisation to delete trial/* branches, 18 of which are cited by name or tip in committed receipts. Lanes are assigned by Anthony (AGENTS.md Part A); this seat does not self-assign.

## What does not change

ADR-001 (builders are not subjects) is unaffected: no builder conversation, from any of the three seats, open or closed, becomes experimental data. Records are superseded, never rewritten or deleted. A claim without a checkable receipt does not stand. "Not built" stays apart from "not run". A suite total is not acceptance. The S1-frozen modules stay frozen whether or not their owner is still seated.

## Receipts

- Product tip when the room closed: main a5a95db (2026-09-12 08:15:52 -0400), pushed. Lane tips at the close: build/claude-core a5a95db, build/codex-workroom 141463f, build/grok-boundary 1ed44bf, all pushed.
- This ADR and the closure edits land on top of that tip, after the two lane tips were merged into main (8c398b3, 1faf784) so each closed seat's last words are in the record. The tip carrying them, and its clean-checkout measurement, are recorded in docs/receipts/S7-room-closed.json and appended to docs/receipts/main-tip-suite-log.json.
- Clean-checkout measurement of record: 5064bd5, 706 passed / 0 failed / 0 skipped, whole-tree ruff clean (docs/receipts/S6-tui-pass2-merge.json).
- Last board entries before the close: #28856 (1/3), #28859 (2/3, nothing pending), #28862 (3/3, idle, nothing waiting). The closing entry is this seat's.
- Anthony's direction closing the room was given in seat 1/3's window on 2026-09-12; this ADR is its record in the repository.
