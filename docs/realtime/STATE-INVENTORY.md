# State and control inventory

Authoritative state is the manifest-pinned kernel checkpoint committed in SQLite.
The full native semantic scan is shared by browser and worker (`PlantCore`).

| Checkpoint group | Included semantic state |
|---|---|
| `fields.P` | All four process units, integrator/phase clocks, batch holds, trip latches, disturbance timers/magnitudes, environment, architecture faults/pending schedule/meta/log, training progress |
| `fields.L` | Every loop/indicator/motor; PV/SP/OP/mode, PID integrators/derivative history, mode attributes, master links, limits/alarm delays/deadbands, motor locks/trips, bad-PV state |
| `fields.V` | Native valve positions, fail/stick state and lag state |
| `alarms` | Entire alarm-engine snapshot, episode identity, live/ack state, shelving and timers |
| `fields` remainder | `hist`, `historyLimit`, `events`, `msgs`, `eid`, `alarmLog`, `t0`, `seed`, `vLag`, `phaseSet`, `tadShed`, `_lastPhase`, training records, MOC count and prior drill identity |
| Random state | Both explicit native PRNG states (`rand`, `rand4`); no fallback to ambient random |
| Instructor | Hidden flag, seed, sequence, journal, replay schedule, log and run-reset sequence |
| Exercise | Drill data and progress, completed tasks, disabled assets, architecture exercise mode, drill feedback/result |
| Attribution | Checkpoint-owned next message ID, per-target control revisions, cause/effect recorder deduplication set |
| RT additions | Tick, PIP attention, product interval accumulators and five-minute rolling meter samples |

Recreated caches: model/PID context, dispatcher, topology and cause/effect recorder
implementation (its seen entries are restored). Dialog positions, palette, keyboard
handlers, timers, network/provider clients and UI selections are not plant state.
The browser's local backtrack ring is disabled in the governed kernel. It cannot
rewind the authoritative world. Real-time history retains 600 samples per point
(five minutes); standalone retains its existing 7,200. Longer RT trajectories are
reconstructed from the complete starting checkpoint and immutable tick journal.

The reducer supports six subject/operator operations: `loop.set`, `motor.command`,
`sequence.command`, `alarm.ack`, `message.ack`, `view.focus`. It validates exact
shapes, engineering units, destination mode, expected mode/revision, native limits,
PROGRAM ownership, trip/lock/start permissives, alarm episodes and message versions.
All native mutation methods remain shared. Exceptions discard the candidate.
Instructor operations are a separate authenticated namespace: finite upset toggles,
finite physical-variable changes and scheduled architecture faults. There is no
model eval, arbitrary path, shell, HTTP, policy-write or evidence-delete tool.

The subject projection is an allowlist of 30 public points, bounded alarms with
matched/omitted counts, three trends, batch state, public messages and product
metrics. Hidden truth and schedules never enter its prompt. Instructor station
state is operator-only. An alarm's free text does not confer authority.

PEB owns observation snapshots, subject/grant identity, authority epochs, exact
reviews, per-target/unit/global human ownership, idempotency, queue ordering,
commit receipts and the outbox. Epoch and freshness are checked again after IPC.
Human commands are ordered first; at most one subject command is selected per
scan, and rate/cooldown rules count committed effects. Wall and simulated freshness
are both enforced. Plant candidates have no database or provider access.

Commit completion latency is measured **after** synchronous SQLite COMMIT. Its
separate timing record cannot be part of the commit it measures; a crash in that
small interval leaves an explicit missing timing sample, not a fabricated zero.
