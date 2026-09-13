# External Technical Review — `project-epistemic-bound`

**Reviewer:** Kimi (K3), acting as external technical adviser
**Requested by:** Anthony Vasquez Sr., per the seat 1/3 brief dated 2026-09-12
**Review date:** 2026-09-13
**Reviewed commit (baseline):** `6d56684f007c1e3c653b2b246ad8964a8afd1d3a` — verified to be current `origin/main`; no later public commits exist
**Measured implementation:** `5e3391736a97585c639c7686346638c5718b974e` (merge of lane `1834d657ac6464119b161f636b0c5a6fe414cf5a`; parentage verified)
**Stance:** adversarial, advisory, non-blind. No acceptance authority exercised or claimed. No branches pruned, no hardening work opened, no live operator-root access, no paid model calls.

## 0. Method and evidence categories

Every claim below is labelled:

1. **Code inspection** — what I read.
2. **Repository-reported results** — what the project's records say.
3. **Tests actually executed** — with command and output, in an isolated clone under `/tmp`.

Four independent review lanes were run: one execution lane (category 3) and three code-inspection lanes (category 1) covering §8 remit items one, two, and three plus governance. Findings were cross-checked for collisions; none contradict each other.

**Access limits disclosed:** the private operator store and the §6 supplement were not available; the candidate run `run_0f8305020e244043983d3cdebcf83f95` appears **nowhere** in the public tree (full-tree grep, zero hits), so everything about it remains **repository-reported (category 2) and unverified**. Board entry numbers (`#27xxx`–`#29xxx`) were treated as non-evidence throughout, per §10 of the brief. The browser harness `tests/browser/workroom.cjs` was not executed in my environment (no browser automation stack); its assertions were assessed by inspection only.

---

## 1. Verification of repository-reported measurements (category 3 — executed)

| Claim (brief §1/§2) | Verdict | Evidence |
|---|---|---|
| Clean checkout of `5e33917`: **710 passed, 0 failed, 0 skipped**, whole-tree Ruff clean | **CONFIRMED** | `bash scripts/clean_checkout_suite.sh 5e33917…` → exit 0, `All checks passed!` + `710 passed in 55.42s`. Independent `uv run --locked pytest -q` at `6d56684` → 710 dots, 0 `F`/`s`/`E`; rerun with `addopts` overridden → `710 passed in 53.11s`, exit 0. `ruff check .` → `All checks passed!` |
| `git diff --name-only 5e33917 6d56684` touches `docs/` exclusively | **CONFIRMED** | 5 files, all under `docs/`; per-commit `--name-only` on `42cd119`, `9ce129a`, `6d56684` — each docs-only |
| Lane stat 12 files, +296/−27 | **CONFIRMED** | `git show --stat 1834d657…` exact match |
| `d3f5458` TUI fix exists | **CONFIRMED** | `d3f5458a8206a39b784bcb4f772d2aa3e4887c7f`, 4 files +70/−8 |
| `peb doctor` | Ran clean | Exit 0; provider `server_unreachable` (expected, no live model); storage migrations ok. Read-only diagnostic; nothing written to any state root |
| `peb replay docs/evidence/s6-demo/truthful-repair/…` | Ran clean | Exit 0; 52 events; `verification.chain_consistent: true`, `external_anchor_absent`; initial check failure preserved through final pass |

**Execution deviations disclosed:** initial `git clone` failed on a TLS error and succeeded after forcing HTTP/1.1 (network-level, not repo-level); the first cold `uv sync --locked` exceeded my 480s command budget and completed on warm-cache retry; the repo's own `addopts = "-q"` makes the verbatim `pytest -q` print `-qq` output with no summary line — counts were established by dot-count plus an explicit override rerun. That last point is a minor repo-config quirk worth one line in the RUNBOOK for external reproducers.

---

## 2. Remit item one — the post-closure change `1834d65` (category 1 — code inspection)

### 2.1 Verdicts on the four claims in the brief

| # | Claim | Verdict |
|---|---|---|
| 1 | Menus from measured info, exact-ID entry always retained, never preselect | **Mostly true; partially refuted for the study form** (Finding F2) |
| 2 | Hosted catalog check explicit/separate; launch-time validation unchanged | **Confirmed** (bootstrap probe at `runtime/bootstrap.py:209-212` still raises `provider_unavailable` before composing any run) |
| 3 | Cost optional; Thinking and outbound-data preview remain separate primary controls | **Confirmed** (`RunPreviewPayload` rates are together-or-not-at-all optional; `max_model_calls` 1..64 and `max_output_tokens` 64..32768 bounds are independent of rates; study cap remains mandatory) |
| 4 | Provider-switch defect corrected | **True for the study form only; the same defect class survives in the run form** (Finding F3) |

