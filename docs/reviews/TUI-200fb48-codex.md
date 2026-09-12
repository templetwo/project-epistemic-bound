# Seat 2/3 review — TUI 200fb48

Verdict: ACCEPT at `200fb48dc902c3d9ff059c93637d8e57323002fa` for the implemented TUI transport, app and CLI unit. This closes seat 2/3 findings #28469, #28502, #28511 and #28526; it does not assert completion of every ADR-019 design milestone or authorize a release.

The final delta requires the first event at cursor zero to have seq zero, type run_created and no previous hash. In an exact archive, the two original malformed-prefix probes and a genesis with a previous hash all return resync; an actual genesis appends. Existing continuity, within-page hash links, run identity and shrink controls remain in place.

The reviewed predecessor 4bbfd88 forwards the resolved state root into the child argument and environment; quitting detaches the server regardless of cached inventory, and reports explicit reattach/shutdown instructions. Untrusted widget and table values render as literal text. Verification with a different or missing checked-event count is unbound, and a subsequent event makes a bound result stale. The gateway transport preserves ambiguous POST outcomes and rejects malformed success responses.

Validation measured by seat 2/3 on an exact 200fb48 archive: 53 TUI and CLI bootstrap tests passed, zero failed, zero skipped (JUnit /private/tmp/astra-tui-200fb48.xml); Ruff passed for src/peb/tui, tests/tui, src/peb/cli.py and tests/unit/test_cli_bootstrap.py. The four independent prefix probes above also passed. Prior 4bbfd88 and a94a048 targeted runs emitted nonblocking unawaited refresh-coroutine warnings; no claim of warning-free full-suite validation is made here. The owner reported 639 full-suite passes; that is the owner's measurement, not this review's run.

Tests used isolated temporary state and headless/fake transports. No operator database, provider inference, paid service or peer worktree was changed.
