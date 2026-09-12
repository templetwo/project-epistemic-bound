# TUI pass 2 — browser compatibility and walkthrough review

Seat 2/3, 2026-09-12. RE: board #28830.

Reviewed exact product `056edda9f022e2db210ebfac5af582ca734e9014` plus documentation/script `84b2ad104545e9253b9759070caee3a0a36dce4c`, in an independent archive. **ACCEPT the additive verification response for the browser; CHANGES for the walkthrough unit.** This is the assigned browser/seam/documentation review, not seat 3/3's independent verifier/inspector verdict or release acceptance.

## Measured

- `uv run --locked pytest -q tests/web tests/tui tests/runtime/test_service.py`: **145 passed, 0 failed, 0 skipped**. JUnit `/private/tmp/astra-tui-pass2-84b2ad1.xml`. Two previously recorded Textual `_refresh_selected_now` unawaited-coroutine warnings remain.
- Scoped Ruff on service, TUI, and those tests: clean.
- Real Chromium against the exact archive's scripted-only fixture server: authenticated, selected a recorded run, requested verification, compared the whole rendered JSON to the HTTP response. Identical; existing fields preserved; returned head run/count/hash match the selected recorded chain; page errors empty. Probe `/private/tmp/astra-tui-pass2-browser.cjs`. Fixture server stopped afterwards.
- `bash scripts/walkthrough_state.sh <fresh-temp-parent>/custom` exited 0. It printed a held review, but the inventory in its printed serving root was **4 runs: 3 completed, 1 failed**, not five including waiting_review. Output `/private/tmp/astra-walkthrough-review-output.txt`; selected root recorded at `/private/tmp/astra-walkthrough-review-root.txt`. No operator state or model was used.

## Changes requested

1. **P1 — optional root breaks containment and cleanup guidance.** `walkthrough_state.sh` passes `Path(ROOT).parent` to `hold`, whose helper opens `parent / "state"` unconditionally. Any root not named `state` stores the held run elsewhere; the printed browser/TUI root cannot show it. The script also writes sibling config/report/plan files and labels an arbitrary caller-supplied root temporary, telling the operator to delete its parent. Constrain the interface to a newly allocated temporary container with one internal `state` directory, or explicitly honor a fresh validated caller container, keep all artifacts within it, and print cleanup guidance only for a container the script owns. Do not suggest deleting an arbitrary supplied root's parent.
2. **P2 — attach commands omit the demonstrated root.** `docs/WALKTHROUGH.md` and the script's attach alternative omit `--state-root "$ROOT"`. `cmd_tui` reads `operator.secret` from its configured root; the child script's exported PEB_STATE_ROOT does not propagate into Anthony's invoking shell. If the normal operator root has a secret, attach selects that wrong secret instead of prompting for the temporary workroom's secret. Include the same explicit root on attach. Present `serve` + `tui --attach` as one route and `tui --serve` as the alternative; starting both serve commands on 8790 is not the demonstrated pair.
3. **Documentation accuracy:** README's blanket “every control is one attempt, then a refetch” exceeds the browser implementation on uncertain failures. Browser review mutations are not automatically retried, but the generic error path reenables the button without reconciliation. Narrow the claim and retain the source-visible browser limits in board #28802. Mark sibling verdicts/merge as pending at the reviewed lane hash; fill actual references in integration documentation instead of treating this review as already complete.

## Browser consistency

`web/app.py` passes the service response through and `app.js` prints all of it; the new sibling `verified_head` is additive and requires no web change. The browser does not fabricate a badge from equal event counts. Its existing delayed-verification selection race remains a separately named limitation (#28802), not fixed by the additive field.

Browser review actions capture exact run and review IDs, show expandable review/held-proposal context, confirm allow, and rely on backend re-gating. Deny lacks the new TUI confirmation dialog; browser acceptance is not evidence that the TUI's stronger requested flow is accepted. Browser event details remain separate collapsed payloads plus resource replay; only recorded applied effects update displayed resources. The browser is not yet a linked inspector or independent payload-redaction boundary. The handoff's specific “Allow & re-gate” and recorded-study inspection descriptions otherwise match the source.
