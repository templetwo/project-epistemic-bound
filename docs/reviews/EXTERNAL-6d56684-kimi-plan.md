# Plan — Adversarial external review of `project-epistemic-bound`

**Task**: Act as external technical adviser (per the seat-1/3 Claude Code brief, dated 2026-09-12).
Adversarially review repo `templetwo/project-epistemic-bound` at pinned commits.

**Pinned references**
- Review baseline: `6d56684f007c1e3c653b2b246ad8964a8afd1d3a`
- Measured implementation: `5e3391736a97585c639c7686346638c5718b974e` (merge of lane `1834d657...`)
- Claim: 710 passed / 0 failed / 0 skipped, Ruff clean on `5e33917`; `git diff --name-only 5e33917 6d56684` should touch docs/ only.

**Required finding form (brief §11)**: reviewed commit; file/function/line; affected requirement; observed vs expected; evidence/repro; severity + uncertainty; smallest proposed correction; concrete closure test. Every claim labelled as: (1) code inspection, (2) repository-reported result, or (3) test actually executed.

**Constraints**: read-only review. No branch pruning, no new experiments, no paid model calls, no live operator-root. Tests in isolated checkout only. Board entry numbers (#27xxx etc.) are NOT evidence. Supplement in §6 unavailable → candidate run (§5) stays unverified; §7 "declined" question assessed from public code/licenses only.

## Stages

### Stage 1 — Deterministic reproduction (verifier subagent)
Clone, `git checkout 6d56684`, `uv sync --locked`, pytest, ruff, `clean_checkout_suite.sh 5e33917`, `git diff --name-only 5e33917 6d56684`, `peb doctor`, `peb replay` of the s6-demo truthful-repair run. Report exact commands + outputs as category-3 evidence. Disclose any environment limits.

### Stage 2 — Parallel code inspection (three reviewer subagents, non-overlapping)
- **R1 — post-closure change `1834d65`** (remit §8-first): model menus, hosted catalog (`probe_hosted_catalog`, health.get payload, POST /api/health), provider-switch invalidation in app.js, exact-ID entry, optional cost disclosure vs mandatory execution limits, hosted preview-token binding, unreachable/key_absent paths, and whether adding fields + a second HTTP method to health.get legitimately avoids the frozen INTERFACES §15 amendment.
- **R2 — evidence & interpretation** (remit §8-second + open question §7): `src/peb/evaluation/predicates.py` vs `docs/PREDICATE_LICENSES.md` (esp. line 38 `voluntary_decline`), whether a structured decline is expressible in the decision schema for `evaluation-pressure-basic`; end-to-end distinguishability of proposed/allowed/applied/denied/held/never-started/unknown; verification-head binding; `None` vs `0` usage; `docs/acceptance-matrix.json` 51 rows; `scripts/check_release.py` reviewer-string weakness.
- **R3 — operator experience + governance** (remit §8-third): Textual coroutine handling and port ownership at `d3f5458` + its tests, attach/detach, review-target confirmation, Inspect tab; read governing docs (BUILD_SPEC rev 1.0, ADR-017/018/019/020, AGENTS.md Part C) for consistency; judge DEFERRED.md/HANDOFF.md staleness vs §5 note.

### Stage 3 — Integration (orchestrator)
Merge findings, deduplicate, enforce the §11 form and category labels, produce `epistemic-bound-external-review.md` + `.docx` (load `docx` skill at this stage).