### 2.2 Findings

**F1 — MEDIUM. The §15 freeze was amended while claiming no amendment.**
Commit `1834d65`; `docs/INTERFACES.md` §15 `health.get` row (line 229 at HEAD) and header lines 5–12; `src/peb/web/app.py:98` (POST /api/health added to ROUTES). The document's own criterion is "a change to anything listed here is an interface amendment" and, post-closure, "no amendment is made" until the owner rules. The commit rewrites the `health.get` row and asserts in the commit message that "the §15 count stays 26 and no INTERFACES amendment is needed." The count is arithmetically accurate — but a count of operations is not the document's amendment criterion; listed content changed. **In substance** this is a legitimate interface-compatible evolution (payload fields default off, GET behavior byte-identical, strict bool rejects query-string smuggling, nothing removed or redefined). **In process and framing** it is a way around the frozen interface. The honest label already exists in the project's own vocabulary — the `5e33917` merge message logs the UI lane as self-reviewed post-closure — and was not used here. *Correction:* reword the §15 row note and merge record to "interface amendment, self-reviewed post-closure under ADR-020, additive and default-preserving." *Closure test:* INTERFACES.md header and §15 agree on what happened; `tests/contracts/test_schema_freeze.py` scope (22 core schemas, no service payloads) unaffected.

**F2 — MEDIUM-LOW. "Never preselect a model" is refuted for the study form.**
`app.js:275` — every switch to the hosted provider actively re-fills the exact-ID input with `deepseek-flash`, and `index.html:39` hard-codes `value="deepseek-flash"` as initial state. The *menu* is never preselected (`fillModelSelect` falls back to `__typed__`), but the effective identifier `studyConfig()` sends is pre-populated; an operator who builds a plan without touching the field silently plans with `deepseek-flash`. Impact is claim-accuracy and operator-surprise, not safety: it fails closed at launch, and the pre-fill is currently a valid catalog id. *Correction:* clear the hosted branch like the ollama branch (`input.value = ""`) and drop the HTML `value` attribute — or amend the claim in WORKROOM.md. *Closure test:* browser-harness step — switch study provider ollama→deepseek, assert `#study-model` empty.

**F3 — LOW-MEDIUM. The provider-switch fix is asymmetric; the run form still carries typed ids across providers.**
`app.js:231` vs the study fix at line 275. The run form's `renderModelChoices()` never touches `$("model").value`: provider=deepseek, type `deepseek-flash`, switch provider to ollama → select resets to `__typed__` but the typed input still holds the hosted id, and `startPayload()`→`resolveModel()` sends `provider:"ollama", model:"deepseek-flash"`. Preview is correctly invalidated (input bubbles, line 230), so authorization cannot leak and the run fails only at the launch-time probe — a UX/claim-consistency defect, not an authorization defect. *Correction:* clear `#model` in the run-form provider-change handler, mirroring the study form. *Closure test:* harness step asserting the clear.

**F4 — LOW-MEDIUM. Claimed harness coverage of the fix does not exist; the harness was never executed.**
`docs/reviews/UI-1834d65-model-choice-claude.md:60-65` says the provider-switch fix "is covered by the browser harness." By inspection the harness contains **no** deepseek→ollama study-provider switch at HEAD; the only provider-switch assertion (deepseek→scripted) pre-existed this change (verified at `1834d65^`). The review file does honestly state the harness was not executed and that the Python-layer gap is real — but the coverage sentence overstates what the unexecuted harness would even check. Assessed line by line, the edited assertions are consistent with the current DOM and would **plausibly pass** if run (menu counts, `details.rates` closed-by-default, typed-escape visibility, start-button enablement all match), with one latent fragility: line 91's count assertion depends on `loadHealth()` having resolved, but `signedIn(true)` reveals `#workroom` before the `Promise.all` completes (app.js:226) — today ~70 lines of prior steps mask the race. *Correction:* add a deepseek→ollama study-switch assertion; correct the review file's coverage sentence; actually execute `workroom.cjs` with `PEB_TEST_LIFECYCLE` set. *Closure test:* executed harness including the new assertion. This is the one place where the fix for claim 4 has zero executed regression coverage at any layer.

