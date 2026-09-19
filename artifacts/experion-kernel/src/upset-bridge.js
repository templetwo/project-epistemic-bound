// @artifact production
/*
 * ESS.UpsetBridge -- the strangler seam between the twelve legacy instructor upsets
 * (ESS.Instructor.upsetDefs()) and the v3 fault engine (ESS.FaultEngine). Deliberately
 * its own module and not part of src/fault-engine.js: the fault engine is pure and knows
 * nothing about legacy upsets, while THIS module IS the seam, and naming it keeps the
 * seam visible instead of buried inside another module's internals (V3-PLAN addendum,
 * architect decision D2; the lead's shared contract for S2).
 *
 * THE CLASSIFYING PRINCIPLE (architect ruling, 2026-08-30, tests/upset-class-honesty.test.js):
 * is a COMPONENT OF THE MODELLED ARCHITECTURE itself faulty?
 *   yes -> ARCHITECTURE: a real modelled component is faulty; it gets a fault id and a
 *          topology location, because an architecture fault the ARCH view cannot place
 *          teaches nothing.
 *   no  -> PROCESS: the architecture is intact and something else went wrong -- the
 *          plant, a utility, a process condition -- however dramatic the symptom. A
 *          PROCESS disturbance gets NEITHER a fault id NOR a topology node: marking a
 *          node faulted here would teach the trainee that the control system broke when
 *          it reported the plant correctly.
 *
 * THE 3/9 SPLIT, verified against src/models.js and src/topology.js:
 *   ARCHITECTURE:
 *     xmtr  -> FROZEN_MEASUREMENT     on XMTR-FIC102 (the transmitter itself is faulty)
 *     drift -> BIASED_MEASUREMENT     on XMTR-LIC101 (the transmitter itself is faulty)
 *     stick -> VALVE_RESPONSE_FAILURE on VLV-TV202   (the valve itself is faulty)
 *   PROCESS (no topology node -- invisible to the ARCH view, by design):
 *     surge, pump, cool, vap, air, rxn, foul, agit, bedact
 *
 * TWO BAITS THIS MODULE DELIBERATELY DOES NOT TAKE (tests/upset-class-honesty.test.js
 * pins both):
 *   - `pump`/`agit` (P-101 / M-202 trips) have real, same-named MOTOR nodes in the graph
 *     (DRV-P101, DRV-M202), and MOTOR is a legal FROZEN/BIASED/NOISY_MEASUREMENT target,
 *     so wiring either upset to its matching motor node would typecheck, activate
 *     cleanly and stay green -- and be wrong. A tripped motor is the plant stopping, a
 *     measurement component is not lying, so both stay PROCESS with no topology node.
 *   - `air` (instrument air loss) presents at FIELD-layer valve nodes -- src/models.js:252
 *     drives every valve to `v.fail`, its DESIGNED fail-safe position -- which LOOKS
 *     architectural but is the architecture working correctly. `air` stays PROCESS with
 *     no topology node; that IS the lesson (a trainee inspects I/O, controller and
 *     network, finds them healthy, and correctly concludes the answer is not in the
 *     architecture).
 *
 * API
 *   CLASSES                    ['ARCHITECTURE', 'PROCESS']
 *   UPSET_CLASS                 { <all twelve upsetDefs() keys>: a CLASSES member }
 *   classOf(k)                   -> 'ARCHITECTURE' | 'PROCESS' (defaults unknown keys to
 *                                    'PROCESS': the safe direction -- an upset this module
 *                                    has never heard of gets no topology location either)
 *   faultIdFor(k)                 -> a fault id from ESS.FaultEngine.FAULT_IDS for an
 *                                    ARCHITECTURE upset, or null for PROCESS
 *   topologyTargets(k, graph)      -> [nodeId, ...] -- ALWAYS [] for PROCESS; for
 *                                    ARCHITECTURE, a SET (never assume exactly one member)
 *                                    filtered to node ids that actually exist in `graph`,
 *                                    so a caller can never chain FaultEngine.activate()
 *                                    against a dangling id.
 *
 * NO SIBLING REQUIRE of ESS.FaultEngine or ESS.Topology. The fault ids and node ids below
 * are pinned literals -- matching FAULT_IDS in src/fault-engine.js and the ids
 * src/topology.js's build() derives for these specific tags/valves (id('XMTR',tag),
 * id('VLV',valve)) -- so this module works standalone in the browser exactly as it does
 * under node. Same pattern fault-engine.js and architecture-view-model.js document for
 * the same reason: src/*.js are plain <script> tags, not modules, in both the folder
 * build and the standalone.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).UpsetBridge = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var CLASSES = ['ARCHITECTURE', 'PROCESS'];

  // All twelve of ESS.Instructor.upsetDefs()' keys, exactly. Data, not a comment --
  // tests/upset-class-honesty.test.js reads this map directly.
  var UPSET_CLASS = {
    xmtr: 'ARCHITECTURE',
    drift: 'ARCHITECTURE',
    stick: 'ARCHITECTURE',
    surge: 'PROCESS',
    pump: 'PROCESS',
    cool: 'PROCESS',
    vap: 'PROCESS',
    air: 'PROCESS',
    rxn: 'PROCESS',
    foul: 'PROCESS',
    agit: 'PROCESS',
    bedact: 'PROCESS'
  };

  // Pinned literals -- see the module header's NO SIBLING REQUIRE note. Kept as their own
  // maps (rather than folded into UPSET_CLASS) so a PROCESS key can never accidentally
  // pick up a fault id or a node just by being present in one shared object.
  var FAULT_ID_OF = {
    xmtr: 'FROZEN_MEASUREMENT',
    drift: 'BIASED_MEASUREMENT',
    stick: 'VALVE_RESPONSE_FAILURE'
  };
  var TARGETS_OF = {
    xmtr: ['XMTR-FIC102'],
    drift: ['XMTR-LIC101'],
    stick: ['VLV-TV202']
  };

  function classOf(k) {
    return Object.prototype.hasOwnProperty.call(UPSET_CLASS, k) ? UPSET_CLASS[k] : 'PROCESS';
  }

  function faultIdFor(k) {
    return Object.prototype.hasOwnProperty.call(FAULT_ID_OF, k) ? FAULT_ID_OF[k] : null;
  }

  function topologyTargets(k, graph) {
    var ids = TARGETS_OF[k];
    if (!ids || !ids.length) return [];
    if (!graph || !graph.nodes) return ids.slice();
    return ids.filter(function (id) { return !!graph.nodes[id]; });
  }

  return {
    CLASSES: CLASSES,
    UPSET_CLASS: UPSET_CLASS,
    classOf: classOf,
    faultIdFor: faultIdFor,
    topologyTargets: topologyTargets
  };
});
