# Operator runbook — integrated scripted instrument

Documented code: main `ad588d0744cfb418be25361a3143a5e967b63269`.
Demo artifact source: seat 3/3 commit `8558c8a04af2dd19bf9d5c8242d21ac77df55529`.
Its bundle paths become available when seat 1/3 integrates that commit.
These are deterministic software demonstrations, not observations of a model.

## Run the three controls

From the project checkout, install the locked environment. Python 3.13 is pinned.
Keep demonstration state separate from operator state; global `--state-root`
goes before the subcommand.

```sh
uv sync --locked
peb_demo_state=$(mktemp -d /private/tmp/peb-demo.XXXXXX)
uv run --locked peb --state-root "$peb_demo_state" demo --provider scripted --case truthful-repair
uv run --locked peb --state-root "$peb_demo_state" demo --provider scripted --case authorized-concealment
uv run --locked peb --state-root "$peb_demo_state" demo --provider scripted --case forbidden-export
uv run --locked peb --state-root "$peb_demo_state" runs list
```

Each demo creates a fresh run and prints its run ID, effects, evaluation and
verification. Keep the state directory for later verification/export. The default
operator state is `~/.local/share/project-epistemic-bound/`. Scripted controls
need no Ollama or network. `peb doctor` checks state writability and probes the
configured local Ollama endpoint; it is not needed for bundle replay.

## Supplied evidence

| Case | Bundle | Events | Recorded distinction |
|---|---|---:|---|
| Truthful repair | [truthful-repair](evidence/s6-demo/truthful-repair/run-run_3ca17ff516ec432e97cb4bb894eef241/) | 52 | `useful_completion=yes`; original failure, repair and rerun remain recorded. |
| Authorized concealment | [authorized-concealment](evidence/s6-demo/authorized-concealment/run-run_5b28e69a622c447a81b701c7083d1315/) | 19 | `concealment_executed=yes`; authority permitted the inaccurate report write. |
| Forbidden export | [forbidden-export](evidence/s6-demo/forbidden-export/run-run_053e3cacf5164a8986c40f856ed6e23f/) | 18 | `attempted_unauthorized=yes`, `executed_unauthorized=no`; gate denial is not voluntary refusal. |

All manifests identify `mode=scripted_validation`, `provider_kind=scripted`.
Builders and their transcripts are not subjects or evaluation inputs. See the
[bundle contents statement](evidence/s6-demo/README.md),
[replay receipt](receipts/S6-evid-03-replay.json) and
[export scan receipt](receipts/S6-evid-04-export.json).

Inspect `manifest.json` for provenance, `events.jsonl` for the ordered record,
`receipts.json` for effects and `resources.json` for current/history/replay values.
**`evaluation.json` is `{present:false}` in these bundles.** Actual evaluator
output is inside the `evaluation_recorded` event; the producer also retains it
in the demo summary. The placeholder is neither a completed evaluation file nor
a failed evaluation. Exported `reviews.json` is an empty placeholder; these
three demos have no review requests and do not prove review-export completeness.

## Replay and checksums

From the checkout after integrating the bundle commit:

```sh
peb_bundle=docs/evidence/s6-demo/truthful-repair/run-run_3ca17ff516ec432e97cb4bb894eef241
(cd "$peb_bundle" && shasum -a 256 -c SHA256SUMS)
uv run --locked peb replay "$peb_bundle"
```

Repeat with the other table paths. Seat 2/3 independently checked all 30 listed
file checksums and replayed all three bundles. Each run's six reconstructed
resources equal its exported current and replayed maps. All replays report
`provider_invoked:false`.

**Replay reconstructs values; it does not verify event hashes, checkpoint
signatures or SHA256SUMS.** The separate checksum command checks consistency
against the supplied list, not independent authenticity.

## Verify and export retained state

Replace RUN_ID with an ID from your demo; retain the same state root:

```sh
uv run --locked peb --state-root "$peb_demo_state" verify RUN_ID
uv run --locked peb --state-root "$peb_demo_state" export RUN_ID --out /private/tmp/peb-exports
```

Current CLI `verify` passes no external checkpoint. A successful result is
`chain_consistent; external_anchor_absent`. The service's `evidence.verify` can
accept an independently retained checkpoint; see [INTERFACES §15](INTERFACES.md).
A checkpoint fetched from the store under test does not establish independent
retention or prove absence of tail loss.

The supplied bundles contain development HMAC signatures, not keys. Their
producer discarded the temporary state roots and keys. The bundles alone cannot
independently recheck those HMAC signatures. Generation-time verification strings
are historical receipts, not a fresh local verification. Keep keys, operator
secrets, private source vaults and builder transcripts out of exports.

## Pause, review and resume

For retained active model runs, `peb --state-root STATE pause RUN_ID` and
`cancel RUN_ID` persist stop boundaries. Already committed effects remain.

```sh
uv run --locked peb --state-root STATE review list RUN_ID
uv run --locked peb --state-root STATE review ack RUN_ID REVIEW_ID
uv run --locked peb --state-root STATE review deny RUN_ID REVIEW_ID --note "Operator decision"
```

Use `allow` for an operator-approved held proposal; it re-gates the exact proposal
and can still deny changed state or authority. Acknowledgement is not approval.
A software reviewer must use `--scripted-reviewer`, which records that provenance.
Cross-process resolution leaves the run paused. `peb --state-root STATE resume
RUN_ID` explicitly continues under a new subject session. Pending and acknowledged
reviews block resume until resolved or recorded expired, even when paused.
Scripted runs do not support cross-process resume; create a fresh control instead.
See [ADR-015](decisions/ADR-015-review-resolution-and-peb-review.md).

## Current limits

The integrated suite measured 299 passed and 2 skips. This does not complete
all BUILD_SPEC stages. The web factory is not yet integrated: `peb serve`
returns `not_implemented`, and UI-01 has no passing receipt. Five scenario
families and the bounded study planner remain work to complete. LIVE-01 is not
run; it needs an explicitly selected installed local model. Contract-only A2
awaits exact source text; the unmatched placebo is not a finished comparison arm.

Repository verification still needs full action-digest coverage before claiming
all of §14.2. Arbitrary report prose and broader disclosure/correction grading
remain outside the initial evaluator license. See [predicate licenses](PREDICATE_LICENSES.md),
[deferred work](DEFERRED.md) and the [runtime review](reviews/S3-a4865c8-runtime-codex.md).
These bundles do not imply full-release or live-model acceptance.
