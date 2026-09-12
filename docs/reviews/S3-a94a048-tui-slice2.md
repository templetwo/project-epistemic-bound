# Review — a94a048 TUI slice 2, 3/3 surface only (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `a94a04845ee050cea11c9267633508abcc63bded`.  
**Verdict:** **ACCEPT** on the three asked points. App/transport/UI remainder is 2/3.

## `--serve` process surface

`peb tui --serve` starts the existing `peb serve` as a child of this interpreter (`sys.executable -c … main(['serve', …])`), attaches, terminates the child on quit. Host must be `127.0.0.1` / `localhost` / `::1` before Popen. No `--secret`. Secret from `operator.secret` under the configured state root, or getpass; dropped after sign-in. **Pass.** This is not a second runtime.

## No store import under `peb.tui`

`git grep` of `src/peb/tui` at this hash: no `SqliteRepository`, no `peb.storage`. The word "storage" is health-status display only. CLI `cmd_tui` reads `load_config` for the secret path (CLI, not the TUI package). **Pass.**

## ISO-02

Suite tests refuse bad URLs / non-loopback `--serve` before serving; app tests use a fake transport (viewing writes nothing). Autouse `PEB_STATE_ROOT` still applies. Operator-root `--serve` is the live cockpit, not a test default. **Pass.**
