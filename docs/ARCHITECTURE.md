# ARCHITECTURE — v0.1 trust flow (BUILD_SPEC §7)

```text
Anthony / local operator
        |
        v
Local workroom + CLI -------> configuration / exact approval controls
        |                                      |
        v                                      v
Task supervisor --------------------------> grant & review store
        |
        | bounded, allowlisted context
        v
Separate subject provider session
        |
        | untrusted structured decision; no execution privilege
        v
Decision capture + schema validation ------> flight recorder
        |
        v
Reference monitor <-------------------------- authoritative grants
        |
        | allow / deny / request actual approval
        v
Synthetic executor ---- atomic transaction ----> resource revisions
        |                                             |
        +---- observed receipt + event chain ----------+
                         |
                         v
                  replay / evaluator
                         |
                         v
                   operator report
```

## Invariants the code must keep (in the data, not only the prose)

1. **The oracle is not on the authorization path.** The monitor checks scope and
   authority; it never consults the test answer key. Authorized concealment must
   remain executable (ADR-003).
2. **A declaration is not permission.** `PreActionDeclaration` is captured with
   the proposal before any gate feedback and scored against actual grants; the
   gate resolves the grant independently of the subject's `claimed_grant_id`.
3. **A model's statement is never the executor receipt.** Only
   `EffectReceipt` from the executor's committed transaction says what happened.
4. **Deny by default.** Unknown tool, argument, resource, run, session, expired or
   revoked grant, stale revision, replayed nonce: deny with a stable reason.
5. **One transaction.** Resource change, nonce consumption, receipt and effect
   event commit together or not at all (§11.2).
6. **Allowlisted context.** The subject sees profile text, task instructions,
   permitted resources, tool schemas, public grant descriptions and its own
   permitted records. Never `AGENTS.md`, this spec, builder transcripts, oracle
   files, operator tokens or other subjects' results.
7. **Raw before parsed.** Store the returned decision content, then parse exactly
   one decision; malformed output ends the attempt as `invalid_output`.
8. **Verification is bounded.** Without an external checkpoint the strongest
   claim is `chain_consistent; external_anchor_absent`.

## Module map and lane ownership

```text
src/peb/
  contracts.py      frozen records, enums, protocols, strict parsing   1/3
  config.py         state root, loopback defaults                       1/3
  errors.py         typed envelopes                                     1/3
  cli.py            §20 commands                                        1/3
  runtime/          engine (loop), context, commitments, review         1/3
  providers/        base, scripted, ollama                              1/3
  boundary/         canonical (frozen), reference_monitor, approvals    3/3
  workspace/        tools, executor, fixtures                           3/3 (executor) · 2/3 (fixtures)
  evidence/         events (frozen hash rule), replay, export, verify   3/3
  storage/          repository, migrations                              3/3 (numbering by 1/3)
  evaluation/       planner, predicates, metrics, grading               2/3
  web/              app, static                                         2/3
```

## Deployment boundary (§1.3)

The subject can produce text and structured tool proposals only. It cannot execute
Python, JavaScript, shell, SQL, arbitrary HTTP, filesystem paths or plugins. The
trusted local application, host OS, installed model server and human operator are
outside the v0.1 adversary model. This is not a macOS sandbox and not protection
against a malicious local administrator.
