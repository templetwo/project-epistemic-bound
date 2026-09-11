# Release checker + acceptance matrix review — seat 1/3 (integrator)

Reviewed: `368d4134dda461ba4d6cf691e0badfc5bf4b0d34` (implementation e09ceb0, tested unit b4b1cfb, receipt 368d413). Verdict: ACCEPT. Reviewed at 2026-09-11T18:03-0400.

Read in full at the exact hash: scripts/check_release.py, tests/unit/test_release_checker.py (14 controls), docs/ACCEPTANCE.md, docs/acceptance-matrix.json (51 rows), docs/receipts/S6-codex-release-checker.json.

Held:
- The checker fails closed: exact commit archived to a temporary directory (safe extraction filter); credential variables stripped from the environment; temporary state root and a closed loopback provider port; locked dependency install; versions recorded; whole-tree ruff and pytest with JUnit testcase records as the authority (declared aggregates are not trusted); every BUILD_SPEC §18 acceptance ID required exactly once; a `passed` row requires a named reviewer and committed in-repo evidence paths (no traversal, no absolute paths); any skip, failure, failed command, missing lint or missing pytest blocks; fresh output directory outside the repository; no model, browser, paid run, push or tag.
- The matrix is honest by construction: 44 needs_review + 7 partial, none passed, no reviewer or evidence set; candidate paths are labelled discovery aids. Prior slice ACCEPTs are not erased and not auto-promoted.
- Independent reproduction by 1/3 on the trial commit e661698 (main 9a74b3e + 368d413): 461 passed / 2 skipped / 0 failed, all six commands exit 0, release_status blocked, 52 findings — identical to 2/3's receipt for b4b1cfb.
- Trial merge: no conflicts; ruff clean.

Notes (not blocking):
- Per-command timeout is 180 s; a cold dependency cache could exceed it on the sync step and read as a blocked release. Measured fine here (warm cache).
- The two remaining suite skips are 1/3's tests (absent-boundary conditions that no longer occur on main); 1/3 replaces them with an isolated seam on its lane.
