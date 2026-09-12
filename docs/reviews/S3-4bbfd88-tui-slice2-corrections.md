# Review — 4bbfd88 TUI slice 2 corrections (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `4bbfd88669e1addb61f134f100c471d9e9be1714`.  
**Verdict:** **ACCEPT** the #28502/#28505 recheck (binding + rendering + child state-root). App/CLI remainder still 2/3.

## apply_events

Exact continuation: cursor at cached end; no shrinking total; contiguous seq (`first = last+1`; genesis at cursor 0 with `prev_hash` None); every `prev_hash` inside the page and across the boundary; run identity when named. Cases `[0,2]`, internal `prev_hash='wrong'`, shrink, foreign run → resync. **Pass.**

## apply_verification

Badge binds only when `checked_events == cached count` (that hash). Otherwise UNBOUND (`head.hash is None`), on the label and as an alert. `checked_events=1` vs cached 2 is UNBOUND, not a blessing of the newest head. **Pass.**

## Rendering

Every pane `markup=False` + `Content(text)`. DataTable cells `Text`. Prompt labels literal. Tests read widget `render().plain` with zero spans on the hostile markup string. **Pass.**

## Child state root (ISO-02)

`_spawn_workroom` forwards resolved `cfg.state_root` as `--state-root` argv and `PEB_STATE_ROOT`. Explicit CLI root overrides inherited env (tested). **Pass.**

## Quit

Detach, never terminate a started child. 2/3's contract. 3/3 notes only: no store write on quit.
