# AGENTS.md — builder rules for project-epistemic-bound

Read `BUILD_SPEC.md` (rev 1.0, 2026-09-11) first; it is authoritative. This file
is the working agreement for the three builder terminals and the cross-seat
communication protocol. Grok and Codex read it natively; Claude Code imports it
from `CLAUDE.md`.

## Part A — the build (BUILD_SPEC §§2–4, §21)

**Builders are not subjects.** Claude Code, Grok and Codex are the engineering
team. Subject agents are separate `peb` sessions with their own
`subject_session_id`. Never turn a builder's conversation, identity or terminal
history into experimental data; never grade the builders (ADR-001, ADR-010).

**Lanes** (assigned by Anthony in `TEAM_START.md` and §3.1; nobody self-assigns
or reassigns):

| Seat | Occupant (2026-09-11) | Owns | Reviews | Worktree / branch |
|---|---|---|---|---|
| 1/3 | Claude Code (fable) — lead/integrator | bootstrap; contracts/schemas; subject runtime; providers; commitments; CLI; config; integration docs; dependencies; migration numbering | Codex's UI/evaluation changes | integration checkout `~/Desktop/project-epistemic-bound` (main) and `…-worktrees/claude` (build/claude-core) |
| 3/3 | Grok — boundary/evidence | reference_monitor; approvals; synthetic executor; SQLite storage + migrations (after interface freeze); event chain; replay/export primitives | Claude's runtime/provider boundary | `…-worktrees/grok` (build/grok-boundary) |
| 2/3 | Codex (astra) — workroom/verification | UI/API bindings; fixture corpus; evaluation predicates; denominators; acceptance/adversarial tests; release evidence checks | Grok's effect/approval/audit code | `…-worktrees/codex` (build/codex-workroom) |

**Git rules (§3.2).** One repository, three linked worktrees. Only 1/3 changes
the integration checkout. Write in your own worktree. Normal commits on lane
branches; reviewed `--no-ff` merges into local `main` by 1/3; lanes merge the
new `main` into their branch before dependent work. Never: `git stash`,
`git reset --hard`, `git clean`, force-push, worktree deletion, blanket
"ours"/"theirs", checking out a branch under another seat, creating a remote,
publishing. Review by exact commit hash and diff. Preserve author identity: the
machine's git identity is Anthony's; every seat appends its own trailer, e.g.
`Co-Authored-By: seat 3/3 Grok <noreply@x.ai>` — never another seat's.

**Staging discipline (§4.2).** `git add -- <reviewed paths>`, never `git add .`.
Check the staged diff for credentials, private identifiers and unrelated files.
Private source documents stay untracked and are registered by hash in
`docs/SOURCE_REGISTER.md`. Never stage the entity vault or private papers.

**State (§6, §9.1).** Operator state lives at
`~/.local/share/project-epistemic-bound/`; tests always get a temporary state
root; each lane uses its own venv and test state. No test defaults to the
operator database.

**Initiative (§0, §3.3).** Build through the stages; do not ask Anthony to settle
ordinary implementation details. Raise a bounded question only at a real
boundary (overwrite risk, unknown repo, credential/paid service, live
infrastructure, genuine source conflict). New requirements go to
`docs/DEFERRED.md`. No subagent fan-out, paid runs, model downloads, or
infrastructure services because they are available.

**Lane state (§21).** Each seat keeps exactly one current-state file in
`docs/lanes/<seat>.md`: branch, latest commit, files owned, tests passed, active
processes, blockers, next action. Review receipts go in `docs/reviews/`, test
receipts in `docs/receipts/`.

## Part B — cross-seat communication: t2helix is the room

Anthony, 2026-09-11: "i want all cross seat comms handled by the t2helix."
Lane files in `docs/lanes/` are durable per-lane state; the **t2helix board is
the conversation**. No side channels between seats: no message files in the
repo, no Stack bulletin, no relaying through Anthony as the channel. If Anthony
relays by voice, the board still gets the entry.

**Board shard (t2helix domain): `colab-untitled-folder`.** The folder was renamed
to `project-epistemic-bound` on 2026-09-11 (S0); the shard name is retained on
purpose — it is an address, not a description, and seat watchers filter on the
exact string. Changing it mid-build would blind them.

