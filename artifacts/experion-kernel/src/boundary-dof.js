// @artifact production
/*
 * ESS.BoundaryDof -- the boundary-stream declaration and pre-drill DOF check
 * (V3-PLAN / CONVERGENCE-SPEC item 6, work item W1, acceptance 3.4.6).
 *
 * PURE. No DOM, no timers, no globals read, no Math.random / ctx.rand / ctx.rand4,
 * no Date.now / wall clock. Everything arrives as an argument and the module hands
 * back plain data; the caller (app integration, W1 section 4) decides what to do
 * with a refusal.
 *
 * Two lanes, kept deliberately separate so either can be removed on its own:
 *
 *   Lane A -- boundary-stream specification (checkBoundaries). The declared
 *     contract over the plant's one real inter-unit material boundary, U3 -> U4
 *     (BOUNDARY_STREAMS). Structurally always passes today -- the models are
 *     flow-driven, so nothing can contend for a boundary variable -- and the lane
 *     says so in its own output (BOUNDARY_SPEC_STRUCTURAL) rather than implying it
 *     proved more than it did. It becomes load-bearing the moment a future pressure-
 *     network solve (item 1) gives a boundary var spec:'pressure' instead of 'flow'.
 *   Lane B -- control-loop specification integrity (checkLoopSpec). The lane with
 *     teeth today: a cascade master driving a slave that isn't listening
 *     (CASCADE_OPEN), and a loop in CAS with no master to follow (CASCADE_NO_MASTER).
 *
 * ISLANDS records the two units the mapping pass found to have NO P-field coupling
 * across a unit boundary, so nothing here -- or anything built on it later -- invents
 * a coupling that does not exist.
 *
 * API
 *   PLANT_MAP                the declared plant map artifact: which units are coupled
 *                            and which are not, derived by reading src/models.js field
 *                            by field. Item 1 (the pressure-flow network) READS this
 *                            map rather than inferring couplings. See its comment.
 *   BOUNDARY_STREAMS         the declared lane-A data: the one U3 -> U4 boundary and
 *                            its three variables. Also PLANT_MAP.boundaries.
 *   ISLANDS                  ['U1','U2'] with the reason each has zero cross-unit
 *                            P-field coupling.
 *   checkBoundaries(P)       -> {ok, lane:'A', findings:[...], note}
 *   checkLoopSpec(L)         -> {ok, lane:'B', findings:[...]}
 *   check(P, L)              -> {ok, findings:[...]}   both lanes, concatenated
 *   formatRefusal(result)    -> string   one operator-readable line naming the
 *                              first finding (the first 'refuse' one if there is
 *                              one, else the first finding of any severity)
 *
 * Every finding is {code, severity, detail, tags}. severity is 'refuse' or 'note';
 * only 'refuse' sets the result's ok to false. tags names the loop/variable
 * identifiers involved, for whatever surface (journal, callout) renders the finding.
 *
 * Sources: RESOURCES-7.1 (Luyben, Process Modeling, Simulation and Control for
 * Chemical Engineers, 2nd ed. 1990) for degrees-of-freedom analysis and the
 * verified-steady-state discipline; RESOURCES-7.3 (Seborg, Edgar, Mellichamp &
 * Doyle, Process Dynamics and Control, 4th ed. 2016) for DOF analysis of control
 * loops specifically -- lane B's citation, not an invented one. Both are
 * CITED-NOT-HELD: cited here for method and framing only. No equation, default or
 * numeric value in this module is taken from either source -- every number in
 * BOUNDARY_STREAMS comes from this repository's own calibrated PARAMS and is
 * labelled nominal / Temple-set below, not measured from a cited work.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).BoundaryDof = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ---------------------------------------------------------------- lane A data

  var BOUNDARY_STREAMS = [{
    id: 'U3-U4',
    from: 'U3', to: 'U4',
    note: 'the only inter-unit material boundary in the simulator',
    vars: [
      { name: 'qfeed', field: 'h.f', kind: 'flow', eu: 'M3/H', spec: 'flow', nominal: 40,
        producer: 'firedHeater (src/models.js:549)', consumer: 'separator (src/models.js:648)' },
      { name: 'Tpre', field: 'h.pre', kind: 'temperature', eu: 'DEG C', spec: 'flow', nominal: 320,
        producer: 'firedHeater (src/models.js:565)', consumer: 'separator (src/models.js:654)' },
      { name: 'Tbed', field: 'h.bed', kind: 'temperature', eu: 'DEG C', spec: 'flow', nominal: 413,
        producer: 'fixedBed (src/models.js:591)', consumer: 'separator (src/models.js:654)' },
      // nominal provenance, so no reader mistakes these for cited values:
      //   qfeed 40  -- the U4 design point, src/models.js PARAMS.U4 header comment ("U3 feed 40 m3/h")
      //   Tpre 320 / Tbed 413 -- the measured U3_HILOAD steady state (CHANGELOG 3.1.0: "44 / 320 holds
      //   the bed flat at 413 C for an hour"). Temple-set reference points for display only; NOTHING
      //   in either check compares against them.
    ],
  }];

  var ISLANDS = [
    { unit: 'U1', reason: "Unit 01 (TK-101 / R-201 / E-301 / V-401) has zero P-field coupling to " +
        "Unit 03: U3's process feed comes from V.FV310.pos on an independent FIC310 loop, not from " +
        'any U1 output.' },
    { unit: 'U2', reason: 'Unit 02 is fully standalone -- every P.b.* field is written and read ' +
        'only inside its own banner.' },
  ];

  // ---------------------------------------------------------------- the declared plant map
  //
  // THE PLANT MAP IS AN ARTIFACT, not a convenience. It is the simulator's own declaration of
  // which units are coupled and which are not, derived by reading src/models.js field by field
  // rather than assumed from the P&ID or the prose. Anthony's ruling, 2026-09-13:
  //
  //     "Record the topology as a declared plant map artifact: U1 and U2 are islands, U3 to U4
  //      is the only boundary. Item 1 reads that map, it doesn't invent couplings."
  //
  // So this is the contract item 1 (the pressure-driven flow network, v4, gate 8.1) consumes. A
  // pressure-flow network solve must place a node and a resistance for every real coupling and
  // for no imagined one; the failure mode it is most exposed to is inventing a U1 -> U3 stream
  // because a reader assumed a feed train that the code does not have. This map says, in data,
  // that U3 -> U4 is the whole of the inter-unit coupling.
  //
  // It is falsifiable and it is tested: tests/boundary-dof.test.js asserts every declared field
  // path resolves on a real ESS.Models.createState(), so the map cannot drift from the model
  // without a test going red.
  var PLANT_MAP = {
    version: 1,
    asOf: '2026-09-13',
    derivedFrom: 'src/models.js, read field by field at checkpoint dfee660',
    units: ['U1', 'U2', 'U3', 'U4'],
    boundaries: BOUNDARY_STREAMS,
    islands: ISLANDS,
    assertion: 'U3 -> U4 is the only inter-unit material coupling in the simulator. U1 and U2 ' +
      'are islands. Anything building a network across units reads this map; it does not infer ' +
      'couplings from the process prose or the graphic.',
    // Deliberately NOT declared here: instructor and fault inputs read by two units but written
    // by neither unit's step code (P.Tcw, env.Tamb, env.catAct / P.faults.bedact) and the global
    // clock (P.t / P.up). They cross unit code, but they are not material streams and counting
    // them as boundaries would put phantom edges in a future flow network.
    notBoundaries: ['P.Tcw', 'env.Tamb', 'env.catAct', 'P.faults.bedact', 'P.t', 'P.up'],
  };

  // ---------------------------------------------------------------- helpers

  function resolvePath(obj, path) {
    var parts = path.split('.');
    var v = obj;
    for (var i = 0; i < parts.length; i++) {
      if (v === null || typeof v === 'undefined') return undefined;
      v = v[parts[i]];
    }
    return v;
  }

  function isFiniteNumber(v) {
    return typeof v === 'number' && isFinite(v);
  }

  // ---------------------------------------------------------------- lane A: checkBoundaries

  function checkBoundaries(P) {
    var findings = [];
    var allNames = [];

    BOUNDARY_STREAMS.forEach(function (stream) {
      stream.vars.forEach(function (v) {
        allNames.push(v.name);
        var val = resolvePath(P, v.field);
        if (!isFiniteNumber(val)) {
          findings.push({
            code: 'BOUNDARY_NOT_FINITE',
            severity: 'refuse',
            detail: stream.id + ' boundary var ' + v.name + ' (P.' + v.field + ') is ' +
              (typeof val === 'undefined' ? 'missing' : 'not a finite number (got ' + String(val) + ')') +
              ' -- written by ' + v.producer + ', read by ' + v.consumer + '.',
            tags: [v.name],
          });
        }
      });
    });

    // Always emitted: this lane cannot fail on over- or under-specification today
    // (every var ships spec:'flow'), and it says so rather than implying otherwise.
    findings.push({
      code: 'BOUNDARY_SPEC_STRUCTURAL',
      severity: 'note',
      detail: "Every declared " + BOUNDARY_STREAMS.map(function (s) { return s.id; }).join(', ') +
        " boundary var ships spec:'flow': the producer fixes the value and the consumer accepts " +
        'it, so contention across this boundary is not constructible today (RESOURCES-7.1 DOF ' +
        "discipline). This is not a pass on stronger grounds than that: it becomes load-bearing " +
        "once a boundary var's spec becomes 'pressure' and a network solve can contend for it.",
      tags: allNames,
    });

    return {
      ok: !findings.some(function (f) { return f.severity === 'refuse'; }),
      lane: 'A',
      findings: findings,
      note: BOUNDARY_STREAMS.map(function (s) { return s.note; }).join('; '),
    };
  }

  // ---------------------------------------------------------------- lane B: checkLoopSpec

  function loopTag(loop, fallback) {
    return (loop && loop.tag) || fallback;
  }

  function checkLoopSpec(L) {
    L = L || {};
    var findings = [];
    var tags = Object.keys(L);

    // CASCADE_OPEN -- walk every loop declaring a slave.
    tags.forEach(function (mTag) {
      var m = L[mTag];
      if (!m || !m.slave) return;
      var s = L[m.slave];
      var mName = loopTag(m, mTag);
      var sName = loopTag(s, m.slave);

      // Exclusion 1: the sequence, not the operator, owns whichever side of this pair
      // is MODEATTR PROGRAM (e.g. FIC211 during FEED, forced MAN -> AUTO by
      // scmRestoreModes -- app:2878). An open-looking cascade on a program-owned mode
      // is not an operator misconfiguration and must not be scored as one.
      var programOwned = m.modeAttr === 'PROGRAM' || (s && s.modeAttr === 'PROGRAM');
      if (programOwned) {
        findings.push({
          code: 'LOOP_SEQUENCE_OWNED',
          severity: 'note',
          detail: (m.modeAttr === 'PROGRAM' ? mName : sName) + ' is MODEATTR PROGRAM: its mode is ' +
            'sequence-owned, not an operator specification, so the ' + mName + ' / ' + sName +
            ' relationship is not scored as a cascade finding.',
          tags: [mName, sName],
        });
        return;
      }

      // Exclusion 2: the slave was shed to MAN on its own bad PV -- a fault response,
      // not a specification choice.
      if (s && s.badPv) {
        findings.push({
          code: 'LOOP_SHED',
          severity: 'note',
          detail: sName + ' is shed to MAN on a bad PV (defaultShed), not on an operator ' +
            'specification choice, so its cascade relationship with master ' + mName + ' is not ' +
            'scored as a cascade finding.',
          tags: [mName, sName],
        });
        return;
      }

      // An open cascade: the master is computing an output nothing consumes.
      //
      // THIS IS A NOTE, NOT A REFUSAL, and the reason is worth keeping. The architect's
      // contract first specified it as 'refuse', on the reading that a master in AUTO plus
      // a slave out of CAS is two specifications for one final element. That reading is
      // wrong, and tests/app-instructor.test.js caught it: that test does
      // setMode('TIC202','MAN') -- taking the jacket slave to MAN while master TIC201 stays
      // AUTO -- and then starts D1. Refusing there blocks a completely legitimate operating
      // state. Taking a slave to MAN while its master tracks is ordinary practice and is
      // drill D6's whole premise (src/models.js:52). In DOF terms it is not over-specified
      // at all: the jacket has exactly ONE specification, the operator's OP, and the master
      // is simply idle, back-calculating through INITMAN (src/pid.js:106-128) so the
      // transfer back to CAS is bumpless. Nothing is ill-posed.
      //
      // It is still worth SAYING at drill start -- "you are starting with the reactor
      // cascade open, the master is not in control" is exactly the kind of thing an
      // instructor wants surfaced, and the board does not otherwise show it. So: reported,
      // never refused.
      var mMode = m.mode;
      var sMode = s ? s.mode : undefined;
      if ((mMode === 'AUTO' || mMode === 'CAS') && sMode !== 'CAS') {
        findings.push({
          code: 'CASCADE_OPEN',
          severity: 'note',
          detail: mName + ' is ' + mMode + ' with slave ' + sName + ' ' +
            (s ? 'in ' + String(sMode) : 'not found') + ': the cascade is open, so ' + mName +
            ' is not in control -- its output tracks the slave through INITMAN rather than ' +
            'driving it. A legitimate state, reported so it is not a surprise mid-drill.',
          tags: [mName, sName],
        });
      }
      // Else: master in MAN (exclusion 3) or the slave is already in CAS -- well-posed,
      // no finding at all.
    });

    // CASCADE_NO_MASTER -- any loop in CAS with no resolvable master.
    tags.forEach(function (sTag) {
      var s = L[sTag];
      if (!s || s.mode !== 'CAS') return;
      var master = s.master ? L[s.master] : undefined;
      if (!s.master || !master) {
        var sName = loopTag(s, sTag);
        findings.push({
          code: 'CASCADE_NO_MASTER',
          severity: 'refuse',
          detail: sName + ' is in CAS with ' +
            (s.master ? 'master ' + s.master + ' not found in the loop table' : 'no master declared') +
            ': the slave waits for a setpoint from nothing.',
          tags: s.master ? [sName, s.master] : [sName],
        });
      }
    });

    // CASCADE_OPEN FIRST (Anthony, 2026-09-13: "Lane B is control-loop configuration,
    // CASCADE_OPEN first"). It is lane B's lead finding -- the one an instructor most wants to
    // see at drill start -- so it is reported ahead of the exclusion notes regardless of the
    // order the walk happened to produce. Refusals are unaffected: formatRefusal() picks the
    // first 'refuse' finding wherever it sits, and ok is a property of the set, not the order.
    var lead = findings.filter(function (f) { return f.code === 'CASCADE_OPEN'; });
    var rest = findings.filter(function (f) { return f.code !== 'CASCADE_OPEN'; });
    var ordered = lead.concat(rest);

    return {
      ok: !ordered.some(function (f) { return f.severity === 'refuse'; }),
      lane: 'B',
      findings: ordered,
    };
  }

  // ---------------------------------------------------------------- both lanes

  function check(P, L) {
    var a = checkBoundaries(P);
    var b = checkLoopSpec(L);
    return {
      ok: a.ok && b.ok,
      findings: a.findings.concat(b.findings),
    };
  }

  function formatRefusal(result) {
    var findings = (result && result.findings) || [];
    var first = null;
    for (var i = 0; i < findings.length; i++) {
      if (findings[i] && findings[i].severity === 'refuse') { first = findings[i]; break; }
    }
    if (!first) first = findings[0];
    if (!first) return 'BOUNDARY/DOF CHECK: no findings.';
    return first.code + ': ' + first.detail;
  }

  return {
    PLANT_MAP: PLANT_MAP,
    BOUNDARY_STREAMS: BOUNDARY_STREAMS,
    ISLANDS: ISLANDS,
    checkBoundaries: checkBoundaries,
    checkLoopSpec: checkLoopSpec,
    check: check,
    formatRefusal: formatRefusal,
  };
});