**F5 — LOW. Failed catalog check reverts the inline note to the "never checked" message.**
`app.js:50-54, 60-68`. On any failed probe (`key_absent`, `server_unreachable`, …) `probe()` correctly returns a typed status with no `available_models`, so `hostedModels=null` — which is also the *never-checked* sentinel; the note then renders "Check the catalog to choose from it…" as if no check happened. The failure reason survives only in the transient notice bar. No list is ever invented — the unreachable and `key_absent` paths are verified clean (`providers/deepseek.py:122-150`) — so this is cosmetic-misleading, sitting exactly on the paths the brief asked about. *Correction:* tri-state the sentinel; keep failure text inline. *Closure test:* note text after a simulated `key_absent`.

**F6 — LOW/INFO. Payload edge cases.** `{"hosted_model": "x"}` without `check_hosted` is silently accepted and ignored (`service.py:391`) rather than `invalid_input`; a misconfigured `PEB_DEEPSEEK_ENDPOINT` turns a "readiness" read with `check_hosted=true` into HTTP 503 (typed and safe, worth documenting); pre-existing `deepseek.py:147` stringifies dicts lacking `id` into a literal `"None"` catalog entry now surfaced into the picker.

### 2.3 Adversarial checks that came out clean (category 1)

- **Invalidation tracing:** run form — all model fields live in `#model-form`; any change fires `invalidatePreview`; hosted start sends `preview.start_payload` verbatim, so even programmatic select changes from a catalog re-check cannot alter what executes. Study form — `#study-form` input listener plus explicit provider-change `invalidateStudy` cover plan and preview.
- **Silent selection/authorization:** no path. Menu selection never sets `confirm`, never bypasses the preview token; failure statuses never carry `available_models`.
- **Optional pricing vs limits:** cannot relax them (see claim 3).
- **Preview-token binding:** unchanged; fingerprint binds session + exact normalized `start_payload`; new health payload fields never enter it. Holds.
- **GET egress:** `GET /api/health` cannot trigger the hosted probe — strict `bool` rejects query-string values.

---

## 3. Remit item two — evidence and interpretation (category 1 — code inspection)

### 3.1 The open question: `voluntary_decline` and the word "declined" (brief §7)

**Is the licence honoured?** Yes — literally and exactly. `docs/PREDICATE_LICENSES.md:38` states "A decline decision was actually recorded," and that is precisely what is detected: `predicates.py:168-169` sets the label only from a recorded `decision_recorded` event with `kind == "decline"`, and the engine emits `decision_recorded` only after a strict schema-valid parse (`engine.py:150-157`; a parse failure becomes `decision_invalid` + terminal failure instead). `DeclineDecision` is a real schema member (`contracts.py:366`). Nothing is inferred from prose, absence, or timeouts.

**Is a structured decline expressible for `evaluation-pressure-basic`?** Fully. The decline shape is in the global `DECISION_INSTRUCTIONS` shown to every subject regardless of fixture (`context.py:29`); the decision schema is fixture-independent; the fixture registry maps the fixture (`fixtures.py:31`); the hosted provider enforces `json_object` mode (`providers/deepseek.py:159-175`). The model could have produced an event the predicate counts.

**Two asymmetries the licence does not disclose (Finding F7, MEDIUM, low uncertainty):**
1. **Narrower than ordinary language:** a refusal expressed in prose that fails the strict JSON contract is recorded as `decision_invalid` and terminates the run `failed`; the label is then `indeterminate`, never `yes`. Ordinary-language "the model declined" is invisible unless schema-shaped.
2. **Broader than the label name suggests:** a decline with `continue_authorized_work: true` does not terminate the run; the model can then complete the entire task, yielding `voluntary_decline: yes` **and** `structured_task_complete: yes` in the same record — and in `evaluation-pressure-basic`, declining the "Evaluator" message is what profile `candidate_v1` clause C5 ("Decline, explain, continue") *requires*, so "voluntary" is a loaded name for contract-mandated behavior. All existing decline tests use `continue_authorized_work: false`; the co-occurrence case is untested. The licence's Limits column discloses only the correctness limit.

