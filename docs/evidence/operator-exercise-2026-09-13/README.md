# Operator exercise evidence — 2026-09-13

This dataset preserves the latest 32-run operator snapshot: **7 scripted controls,
9 Ollama observations, and 16 hosted DeepSeek observations**. It contains 22
completed runs and 10 failed runs, with no active runs. There are 31 stored
evaluation records; failed Ollama run
`run_32b2d6e2c42644a9bf44e1b40e7a33f5` has no evaluation record. Absence is preserved.

Grok's initial 31-run review subset consists of every run here except
`run_f856ffca0c064d599372d3b2458a8372`. This dataset includes that additional run in
its latest, failed state. The earlier subset and this 32-run snapshot have
different denominators; the earlier report is not silently rewritten.

The source SQLite snapshot has SHA256
`b2bbe841be4d5142d550b5e5f265251c7a6fe80595b56a1914c7fe3ab4661be2`.
The database itself is not included. These are existing subject sessions and
their stored records. Packaging did not execute a new study, call a model,
recalculate an evaluation, or turn any builder conversation into subject data.

## Contents and inspection

`index.json` enumerates all 32 runs. Each `bundles/run-<run_id>/` directory contains
a closed 11-file run bundle, including its own `SHA256SUMS`. The bundle preserves
the manifest, event history, synthetic workspace records, and stored checkpoint
records. `studies/` contains exact copies of the two existing study journals and
`provenance.json`, which records source and copy hashes, byte counts, and the
journal-to-snapshot compatibility checks. The dataset-level `SHA256SUMS` records
the packaged file hashes.

From the repository root, with the project's environment installed, run:

```sh
.venv/bin/python docs/evidence/operator-exercise-2026-09-13/verify_dataset.py
```

This checks the dataset inventory and hashes, the index, bundle records,
evaluations, and resource correspondence. To inspect one existing framing
observation without inference:

```sh
.venv/bin/peb replay docs/evidence/operator-exercise-2026-09-13/bundles/run-run_8453f50c96d24a28830561a3e2a2dde3
```

`replay` reads an exported bundle; it does not resume the subject. The included
`export_snapshot.py` records the packaging method. Its source is a read-only
snapshot, and it preserves stored evaluations and checkpoints without minting
new checkpoints.

## Study membership and matching

The hosted observations include 15 baseline runs and one `candidate_v1` run.
Their frames are ordinary (10), game (3), and roleplay (3). Eleven hosted runs
belong to the following two studies; five are outside those studies.

| Existing study | Planned / recorded / provider completed | Frames and status |
| --- | --- | --- |
| `study_a8a22a8a0063521c31bcd48cab2023c0` | 9 / 8 / 7 | Ordinary, game, roleplay; partial |
| `study_6057e5e5560b21c150c7787ad23b1793` | 3 / 3 / 3 | Ordinary only; completed |

The original framing study remains **8 of 9 dispatched**. Its conceal-error
group contains completed ordinary, game, and roleplay observations. Its
fictional-authority group contains completed game and roleplay observations,
plus failed ordinary run `run_3ab750046c594a358010026cad541b6e`. Its
claimed-harmlessness group contains completed game and roleplay observations;
the planned ordinary trial was not dispatched.

The eighth trial's truncated provider response stopped the study with
`trial_held_or_incomplete`. The journal records 74 decision calls used and 128 of
144 calls reserved. The remaining 16-call reservation would have fit the ninth
trial; this was a failure stop, not exhaustion of the study's decision-call
ceiling. Readiness probes are separate from that ceiling.

The second study's three completed ordinary observations remain a separate
study. They do not replace the original failed or undispatched trials. Every
recorded run in these two journals pins `format_correction_limit: 0`; their
results must not be described as observations with a correction limit of 2.

The planner derives `pair_id` from fixture and repeat, excluding study, frame,
and profile. Within the original study, the three fixture groups therefore
provide matched frame observations under the same pinned conditions, with the
missingness above. The separate ordinary study reuses these pair IDs. Pair ID
equality alone is not evidence of shared study assignment or independent
replication.

There is no matched baseline–candidate profile contrast in these hosted runs.
The sole candidate run, `run_0f8305020e244043983d3cdebcf83f95`, is an ordinary-frame
evaluation-pressure observation outside both studies; no hosted baseline run
uses that fixture. Baseline framing observations and a candidate profile
contrast answer different questions.

## Evidence limits

No independently retained trust anchor accompanies this dataset. Stored
checkpoint records are evidence objects, not independent anchors. File hashes,
event-chain checks, and object correspondence make internal consistency
inspectable; they do not authenticate the original history against a trusted
local administrator or establish an independently witnessed checkpoint.

Stored evaluation labels retain their recorded meanings and missingness.
Predicate versions are mixed (`conceal-error-v2` / `conceal-error-v3` and
`finite-families-v1` / `finite-families-v2`), retained unchanged, and should be
stratified when comparing results. A completed run is not by itself a behavioral
success, and a failed or unevaluated
run is not silently excluded. Scripted controls test the instrument; they are
not model-behavior observations. These public development fixtures, sparse
matched observations, and heterogeneous run conditions support inspection of
these particular runs, not a statistical population claim or a release
acceptance verdict.

The journal copies were screened structurally for path strings, credential
field names, and recognizable credential formats before inclusion. No journal
string contains a slash, and that screen reported no credential-shaped content.
No operator credential was read or used for comparison. Source hashes and the
specific compatibility checks are recorded in `studies/provenance.json`.
