// @artifact production
/*
 * ESS.CauseEffect -- the cause-and-effect matrix as a declarative assertion layer
 * (CONVERGENCE-SPEC.md item 2 / work item W2, acceptance 3.1.6; contract
 * docs/dev/W2-CAUSE-EFFECT-CONTRACT.md).
 *
 * PURE. No DOM, no timers, no clock, no randomness, and it never writes to anything
 * it is passed. `src/models.js` is not touched and is not required by this module --
 * the matrix DECLARES the seven cause rows as data, copied by hand from the six
 * `raiseTrip` call sites in `src/models.js` plus the one app-side tube-skin trip; it
 * never re-derives or re-evaluates them. The code stays the source of truth. This
 * module never fires an effect, never closes a valve, never trips anything -- it
 * observes what the code already did (via a recorder the caller feeds) and asserts
 * that the two agree. Matrix-as-source-of-truth is v4, gate 8.1, and is out of scope
 * here.
 *
 * API
 *   MATRIX            the declared data: { causes: [...], effects: [...] } (below)
 *   CHART_VISIBILITY  'instructor' | 'operator' -- the one-line promotion flag (see
 *                     the comment on its declaration)
 *   causes()          -> the seven declared cause rows (frozen, read-only)
 *   effects()         -> the declared effect columns (frozen, read-only)
 *   cells()           -> [{causeId, effectId, action}, ...] -- the chart body,
 *                        flattened from each effect's own `causedBy` list
 *   createRecorder()  -> {observe(src, cond, simTime), seen(), reset()}
 *                        a plain, append-only log of what a seam fired. NO
 *                        de-duplication: `onTrip` fires exactly once per latch
 *                        transition (src/models.js:294-297 and its six call sites,
 *                        each guarded by `!P.trips.<flag>`), so a second firing after
 *                        a reset is a genuinely new trip event and must be recorded
 *                        as one, not folded into the first.
 *   verify(seen)      -> {ok, findings:[...]} -- compares a recorder's seen() log
 *                        against the declared `onTrip`-seam rows (six of the seven;
 *                        see the H310_SKIN row below). Two codes, both severity
 *                        'refuse': SEAM_TRIP_UNDECLARED (something fired at the seam
 *                        with no matching row) and SEAM_ROW_UNREACHED (a declared row
 *                        no observation ever reached). Findings are
 *                        {code, severity, detail, tags}, as in W1.
 *   chart()           -> {rows, cols, cells, orphans} -- the render model for the
 *                        C&E display; `orphans` lists any cause row with no cell
 *                        (empty today -- every cause reaches at least one effect).
 *
 * Citations. RESOURCES-7.8 (IEC 61511-1) and RESOURCES-7.10 (CCPS, Guidelines for
 * Safe Automation of Chemical Processes) are cited for the cause-and-effect FRAMING
 * and the VOTING VOCABULARY only -- both are CITED-NOT-HELD. No number, default,
 * comparator or reset value in this file is taken from either source: every
 * threshold below is copied, by hand, from this repository's own src/models.js (the
 * `site` field on each row names the exact line), or, for the seventh row, from
 * "Experion Station Simulator.dc.html"'s own interlock. A future 2oo3-style voting
 * cell, if one is ever declared, would cite 7.8/7.10 for the vocabulary the same way.
 *
 * Provenance note on the seven rows (docs/dev/W2-CAUSE-EFFECT-CONTRACT.md §0.1-0.3):
 * six of the seven trips pass through `ctx.onTrip(src, cond)` -- the shared seam at
 * src/models.js:294-297, chained (not replaced) at the app's onTrip callback. The
 * seventh, H-310's tube-skin trip (P.trips.skin), is raised in the APP's own
 * interlocks(), calls dTrip() directly and never reaches ctx.onTrip -- a reader on
 * the seam will never see it. It is declared here anyway (seam:'app') because it
 * shares FV311's effect column with R-310's bed trip: VALVE_TARGET's own entry is
 * `FV311: (P, L) => (P.trips.bed || P.trips.skin) ? 0 : ...` (src/models.js:332). A
 * matrix that omitted it would be wrong about the plant. `verify()` only ever
 * expects the six seam:'onTrip' rows to appear in a recorder's log, by design.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).CauseEffect = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ---------------------------------------------------------------- the app file's
  // own name, spelled once, so no row below has to repeat the awkward literal.
  var APP_FILE = 'src/plant-core.js';

  // ---------------------------------------------------------------- seven cause rows
  //
  // Verified against the code at checkpoint 0bbfd13 on branch v3. Every `desc` is the
  // raiseTrip / raiseA description string, copied character for character -- it is
  // what the operator actually sees in the alarm summary, not a paraphrase.

  // Every row carries the SAME four fields Anthony named -- latch, reset, lockout, permissive --
  // whatever kind of thing it describes. The schema is standard rather than bespoke so a reader
  // (or a chart, or a future item 1) can walk any row without knowing which family it came from;
  // a field that does not apply is null, never absent.
  //
  // A fifth field, `enforced`, carries the distinction that makes the motor rows honest:
  //   enforced:true  -- the plant PREVENTS the thing. A process trip really does shut the valve;
  //                     the P-101 level permissive really does refuse the START.
  //   enforced:false -- the plant PERMITS it and RECORDS it. A motor trip latch does not block a
  //                     restart: motorCmd sets m.trip=false and starts, then stamps
  //                     INTERLOCK.DEFEAT. That is the real control philosophy and a trainee is
  //                     better served knowing it than being told about a guard that is not there.
  var CAUSES = Object.freeze([
    Object.freeze({
      id: 'TK101_HIHI', src: 'TK-101', cond: 'HIHI TRIP', seam: 'onTrip', kind: 'process-trip',
      variable: 'tankL', comparator: '>=', threshold: 98, eu: '%',
      latched: true,
      latch: Object.freeze({ field: 'P.trips.ovf' }),
      reset: Object.freeze({ kind: 'auto-hysteresis', expr: 'P.tankL < 90' }),
      lockout: null,
      permissive: null,
      enforced: true,
      desc: 'FEED TANK OVERFLOW PROTECTION — FEED ISOLATED',
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'TK-101', 'HIHI TRIP'" },
    }),
    Object.freeze({
      id: 'R201_HITEMP', src: 'R-201', cond: 'HI TEMP TRIP', seam: 'onTrip', kind: 'process-trip',
      variable: 'rT', comparator: '>=', threshold: 185, eu: 'DEG C',
      latched: true,
      latch: Object.freeze({ field: 'P.trips.rx' }),
      reset: Object.freeze({ kind: 'auto-hysteresis', expr: 'P.rT < 160' }),
      lockout: null,
      permissive: null,
      enforced: true,
      desc: 'REACTOR HIGH TEMPERATURE TRIP — FEED VALVE CLOSED',
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'R-201', 'HI TEMP TRIP'" },
    }),
    Object.freeze({
      id: 'V401_PSV', src: 'V-401', cond: 'PSV LIFT', seam: 'onTrip', kind: 'process-trip',
      variable: 'drumP', comparator: '>', threshold: 950, eu: 'KPA',
      latched: true,
      latch: Object.freeze({ field: 'P.trips.psv' }),
      reset: Object.freeze({ kind: 'auto-hysteresis', expr: 'P.drumP < 900' }),
      lockout: null,
      permissive: null,
      enforced: true,
      desc: 'RELIEF VALVE LIFTED TO FLARE',
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'V-401', 'PSV LIFT'" },
    }),
    Object.freeze({
      id: 'R202_HITEMP', src: 'R-202', cond: 'HI TEMP TRIP', seam: 'onTrip', kind: 'process-trip',
      variable: 'b.T', comparator: '>=', threshold: 110, eu: 'DEG C',
      latched: true,
      latch: Object.freeze({ field: 'P.trips.batch' }),
      reset: Object.freeze({ kind: 'auto-hysteresis', expr: 'b.T < 70' }),
      lockout: null,
      permissive: null,
      enforced: true,
      desc: 'BATCH REACTOR OVERTEMP — FEED CUT, JACKET FULL COLD',
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'R-202', 'HI TEMP TRIP'" },
    }),
    Object.freeze({
      id: 'R310_HITEMP', src: 'R-310', cond: 'HI TEMP TRIP', seam: 'onTrip', kind: 'process-trip',
      variable: 'h.bed', comparator: '>=', threshold: 480, eu: 'DEG C',
      latched: true,
      latch: Object.freeze({ field: 'P.trips.bed' }),
      reset: Object.freeze({ kind: 'auto-hysteresis', expr: 'h.bed < 400' }),
      lockout: null,
      permissive: null,
      enforced: true,
      desc: 'BED OVERTEMP — FUEL GAS SHUT OFF',
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'R-310', 'HI TEMP TRIP'" },
    }),
    Object.freeze({
      id: 'V502_PSV', src: 'V-502', cond: 'PSV LIFT', seam: 'onTrip', kind: 'process-trip',
      variable: 's.pres', comparator: '>=', threshold: 1100, eu: 'KPA',
      latched: true,
      latch: Object.freeze({ field: 'P.trips.psv502' }),
      reset: Object.freeze({ kind: 'auto-hysteresis', expr: 's.pres < 1000' }),
      lockout: null,
      permissive: null,
      enforced: true,
      desc: 'SEPARATOR RELIEF — VENTING TO FLARE',
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'V-502', 'PSV LIFT'" },
    }),
    // The seventh process row. seam:'app', not 'onTrip' -- contract §0.3. Its threshold is not
    // one number: the app latches on EITHER tube-skin channel reaching its own Urgent (PVHH)
    // limit, TI314 at 490 or TI315 at 500, so both are named rather than hiding one.
    Object.freeze({
      id: 'H310_SKIN', src: 'H-310', cond: 'TUBE SKIN TRIP', seam: 'app', kind: 'process-trip',
      variable: 'max(h.ts1, h.ts2)', comparator: 'PVHH latch (either channel)',
      threshold: 'TI314 >= 490 DEG C or TI315 >= 500 DEG C', eu: 'DEG C',
      latched: true,
      latch: Object.freeze({ field: 'P.trips.skin' }),
      reset: Object.freeze({ kind: 'auto-hysteresis', expr: 'h.ts1 < 400 && h.ts2 < 400' }),
      lockout: null,
      permissive: null,
      enforced: true,
      desc: 'TUBE SKIN OVERTEMP — FUEL GAS SHUT OFF',
      site: { file: APP_FILE, anchor: "this.raiseA('H-310','TUBE SKIN TRIP'" },
    }),

    // ---- motor rows. Manual reset by START after the lockout, and RECORDED, not prevented. ----
    Object.freeze({
      id: 'P101_TRIP', src: 'P-101', cond: 'MOTOR TRIP', seam: 'app', kind: 'motor-trip',
      variable: 'L.P101.trip', comparator: 'latched by', threshold: 'CAVITATION (P.tankL < 2) or the pump fault (UNCOMMANDED STOP)', eu: '',
      latched: true,
      latch: Object.freeze({ field: 'L.P101.trip' }),
      reset: Object.freeze({
        kind: 'manual-start', expr: 'operator START once L.P101.lock reaches 0',
        recorded: true,
        note: 'START sets m.trip=false and runs the motor; it is NOT refused. The defeat is ' +
          'stamped as INTERLOCK.DEFEAT on DRV-P101.',
      }),
      lockout: Object.freeze({ sec: 30, after: 'trip', alsoSec: 15, alsoAfter: 'stop',
        site: { file: APP_FILE, anchor: 'm.run=false; m.trip=true; m.tripWhy=why; m.lock=30;' } }),
      permissive: Object.freeze({ expr: 'P.tankL >= 5', enforced: true, ref: 'P101_PERMISSIVE' }),
      enforced: false,
      desc: 'PUMP TRIPPED',
      site: { file: 'src/models.js', anchor: "ctx.tripMotor('P101', 'CAVITATION — LOW SUCTION LEVEL')" },
    }),
    Object.freeze({
      id: 'M202_TRIP', src: 'M-202', cond: 'MOTOR TRIP', seam: 'app', kind: 'motor-trip',
      variable: 'L.M202.trip', comparator: 'latched by', threshold: 'the agit upset (UNCOMMANDED STOP)', eu: '',
      latched: true,
      latch: Object.freeze({ field: 'L.M202.trip' }),
      reset: Object.freeze({
        kind: 'manual-start', expr: 'operator START once L.M202.lock reaches 0',
        recorded: true,
        note: 'As P-101: START clears the latch rather than being refused, and stamps ' +
          'INTERLOCK.DEFEAT on DRV-M202. This is the column drill A5 gates on.',
      }),
      lockout: Object.freeze({ sec: 30, after: 'trip', alsoSec: 15, alsoAfter: 'stop',
        site: { file: APP_FILE, anchor: 'm.run=false; m.trip=true; m.tripWhy=why; m.lock=30;' } }),
      permissive: null,   // the faceplate says so in as many words: "PERMISSIVE: NONE CONFIGURED"
      enforced: false,
      desc: 'AGITATOR TRIPPED',
      site: { file: APP_FILE, anchor: "this.tripMotor('M202','UNCOMMANDED STOP')" },
    }),

    // ---- the one ENFORCED permissive. Unlike a motor trip latch, this really does refuse. ----
    Object.freeze({
      id: 'P101_PERMISSIVE', src: 'P-101', cond: 'START PERMISSIVE', seam: 'app', kind: 'permissive',
      variable: 'P.tankL', comparator: '<', threshold: 5, eu: '%',
      latched: false,
      latch: null,
      reset: Object.freeze({ kind: 'continuous', expr: 'P.tankL >= 5 -- the permissive is re-evaluated on every START, nothing latches' }),
      lockout: null,
      permissive: Object.freeze({ expr: 'P.tankL >= 5', enforced: true }),
      enforced: true,
      desc: 'START PERMISSIVE NOT MET — TK-101 LEVEL LOW',
      site: { file: APP_FILE, anchor: "this.P.tankL<5" },
    }),
  ]);

  // ---------------------------------------------------------------- effect columns
  //
  // Declared from VALVE_TARGET's OWN gating (src/models.js:323-337), not re-derived:
  // a valve is an effect column here only because VALVE_TARGET itself names a trip
  // flag in that valve's ternary. Non-valve effects (feed isolation, the two relief
  // actions) carry no VALVE_TARGET entry at all -- trips.ovf, trips.psv and
  // trips.psv502 gate no valve in the table -- so they are declared as action text
  // taken verbatim from their cause's own raiseTrip desc instead.
  //
  // FV311 is the one column two causes share: VALVE_TARGET's entry reads
  // `(P.trips.bed || P.trips.skin) ? 0 : ...` -- one valve, two independent trips
  // that each close it (docs/dev/W2-CAUSE-EFFECT-CONTRACT.md §0.3).

  var EFFECTS = Object.freeze([
    Object.freeze({
      id: 'FV102', kind: 'valve', target: 'FV102',
      action: "VALVE_TARGET FV102 -> 0: P.trips.rx closes the R-201 feed valve.",
      causedBy: Object.freeze(['R201_HITEMP']),
      site: { file: 'src/models.js', anchor: 'FV102: (P, L) => P.trips.rx ? 0 :' },
    }),
    Object.freeze({
      id: 'MV211', kind: 'valve', target: 'MV211',
      action: "VALVE_TARGET MV211 -> 0: P.trips.batch cuts the R-202 monomer feed.",
      causedBy: Object.freeze(['R202_HITEMP']),
      site: { file: 'src/models.js', anchor: 'MV211: (P, L) => P.trips.batch ? 0 :' },
    }),
    Object.freeze({
      id: 'JV213', kind: 'valve', target: 'JV213',
      action: "VALVE_TARGET JV213 -> 0: P.trips.batch drives the R-202 jacket to its " +
        "coldest tempered-water mix (c.medMin).",
      causedBy: Object.freeze(['R202_HITEMP']),
      site: { file: 'src/models.js', anchor: 'JV213: (P, L) => P.trips.batch ? 0 :' },
    }),
    Object.freeze({
      id: 'FV311', kind: 'valve', target: 'FV311',
      action: "VALVE_TARGET FV311 -> 0: P.trips.bed OR P.trips.skin closes the H-310 " +
        "fuel-gas valve -- one valve, two independent causes.",
      causedBy: Object.freeze(['R310_HITEMP', 'H310_SKIN']),
      site: { file: 'src/models.js', anchor: 'FV311: (P, L) => (P.trips.bed || P.trips.skin) ? 0 :' },
    }),
    Object.freeze({
      id: 'TK101_FEED_ISOLATED', kind: 'action', target: 'TK-101 unit feed (P.qin)',
      action: 'FEED TANK OVERFLOW PROTECTION — FEED ISOLATED',
      causedBy: Object.freeze(['TK101_HIHI']),
      site: { file: 'src/models.js', anchor: 'if (P.trips.ovf) qin = 0;' },
    }),
    Object.freeze({
      id: 'V401_RELIEF', kind: 'action', target: 'V-401',
      action: 'RELIEF VALVE LIFTED TO FLARE',
      causedBy: Object.freeze(['V401_PSV']),
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'V-401', 'PSV LIFT'" },
    }),
    Object.freeze({
      id: 'V502_RELIEF', kind: 'action', target: 'V-502',
      action: 'SEPARATOR RELIEF — VENTING TO FLARE',
      causedBy: Object.freeze(['V502_PSV']),
      site: { file: 'src/models.js', anchor: "raiseTrip(ctx, 'V-502', 'PSV LIFT'" },
    }),
    // ---- the JOIN KEY. These ids are 'DRV-' + tag, built the same way motorCmd builds the
    // target it stamps on an INTERLOCK.DEFEAT:  archSynthEvent('INTERLOCK.DEFEAT','DRV-'+tag,null).
    // That string equality IS the join: a defeat resolves to this column, and the column names the
    // cause. Nothing else connects the drill gate to the matrix, so the id is not cosmetic and
    // must not be prettified -- tests/cause-effect.test.js pins it against the app's own template.
    Object.freeze({
      id: 'DRV-P101', kind: 'motor', target: 'P-101',
      action: 'START clears L.P101.trip and runs the pump. NOT refused: the latch is advisory and ' +
        'the restart is recorded as INTERLOCK.DEFEAT. The enforced guard on this motor is its ' +
        'permissive (TK-101 level >= 5 %), which does refuse.',
      causedBy: Object.freeze(['P101_TRIP']),
      site: { file: APP_FILE, anchor: "this.archSynthEvent('INTERLOCK.DEFEAT','DRV-'+tag,null)" },
    }),
    Object.freeze({
      id: 'DRV-M202', kind: 'motor', target: 'M-202',
      action: 'START clears L.M202.trip and runs the agitator. NOT refused: the latch is advisory ' +
        'and the restart is recorded as INTERLOCK.DEFEAT. No permissive is configured on this ' +
        'motor. This is the column drill A5 gates on.',
      causedBy: Object.freeze(['M202_TRIP']),
      site: { file: APP_FILE, anchor: "this.archSynthEvent('INTERLOCK.DEFEAT','DRV-'+tag,null)" },
    }),
    Object.freeze({
      id: 'P101-START-INHIBIT', kind: 'permissive', target: 'P-101',
      action: 'START is REFUSED while TK-101 level < 5 %: motorCmd returns early, raises P101 ' +
        'CMDFAIL and messages the operator. The only motor guard in the plant that actually blocks.',
      causedBy: Object.freeze(['P101_PERMISSIVE']),
      site: { file: APP_FILE, anchor: "'START PERMISSIVE NOT MET — TK-101 LEVEL LOW'" },
    }),
  ]);

  var MATRIX = Object.freeze({ causes: CAUSES, effects: EFFECTS });

  // ---------------------------------------------------------------- the one-line flag
  //
  // CONVERGENCE-SPEC.md §10.2: the C&E chart ships instructor-only and stays
  // instructor-only "until the assertion test has passed clean across the full
  // golden set". There is no existing feature-flag idiom elsewhere in this repo for
  // a display gate like this one, so this establishes it, minimally: a single
  // module-level string, read by the app and defaulted closed if absent. Flipping
  // this one word to 'operator' -- once tests/cause-effect-coverage.test.js passes
  // clean across all four golden scenarios plus the two authored ones, all six seam
  // rows, tick-for-tick -- IS the promotion; flipping it back IS the demotion. The
  // app must fail CLOSED (instructor-only) if this module or this field is missing,
  // the opposite of dofPreflight's fail-open, because here the risk is a surface
  // shown to a trainee before it has earned the right to be believed, not a drill
  // wrongly blocked.
  var CHART_VISIBILITY = 'instructor';

  // ---------------------------------------------------------------- accessors

  function causes() { return CAUSES; }
  function effects() { return EFFECTS; }

  function cells() {
    var out = [];
    for (var i = 0; i < EFFECTS.length; i++) {
      var e = EFFECTS[i];
      for (var j = 0; j < e.causedBy.length; j++) {
        out.push({ causeId: e.causedBy[j], effectId: e.id, action: e.action });
      }
    }
    return out;
  }

  // ---------------------------------------------------------------- defeat annotation
  //
  // "Scored from the matrix" means, per Anthony's ruling of 2026-09-13: the defeat RESOLVES to an
  // effect column, and the reader annotates the cause and the cause-state at reset.
  //
  // ANNOTATION ONLY. This function returns text. It does not score, does not cap, does not touch
  // src/drill-arch.js, and no A-drill score moves because of it. The gate logic is exactly what it
  // was; the matrix supplies the explanation the gate never had.
  //
  // causeState is whatever the caller can observe at the moment of the reset -- typically
  // {tankL: …} for P-101's cavitation. It is optional: when the caller cannot evaluate the cause,
  // the annotation says so rather than guessing.
  function annotateDefeat(target, causeState) {
    var col = null, i;
    for (i = 0; i < EFFECTS.length; i++) if (EFFECTS[i].id === target) { col = EFFECTS[i]; break; }
    if (!col) {
      return {
        resolved: false, target: target, causes: [],
        text: 'INTERLOCK.DEFEAT on ' + target + ': no declared effect column. The matrix cannot ' +
          'explain this defeat, which is itself worth knowing.',
      };
    }
    var causes = col.causedBy.map(function (cid) {
      var row = null, j;
      for (j = 0; j < CAUSES.length; j++) if (CAUSES[j].id === cid) { row = CAUSES[j]; break; }
      return row;
    }).filter(Boolean);

    var parts = causes.map(function (r) {
      var bit = r.src + ' ' + r.cond + ' (' + r.desc + ')';
      if (r.lockout) bit += '; reset is a manual START after a ' + r.lockout.sec + ' s lockout, and is recorded';
      if (r.enforced === false) bit += '; the latch is advisory -- the plant permits the restart and records it';
      if (r.permissive && r.permissive.enforced) bit += '; the enforced guard here is the permissive ' + r.permissive.expr;
      return bit;
    });

    var state = 'cause-state at reset: not evaluated';
    if (causeState && typeof causeState === 'object') {
      var keys = Object.keys(causeState);
      state = keys.length
        ? 'cause-state at reset: ' + keys.map(function (k) { return k + '=' + causeState[k]; }).join(', ')
        : 'cause-state at reset: nothing observable was supplied';
    }

    return {
      resolved: true, target: target, column: col.id,
      causes: causes.map(function (r) { return r.id; }),
      text: 'INTERLOCK.DEFEAT on ' + target + ' resolves to effect column ' + col.id + ' — ' +
        parts.join(' | ') + '. ' + state + '.',
    };
  }

  function chart() {
    var rows = causes();
    var cols = effects();
    var cellList = cells();
    var covered = {};
    for (var i = 0; i < cellList.length; i++) covered[cellList[i].causeId] = true;
    var orphans = [];
    for (var r = 0; r < rows.length; r++) {
      if (!covered[rows[r].id]) orphans.push(rows[r].id);
    }
    return { rows: rows, cols: cols, cells: cellList, orphans: orphans };
  }

  // ---------------------------------------------------------------- the recorder
  //
  // A plain, private, append-only log. observe() never inspects the matrix and
  // never de-duplicates -- see the API doc above. seen() returns a fresh copy each
  // call so a caller mutating the returned array cannot corrupt the recorder's own
  // state (the recorder never writes to anything it is passed, and nothing it
  // returns is the log itself).

  function createRecorder() {
    var log = [];
    return {
      observe: function (src, cond, simTime) {
        log.push({ src: src, cond: cond, t: simTime });
      },
      seen: function () {
        return log.map(function (ev) { return { src: ev.src, cond: ev.cond, t: ev.t }; });
      },
      reset: function () {
        log = [];
      },
    };
  }

  // ---------------------------------------------------------------- verify()
  //
  // Compares a recorder's seen() log against the six seam:'onTrip' rows. Order and
  // tick, not just membership: the log is walked in the order it was recorded, each
  // event is checked against the declared (src, cond) rows as it is reached, and the
  // first tick a declared row is actually observed at is what SEAM_ROW_UNREACHED's
  // absence records; an event with no matching row is flagged with its own
  // recorded-order position and tick, not folded into a set first. H310_SKIN
  // (seam:'app') is never expected in a seam recorder's log and is excluded from
  // both directions of this check by design (see the header comment).

  function onTripRows() {
    return CAUSES.filter(function (c) { return c.seam === 'onTrip'; });
  }

  function verify(seen) {
    seen = seen || [];
    var declared = {};
    var rows = onTripRows();
    for (var i = 0; i < rows.length; i++) {
      declared[rows[i].src + '|' + rows[i].cond] = rows[i];
    }

    var findings = [];
    var firstTick = {};

    for (var k = 0; k < seen.length; k++) {
      var ev = seen[k];
      var key = ev.src + '|' + ev.cond;
      var row = declared[key];
      if (!row) {
        findings.push({
          code: 'SEAM_TRIP_UNDECLARED',
          severity: 'refuse',
          detail: 'the seam observed ' + ev.src + ' / ' + ev.cond + ' at t=' + ev.t +
            ' (recorder position ' + k + ') with no matching seam:\'onTrip\' row in MATRIX.causes.',
          tags: [ev.src, ev.cond],
        });
      } else if (!Object.prototype.hasOwnProperty.call(firstTick, row.id)) {
        firstTick[row.id] = ev.t;
      }
    }

    for (var j = 0; j < rows.length; j++) {
      var r = rows[j];
      if (!Object.prototype.hasOwnProperty.call(firstTick, r.id)) {
        findings.push({
          code: 'SEAM_ROW_UNREACHED',
          severity: 'refuse',
          detail: 'matrix row ' + r.id + ' (' + r.src + ' / ' + r.cond + ') declares a seam ' +
            'trip that no observation in this recorder ever reached.',
          tags: [r.id, r.src, r.cond],
        });
      }
    }

    return {
      ok: !findings.some(function (f) { return f.severity === 'refuse'; }),
      findings: findings,
    };
  }

  return {
    MATRIX: MATRIX,
    CHART_VISIBILITY: CHART_VISIBILITY,
    causes: causes,
    effects: effects,
    cells: cells,
    createRecorder: createRecorder,
    verify: verify,
    chart: chart,
    annotateDefeat: annotateDefeat,
  };
});
