// @artifact production
// ESS.Instructor — instructor-station data and helpers for the simulator.
//
// What a process training simulator's instructor station carries, in our own
// design: snapshots and initial conditions, an automatic backtrack ring, freeze /
// step / fast time, upsets with a hidden switch and a magnitude, instructor
// variables, an action journal that can be replayed, and live assessment
// (Forge PTS instructor feature list, RESOURCES 2.14; seeded determinism plus
// action-journal replay and snapshot / backtrack as in the cstr-ots architecture
// notes, RESOURCES 4.9). Pure logic: no DOM, no timers, no Component access; the
// app owns the process state and calls these helpers with plain data.
//
// API
//   create(opts)                 -> instructor state {auth, hidden, seed, seq, snapshots[8], ring, journal, replay, log}
//   resetRun(I)                  clear ring / journal / replay for a fresh process (snapshots, auth, hidden, seed stay)
//   clone(o)                     JSON deep clone (process state is plain data)
//   makeSnapshot(src, name)      -> snapshot record from {t, P, L, V, alarms, eventsCount, journalSeq, tadShed, phaseSet, disabledAssets, seed,
//                                randState, drill}; throws when P, L or V hold a non-finite number (JSON would turn it
//                                into null and a restore would corrupt the process state)
//   nonFinitePath(o, prefix)     first path holding NaN / Infinity, or null
//   pushRing(I, snap, t)         30 s ring buffer covering the last 10 sim-minutes; returns true when stored
//   ringPick(I, t, backMs)       ring entry nearest to t - backMs (the ring is sampled every RING_MS, so the first
//                                entry at least backMs old could be almost RING_MS further back than asked)
//   trimAfter(I, t, seq)         drop ring entries later than t and journal entries after sequence seq (time when seq is null)
//   journalAdd(I, entry)         append {t, op, tag, ...} stamped with the next sequence number; capped
//   replayRefusal(I, snap)       null, or {code, reason, lostFromSeq?, lostToSeq?} when the journal no longer covers the snapshot
//   replayPlan(I, snap, nowT)    entries journaled after the snapshot (by sequence, so actions taken while frozen at the
//                                snapshot time count) up to nowT, ordered; instructor entries (instr:true) included
//   replayDue(replay, t)         entries whose time has come, advancing the cursor
//   journalText(e, fmtT)         one-line text for a journal entry
//   presets()                    initial-condition definitions (data only)
//   compoundScripts()            ordered architecture-fault timelines (instructor staging)
//   upsetDefs()                  upset list with the magnitude control where meaningful
//   variableDefs()               instructor variables and their ranges
//   speeds()                     [1, 2, 5, 10]
//   RING_MS, RING_SPAN_MS, SLOTS, JOURNAL_CAP, DEFAULT_SEED
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Instructor = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var RING_MS = 30000;            // backtrack spacing, sim ms
  var RING_SPAN_MS = 600000;      // backtrack depth, sim ms
  var SLOTS = 8;                  // named snapshot slots
  var JOURNAL_CAP = 2000;
  var LOG_CAP = 200;
  var DEFAULT_SEED = 20260829;

  function clone(o) { return o === undefined ? undefined : JSON.parse(JSON.stringify(o)); }

  function create(opts) {
    opts = opts || {};
    var I = {
      auth: false,                // instructor password given this session
      hidden: false,              // upsets leave no trace in trainee displays
      seed: opts.seed || DEFAULT_SEED,
      seq: 0,                     // journal sequence counter; a snapshot records the value at save time
      snapshots: [], ring: [], journal: [], replay: null, log: [], lastRingT: -Infinity
    };
    for (var i = 0; i < SLOTS; i++) I.snapshots.push(null);
    return I;
  }

  // A run reset (initSim: a fresh plant, an initial condition, a canonical drill start)
  // clears the journal but not the sequence counter, so entries up to I.seq are gone for
  // good. runResetSeq remembers where, so replayRefusal can say WHY a gap exists rather
  // than blaming the journal cap for a reset the instructor or trainee performed.
  function resetRun(I) {
    I.ring = []; I.journal = []; I.replay = null; I.lastRingT = -Infinity;
    I.runResetSeq = I.seq;
  }

  function nonFinitePath(o, prefix) {
    if (typeof o === 'number') return isFinite(o) ? null : (prefix || 'value');
    if (!o || typeof o !== 'object') return null;
    for (var k in o) {
      var hit = nonFinitePath(o[k], prefix ? prefix + '.' + k : k);
      if (hit) return hit;
    }
    return null;
  }

  // V3-PLAN §4 snapshot v3. New records carry schemaVersion. v2 records in the wild
  // carry NO version marker at all; restore MUST key on absence of the field, never
  // on `schemaVersion < 3` (undefined < 3 is false, which would skip migration).
  var SCHEMA_VERSION = '3.0';

  function architectureFromProcess(P) {
    P = P || {};
    var faults = P.archFaults || {};
    var meta = P.archMeta || {};
    var active = Array.isArray(faults.activeFaults) ? clone(faults.activeFaults) : [];
    return {
      nodeHealth: meta.nodeHealth && typeof meta.nodeHealth === 'object' ? clone(meta.nodeHealth) : {},
      edgeHealth: meta.edgeHealth && typeof meta.edgeHealth === 'object' ? clone(meta.edgeHealth) : {},
      activeFaults: active,
      profile: typeof meta.profile === 'string' && meta.profile ? meta.profile : 'console'
    };
  }

  function makeSnapshot(src, name) {
    var bad = nonFinitePath({ P: src.P, L: src.L, V: src.V }, '');
    if (bad) throw new Error('non-finite value at ' + bad);
    var ess = (typeof globalThis !== 'undefined' && globalThis.ESS) || null;
    return {
      schemaVersion: SCHEMA_VERSION,
      modelId: src.modelId != null ? src.modelId : (ess && ess.MODEL_ID) || null,
      name: name || '', t: src.t, wall: src.wall || 0,
      seed: src.seed, randState: src.randState == null ? null : src.randState,
      randState4: src.randState4 == null ? null : src.randState4,   // Unit 04's own seeded stream (U4-SEPARATOR-CONTRACT rule 0.2)
      P: clone(src.P), L: clone(src.L), V: clone(src.V),
      alarms: clone(src.alarms), eventsCount: src.eventsCount || 0, journalSeq: src.journalSeq == null ? null : src.journalSeq,
      tadShed: !!src.tadShed, phaseSet: src.phaseSet || null,
      disabledAssets: Array.isArray(src.disabledAssets) ? src.disabledAssets.slice() : [],
      drill: src.drill ? clone(src.drill) : null,
      architecture: src.architecture ? clone(src.architecture) : architectureFromProcess(src.P)
    };
  }

  function pushRing(I, snap, t) {
    if (t - I.lastRingT < RING_MS) return false;
    I.lastRingT = t;
    I.ring.push(snap);
    var floor = t - RING_SPAN_MS - 1;
    while (I.ring.length && I.ring[0].t < floor) I.ring.shift();
    return true;
  }

  function ringPick(I, t, backMs) {
    if (!I.ring.length) return null;
    var want = t - backMs, best = null, bestD = Infinity;
    for (var i = 0; i < I.ring.length; i++) {
      var d = Math.abs(I.ring[i].t - want);
      if (d < bestD || (d === bestD && I.ring[i].t < want)) { best = I.ring[i]; bestD = d; }
    }
    return best;
  }

  // Journal entries are cut by sequence when the snapshot carries one: with the sim frozen, actions taken after the
  // save share its sim time, and only the sequence tells which side of the snapshot they belong to.
  function trimAfter(I, t, seq) {
    I.ring = I.ring.filter(function (s) { return s.t <= t; });
    I.journal = I.journal.filter(function (e) { return seq == null ? e.t <= t : e.seq <= seq; });
    I.lastRingT = I.ring.length ? I.ring[I.ring.length - 1].t : -Infinity;
  }

  // Truncation is REMEMBERED, not just performed (thread #28, S4): when the cap splices the
  // oldest entries away, the seq and sim time of the last one lost are kept on I (lazily, so
  // create()'s shape is unchanged for callers that never overflow). replayPlan reads them to
  // refuse a replay that would silently cross the gap.
  function journalAdd(I, entry) {
    entry.seq = ++I.seq;
    I.journal.push(entry);
    if (I.journal.length > JOURNAL_CAP) {
      var dropped = I.journal.splice(0, I.journal.length - JOURNAL_CAP);
      var last = dropped[dropped.length - 1];
      I.journalDroppedSeq = last.seq;
      I.journalDroppedT = last.t;
      I.journalDroppedCount = (I.journalDroppedCount || 0) + dropped.length;
    }
  }

  /** Why a replay from `snap` cannot be trusted, or null when the journal fully covers it.
   *  Sequence-carrying snapshots: seq is contiguous (every journalAdd increments), so an oldest
   *  surviving seq above snap.journalSeq + 1 PROVES entries after the snapshot were spliced away;
   *  an empty journal with I.seq beyond the snapshot proves the same. Legacy snapshots
   *  (journalSeq == null, pre-S0) carry no sequence, so the only evidence is a REMEMBERED drop
   *  whose sim time postdates the snapshot; drops that happened before this module started
   *  remembering them are undetectable on that path, and that limitation is deliberate and named
   *  rather than papered over with a guess. */
  function replayRefusal(I, snap) {
    if (!snap) return { code: 'NO_SNAPSHOT', reason: 'no snapshot to replay from' };
    if (snap.journalSeq != null) {
      var oldest = I.journal.length ? I.journal[0].seq : null;
      // A run reset after the snapshot (initial condition loaded, canonical drill started)
      // is the common way a gap appears on the trainee's own path; name it, never the cap.
      var resetAfter = I.runResetSeq != null && I.runResetSeq > snap.journalSeq;
      if (oldest != null && oldest > snap.journalSeq + 1) {
        if (resetAfter) {
          return { code: 'RUN_RESET_AFTER_SNAPSHOT', reason: 'the run was reset after this snapshot (an initial condition was loaded or a canonical drill was started, which clears the action journal): actions seq ' + (snap.journalSeq + 1) + '-' + (oldest - 1) + ' are gone and a replay would omit them; replay from a snapshot taken after the reset', lostFromSeq: snap.journalSeq + 1, lostToSeq: oldest - 1 };
        }
        return { code: 'JOURNAL_TRUNCATED', reason: 'journal truncated across the snapshot: actions seq ' + (snap.journalSeq + 1) + '-' + (oldest - 1) + ' were dropped by the ' + JOURNAL_CAP + '-entry cap; a replay would silently omit them', lostFromSeq: snap.journalSeq + 1, lostToSeq: oldest - 1 };
      }
      if (oldest == null && I.seq > snap.journalSeq) {
        if (resetAfter) {
          return { code: 'RUN_RESET_AFTER_SNAPSHOT', reason: 'the run was reset after this snapshot (an initial condition was loaded or a canonical drill was started, which clears the action journal): the ' + (I.seq - snap.journalSeq) + ' actions recorded after it are gone; replay from a snapshot taken after the reset', lostFromSeq: snap.journalSeq + 1, lostToSeq: I.seq };
        }
        return { code: 'JOURNAL_EMPTY_AFTER_SNAPSHOT', reason: 'the journal holds none of the ' + (I.seq - snap.journalSeq) + ' actions recorded after the snapshot (cleared or truncated); a replay would reproduce a different exercise', lostFromSeq: snap.journalSeq + 1, lostToSeq: I.seq };
      }
      return null;
    }
    if (I.journalDroppedT != null && I.journalDroppedT > snap.t) {
      return { code: 'JOURNAL_TRUNCATED_LEGACY', reason: 'legacy snapshot (no sequence): ' + I.journalDroppedCount + ' journal entries were dropped by the cap and the last dropped (seq ' + I.journalDroppedSeq + ') postdates the snapshot; a replay would silently omit actions', lostToSeq: I.journalDroppedSeq };
    }
    return null;
  }

  function logAdd(I, t, txt) {
    I.log.unshift({ t: t, txt: txt });
    if (I.log.length > LOG_CAP) I.log.length = LOG_CAP;
  }

  // e.accepted !== false (thread #28, V3-PLAN S2 architect decision D3(a)): a command
  // dispatch refused is journaled anyway (accepted:false, with a reason -- that marking is
  // the whole point, the v3 scorer's safety gate needs to see a trainee attempt something
  // unsafe and get refused), but it was never actually applied, so it must never be
  // scheduled for replay. `undefined` (every entry journaled outside ESS.Dispatch, which
  // carries no `accepted` field at all) passes this check same as `true` -- only an
  // explicit accepted:false is excluded. src/dispatch.js's header documents the hazard this
  // closes; tests/dispatch.test.js pins the fix.
  // A plan that would cross a truncation is REFUSED (entries: [], refused: <code>, reason)
  // rather than returned short: a short replay that reports REPLAY COMPLETE reproduces a
  // different exercise, which is the failure class release gate 3 exists to catch. Callers
  // that only test entries.length see "nothing to replay"; callers that read `refused`
  // can say why. replayRefusal(I, snap) gives the same answer without building a plan.
  function replayPlan(I, snap, nowT) {
    var refusal = replayRefusal(I, snap);
    if (refusal) {
      return { entries: [], i: 0, fromT: snap.t, endT: snap.t, toT: nowT, refused: refusal.code, reason: refusal.reason,
        lostFromSeq: refusal.lostFromSeq == null ? null : refusal.lostFromSeq, lostToSeq: refusal.lostToSeq == null ? null : refusal.lostToSeq };
    }
    var afterSnap = snap.journalSeq == null ? function (e) { return e.t > snap.t; } : function (e) { return e.seq > snap.journalSeq; };
    var list = I.journal.filter(function (e) { return afterSnap(e) && e.t <= nowT && e.accepted !== false; })
      .sort(function (a, b) { return a.t - b.t || a.seq - b.seq; }).map(clone);
    return { entries: list, i: 0, fromT: snap.t, endT: list.length ? list[list.length - 1].t : snap.t, toT: nowT, legacy: snap.journalSeq == null };
  }

  function replayDue(replay, t) {
    var due = [];
    while (replay.i < replay.entries.length && replay.entries[replay.i].t <= t) due.push(replay.entries[replay.i++]);
    return due;
  }

  function journalText(e, fmtT) {
    var tt = fmtT ? fmtT(e.t) : String(e.t);
    var body;
    switch (e.op) {
      case 'MODE': body = e.tag + ' MODE ' + e.arg; break;
      case 'STORE': body = e.tag + ' ' + e.param + ' ' + e.arg; break;
      case 'RAISE': body = e.tag + ' RAISE'; break;
      case 'LOWER': body = e.tag + ' LOWER'; break;
      case 'START': case 'STOP': body = e.tag + ' ' + e.op; break;
      case 'SEQ': body = 'SCM202 ' + e.arg; break;
      case 'ACK': body = 'ACK ' + e.arg; break;
      case 'ACKPAGE': body = 'ACK PAGE'; break;
      case 'SIL': body = 'SILENCE'; break;
      case 'SHELVE': body = 'SHELVE ' + e.arg + ' ' + e.mins + ' MIN'; break;
      case 'UNSHELVE': body = 'UNSHELVE ' + e.arg; break;
      case 'UPSET': body = 'INSTR UPSET ' + e.tag + ' ' + e.arg; break;
      case 'MAG': body = 'INSTR MAGNITUDE ' + e.tag + ' = ' + e.arg; break;
      case 'VAR': body = 'INSTR VARIABLE ' + e.tag + ' = ' + e.arg; break;
      case 'SEED': body = 'INSTR SEED ' + e.arg; break;
      case 'DRILL': body = 'INSTR DRILL ' + e.tag + ' ARMED'; break;
      case 'DRILLEND': body = 'INSTR DRILL ' + e.tag + ' ENDED'; break;
      case 'CTLACTN': body = e.tag + ' CONTROL ACTION ' + e.arg; break;
      case 'PVTRACK': body = e.tag + ' PV TRACKING ' + e.arg; break;
      case 'OOS': body = e.tag + ' ' + e.cond + (e.arg === 'ON' ? ' OUT OF SERVICE' : ' RETURN TO SERVICE'); break;
      case 'PRIO': body = e.tag + ' ' + e.cond + ' PRIORITY ' + String(e.arg).toUpperCase(); break;
      case 'COMMENT': body = 'COMMENT ' + e.arg + ': ' + e.text; break;
      case 'CONFIRM': body = 'CONFIRM MESSAGE ' + e.tag + ': ' + e.arg; break;
      case 'ASSET': body = 'ALARMS ' + (e.arg === 'ON' ? 'DISABLED' : 'RE-ENABLED') + ' FOR ASSET ' + e.tag; break;
      default: body = e.op + (e.tag ? ' ' + e.tag : '') + (e.arg != null ? ' ' + e.arg : '');
    }
    return tt + '  ' + body;
  }

  // Initial conditions as data: overrides applied to a fresh process, optionally a batch start and a
  // condition to run to (phase / level), then a settling run. The app builds the snapshot and restores it.
  function presets() {
    return [
      { id: 'U1_SS', label: 'U1 steady state', desc: 'Continuous unit at design feed, all loops on setpoint, no batch running.', run: 120 },
      { id: 'U1_HIFEED', label: 'U1 high feed', desc: 'Feed tank being drawn down to a 40 % setpoint: throughput up and R-201 near its High limit with little jacket margin, for about ten minutes until the tank settles and throughput returns to the supply rate. Start the exercise inside that window.',
        set: { L: { LIC101: { sp: 40 } } }, run: 480 },
      { id: 'U2_FEED', label: 'U2 batch mid-FEED', desc: 'A batch started and run into the FEED phase with about half the monomer charged.',
        batch: true, waitPhase: 'FEED', waitLvl: 55, maxRun: 3600, run: 10 },
      { id: 'U2_REACT', label: 'U2 batch REACT', desc: 'A batch run through FEED into REACT: monomer inventory still high, jacket working.',
        batch: true, waitPhase: 'REACT', maxRun: 6000, run: 10 },
      // Feed 46 / preheat 322 put the bed past its open-loop stability limit (loop gain crosses
      // 1.0 near 435 C at that feed) and the unit limit-cycled 312-479 C and tripped itself with
      // nobody at the console (veteran review 2026-09-03). Measured: feed 44 / preheat 320 holds
      // the bed flat at 413 C for an hour; 45 and above limit-cycle and trip. A steady high load
      // 27 C under the High alarm, with less margin than design, is what the label promises.
      { id: 'U3_HILOAD', label: 'U3 high load', desc: 'Fired reactor at raised feed and preheat: the bed hotspot settles near 413 DEG C and holds there, under its 440 High limit with less margin than design; the tube skins run above design.',
        set: { L: { FIC310: { sp: 44 }, TIC311: { sp: 320 } } }, run: 480 }
    ];
  }

  // Upsets = the existing faults, each with the magnitude control that makes sense for it.
  function upsetDefs() {
    return [
      { k: 'xmtr', label: 'FIC102 transmitter failure (BADPV)', unit: 'U1' },
      { k: 'drift', label: 'LIC101 transmitter drift', unit: 'U1', mag: { key: 'drift', label: 'Drift rate', min: 0.2, max: 5, step: 0.1, eu: '% / MIN' } },
      { k: 'surge', label: 'Feed inflow surge (8 min)', unit: 'U1', mag: { key: 'surge', label: 'Surge', min: 10, max: 80, step: 5, eu: 'M3/H' } },
      { k: 'pump', label: 'P-101 pump trip (one-shot)', unit: 'U1' },
      { k: 'cool', label: 'Cooling water loss (backup in 3 min)', unit: 'U1', mag: { key: 'coolLoss', label: 'Fraction lost', min: 0.25, max: 1, step: 0.05, eu: '' } },
      { k: 'stick', label: 'TV-202 valve stiction (+ reaction load)', unit: 'U1' },
      { k: 'vap', label: 'Flash drum vapor surge (5 min)', unit: 'U1' },
      { k: 'air', label: 'Instrument air loss — valves to fail state', unit: 'ALL' },
      { k: 'rxn', label: 'Off-spec feed: reaction rate step', unit: 'U1' },
      { k: 'foul', label: 'E-301 fouling (progressive)', unit: 'U1' },
      { k: 'agit', label: 'M-202 agitator trip (one-shot)', unit: 'U2' },
      { k: 'bedact', label: 'R-310 catalyst activity step', unit: 'U3', mag: { key: 'bedact', label: 'Activity ×', min: 1.1, max: 1.6, step: 0.05, eu: '' } }
    ];
  }

  // Instructor variables: plant conditions the trainee cannot see directly. `path` names the P field.
  function variableDefs() {
    return [
      { k: 'feedConc', label: 'Feed concentration', path: 'env.feedConc', min: 0.7, max: 1.3, step: 0.01, def: 1, eu: '× design', dec: 2 },
      { k: 'cwT', label: 'Cooling water supply', path: 'Tcw', min: 4, max: 20, step: 0.5, def: 8, eu: 'DEG C', dec: 1 },
      { k: 'Tamb', label: 'Ambient temperature', path: 'env.Tamb', min: -10, max: 45, step: 1, def: 25, eu: 'DEG C', dec: 0 },
      { k: 'foulRate', label: 'E-301 fouling rate (baseline 2 %/h × this; the fouling upset runs on top)', path: 'env.foulRate', min: 0.5, max: 3, step: 0.1, def: 1, eu: '× base', dec: 1 },
      { k: 'catAct', label: 'R-310 catalyst activity', path: 'env.catAct', min: 0.7, max: 1.3, step: 0.01, def: 1, eu: '× design', dec: 2 },
      { k: 'monoPurity', label: 'Monomer purity', path: 'env.monoPurity', min: 0.8, max: 1, step: 0.01, def: 1, eu: 'fraction', dec: 2 },
      { k: 'weirH', label: 'V-502 weir height', path: 'env.weirH', min: 30, max: 90, step: 1, def: 55, eu: '%', dec: 0 }
    ];
  }

  function getPath(P, path) { return path.split('.').reduce(function (o, k) { return o == null ? undefined : o[k]; }, P); }
  function setPath(P, path, v) {
    var parts = path.split('.'), o = P;
    for (var i = 0; i < parts.length - 1; i++) o = o[parts[i]] = o[parts[i]] || {};
    o[parts[parts.length - 1]] = v;
  }

  function speeds() { return [1, 2, 5, 10]; }

  // V3-PLAN section 8: compound scripts as ordered fault timelines. Data only;
  // the app's runCompoundScript() fires each step through setArchFault so every
  // onset is dispatch-journaled. Reserved legacy pairs (xmtr/drift/stick) are
  // deliberately not used here -- the matrix already excludes them.
  function compoundScripts() {
    return [
      {
        id: 'CS1',
        title: 'Degraded path, then bias, then history gap',
        desc: 'V3-PLAN section 8 example: net-path degradation, then a transmitter bias, then history loss. Three independent domains, staggered onsets.',
        steps: [
          { tSec: 0, faultId: 'NET_PATH_DEGRADED', target: 'NET-U1-B' },
          { tSec: 30, faultId: 'BIASED_MEASUREMENT', target: 'XMTR-TIC201', magnitude: 2 },
          { tSec: 60, faultId: 'HISTORIAN_GAP', target: 'SVC-HISTORY' }
        ]
      },
      {
        id: 'CS2',
        title: 'Partition then server',
        desc: 'Both of U3\'s redundant network paths fail together, then the data server degrades. Common-cause comms followed by a service fault.',
        steps: [
          { tSec: 0, faultId: 'COMMS_PARTITION', target: 'NET-U3-A' },
          { tSec: 0, faultId: 'COMMS_PARTITION', target: 'NET-U3-B' },
          { tSec: 45, faultId: 'SERVER_SERVICE_DEGRADED', target: 'SVC-SERVER' }
        ]
      }
    ];
  }

  return {
    create: create, resetRun: resetRun, clone: clone, makeSnapshot: makeSnapshot,
    SCHEMA_VERSION: SCHEMA_VERSION, architectureFromProcess: architectureFromProcess,
    replayRefusal: replayRefusal,
    pushRing: pushRing, ringPick: ringPick, trimAfter: trimAfter,
    journalAdd: journalAdd, logAdd: logAdd, nonFinitePath: nonFinitePath, replayPlan: replayPlan, replayDue: replayDue, journalText: journalText,
    presets: presets, upsetDefs: upsetDefs, variableDefs: variableDefs, getPath: getPath, setPath: setPath, speeds: speeds,
    compoundScripts: compoundScripts,
    RING_MS: RING_MS, RING_SPAN_MS: RING_SPAN_MS, SLOTS: SLOTS, JOURNAL_CAP: JOURNAL_CAP, DEFAULT_SEED: DEFAULT_SEED
  };
});