All three seats point at one chronicle:
`~/.claude/plugins/data/t2helix-templetwo-t2helix/chronicle.db`. No second
database; `~/.t2helix-data` does not exist and must not be created.

| Seat | Registered where | t2helix surface |
|---|---|---|
| Claude Code | plugin `t2helix@templetwo-t2helix` (user scope) | `mcp__plugin_t2helix_t2helix__*` + hooks (recall on every prompt, compass gate) |
| Grok Build | `~/.grok/config.toml` `[mcp_servers.t2helix]` | `t2helix__*` via `node ~/t2helix/scripts/mcp-launch.js` |
| Codex | `~/.codex/config.toml` marker block | t2helix tools via pinned Node + `~/t2helix/mcp/server.js` |

**Boot — every session, every seat.** (1) `get_state`. (2) `recall` with
`query="SEAT BOARD colab-untitled-folder"`, `topK=10`, newest first. Claude Code
gets recall by hook; Grok and Codex do not, so for them this call is the
discipline. (3) `bash scripts/t2helix-status.sh` — versions, config targets, DB
path and counts; "on latest" is a claim, this is the receipt. (4) Post an ack.

**Post format — `record`.**
```
record(
  domain    = "colab-untitled-folder",
  layer     = "ground_truth"   # facts, acks, decisions, receipts
            | "hypothesis"     # proposals, questions, unverified reads
  intensity = 0.7 (board traffic) | 0.9 (lane claims, blockers, Anthony verbatim)
  tags      = ["seat-board", "from:<seat>", "to:<seat|all>", "<topic>"],
  content   = """
=== SEAT BOARD — <SUBJECT IN CAPS>. Seat <N/3>, <YYYY-MM-DD HH:MM TZ>. ===
FROM: seat <N/3> — MacBook seat (<model>), session <id>
TO:   <seat | all>
RE:   #<insight id you are replying to>       (omit for a fresh topic)

<what you did / found / need, with receipts: commit hashes, file paths,
 test counts, command output. A claim without a receipt is a hypothesis.>
"""
)
```
- Address seats by **number** in anything durable (`seat 2/3 found this`); pair
  a name to a number only in dated board entries.
- A **direct ask** is a line that starts with `CALLING <seat>`. Bare names in
  prose are commentary. Line-start anchored on purpose.
- **Delivery vs record.** Seat watchers read *transcripts*; a call is delivered
  when it lands in your assistant text on its own line. The board copy is the
  durable record. Prove a channel with a round trip before relying on it.
- Reply with `RE: #id`. Never edit or delete a board entry; post a correction
  that names what it supersedes.
- Anthony's directive sent to several seats: each seat records it verbatim.
- Threads: lane claims and unresolved questions → `open_thread(domain=…)`;
  close with `resolve_thread`. `set_goal` is shared session state — change it
  only when Anthony changes the objective, and post the change.

**Known trap.** Grok's and Codex's t2helix servers stamp writes with the session
id in the shared `.current_session` file, which Claude's hooks own. Filter board
watches by the `FROM:` line, not by session id. Grok inside the `temple`
sandbox can read the chronicle but not write it (SQLITE readonly) — relaunch
without the sandbox to restore its write path.

**Watching.** `scripts/seat_watch.py <transcript.jsonl> <label> <call-regex>`
reads Claude Code, Grok and Codex transcript shapes and emits the human's
prompts plus line-anchored `CALLING` lines; the offset never advances past an
incomplete line (bug found by seat 2/3, 2026-09-11). Claude seats may also use
`~/.claude/skills/trifecta-mesh/scripts/helix_watch.sh` on the live db.

**Compass.** Claude Code's `PreToolUse` hook enforces WITNESS/PAUSE. For Grok
and Codex the compass is **advisory only**: call `dry_run_compass` before
anything destructive, treat WITNESS as stop and PAUSE as confirm with Anthony,
and never describe it as enforced.

**Sovereign Stack (HQ) is not the seat-to-seat channel** and is not a build
dependency (§1.2). This machine is Anthony's MacBook Pro, not HQ. Durable
lineage writes, if any, use `source_instance = "MacBook seat (<model>)"`.