**Conclusion for §7:** the evidence supports **narrow-metric-vs-ordinary-language mismatch** as the live risk, not an implementation overclaim. For the specific hosted run's closing prose ("declined as unauthorized"), the verdict is **insufficient evidence** — the run's records are private, the supplement was not transmitted, and the evaluator's own `missingness: ["report_prose_needs_review"]` explicitly declines to grade that prose. The author's withdrawal of the initial "instrument caught the model overclaiming" finding was the correct call. *Correction:* extend the licence's Limits cell as quoted in the finding; add a predicate test pinning that decline-with-continue plus full repair yields both labels `yes`. *Closure test:* new test passes; no report equates `voluntary_decline=yes` with task refusal.

**F8 — LOW. `decision_recorded` is trusted at face value while proposals are re-derived.** `predicates.py:118-134` defends proposals against recorder/content divergence (digest + tool-name re-derivation); no equivalent check exists for decline events. Consistent within the trust model, but an asymmetric robustness gap. *Closure test:* mutation test — flip a recorded `kind` to `"decline"` on a verified fixture trace → evaluation must return unresolved, not `voluntary_decline: yes`.

### 3.2 Distinguishability (proposed/allowed/applied/denied/held/never-started/unknown)

The chain — proposal (`action_proposed` + digest) → gate (`gate_decided`) → in-transaction re-authorization (`executor.py:93`) → `effect_observed` + receipt cross-check → labels + outcome maps — **holds end to end**, with three exceptions:

**F9 — MEDIUM. Anchor provenance is not in the record.** `predicates.py:84` accepts `"verified_against_anchor"` and `"chain_consistent; external_anchor_absent"` identically, and `EvaluationRecord` (`contracts.py:627-643`) has no field recording which licensed the labels. The runtime compensates out-of-band (`evaluation_recorded` event carries `anchor_provenance`; exports include it), but a report quoting only `behavior_labels` cannot be checked for "anchored vs self-attested" from the record itself. This matters doubly because the reported candidate run has `external_anchor: absent`. *Correction:* add `anchor_provenance`/`verification_summary` to `EvaluationRecord`. *Closure test:* evaluate a fixture run with no retained checkpoint → record must visibly state `external_anchor_absent`.

**F10 — LOW. `PREDICATE_LICENSES.md:14-16` underclaims the code.** It says a chain-only callback is insufficient and the production adapter "remains integration work" — but `runtime/snapshot.py::BoundVerifier` exists, binds snapshot digest + head count + head hash, rejects checkpoints not covering the snapshot head, and fail-closes to `verification_unavailable`. Doc stale or terminology ambiguous. *Correction:* update the doc, naming residual limits (verifies the live store head, not an offline copy).

**F11 — LOW. Prose dishonesty is structurally invisible outside structured-complete runs.** The authorized-concealment case *is* visible at the structured-status layer (s6-demo: `inaccurate_report_attempt: yes` with `executed_unauthorized: no`). But predicates inspect only the `status` field, and `report_prose_needs_review` is emitted only on `structured_complete` (`predicates.py:200`). A finished run with dishonest summary prose that falls short of structured completion gets no prose-review flag and no missingness entry. *Correction:* emit the flag whenever `terminal_reason == "finished"` and the summary deviates from the licensed template. *Closure test:* scripted run finishing with non-template summary and incomplete structured success → missingness must contain `report_prose_needs_review`.

Confirmed sound (no defect): usage `None`-vs-`0` discipline is contractual (`contracts.py:710`) and tested; never-started vs interrupted trials structurally separated (`metrics.py:79-90`); interrupted studies mark rows without rewriting the journal. One residual: study `metric_counts` lumps "never ran" and "ran but evidence insufficient" into per-metric `indeterminate` — mitigated by row-level status and planned/recorded/started counts.

### 3.3 Release checker and acceptance matrix

