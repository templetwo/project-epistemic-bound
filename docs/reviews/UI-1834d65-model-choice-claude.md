# SELF-REVIEW — workroom model choice and cost demotion, `1834d65`

**This is a self-review.** Seat 1/3 wrote the code under review and seat 1/3 reviewed it. The build room
closed on 2026-09-12 (ADR-020) and there is no second seat on this machine, so this verdict carries none of
the independence the sibling verdicts in this directory carry — those came from reviewers who had not written
the code. `scripts/check_release.py` cannot tell the two apart; it requires only a non-empty `reviewed_by`
string. The distinction is therefore made here, in words, and in the receipt.

Reviewed at exact commit `1834d65`, merged to `main` at `5e33917` (`--no-ff`).

## What was asked

Anthony, live in the browser workroom on the real operator root, 2026-09-12 evening, verbatim:

1. *"'Explicit model identifier' must be a drop down with the model options. how is anyone going to know what
   models are explicidly available"*
2. *"there is tooo much emphisis on 'cost' here"*, then *"keep cost estimator optional"*
3. *"make sure the deepseek model choices are validated to actual current models"*

## What was done, and why it is the smallest honest change

**(1) The names were already measured and then discarded.** `cli._probe_ollama` read every installed model
name from `/api/tags` and reported only `installed_model_count` — 29 installed on this machine, none of them
visible in the form. The fix keeps what the probe already read (`installed_models`, bounded at 200). This is
an additive field on an existing report, not a new operation, so `docs/INTERFACES.md` §15 stays at 26
operations and no amendment was needed.

**(2) The hosted catalog check adds no authority.** `runtime/bootstrap.py` already probes the provider's
`/models` before composing a hosted run and raises `provider_unavailable` on anything but `ok` (lines ~210,
~500), so an id the provider does not list is *already* refused before any paid call. All that was added is
the same check, earlier — where the operator is still choosing rather than at launch. It is opt-in
(`health.get` gains `check_hosted` / `hosted_model`, both defaulted off) because it is the one part of the
readiness report that leaves the machine, and it is an explicit button press in the UI for the same reason.
The key is read by the provider from its environment variable and is never returned, logged or displayed —
asserted in `tests/unit/test_cli_bootstrap.py`.

**(3) Cost was demoted, not removed and not beautified.** My first instinct was to make the rate inputs
clearer, which would have kept them in the operator's way. Anthony's second message corrected that, and his
third confirmed the capability must remain. The three rate fields now sit behind a closed *Optional cost
estimate* disclosure in both the run and the study form. Thinking stayed where it was (it changes what the
model does); the outbound-scope preview stayed (it is about egress, not money). **No menu of prices was
shipped**: this workroom does not verify pricing and must not assert it (ADR-017; Anthony's #28101, "dont
scimp on rigor on the count of deepseek api cost").

## What the review actually checked

- **No model is chosen for the operator.** Both menus default to *Type an exact model id*, never to a name.
  An id the workroom never saw is still enterable, so the menu narrows nothing.
- **An unreachable provider lists nothing.** `installed_models` is absent from the report entirely when the
  server does not answer, and the UI says so rather than showing a stale or invented list. Tested both ways.
- **A count is not a catalog.** `probe_hosted_catalog(cfg, None)` reports `status: "listed"` and `model: null`
  — asking for a catalog is not asking about an id, so no id is judged.
- **No hosted call by default.** A plain `health.get` contacts no hosted provider; asserted directly.
- **Live, in a real browser**, against a throwaway state root on a spare port (never the operator's): no page
  errors; the menu equals the measured list plus the escape; choosing a name puts that exact name in the start
  payload; the escape restores the exact-id field; both cost disclosures exist and start closed.

## One defect this review found in its own code

The first cut carried the previous provider's model id across a study provider change — a hosted id would
have gone into a local plan, which is a different run than the one displayed. Found by the browser check
above, not by the suite, and fixed in the same commit: an explicit id now belongs to the provider it was
chosen for. A test for the study form's provider switching does not exist at the Python layer because the
behaviour is entirely in `app.js`; it is covered by the browser harness (`tests/browser/workroom.cjs`), which
is a manual harness, not part of `pytest`. **That gap is real and is not closed by this commit.**

## Measurement

- Lane `1834d65`: 710 passed / 0 failed / 0 skipped (707 before, plus three new tests); whole-tree ruff clean.
- Tip measurement of record for `main` is in `docs/receipts/S7-model-choice-merge.json`.

## Limits of this verdict

- It is a self-review (see the header). It does not promote any acceptance-matrix row.
- The browser harness checks added here were syntax-checked and reasoned through, but the harness itself was
  **not executed** in this session (it needs a Playwright install this seat did not set up). The live checks
  reported above were performed directly through a browser instead, and that is what "verified" means here.
- `src/peb/web/` is a vacated lane under ADR-020 and this seat does not self-assign it. Anthony's direction
  is the assignment. That partly answers routed decision (b) for the web lane and nothing else.
