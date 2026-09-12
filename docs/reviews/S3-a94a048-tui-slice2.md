# Review — a94a048 TUI slice 2, 3/3 surface (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce.  
**Reviewed:** `a94a04845ee050cea11c9267633508abcc63bded`.  
**Verdict:** **ACCEPT** `--serve` / no `peb.tui` store / ISO-02 (unchanged). **CHANGES** on evidence-display binding and widget rendering (#28502). Those are 1/3's to fix.

## `--serve` / store / ISO-02 — ACCEPT

`peb tui --serve` starts existing `peb serve` as a child, loopback only, no `--secret`. `src/peb/tui` does not import the store. Tests refuse bad attach/`--serve` before serving; fake transport writes nothing.

## Recheck of #28502 (3/3 evidence-display)

**apply_events.** Confirmed. Continuity is `page.cursor == len(known)` plus `first_prev == known[-1].event_hash` plus pairwise `a < b` on seq. A first page `seq [0, 2]` is still "ordered". Internal `prev_hash='wrong'` on a contiguous seq page is not checked. Require contiguous seq from the expected offset, every `prev_hash` link, and run identity; shrink/total mismatch → resync.

**apply_verification.** Confirmed. The badge is bound to `self.selected.head` at apply time, not to `checked_events` / the head the verifier covered. A verify of head 1 applied after the cache grew to head 2 looks current, not STALE. Capture the head the verifier actually covered; a race must be stale/unbound.

**Widget markup.** Confirmed as a 3/3 display-safety hole. `display()` does not neutralize Textual markup (`[red]…[/red]`). `Static`/`Label` default `markup=True`. Sanitizer tests on `app.rendered` (pre-render string) do not prove the widget. Pass literal `Content`/`Text` or `markup=False` on every untrusted surface, including prompts and table cells. Test actual rendered output.

Slice 1 ACCEPT of `display()` + `Badge.label()` stands as the helpers. End-to-end display and head binding do not yet follow those helpers.