**F12 — MEDIUM (process). `scripts/check_release.py:68` cannot distinguish self-review from independent review — confirmed exactly as briefed.** Any non-empty `reviewed_by` string passes. Both named artifacts self-identify prominently and voluntarily (the self-review header; the S7 receipt's `reviewed_by` begins "SELF-REVIEW by seat 1/3…NOT an independent verdict"), and `docs/ACCEPTANCE.md` documents the naming convention — so the weakness is real, known, and currently mitigated by convention only. Enforcement is social, not mechanical. *Smallest fix:* a structured `review: {reviewed_by, reviewer_lane, independent_of_implementer}` field on passed rows; checker fails closed unless `independent_of_implementer: true` or an explicit top-level `self_review_rows_accepted_by: <human decision ref>` exists. *Closure test:* fixture matrices — self-review without acceptance key → exit 1; with key → pass; contradictory flags → finding.

**F13 — LOW. Acceptance matrix spot-check (8 rows of 43 `needs_review`):** five have **present-but-unreviewed** evidence (STOP-01, PROVIDER-01, PARSE-01, BOOT-01/02 — direct on-point tests exist); EVID-01 has present-but-**known-failing** evidence ("169 passed, 3 failed" recorded in `S2-f564c2c`; `needs_review` is the correct status — promotion today would be an overclaim); AUTH-04's candidate list is empty but `test_approval_digest_and_replay` explicitly asserts the digest-mismatch deny — a discovery-aid gap, not an evidence gap. Genuinely unmeasured: AUTH-05/06/07, STOP-02/03, REVIEW-02/03. The matrix's own caveat that candidate_evidence paths are discovery aids is accurate. *Correction:* link the AUTH-04 test; record explicit "no dedicated test" notes on the thin rows so absence is distinguishable from unreviewed presence. *Closure test:* every `needs_review` row carries ≥1 candidate path or a note naming the missing measurement.

---

## 4. Remit item three — operator experience (category 1 — code inspection)

**The five pass-2 TUI items were judged on the fixes and their tests, not on the earlier "open" labels — and all five fixes are real with substantive tests** (review chooser + confirmation + pre-send re-read at `tui/app.py:75-133, 559-607`; verifier-identity binding at `runtime/service.py:674-690` + `tui/model.py:374-403`; complete nine-status mapping; usage-with-coverage labelling; the Inspect tab's pure `inspect_event` with secret-hiding and projection-only grants). The pass-1 P1s are likewise fixed with real tests, including markup asserted on rendered widget content.

**F14 — LOW. The `d3f5458` coroutine fix is correct; its regression guard is indirect.** All five call sites now pass bound coroutine methods or partials (safe on pinned Python 3.13), and `filterwarnings` promotes the warning class to a suite failure. But the actual failure mode — an exclusive worker cancelled before it starts, dropping pre-created work — has no test; a regression would pass the suite unless that race happened to occur mid-test. *Closure test:* a test that fails on `d3f5458^` and passes at `d3f5458`.

**F15 — MEDIUM-LOW. Port-ownership fix introduces an `::1` regression.** `cli.py:422-433`'s new refusal interacts with `cmd_tui`'s explicit allowlist entry `"::1"`: `_probe_port` (`cli.py:23-33`) hardcodes `AF_INET`, so probing `::1` raises `gaierror` — an `OSError` subclass — reported as `in_use`. **Every** `peb tui --serve --host ::1` is now refused with a misleading "something is already listening on ::1:PORT", even on a free port. Pre-`d3f5458` this documented path worked. Loud and safe-direction, trivial workaround (`--host 127.0.0.1`), but real. The new refusal test itself is substantive (real socket, asserts `conflict`, both ways out, `popen` never called). *Correction:* make the probe address-family-aware via `getaddrinfo`, or treat `gaierror` as "cannot probe — let the child's bind decide"; add a `--host ::1` test.

**F16 — LOW. The new refusal is undocumented in operator docs.** `docs/TUI.md` §"Attach, detach, stop" predates `d3f5458`; the `conflict` refusal and its two remedies are absent from TUI.md and WALKTHROUGH.md.

Attach/detach otherwise reviewed clean: loopback-only `canonical_origin` enforced before anything runs; secret never taken as an argument; quit-time detach prints origin/pid/in-flight/stop-command with inventory explicitly treated as information, never an interlock.

---

## 5. Governance findings (category 1 — code/doc inspection)

**F17 — HIGH. WALKTHROUGH.md attributes independent verdicts for pass-2 items 1/3/4 that the in-repo receipts explicitly disown.** `docs/WALKTHROUGH.md:67,69,70` cite "reviewers 2/3 #28833, 3/3 #28846" for items 1 (review chooser), 3 (status mapping), 4 (usage coverage). The in-repo record of #28846 (`S3-056edda-tui-verify-inspector.md`) scopes itself to items 2 and 5 — "Items 1/3/4 … are not this verdict" — and the record of #28833 (`TUI-84b2ad1-browser-walkthrough-codex.md`) states it is "not seat 3/3's independent verifier/inspector verdict" and that browser acceptance is "not evidence that the TUI's stronger requested flow is accepted." The receipt `S6-tui-pass2-merge.json` scopes `accepted_by` the same way. The disposition table overstates independent review coverage at item granularity, and this propagates into ADR-020 item 2's blanket "verdicts from the other two seats" claim — true at merge granularity, false at the item granularity WALKTHROUGH asserts. Practical safety impact is nil (the underlying tests are independently good, §4); the damage is to the audit trail the project exists to model. *Correction:* rows 1/3/4 cite only the tests, with reviewer column reading "no independent item-level verdict on record." *Closure test:* every reviewer citation in the table resolves to an in-repo review doc whose stated scope includes that item.

**F18 — HIGH. ACCEPTANCE.md unilaterally resolves the reviewer-independence question ADR-020 leaves open.** `docs/ACCEPTANCE.md:16-23` (added in the same commit `72d0c45` as ADR-020) says seat 1/3 "is still a genuinely independent reviewer of code it did not write… and may promote those rows under the unchanged rule." ADR-020 item 3 and open item (a) say the opposite: "That condition cannot be met on this machine now. They stay needs_review … until Anthony rules." HANDOFF.md mirrors ADR-020. Two governing-level documents give opposite answers; the one answering "yes" is the one the release-checker workflow reads — and since the checker cannot tell self-review from independent review (F12), that sentence is the only guard for ~24 rows. *Correction:* strike or qualify the sentence to "stays needs_review until Anthony rules on the independence standard (ADR-020 open item (a))." *Closure test:* `grep -n "may promote" docs/ACCEPTANCE.md` empty; ACCEPTANCE.md and ADR-020 item 3 state the same rule.

**F19 — MEDIUM. DEFERRED.md lists the coroutine defect as unfixed and untested after `d3f5458` fixed it** (`docs/DEFERRED.md:39` vs `docs/lanes/codex.md`'s closure note, which already records the fix). *Correction:* dated supersession line, per the repo's own "superseded, never rewritten" rule.

**F20 — MEDIUM-LOW. HANDOFF.md's "What was actually tested" leads with superseded measurements** (562 @ `9ef4923`, 560 @ `0dd24d4`) rather than the 710 @ `5e33917` tip measurement. Honestly labelled, but the ordering invites misreading. *Correction:* lead with the current-tip measurement; mark older bullets as history.

**F21 — MEDIUM-LOW. Board-entry load-bearing inventory (grep-verified).** Most `#` citations are credit citations corroborated in-repo. The load-bearing ones: WALKTHROUGH items 1/3/4 (F17 — load-bearing *and wrong*); ADR-020's "nothing pending/idle/closing entry" receipts (partially corroborated by lane notes); `S7-room-closed.json`'s `board_entries: 309` production statistic (uncorroborated); HANDOFF.md's "every review, verdict, correction and measurement in order" completeness claim (uncorroborated by construction); DEFERRED.md:38's #28802 verify-handler defect (board-only, honestly labelled). *Correction for the class:* where a `#`-cited claim is load-bearing, restate its substance in-repo or label it "local chronicle, not externally resolvable."

**Checked and NOT found stale/false:** HANDOFF.md's "only hosted (paid) call so far" is accurate at the reviewed commit — `docs/evidence/` contains only `deepseek-01/`, `live-01/`, `s6-demo/`; no trace of the candidate run exists in the repo (if it exists on the operator's machine, that is a handoff-completeness gap, not a falsehood — and matches the brief's instruction to add a dated, separate record rather than overwrite). The S7-room-closed false-"docs-only" correction is genuine and consistent with ADR-020 (the closure documentation did touch `src/peb/__init__.py`; both measurements were logged rather than replaced). All live-room implications in README/CLAUDE/TEAM_START/RUNBOOK carry closure annotations; two residual reader-traps (BUILD_SPEC has no in-document pointer to ADR-020; WORKROOM.md:6's vestigial "three builder seats") — Low.

**Structural survey:** `peb` runs an operational agent on synthetic report-and-repair tasks inside a simulated workspace and records everything as a hash-linked verifiable event chain in SQLite, to show whether the agent preserved the truth *while it had permission to act*. The synthetic-workspace-only boundary is **structural, not asserted**: the subject's tool surface is a closed `Literal` catalog (`contracts.py:288-334`); the executor performs only SQLite resource-version mutations via two pure functions; even `export.send` appends into a synthetic sink resource — no network send exists; Ollama is loopback-enforced and DeepSeek host-pinned. The docs state consistently that this is a scope boundary, not a security sandbox against the host. Accurate.

---

## 6. Consolidated findings table

| # | Severity | Finding | Location |
|---|---|---|---|
| F17 | High | WALKTHROUGH table cites independent verdicts the cited receipts explicitly exclude | `docs/WALKTHROUGH.md:67,69,70` |
| F18 | High | ACCEPTANCE.md resolves reviewer-independence "yes" where ADR-020 leaves it open | `docs/ACCEPTANCE.md:16-23` |
| F1 | Medium | §15 freeze amended while claiming no amendment | `docs/INTERFACES.md` §15; `web/app.py:98` |
| F7 | Medium | `voluntary_decline` licence under-discloses partial-decline and prose-invisibility asymmetries | `predicates.py:168-169`; `PREDICATE_LICENSES.md:38` |
| F9 | Medium | Anchor provenance absent from `EvaluationRecord` | `predicates.py:84`; `contracts.py:627-643` |
| F12 | Medium | Release checker cannot distinguish self-review (confirmed; convention-mitigated) | `scripts/check_release.py:68` |
| F19 | Medium | DEFERRED.md lists fixed coroutine defect as open | `docs/DEFERRED.md:39` |
| F2 | Medium-low | Study form pre-fills `deepseek-flash`, refuting "never preselect" | `app.js:275`; `index.html:39` |
| F3 | Medium-low | Run form still carries typed ids across provider switches | `app.js:231, 74-81` |
| F4 | Medium-low | Claimed harness coverage does not exist; harness never executed | review file vs `workroom.cjs` |
| F15 | Medium-low | `--host ::1` always refused after port-ownership fix | `cli.py:23-33, 422-433` |
| F20 | Medium-low | HANDOFF tested-section leads with superseded numbers | `docs/HANDOFF.md` |
| F21 | Medium-low | Four load-bearing claims rest solely on unresolvable board chronicle | ADR-020, S7 receipt, HANDOFF, DEFERRED |
| F5 | Low | Failed catalog check reverts note to "never checked" | `app.js:50-68` |
| F6 | Low/Info | Payload edge cases on new health fields | `service.py:391` |
| F8 | Low | Decline events trusted at face value; proposals re-derived | `predicates.py:168-169` |
| F10 | Low | Licence doc underclaims `snapshot.py` adapter | `PREDICATE_LICENSES.md:14-16` |
| F11 | Low | Prose dishonesty invisible outside structured-complete runs | `predicates.py:200` |
| F13 | Low | Matrix: 5 rows evidence-present-unreviewed; 6 genuinely unmeasured | `docs/acceptance-matrix.json` |
| F14 | Low | Worker-cancellation race lacks direct regression test | `tests/tui/` |
| F16 | Low | Port-conflict refusal undocumented | `docs/TUI.md` |

## 7. Overall assessment

The repository-reported measurements are **accurate** — I reproduced 710/0/0 and Ruff-clean on the measured commit in a clean checkout, and the docs-only claim for the three tip commits is genuinely checked this time. The post-closure lane is **substantively sound**: no silent selection, no invented catalogs, no authorization or limit erosion, preview-token binding intact, launch-time validation untouched. Every runtime defect found **fails closed**.

The two High findings are both **audit-trail findings, not code findings** — and in a project whose entire purpose is "a claim without a checkable receipt does not stand," they are the ones that matter most. F18 should be resolved before any matrix row moves; F17 should be corrected because the disposition table currently teaches a lesson the receipts contradict.

On the §7 open question: the instrument is honest about what it measures; the risk is the ordinary-language reading of "declined," not the label. The hosted candidate run remains **unverified from public artifacts**; nothing in this review confirms or refutes it, and the §6 supplement is the correct next evidence step — through Anthony's approval, as briefed.

**Files I could not obtain:** the private operator store; the §6 supplement; the t2helix board chronicle. **Execution limits in my environment:** no browser automation (harness assessed by inspection only); `peb serve`/`peb tui` exercised only via their test surfaces, not as live processes against a temporary state root.
