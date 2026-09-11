# S1 review — seat 2/3

- Author of reviewed code: seat 1/3.
- Reviewer: seat 2/3 (Codex, GPT-6 Astra), 2026-09-11.
- Reviewed commit: `191d60bc800e00e5bb079a37ffc1513e36d01dd0`.
- Follow-up correction: `7ee2291973b85f13f50f8fcdaaba1daeddb62de1`.
- Scope: fixture/oracle separation, tool argument expressiveness, parser testability,
  and evidence regressions identified during the draft review.
- Verdict: **ACCEPT for S1 fixture/interface use after the 7ee2291 correction.**
  This is not S2 authorization/effect acceptance or a release approval.

## Findings and resolution

1. Draft event IDs were not covered by the event hash. A valid chain remained green
   after changing an event ID. Fixed in 191d60b, with a regression on changed IDs.
2. A draft checkpoint for another run could anchor the chain. Fixed in 191d60b.
   S2 storage must supply the trusted key and manifest to verify checkpoint
   authenticity; a low-level structural match without those arguments is not
   authenticated evidence. Test that requirement at the public verification route.
3. At 191d60b, `parse_decision` accepted `schema_version: true` and `1.0`, converting
   either to integer 1. Reproduced by this reviewer with a valid finish decision.
   Fixed by the schema owner in 7ee2291 using an exact-type validator, with tests
   for JSON and Python paths. The serialized schema shape is unchanged.

`TaskSpec` and `PrivateOracle` are separate types. Full TaskSpec includes family
and predicate IDs, so runtime context must use an explicit public projection;
separate classes alone do not establish ISO-01. The fixture loader in this lane
supplies and tests that projection. PrivateOracle/frame/arm and script identities
are evaluator inputs only. There is no oracle-derived denial reason in the gate
contract. The eight tool variants express the three initial scripted scenarios.

## Measured validation

In this lane's own environment, at 191d60b:
`uv run --locked pytest -o addopts='' -q --junitxml=/private/tmp/astra-s1-junit.xml`
returned **54 passed**, exit 0. This corrected the earlier 55-test claim on the
board. At 7ee2291 with the new fixture slice, **81 passed**, including 23 new
fixture/capture/adversarial cases. The durable slice receipt records the final
command, timestamps, counts, hashes, environment and scope.

No gate, executor, model observation or behavioral acceptance is inferred from
these results. Review lineage: t2helix #27432, #27436, #27448, #27453, #27457.
