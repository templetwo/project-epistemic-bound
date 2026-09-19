// @artifact production
/*
 * ESS.DrillArch — the twelve architecture drills (A1-A12) as DATA, plus the
 * evidence-based scorer that reads a journal of ActionEvents and grades it.
 *
 * PURE DATA + PURE FUNCTION. A drill is a plain object: no drill-specific UI code
 * runs it, no DOM, no timers. The scorer is a pure function of (drillId, journal) ->
 * result; called twice with the same journal it returns byte-identical output. The
 * journal must include the app's accepted DRILL.FAULT_PRESENT lifecycle receipt;
 * trainee work before that receipt is deliberately ineligible for credit.
 * (V3-PLAN sections 4 and 6; RESOURCES 2.14 for the instructor/assessment precedent
 * this generalises -- snapshots, upsets, performance assessment -- and RESOURCES 2.3
 * for the console-vs-flex profile distinction A8 and A9 teach.)
 *
 * SCOPE. This file does not wire into the app, does not call src/topology.js or
 * src/fault-engine.js, and does not touch ESS.Kpi or ESS.Training. Stage SA is pure
 * modules; integration is S3/S4's job. See "Coexistence with ESS.Kpi.scoreDrill"
 * below for how the two scorers sit side by side without either one touching the
 * other's inputs.
 *
 * FAULT VOCABULARY. The 13 fault ids below are drill-arch's OWN pinned copy of the
 * fault catalogue in V3-PLAN section 5, in the table's own order. src/fault-engine.js
 * (built in parallel, by a different agent, in the same stage) exports the identical
 * literal list from its own file -- there is no require() between the two modules.
 * The stage-exit suite proves they match with no require-time coupling: each file's
 * own test asserts its list against the same 13 literal strings.
 *
 * ACTION VOCABULARY. Every expectedActions/safetyGate entry below is matched against
 * a journal entry shaped like V3-PLAN section 4's ActionEvent:
 *   { seq, simTime, actor, actionType, target, payload, accepted, reason? }
 * The actionType strings under `ACTION` are this module's own convention -- there is
 * no existing dispatch.js yet to borrow real names from. TRAINING.MARK_EVIDENCE,
 * TRAINING.PIN_COMPARE and TRAINING.SUBMIT_HYPOTHESIS are named directly from
 * V3-PLAN section 6 ("Evidence and hypothesis are first-class commands"). ACK and
 * the three safety-gate action types (MODE.SET, POINT.SUPPRESS, INTERLOCK.DEFEAT)
 * are drill-arch's own names for the corresponding trainee moves; S3 wiring maps the
 * real UI/dispatch actions onto these when the drills go live. Renaming them there
 * is a compatible change as long as this file's own tests are updated with it.
 *
 * NODE REFERENCES. Every node id a drill mentions (fault targets, evidence targets,
 * safety-gate targets) is a real id from a graph built by src/topology.js on the
 * live tag database -- verified in tests/drill-arch.test.js by building the actual
 * graph and resolving every one through Topology.node(). None are guessed.
 *
 * SCORER. scoreDrill(drillId, journal) walks the drill's own `scoringRules` (five
 * categories -- stabilize, evidence, localization, verification, debrief -- whose
 * weights are this drill's EFFECTIVE weights, already resolved, always summing to
 * 100) and, for each category, the fraction of that category's required
 * `expectedActions` matched by an accepted entry at or after the fault-present
 * receipt. Elapsed time has no weighted category of its own: V3-PLAN section 6 caps time's influence to
 * "at most a small weight except where a drill explicitly tests alarm-response
 * urgency", and none of these twelve does, so the honest weight here is zero rather
 * than a fabricated small number. AI/assistant latency never enters the clock either
 * way, so this omission costs nothing.
 *
 * SAFETY GATE. Every drill also carries at least one `safetyGate` rule describing
 * ITS OWN major-unsafe move (V3-PLAN section 6: "defeating an interlock,
 * destabilizing manual moves, MAN-and-abandon"). If any accepted journal entry
 * matches a gate rule, the final score is capped at PASS_MARK - 1 regardless of the
 * raw category total -- a trainee who earns 100/100 on the rubric but trips the gate
 * still fails. The cap, not a zeroed category, is what "regardless of every other
 * point earned" means here: category credit for genuinely-completed work is not
 * erased, the pass/fail line just cannot be crossed while it is armed.
 *
 * Coexistence with ESS.Kpi.scoreDrill: D1-D12 (the legacy drills) flow app metrics
 * gathered by the Component (drill timers, trip flags, alarm load -- Component
 * ~2216-2223) into ESS.Kpi.scoreDrill (src/kpi.js:209), which grades against a
 * six-row DOM/journal-blind metrics object. A1-A12 (this file) grade a completely
 * different input -- the ActionEvent journal itself, never the DOM or the app's
 * drill-timer metrics -- against a five-category rubric. Nothing in this file reads
 * or writes anything ESS.Kpi reads or writes, and nothing in src/kpi.js is touched
 * by this change, so the D-series golden tests (tests/golden-drills.test.js) cannot
 * move: the two scorers' call paths never intersect. A later stage may add a
 * *dispatcher* that looks at whether a running drill's id matches /^D/ or /^A/ and
 * calls one scorer or the other; that dispatcher does not exist yet and is not this
 * file's job to build.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).DrillArch = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ---------------------------------------------------------------- vocabularies

  // V3-PLAN section 5's fault catalogue, thirteen rows, in the table's own order.
  // Frozen: src/fault-engine.js pins the identical literal list independently.
  var FAULT_IDS = Object.freeze([
    'FROZEN_MEASUREMENT',
    'BIASED_MEASUREMENT',
    'NOISY_MEASUREMENT',
    'OPEN_INPUT_BAD_QUALITY',
    'VALVE_RESPONSE_FAILURE',
    'CONTROLLER_LOSS',
    'REDUNDANCY_SWITCHOVER',
    'NET_PATH_DEGRADED',
    'COMMS_PARTITION',
    'SERVER_SERVICE_DEGRADED',
    'STATION_LOSS_PEER',
    'HISTORIAN_GAP',
    'ASSISTANT_LOSS'
  ]);

  var CATEGORIES = Object.freeze(['stabilize', 'evidence', 'localization', 'verification', 'debrief']);

  var DEFAULT_WEIGHTS = Object.freeze({ stabilize: 30, evidence: 25, localization: 20, verification: 15, debrief: 10 });

  var PASS_MARK = 80;
  // Wording convention of src/training.js:35 / src/kpi.js:244, restated as this
  // file's own string -- no cross-require between drill-arch and either module.
  var PASS_LABEL = PASS_MARK + ' % pass mark — this project’s own architecture-drill threshold, independent of any vendor certification';

  // This module's own actionType vocabulary (see file header). Exported so a future
  // dispatch/UI layer can reuse the exact literal strings instead of re-typing them.
  var ACTION = Object.freeze({
    ACK: 'ACK',
    MARK_EVIDENCE: 'TRAINING.MARK_EVIDENCE',
    PIN_COMPARE: 'TRAINING.PIN_COMPARE',
    SUBMIT_HYPOTHESIS: 'TRAINING.SUBMIT_HYPOTHESIS',
    VERIFY: 'TRAINING.VERIFY',
    DEBRIEF: 'TRAINING.DEBRIEF',
    FAULT_PRESENT: 'DRILL.FAULT_PRESENT',
    // major-unsafe vocabulary for safetyGate rules
    MODE_SET: 'MODE.SET',
    POINT_SUPPRESS: 'POINT.SUPPRESS',
    INTERLOCK_DEFEAT: 'INTERLOCK.DEFEAT'
  });

  function round2(v) { return Math.round(v * 100) / 100; }

  /** Object.freeze is shallow -- a drill's nested expectedActions/scoringRules/
   *  faultTimeline/safetyGate entries (and any array-valued rule target, e.g. A4's
   *  three-CM gate) would otherwise stay mutable even though the drill itself is
   *  frozen, which would let any caller holding a reference silently corrupt the
   *  shared DRILLS singleton and break the "same drillId + same journal -> same
   *  result, always" purity this module promises. Freeze all the way down. */
  function deepFreeze(o) {
    if (o && typeof o === 'object' && !Object.isFrozen(o)) {
      Object.getOwnPropertyNames(o).forEach(function (k) { deepFreeze(o[k]); });
      Object.freeze(o);
    }
    return o;
  }

  // ---------------------------------------------------------------- drill factory

  /**
   * Every drill gets the same diagnostic expectedActions (two for evidence, one
   * each for localization, verification and debrief) from a compact spec. Alarm-
   * backed drills add a real ACK as their stabilization action. Architecture-only
   * faults instead declare SAFE_RESTRAINT: completing the whole diagnostic workflow
   * without tripping the drill's major-unsafe gate is the positive evidence that the
   * trainee kept an already-stable process stable. No process alarm is synthesized
   * merely to make the rubric reachable.
   */
  function buildDrill(spec) {
    var primary = spec.primary;
    var stabilizationPolicy = spec.stabilizationPolicy || 'ACK';
    var actions = [];
    if (stabilizationPolicy === 'ACK') actions.push({
        id: 'ACK', category: 'stabilize', required: true, actionType: ACTION.ACK, target: primary,
        description: 'Acknowledge the indication raised at ' + primary + '.'
      });
    actions.push(
      {
        id: 'EV1', category: 'evidence', required: true, actionType: ACTION.MARK_EVIDENCE, target: primary,
        description: 'Mark ' + primary + ' as evidence.'
      },
      {
        id: 'EV2', category: 'evidence', required: true, actionType: ACTION.PIN_COMPARE,
        payloadMatch: { targets: spec.compare.slice() },
        description: 'Pin ' + spec.compare.join(' against ') + ' side by side for comparison.'
      },
      {
        id: 'LOC', category: 'localization', required: true, actionType: ACTION.SUBMIT_HYPOTHESIS,
        payloadMatch: { domain: spec.domain },
        description: 'Submit ' + spec.domain + ' as the failure domain.'
      },
      {
        id: 'VER', category: 'verification', required: true, actionType: ACTION.VERIFY, target: primary,
        description: 'Re-check ' + primary + ' after diagnosis to confirm the picture is resolved or understood.'
      },
      {
        id: 'DEB', category: 'debrief', required: true, actionType: ACTION.DEBRIEF,
        payloadMatch: { correct: true },
        description: 'Answer the debrief question correctly: cause vs symptom for this drill.'
      }
    );

    var weights = {};
    CATEGORIES.forEach(function (c) { weights[c] = (spec.weights && spec.weights[c] !== undefined) ? spec.weights[c] : DEFAULT_WEIGHTS[c]; });
    var scoringRules = CATEGORIES.map(function (c) { return { category: c, weight: weights[c] }; });

    var gate = { id: 'GATE', description: spec.gateDescription };
    Object.keys(spec.gate).forEach(function (k) { gate[k] = spec.gate[k]; });

    return deepFreeze({
      id: spec.id,
      title: spec.title,
      // The internal title is an answer key. Trainee surfaces and PIP receive only
      // this deliberately non-causal label until the exercise is adjudicated.
      traineeTitle: spec.traineeTitle || 'Hidden architecture diagnosis',
      stabilizationPolicy: stabilizationPolicy,
      objectives: spec.objectives.slice(),
      basePreset: spec.basePreset,
      trigger: { type: 'DRILL_START', description: spec.triggerNote || 'Drill begins once the base preset has settled; fault timing below is relative to drill start.' },
      faultTimeline: spec.faultTimeline.map(function (f) {
        var step = { tSec: f.tSec, faultId: f.faultId, targets: f.targets.slice(), note: f.note };
        if (f.magnitude != null) step.magnitude = f.magnitude;
        if (f.direction != null) step.direction = f.direction;
        return step;
      }),
      expectedActions: actions,
      scoringRules: scoringRules,
      safetyGate: [gate],
      completionRules: spec.completionRules || [
        { id: 'HYPOTHESIS_AND_DEBRIEF', description: 'Completes once ' + spec.domain + ' is submitted as the failure domain and the debrief question is answered correctly.' }
      ],
      abortRules: spec.abortRules || [
        { id: 'PROCESS_TRIP', description: 'A real trip on any equipment during the drill aborts it for review; an aborted run is not scored as a pass or a fail.' }
      ],
      hints: spec.hints.slice(),
      // Canonical registry form is RESOURCES-<section>, matching src/topology.js and
      // resolved by tests/provenance.test.js against docs/RESOURCES.md. An internal spec
      // section is NOT a public source and cannot discharge release gate 5, so the
      // fallback cites the training-assessment precedent rather than V3-PLAN.
      sourceBasis: (spec.sourceBasis || ['RESOURCES-2.14']).slice()
    });
  }

  // ---------------------------------------------------------------- the twelve

  var DRILLS = Object.freeze([
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): the CBE30338 gravity-drained
      // tank model supplies the real FV102 discharge flow the frozen reading contradicts;
      // standards for measurement quality.
      sourceBasis: ['RESOURCES-4.6', 'RESOURCES-2.19'],
      id: 'A1', title: 'Frozen flow measurement',
      objectives: [
        'Distinguish a frozen/stuck measurement from a genuine loss of flow.',
        'Use the valve position, not just the PV, as independent evidence.'
      ],
      basePreset: 'U1_SS',
      primary: 'XMTR-FIC102', domain: 'FIELD', compare: ['XMTR-FIC102', 'VLV-FV102'],
      faultTimeline: [{ tSec: 60, faultId: 'FROZEN_MEASUREMENT', targets: ['XMTR-FIC102'], note: 'FIC102 transmitter output freezes at its pre-fault value; the flow loop keeps calling for correction.' }],
      gate: { actionType: 'MODE.SET', target: 'CM-CM2_FIC102', payloadMatch: { mode: 'MAN' } },
      gateDescription: 'Forcing FIC102 to MAN and driving the valve open from a frozen reading, without first checking whether the field element is even moving, is a MAN-and-abandon move on a measurement problem, not a flow problem.',
      hints: [
        'A frozen PV does not move even when the valve does. Check the valve position, not just the trend.',
        'This bridged exercise reports BADPV and sheds the loop; use valve position to distinguish the frozen measurement from a real loss of flow.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): channel/quality handling per standards; I/O and controller platform concepts.
      sourceBasis: ['RESOURCES-2.19', 'RESOURCES-2.16'],
      id: 'A2', title: 'Input channel failure',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Distinguish a field-device problem from an I/O-path problem.',
        'Use the field element’s own diagnostics as the tie-breaker.'
      ],
      basePreset: 'U2_FEED',
      primary: 'AI-FIC211', domain: 'IO', compare: ['AI-FIC211', 'XMTR-FIC211'],
      faultTimeline: [{ tSec: 60, faultId: 'OPEN_INPUT_BAD_QUALITY', targets: ['AI-FIC211'], note: 'FIC211 input channel reports bad quality; the field transmitter itself is not at fault.' }],
      gate: { actionType: 'POINT.SUPPRESS', target: 'CM-CM10_FIC211', payloadMatch: { arg: 'ON' } },
      gateDescription: 'Taking FIC211 out of service to silence the bad-quality shed, instead of checking the field element first, defeats the very safeguard (SHEDHOLD) this drill is teaching the trainee to read.',
      hints: [
        'Bad quality on the channel does not automatically mean the field device is broken.',
        'Compare the channel status against the field element’s own diagnostics before concluding where the fault lives.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): ISA-18.2 state and quality model
      // -- GOOD quality is a channel claim, not a correctness proof; the CBE30338 gravity-drained
      // tank model supplies the true TK-101 level that contradicts the biased LIC101 reading.
      sourceBasis: ['RESOURCES-2.5', 'RESOURCES-4.6'],
      id: 'A3', title: 'Bias with GOOD quality',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Recognise that GOOD quality is not proof of correctness.',
        'Independently verify a slowly-biasing measurement rather than trusting its quality flag.'
      ],
      basePreset: 'U1_SS',
      primary: 'XMTR-LIC101', domain: 'FIELD', compare: ['XMTR-LIC101', 'CM-CM1_LIC101'],
      faultTimeline: [{ tSec: 90, faultId: 'BIASED_MEASUREMENT', targets: ['XMTR-LIC101'], note: 'LIC101 develops a slow bias; no bad-quality flag is ever raised.' }],
      gate: { actionType: 'POINT.SUPPRESS', target: 'CM-CM1_LIC101', payloadMatch: { arg: 'ON' } },
      gateDescription: 'Suppressing the LIC101 alarm because the point still reads GOOD quality, instead of independently verifying the level, is exactly the trap this drill sets.',
      hints: [
        'A bias this gradual will not trip a quality flag. Quality is not the test that matters here.',
        'What else in the plant should move with level, and does it agree with LIC101?'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): redundant controller platform concepts.
      sourceBasis: ['RESOURCES-2.16'],
      id: 'A4', title: 'Redundancy switchover',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Recognise a degraded-redundancy transient for what it is.',
        'Avoid overreacting to a brief, self-correcting event.'
      ],
      basePreset: 'U3_HILOAD',
      primary: 'CTRL-U3', domain: 'CONTROL', compare: ['CTRL-U3', 'CEE-U3'],
      faultTimeline: [{ tSec: 60, faultId: 'REDUNDANCY_SWITCHOVER', targets: ['CTRL-U3'], note: 'U3’s primary controller fails over to its standby; the switch is brief and the process stays controlled throughout.' }],
      gate: { actionType: 'MODE.SET', target: ['CM-CM16_FIC310', 'CM-CM19_FIC313', 'CM-CM17_TIC311'], payloadMatch: { mode: 'MAN' } },
      gateDescription: 'Seizing manual control across U3’s loops for a brief, self-correcting redundancy switchover is the overreaction this drill penalises -- restraint is the correct response.',
      hints: [
        'Did the process actually leave setpoint, or only the indication blip?',
        'A switchover event in the system log is not the same thing as a control failure.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): controller platform concepts; server/SCADA architecture for what goes stale together.
      sourceBasis: ['RESOURCES-2.16', 'RESOURCES-2.13'],
      id: 'A5', title: 'Controller loss',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Recognise a common-cause pattern: many points invalid together, not many independent faults.',
        'Localise the fix at the controller, not at each affected loop separately.'
      ],
      basePreset: 'U2_REACT',
      primary: 'CTRL-U2', domain: 'CONTROL', compare: ['CM-CM10_FIC211', 'CM-CM12_TIC213'],
      faultTimeline: [{ tSec: 60, faultId: 'CONTROLLER_LOSS', targets: ['CTRL-U2'], note: 'U2’s controller is lost; every control module it executes goes stale together.' }],
      weights: { stabilize: 25, evidence: 25, localization: 30, verification: 10, debrief: 10 },
      gate: { actionType: 'INTERLOCK.DEFEAT', target: 'DRV-M202' },
      gateDescription: 'Defeating the M202 agitator interlock to force a restart while the whole U2 controller domain is stale treats a common-cause failure as a single-equipment problem -- exactly the wrong localisation.',
      hints: [
        'FIC211, TIC213 and the rest did not all break independently at the same second. What do they share?',
        'The fix that helps every affected loop at once lives one layer up from the loops themselves.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): redundant path concepts; standards for degraded-vs-failed reporting.
      sourceBasis: ['RESOURCES-2.16', 'RESOURCES-2.19'],
      id: 'A6', title: 'Single network path degradation',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Distinguish degraded redundancy from a total communications loss.',
        'Show restraint: data stays fresh, so no corrective action is needed.'
      ],
      basePreset: 'U1_SS',
      primary: 'NET-U1-B', domain: 'NETWORK', compare: ['NET-U1-A', 'NET-U1-B'],
      faultTimeline: [{ tSec: 45, faultId: 'NET_PATH_DEGRADED', targets: ['NET-U1-B'], note: 'One of U1’s two redundant network paths degrades; the other keeps carrying live data.' }],
      weights: { stabilize: 20, evidence: 30, localization: 25, verification: 15, debrief: 10 },
      gate: { actionType: 'MODE.SET', target: 'CM-CM6_LIC401', payloadMatch: { mode: 'MAN' } },
      gateDescription: 'Seizing manual control of an unrelated U1 loop because a redundancy indicator degraded, while data stayed fresh throughout, is overreaction, not restraint.',
      hints: [
        'Check both paths, not just the one the alarm points at.',
        'Redundancy degraded is not the same event as redundancy lost.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): path loss, server architecture and the stale-data pattern a partition produces.
      sourceBasis: ['RESOURCES-2.16', 'RESOURCES-2.13', 'RESOURCES-2.19'],
      id: 'A7', title: 'Communications partition',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Distinguish a communications failure from a process upset.',
        'Recognise the common stale-data signature across an entire unit’s points.'
      ],
      basePreset: 'U3_HILOAD',
      primary: 'NET-U3-A', domain: 'NETWORK', compare: ['CM-CM16_FIC310', 'CM-CM17_TIC311'],
      faultTimeline: [{ tSec: 60, faultId: 'COMMS_PARTITION', targets: ['NET-U3-A', 'NET-U3-B'], note: 'Both of U3’s redundant network paths are lost together; U3’s points go stale as a single pattern.' }],
      gate: { actionType: 'POINT.SUPPRESS', target: 'CM-CM16_FIC310', payloadMatch: { arg: 'ON' } },
      gateDescription: 'Suppressing the stale-data alarms across U3 instead of recognising the shared partition pattern hides the very evidence this drill is testing for.',
      hints: [
        'One stale point could be a coincidence. Several at once, across one unit, is a pattern.',
        'This is what a single-path degradation (A6) would look like if it happened on both paths at once.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): server/SCADA architecture; station HMI concepts -- the console-vs-flex split this drill exists to teach.
      sourceBasis: ['RESOURCES-2.13', 'RESOURCES-2.1'],
      id: 'A8', title: 'Server / flex service loss',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Distinguish a server (SERVICE) failure domain from a controller (CONTROL) failure domain.',
        'Use the console profile, which bypasses the server, as the tie-breaker.'
      ],
      basePreset: 'U1_SS',
      primary: 'SVC-SERVER', domain: 'SERVICE', compare: ['STN-CONSOLE', 'STN-FLEX'],
      faultTimeline: [{ tSec: 60, faultId: 'SERVER_SERVICE_DEGRADED', targets: ['SVC-SERVER'], note: 'The data server degrades; the flex profile goes stale while the console profile, which reads the controller directly, stays correct.' }],
      gate: { actionType: 'MODE.SET', target: 'CM-CM7_PIC401', payloadMatch: { mode: 'MAN' } },
      gateDescription: 'Seizing manual control of PIC401 because the flex-profile display looked stale, when the console profile and the controller behind it were correct throughout, mislocates a server fault as a control fault.',
      hints: [
        'If the console profile still shows a good value, the controller is not the problem.',
        'This simulator has one physical station; console and flex are two view profiles on it (RESOURCES 2.3).'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): station and HMI concepts: one operator position down is not a plant down.
      sourceBasis: ['RESOURCES-2.1', 'RESOURCES-2.3'],
      id: 'A9', title: 'Local station failure',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Recognise that one HMI going dark is not a plant-wide event.',
        'Distinguish a station-level failure from the server fault it can resemble (A8).'
      ],
      basePreset: 'U1_SS',
      primary: 'STN-FLEX', domain: 'HMI', compare: ['STN-CONSOLE', 'STN-FLEX'],
      faultTimeline: [{ tSec: 60, faultId: 'STATION_LOSS_PEER', targets: ['STN-FLEX'], note: 'The simulated peer station stops updating; the server and every controller stay healthy.' }],
      weights: { stabilize: 20, evidence: 25, localization: 25, verification: 20, debrief: 10 },
      gate: { actionType: 'MODE.SET', target: 'CM-CM4_TIC202', payloadMatch: { mode: 'MAN' } },
      gateDescription: 'Seizing manual control of TIC202 station-wide because one peer HMI stopped updating overreacts to a single-station failure with a plant-wide response.',
      hints: [
        'The same two stations you compared in A8 look identical here -- so which node is actually unhealthy?',
        'Check the server’s own health before concluding the station itself is the failure domain.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): history collection architecture; HMI trend presentation.
      sourceBasis: ['RESOURCES-2.13', 'RESOURCES-2.3'],
      id: 'A10', title: 'Historian gap',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Distinguish live control health from historical data availability.',
        'Recognise a collection gap as an INFORMATION-layer fault, not a control-layer one.'
      ],
      basePreset: 'U1_SS',
      primary: 'SVC-HISTORY', domain: 'INFORMATION', compare: ['CM-CM1_LIC101', 'HIST-STORE'],
      faultTimeline: [{ tSec: 60, faultId: 'HISTORIAN_GAP', targets: ['SVC-HISTORY'], note: 'History collection stops for an interval; live values and control are unaffected throughout.' }],
      gate: { actionType: 'MODE.SET', target: 'CM-CM12_TIC213', payloadMatch: { mode: 'MAN' } },
      gateDescription: 'Seizing manual control of TIC213 because a trend shows a gap, when the live value behind it was correct the whole time, mistakes a historian fault for a control fault.',
      hints: [
        'Compare a live value against its own trend for the same interval.',
        'A gap in the trend and a gap in control are two different claims -- check both before assuming either.'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): operations-assistant concept -- advisory, never control.
      sourceBasis: ['RESOURCES-2.15'],
      id: 'A11', title: 'Assistant loss',
      stabilizationPolicy: 'SAFE_RESTRAINT',
      objectives: [
        'Recognise the Ops Assistant as advisory, not load-bearing.',
        'Operate normally with decision support unavailable or delayed.'
      ],
      basePreset: 'U1_SS',
      primary: 'APP-ASSIST', domain: 'INFORMATION', compare: ['APP-ASSIST', 'STN-CONSOLE'],
      faultTimeline: [{ tSec: 60, faultId: 'ASSISTANT_LOSS', targets: ['APP-ASSIST'], note: 'The Ops Assistant becomes unavailable mid-upset; process indication and control are unaffected.' }],
      gate: { actionType: 'MODE.SET', target: 'CM-CM19_FIC313', payloadMatch: { mode: 'MAN' } },
      gateDescription: 'Seizing manual control of FIC313 because the assistant stopped responding, when nothing about process indication or control changed, treats losing advice as losing control.',
      hints: [
        'The assistant reads the same data you do -- it does not supply any data control depends on.',
        'If it is unavailable, what changes for the operator besides not having its suggestions?'
      ]
    }),
    buildDrill({
      // Provenance for THIS drill's concepts (release gate 5): control-system
      // architecture for tracing a bad field measurement through a cascade, plus
      // the Henson/Seborg exothermic CSTR for the controller/process consequence
      // -- R-201 really warms when the cascade answers the biased TIC201.
      sourceBasis: ['RESOURCES-2.7', 'RESOURCES-4.4'],
      id: 'A12', title: 'Causal measurement bias',
      objectives: [
        'Trace a biased temperature measurement through the cascade controller to its process consequence.',
        'Localise the fault to the FIELD layer by separating the bad reading from the controller’s correct response to it.'
      ],
      basePreset: 'U1_HIFEED',
      primary: 'XMTR-TIC201', domain: 'FIELD', compare: ['XMTR-TIC201', 'CM-CM3_TIC201'],
      faultTimeline: [{ tSec: 120, faultId: 'BIASED_MEASUREMENT', targets: ['XMTR-TIC201'], magnitude: 2, direction: 'LOW', note: 'TIC201 biases low while R-201 is already running hot at high feed. The master controller responds to the bad reading by raising the cascade demand, so the jacket and real reactor warm relative to an unbiased run.' }],
      gate: { actionType: 'POINT.SUPPRESS', target: 'CM-CM3_TIC201', payloadMatch: { arg: 'ON' } },
      gateDescription: 'Suppressing TIC201 because its indication conflicts with independent process evidence hides the symptom without locating or correcting the biased field measurement.',
      hints: [
        'Watch what master TIC201 asks of cascade slave TIC202 after the indicated temperature begins to fall.',
        'The controller can respond correctly to a bad input. Separate the field measurement fault from the controller and process consequences it causes.'
      ]
    })
  ]);

  // ---------------------------------------------------------------- lookups

  var BY_ID = {};
  DRILLS.forEach(function (d) { BY_ID[d.id] = d; });

  function drillIds() { return DRILLS.map(function (d) { return d.id; }); }
  function drillById(id) { return BY_ID[id] || null; }

  function nodeRefsOf(drill) {
    var out = [], seen = {};
    function add(v) {
      if (v === undefined || v === null) return;
      if (Array.isArray(v)) { v.forEach(add); return; }
      if (typeof v === 'string' && !seen[v]) { seen[v] = true; out.push(v); }
    }
    (drill.faultTimeline || []).forEach(function (f) { add(f.targets); });
    (drill.expectedActions || []).forEach(function (a) {
      add(a.target);
      if (a.actionType === ACTION.PIN_COMPARE && a.payloadMatch) add(a.payloadMatch.targets);
    });
    (drill.safetyGate || []).forEach(function (g) { add(g.target); });
    return out;
  }

  function faultIdsOf(drill) {
    var out = [], seen = {};
    (drill.faultTimeline || []).forEach(function (f) { if (!seen[f.faultId]) { seen[f.faultId] = true; out.push(f.faultId); } });
    return out;
  }

  function domainsOf(drill) {
    var out = [];
    (drill.expectedActions || []).forEach(function (a) {
      if (a.actionType === ACTION.SUBMIT_HYPOTHESIS && a.payloadMatch && a.payloadMatch.domain) out.push(a.payloadMatch.domain);
    });
    return out;
  }

  // ---------------------------------------------------------------- matching

  function targetMatches(entryTarget, ruleTarget) {
    if (ruleTarget === undefined) return true;
    if (Array.isArray(ruleTarget)) return ruleTarget.indexOf(entryTarget) >= 0;
    return entryTarget === ruleTarget;
  }

  function payloadMatches(entryPayload, match) {
    if (!match) return true;
    var p = entryPayload || {};
    return Object.keys(match).every(function (k) {
      var want = match[k], got = p[k];
      if (Array.isArray(want)) {
        if (!Array.isArray(got) || got.length !== want.length) return false;
        var a = want.slice().sort(), b = got.slice().sort();
        return a.every(function (v, i) { return v === b[i]; });
      }
      return got === want;
    });
  }

  /** Does journal entry `e` (an ActionEvent) satisfy rule `r` (an expectedActions or
   *  safetyGate entry)? A rejected action (accepted === false) never matches -- it
   *  did not actually happen in the simulated world. */
  function matchAction(e, r) {
    if (!e || !r) return false;
    if (e.actionType !== r.actionType) return false;
    if (e.accepted === false) return false;
    if (!targetMatches(e.target, r.target)) return false;
    if (!payloadMatches(e.payload, r.payloadMatch)) return false;
    return true;
  }

  function eventCmp(a, b) {
    return a.simTime - b.simTime || (a.seq || 0) - (b.seq || 0);
  }

  function strictlyAfter(e, prior) {
    return !!e && !!prior && eventCmp(e, prior) > 0;
  }

  /**
   * Resolve the causal workflow without judging whether the bound hypothesis is
   * correct. Evidence must precede the binding post-onset hypothesis, verification
   * must follow that hypothesis, and debrief must follow verification. The app uses
   * `debriefReady` to prevent a trainee from finalizing the answer before doing the
   * work; scoreDrill uses the same resolved events so UI and adjudication cannot drift.
   */
  function workflowState(drillId, journal) {
    var drill = drillById(drillId);
    if (!drill) throw new Error('ESS.DrillArch.workflowState: unknown drill id ' + drillId);
    var entries = Array.isArray(journal) ? journal : [];
    var onset = entries.filter(function (e) {
      return e && e.accepted !== false && e.actionType === ACTION.FAULT_PRESENT &&
        e.target === drillId && typeof e.simTime === 'number';
    }).sort(eventCmp)[0] || null;
    var eligible = onset ? entries.filter(function (e) {
      return e && typeof e.simTime === 'number' && eventCmp(e, onset) >= 0;
    }).sort(eventCmp) : [];
    var evidenceRules = drill.expectedActions.filter(function (a) {
      return a.required !== false && a.category === 'evidence';
    });
    var evidenceEvents = evidenceRules.map(function (rule) {
      return eligible.filter(function (e) { return matchAction(e, rule); }).sort(eventCmp)[0] || null;
    });
    var firstHypothesis = eligible.filter(function (e) {
      return e.accepted !== false && e.actionType === ACTION.SUBMIT_HYPOTHESIS;
    }).sort(eventCmp)[0] || null;
    var localizationReady = !!firstHypothesis && evidenceEvents.length > 0 && evidenceEvents.every(function (e) {
      return !!e && strictlyAfter(firstHypothesis, e);
    });
    var verifyRule = drill.expectedActions.filter(function (a) { return a.id === 'VER'; })[0] || null;
    var firstVerification = firstHypothesis && verifyRule ? eligible.filter(function (e) {
      return strictlyAfter(e, firstHypothesis) && matchAction(e, verifyRule);
    }).sort(eventCmp)[0] || null : null;
    var debriefRule = drill.expectedActions.filter(function (a) { return a.id === 'DEB'; })[0] || null;
    var firstDebrief = firstVerification && debriefRule ? eligible.filter(function (e) {
      return strictlyAfter(e, firstVerification) && matchAction(e, debriefRule);
    }).sort(eventCmp)[0] || null : null;
    return {
      onset: onset, eligible: eligible, evidenceEvents: evidenceEvents,
      firstHypothesis: firstHypothesis, localizationReady: localizationReady,
      firstVerification: firstVerification, firstDebrief: firstDebrief,
      debriefReady: !!onset && localizationReady && !!firstVerification
    };
  }

  // ---------------------------------------------------------------- scorer

  /**
   * Score one drill's journal. `journal` is an array of ActionEvent-shaped entries;
   * only category credit for entries with accepted !== false is ever counted.
   * Pure function: same drillId + same journal (by value) => same result, always.
   */
  function scoreDrill(drillId, journal) {
    var drill = drillById(drillId);
    if (!drill) throw new Error('ESS.DrillArch.scoreDrill: unknown drill id ' + drillId);
    var entries = Array.isArray(journal) ? journal : [];
    var workflow = workflowState(drillId, entries);
    var onset = workflow.onset, eligible = workflow.eligible;
    function actionMatched(action) {
      if (action.id === 'LOC') return workflow.localizationReady && matchAction(workflow.firstHypothesis, action);
      if (action.id === 'VER') return !!workflow.firstVerification && matchAction(workflow.firstVerification, action);
      if (action.id === 'DEB') return !!workflow.firstDebrief && matchAction(workflow.firstDebrief, action);
      return eligible.some(function (e) { return matchAction(e, action); });
    }

    var gateHits = (drill.safetyGate || []).filter(function (g) { return entries.some(function (e) { return matchAction(e, g); }); });
    var gated = gateHits.length > 0;

    var rows = drill.scoringRules.map(function (rule) {
      if (rule.category === 'stabilize' && drill.stabilizationPolicy === 'SAFE_RESTRAINT') {
        var completion = drill.expectedActions.filter(function (a) { return a.required !== false; });
        var completed = completion.length > 0 && completion.every(actionMatched);
        var safe = completed && !gated;
        return {
          category: rule.category, weight: rule.weight,
          required: 1, matched: safe ? 1 : 0, fraction: safe ? 1 : 0,
          earned: safe ? rule.weight : 0
        };
      }
      var acts = drill.expectedActions.filter(function (a) { return a.category === rule.category; });
      var required = acts.filter(function (a) { return a.required !== false; });
      var matched = required.filter(actionMatched);
      var fraction = required.length ? matched.length / required.length : 1;
      return {
        category: rule.category, weight: rule.weight,
        required: required.length, matched: matched.length, fraction: fraction,
        earned: round2(rule.weight * fraction)
      };
    });

    var rawScore = round2(rows.reduce(function (a, r) { return a + r.earned; }, 0));
    var clamped = Math.max(0, Math.min(100, rawScore));

    var missingRequired = drill.expectedActions.filter(function (a) {
      return a.required !== false && !actionMatched(a);
    }).map(function (a) { return a.id; });
    var complete = !!onset && missingRequired.length === 0;
    var score = Math.round(gated ? Math.min(clamped, PASS_MARK - 1) : clamped);

    return {
      drillId: drillId,
      score: score,
      pass: score >= PASS_MARK && complete && !gated,
      passMark: PASS_MARK,
      passLabel: PASS_LABEL,
      gated: gated,
      gateHits: gateHits.map(function (g) { return g.id; }),
      causalReady: !!onset,
      workflowReady: workflow.debriefReady,
      missingRequired: missingRequired,
      breakdown: rows
    };
  }

  return {
    FAULT_IDS: FAULT_IDS,
    CATEGORIES: CATEGORIES,
    DEFAULT_WEIGHTS: DEFAULT_WEIGHTS,
    PASS_MARK: PASS_MARK,
    PASS_LABEL: PASS_LABEL,
    ACTION: ACTION,
    workflowState: workflowState,
    DRILLS: DRILLS,
    drillIds: drillIds,
    drillById: drillById,
    nodeRefsOf: nodeRefsOf,
    faultIdsOf: faultIdsOf,
    domainsOf: domainsOf,
    matchAction: matchAction,
    scoreDrill: scoreDrill
  };
});
