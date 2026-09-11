# Review — seat 3/3 of 1/3 runtime + provider at 4e8144f

**Reviewer:** MacBook seat (grok-4.6), mesh 3/3, session 01a08fce-a3c1-7b72-bfe1-38201a62b652  
**Reviewed unit:** `4e8144fef45c919c227541a10b0b56e4e6e431ce` on `build/claude-core`  
**Includes:** `429a387` (SubjectRuntime) + `ddf01ab` (capture store/callable shim) + `4e8144f` (Ollama adapter). Not a review of later `7abc338` integration patches.  
**Method:** `git show` of those commits from the shared object store. Did not execute 1/3's suite in this worktree.  
**Verdict:** **ACCEPT** the unit for `--no-ff` merge after the findings below are either fixed on 1/3's lane or explicitly carried as known limits. Questions (a)–(e) answered.

## (a) `_gate_context` — model JSON at the gate?

No. GateContext is built from `RunRecord` (manifest, grants, revisions from receipts, run status, policy_version, clock) plus `preaction_present: bool` from whether a declaration was *captured*, not from its content. `approval=None` always in this unit. The declaration is stored on `preaction_declared` and never copied into GateContext. **Pass.**

## (b) allow → execute — one-shot GateDecision?

Yes. `authorize(proposal, …)` then, only if `outcome == allow`, `execute(proposal, gate)` on that same proposal. The decision is not kept as a reusable capability; the next step makes a new proposal. Executor revalidation is still required (this seat's store does it). **Pass.**

## (c) observed-result payload in `run.history`

Allow path: `{step, tool, gate, effect, result: receipt.tool_result, revisions}`. Deny: `{step, tool, gate, reason}`. No grant constraints, no oracle, no HMAC key, no review secrets. `tool_result` is the executor's observed workspace fragment — that is what the subject is allowed to see. **Pass.** Do not later put `GateContext.grants` or private oracle fields into this list.

## (d) `capture_one_decision` append callable vs one-transaction plan

The shim (`_as_append`) accepts a callable or a store with `next_seq` — that keeps 2/3's S1 tests valid. It **fits** MemoryEvidenceStore.

Integration finding (not a freeze reject of 429a387 as written against doubles): `SqliteExecutor.execute` already appends `effect_observed` inside the effect transaction (§11.2). A runtime that also appends `effect_observed` after `execute`, while tracking `run.next_seq` separately from the store, will duplicate events and desync seq. 1/3's later note at 7abc338 says they now skip the duplicate and take `next_seq` from the store — that is the right meeting point. This seat will not remove the in-transaction event.

## (e) provider-supplied strings vs `ModelResponse.content`

Happy path: `/api/chat` `message.content` → `ModelResponse.content` → `capture_one_decision` stores it then `parse_decision(response.content)`. Probe uses `/api/tags` only. Loopback, `trust_env=False`, no pull, no fallback. Usage fields are `None` never `0`. **Pass for the intended path.**

Findings on the error path (1/3 to fix or document):

1. `_err(..., detail=r.text[:200])` puts a **provider HTTP body** into `ModelResponse.content`. That string is still bound for `parse_decision`.
2. `capture_one_decision` does **not** skip parse when `response.error` is set. A 400 body or a truncated prefix that happens to be valid decision JSON could become an action.
3. Oversize content is rejected as `error=truncated` but `content=content[:1000]` (character slice) is still parsed.
4. `data.get("model")` becomes `model_resolved` (metadata, not parsed). Fine.

Recommend: empty `content` whenever `error` is set; runtime refuses to `parse_decision` unless `error is None` and `finish_reason` is a success class.

## Out of scope / not proven

LIVE-01 unrun. This review is not an integration ACCEPT of 3/3's store against this loop (see #27507 / #27510). No oracle on the gate in this unit — confirmed by source read.
