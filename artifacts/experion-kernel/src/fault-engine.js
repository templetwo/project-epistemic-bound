// @artifact production
/*
 * ESS.FaultEngine -- composable fault transforms with instructor-only truth.
 *
 * A FaultDefinition is DATA, never an ad-hoc flag scattered through the UI
 * (V3-PLAN sections 0 and 5): { id, domain, targets[], activation, effects[],
 * observableSymptoms[], recovery, conflicts[], difficulty, truthVisibility }.
 * This module registers exactly the thirteen faults the lead's vocabulary pins
 * (FAULT_IDS, frozen, exported so drill-arch can reference them literally without
 * requiring this module -- V3-PLAN addendum, "no cross-require mid-stage").
 *
 * THE CAUSE/SYMPTOM SPLIT IS THE SPINE (V3-PLAN section 3). Three projections read
 * the same engine state:
 *   healthProjection(state, graph) -> trainee view: SYMPTOMS ONLY, keyed by node,
 *     with generic health-derived prose. It never places a fault id, a domain, an
 *     instance id or the literal string "INSTRUCTOR_ONLY" into anything it returns.
 *     Because the exact changed node is still localization truth, the app does not
 *     expose this projection during a live A-drill.
 *   symptomProjection(state, graph) -> authored architecture-drill indications,
 *     detached from the root node and explicitly graded as simulated cues rather
 *     than measured process values. Model-backed process effects remain visible on
 *     their normal board surfaces; this lane covers diagnostic architecture effects.
 *     It carries no fault, domain, instance, or target-node id and cannot highlight
 *     a structural node; observable prose may still name an affected subsystem.
 *   truthProjection(state, graph)  -> instructor view: the active faults themselves,
 *     their domain, target, magnitude and root-cause visibility.
 * Neither projection needs to branch on truthVisibility -- every definition carries
 * the same value ('INSTRUCTOR_ONLY'), so nothing here reads that field to decide
 * behaviour. What makes healthProjection trainee-safe is that its OUTPUT never
 * contains a fault id or instance id, not that its code path avoids the fault list
 * (it cannot: computing health requires knowing which nodes a fault touched).
 *
 * REDUNDANCY IS GROUP-AWARE, NOT A BLIND BLAST-RADIUS WALK. Topology nodes carry
 * `redundancyGroup` (both members of a NET path pair share one, e.g. 'NET-U1').
 * Failing one member marks that node FAILED but does not propagate: the group as a
 * whole still carries the signal, which is what "redundancy degraded, not an outage"
 * means concretely. Only when every member of a group is FAILED does the fault
 * behave like a common-cause failure and propagate downstream via forward reach-
 * ability. A plain forward walk from one path node over-reports here -- everything
 * downstream of NET-U1-A is reachable from it whether or not NET-U1-B is healthy.
 *
 * FIELD/IO faults do not propagate at all. A biased transmitter can wreck a control
 * response while every network and server node stays healthy (V3-PLAN section 3);
 * the point-level control consequence (a shed to MAN, a bad control action) is a
 * model/control-layer concern for S2, not a node-health concern here.
 *
 * DETERMINISM. Engine state is plain JSON: { activeFaults: [...] }, safe to pass
 * through JSON.parse(JSON.stringify(...)) for snapshot/restore with no special
 * handling. No function in this module calls Math.random. The one place a fault
 * needs a value it was not given explicitly (a bias/noise magnitude) takes a seeded
 * generator from the caller (ctx.rand, the same contract as ESS.Models.createRand)
 * and throws rather than falling back to Math.random when neither a magnitude nor
 * a rand function is supplied.
 *
 * NO SIBLING-MODULE DEPENDENCY. This file does not require or reference
 * ESS.Topology (there is no ESS.Topology global under the test harness, and a
 * require() of a sibling src file would not survive the browser/standalone, where
 * every src/*.js is a plain <script>, not a module). The tiny forward-reachability
 * walk below is a deliberate, self-contained duplicate of the same BFS
 * topology.js's blastRadius() runs, operating only on the plain {nodes, edges}
 * graph shape both modules receive as data.
 *
 * API
 *   FAULT_IDS                                  frozen array of the 13 fault ids
 *   FAULT_DEFS                                 frozen map id -> FaultDefinition
 *   getFaultDef(id)                             FaultDefinition or null
 *   createState()                              -> { activeFaults: [] }
 *   activate(state, graph, opts)               -> { state, accepted, reason, instance }
 *     opts: { faultId, targetNodeId, simTime?, magnitude?, rand? }
 *   deactivate(state, opts)                    -> { state, accepted, reason }
 *     opts: { faultId, targetNodeId }
 *   isActive(state, faultId, targetNodeId)     -> bool
 *   listActive(state)                          -> activeFaults[] (read-only copy)
 *   computeHealth(state, graph)                -> { nodeId: HEALTH } over EVERY node
 *   healthProjection(state, graph)             -> trainee view (see above)
 *   symptomProjection(state, graph)            -> root-detached simulated drill cues
 *   truthProjection(state, graph)              -> instructor view (see above)
 *   snapshot(state) / restore(json)            plain JSON round-trip
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).FaultEngine = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ------------------------------------------------------------------ fixed vocabulary
  // Pinned literally so drill-arch can copy this list into its own code/test without
  // requiring this module mid-stage (V3-PLAN addendum).
  var FAULT_IDS = [
    'FROZEN_MEASUREMENT', 'BIASED_MEASUREMENT', 'NOISY_MEASUREMENT',
    // Spec section 5 table order: the IO row precedes the FIELD/IO valve row.
    'OPEN_INPUT_BAD_QUALITY', 'VALVE_RESPONSE_FAILURE',
    'CONTROLLER_LOSS', 'REDUNDANCY_SWITCHOVER',
    'NET_PATH_DEGRADED', 'COMMS_PARTITION',
    'SERVER_SERVICE_DEGRADED',
    'STATION_LOSS_PEER',
    'HISTORIAN_GAP', 'ASSISTANT_LOSS'
  ];

  function deepFreeze(o) {
    if (o && typeof o === 'object' && !Object.isFrozen(o)) {
      Object.getOwnPropertyNames(o).forEach(function (k) { deepFreeze(o[k]); });
      Object.freeze(o);
    }
    return o;
  }

  // def(...) fields beyond the FaultDefinition shape the plan names (targets, domain,
  // activation, effects, observableSymptoms, recovery, conflicts, difficulty,
  // truthVisibility) are engine plumbing, documented per field below:
  //   healthEffect  HEALTH mark applied to the fault's own target node(s)
  //   propagate     'NONE' | 'BLAST' | 'GROUP_AWARE' -- see module header
  //   groupWide     true only for faults whose target is really "the whole
  //                 redundancy group", e.g. a communications partition
  //   magnitudeRange  {min,max,step,eu} or null -- see resolveMagnitude()
  //   targetIds     optional exact-id allow-list, narrower than `targets` (kinds).
  //                 Needed because topology.js gives SVC-SERVER, SVC-ALARM and
  //                 SVC-HISTORY the SAME kind (SERVER_SVC) despite very different
  //                 fan-out; a fault whose documented symptoms name one specific
  //                 service (e.g. HISTORIAN_GAP promises "live values stay
  //                 correct") must not be activatable against a sibling of that
  //                 kind, or the promise breaks silently. null means "any node of
  //                 the declared kind(s)", which is correct for kinds that really
  //                 are interchangeable (TRANSMITTER, VALVE, AI_CH, CONTROLLER,
  //                 NET_PATH, STATION).
  function def(spec) {
    return {
      id: spec.id, domain: spec.domain, targets: spec.targets.slice(),
      activation: spec.activation, effects: spec.effects.slice(),
      observableSymptoms: spec.observableSymptoms.slice(), recovery: spec.recovery,
      conflicts: spec.conflicts.slice(), difficulty: spec.difficulty,
      truthVisibility: 'INSTRUCTOR_ONLY',
      healthEffect: spec.healthEffect, propagate: spec.propagate,
      groupWide: !!spec.groupWide, magnitudeRange: spec.magnitudeRange || null,
      targetIds: spec.targetIds ? spec.targetIds.slice() : null
    };
  }

  var FAULT_DEFS = {
    FROZEN_MEASUREMENT: def({
      id: 'FROZEN_MEASUREMENT', domain: 'FIELD', targets: ['TRANSMITTER', 'MOTOR'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'FREEZE_PV', hook: 'models.js xmtr decay-to-frozen pattern (models.js:327-336)' }],
      observableSymptoms: ['PV static while correlated variables keep moving', 'quality flag stays GOOD'],
      recovery: 'Cleared explicitly by the instructor; the reading resumes tracking the process.',
      conflicts: ['BIASED_MEASUREMENT', 'NOISY_MEASUREMENT'], difficulty: 2,
      healthEffect: 'DEGRADED', propagate: 'NONE'
    }),
    BIASED_MEASUREMENT: def({
      id: 'BIASED_MEASUREMENT', domain: 'FIELD', targets: ['TRANSMITTER', 'MOTOR'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'BIAS_PV', hook: 'measurementBias() supplies a deterministic engineering-unit offset to the model measurement path before PID/alarm evaluation' }],
      observableSymptoms: ['PV inconsistent with correlated evidence', 'quality flag stays GOOD'],
      recovery: 'Cleared explicitly by the instructor; the offset is removed.',
      conflicts: ['FROZEN_MEASUREMENT'], difficulty: 3,
      healthEffect: 'DEGRADED', propagate: 'NONE',
      magnitudeRange: { min: 0.2, max: 5, step: 0.1, eu: '%/MIN' }
    }),
    NOISY_MEASUREMENT: def({
      id: 'NOISY_MEASUREMENT', domain: 'FIELD', targets: ['TRANSMITTER', 'MOTOR'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'SCALE_NOISE', hook: 'n(sigma) multiplier (models.js noiseFn)' }],
      observableSymptoms: ['PV variance up', 'control activity up'],
      recovery: 'Cleared explicitly by the instructor; variance returns to baseline.',
      conflicts: ['FROZEN_MEASUREMENT'], difficulty: 2,
      healthEffect: 'DEGRADED', propagate: 'NONE',
      magnitudeRange: { min: 1, max: 4, step: 0.25, eu: 'x sigma' }
    }),
    VALVE_RESPONSE_FAILURE: def({
      id: 'VALVE_RESPONSE_FAILURE', domain: 'FIELD', targets: ['VALVE'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'STICK_VALVE', hook: 'V[x].stuck (models.js moveValves)' }],
      observableSymptoms: ['OP moves', 'position and correlated variables do not follow'],
      recovery: 'Cleared explicitly by the instructor; the valve resumes following demand.',
      conflicts: [], difficulty: 3,
      healthEffect: 'FAILED', propagate: 'NONE'
    }),
    OPEN_INPUT_BAD_QUALITY: def({
      id: 'OPEN_INPUT_BAD_QUALITY', domain: 'IO', targets: ['AI_CH'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'BAD_QUALITY_SHED', hook: 'l.badPv + defaultShed(l,ctx) honouring SHEDHOLD/SHEDLOW/SHEDHIGH/SHEDSAFE (models.js:231)' }],
      observableSymptoms: ['BADPV', 'quality flag set', 'loop sheds per its configured SHED behaviour'],
      recovery: 'Cleared explicitly by the instructor; the channel returns GOOD quality.',
      conflicts: [], difficulty: 2,
      healthEffect: 'FAILED', propagate: 'NONE'
    }),
    CONTROLLER_LOSS: def({
      id: 'CONTROLLER_LOSS', domain: 'CONTROL', targets: ['CONTROLLER'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'STALE_GROUP', hook: 'symptomProjection cue lane; topology health only, no process-state mutation' }],
      observableSymptoms: ['a correlated group of points goes stale or invalid together'],
      recovery: 'Cleared explicitly by the instructor; the controller and its modules resume.',
      conflicts: ['REDUNDANCY_SWITCHOVER'], difficulty: 3,
      healthEffect: 'FAILED', propagate: 'BLAST'
    }),
    REDUNDANCY_SWITCHOVER: def({
      id: 'REDUNDANCY_SWITCHOVER', domain: 'CONTROL', targets: ['CONTROLLER'],
      activation: { style: 'TRANSIENT', defaultDurationMs: 15000 },
      effects: [{ kind: 'TRANSIENT_EVENT', hook: 'journal a SYSTEM event; no lasting state change' }],
      observableSymptoms: ['a brief transient and a system event', 'the process stays controlled throughout'],
      recovery: 'Automatic: the standby completes takeover and the event clears itself.',
      conflicts: ['CONTROLLER_LOSS'], difficulty: 2,
      healthEffect: 'DEGRADED', propagate: 'NONE'
    }),
    NET_PATH_DEGRADED: def({
      id: 'NET_PATH_DEGRADED', domain: 'NETWORK', targets: ['NET_PATH'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'PATH_DOWN', hook: 'symptomProjection cue lane plus group-aware topology health; no process-state mutation' }],
      observableSymptoms: ['redundancy-degraded indication only', 'data stays fresh'],
      recovery: 'Cleared explicitly by the instructor; the path rejoins the redundant pair.',
      conflicts: ['COMMS_PARTITION'], difficulty: 2,
      healthEffect: 'FAILED', propagate: 'GROUP_AWARE'
    }),
    COMMS_PARTITION: def({
      id: 'COMMS_PARTITION', domain: 'NETWORK', targets: ['NET_PATH'],
      activation: { style: 'SUSTAINED' }, groupWide: true,
      effects: [{ kind: 'GROUP_DOWN', hook: 'symptomProjection cue lane plus group-wide topology health; no process-state mutation' }],
      observableSymptoms: ['a common stale-data pattern across a controller\'s points'],
      recovery: 'Cleared explicitly by the instructor; both paths must be restored.',
      conflicts: ['NET_PATH_DEGRADED'], difficulty: 4,
      healthEffect: 'FAILED', propagate: 'GROUP_AWARE'
    }),
    SERVER_SERVICE_DEGRADED: def({
      id: 'SERVER_SERVICE_DEGRADED', domain: 'SERVICE', targets: ['SERVER_SVC'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'SERVICE_DEGRADE', hook: 'symptomProjection cue lane; topology health only, no process-state mutation' }],
      observableSymptoms: ['flex-profile station stale', 'console-profile station stays healthy'],
      recovery: 'Cleared explicitly by the instructor; cached data resumes updating.',
      conflicts: [], difficulty: 3,
      healthEffect: 'DEGRADED', propagate: 'BLAST', targetIds: ['SVC-SERVER']
    }),
    STATION_LOSS_PEER: def({
      id: 'STATION_LOSS_PEER', domain: 'HMI', targets: ['STATION'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'PEER_DOWN', hook: 'symptomProjection cue lane; topology health only, no process-state mutation' }],
      observableSymptoms: ['Station Health shows the peer down', 'local station data is unaffected'],
      recovery: 'Cleared explicitly by the instructor; the peer station reappears.',
      conflicts: [], difficulty: 2,
      healthEffect: 'FAILED', propagate: 'NONE'
    }),
    HISTORIAN_GAP: def({
      id: 'HISTORIAN_GAP', domain: 'INFORMATION', targets: ['SERVER_SVC'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'COLLECTION_STOP', hook: 'collection stops; the store and its trend read-back show a gap for the interval' }],
      observableSymptoms: ['live values stay correct', 'trend and history show a gap for the interval'],
      recovery: 'Cleared explicitly by the instructor; collection resumes (the gap itself does not backfill).',
      conflicts: [], difficulty: 2,
      healthEffect: 'DEGRADED', propagate: 'BLAST', targetIds: ['SVC-HISTORY']
    }),
    ASSISTANT_LOSS: def({
      id: 'ASSISTANT_LOSS', domain: 'INFORMATION', targets: ['APP'],
      activation: { style: 'SUSTAINED' },
      effects: [{ kind: 'APP_DOWN', hook: 'advisory only; never blocks control or command paths' }],
      observableSymptoms: ['the Ops Assistant is unavailable or delayed'],
      recovery: 'Cleared explicitly by the instructor; the assistant resumes.',
      conflicts: [], difficulty: 1,
      healthEffect: 'DEGRADED', propagate: 'NONE'
    })
  };

  deepFreeze(FAULT_IDS);
  deepFreeze(FAULT_DEFS);

  function getFaultDef(id) { return FAULT_DEFS[id] || null; }

  // ------------------------------------------------------------------ graph helpers
  // Self-contained forward-reachability walk. Deliberately the same BFS shape as
  // topology.js's blastRadius() (module header), operating only on plain graph data
  // so this file never requires ESS.Topology.
  function dependentsOf(graph, nid) {
    var out = [];
    graph.edges.forEach(function (e) { if (e.from === nid && out.indexOf(e.to) < 0) out.push(e.to); });
    return out;
  }

  function forwardReachable(graph, nid) {
    var seen = {}, queue = [nid], order = [];
    while (queue.length) {
      var cur = queue.shift();
      if (seen[cur]) continue;
      seen[cur] = true;
      if (cur !== nid) order.push(cur);
      dependentsOf(graph, cur).forEach(function (d) { if (!seen[d]) queue.push(d); });
    }
    return order;
  }

  function groupOf(graph, nid) {
    var n = graph.nodes[nid];
    return n && n.redundancyGroup ? n.redundancyGroup : null;
  }

  function membersOfGroup(graph, groupId) {
    return Object.keys(graph.nodes).filter(function (id) { return graph.nodes[id].redundancyGroup === groupId; }).sort();
  }

  function groupMembersOfNode(graph, nid) {
    var g = groupOf(graph, nid);
    return g ? membersOfGroup(graph, g) : [nid];
  }

  var HEALTH_RANK = { HEALTHY: 0, UNKNOWN: 1, DEGRADED: 1, FAILED: 2 };
  function worseOf(a, b) {
    var ra = HEALTH_RANK.hasOwnProperty(a) ? HEALTH_RANK[a] : 0;
    var rb = HEALTH_RANK.hasOwnProperty(b) ? HEALTH_RANK[b] : 0;
    return rb > ra ? b : a;
  }

  // ------------------------------------------------------------------ engine state
  function createState() { return { activeFaults: [] }; }

  function cloneState(state) { return JSON.parse(JSON.stringify(state || createState())); }

  function instanceId(faultId, targetNodeId) { return faultId + '@' + targetNodeId; }

  function findActive(state, faultId, targetNodeId) {
    var iid = instanceId(faultId, targetNodeId);
    var list = (state && state.activeFaults) || [];
    for (var i = 0; i < list.length; i++) if (list[i].instanceId === iid) return list[i];
    return null;
  }

  function isActive(state, faultId, targetNodeId) { return !!findActive(state, faultId, targetNodeId); }

  function listActive(state) { return ((state && state.activeFaults) || []).map(function (f) { return Object.assign({}, f); }); }

  function validateActivation(graph, faultId, targetNodeId) {
    var d = FAULT_DEFS[faultId];
    if (!d) throw new Error('ESS.FaultEngine.activate: unknown fault id ' + faultId);
    if (!graph || !graph.nodes) throw new Error('ESS.FaultEngine.activate: graph is required');
    var node = graph.nodes[targetNodeId];
    if (!node) throw new Error('ESS.FaultEngine.activate: unknown target node ' + targetNodeId);
    if (d.targets.indexOf(node.kind) < 0) {
      throw new Error('ESS.FaultEngine.activate: ' + faultId + ' cannot target kind ' + node.kind + ' (' + targetNodeId + '); expected one of ' + d.targets.join(', '));
    }
    if (d.targetIds && d.targetIds.indexOf(targetNodeId) < 0) {
      // Same kind, wrong specific node -- see the targetIds doc comment on def().
      throw new Error('ESS.FaultEngine.activate: ' + faultId + ' cannot target ' + targetNodeId + '; expected one of ' + d.targetIds.join(', '));
    }
    return d;
  }

  /**
   * Resolve the magnitude used by a fault instance. An explicit opts.magnitude always
   * wins. Otherwise, when the definition declares a magnitudeRange, a value is drawn
   * from a caller-supplied seeded generator (opts.rand, the ESS.Models.createRand
   * contract: a zero-argument fn returning a float in [0,1)) -- never Math.random.
   * Faults with no magnitudeRange (most of them) always resolve to null.
   */
  function resolveMagnitude(d, opts) {
    if (opts && typeof opts.magnitude === 'number') return opts.magnitude;
    if (!d.magnitudeRange) return null;
    var rand = opts && opts.rand;
    if (typeof rand !== 'function') {
      throw new Error('ESS.FaultEngine.activate: ' + d.id + ' needs an explicit magnitude or a seeded rand() -- it never falls back to Math.random');
    }
    var r = d.magnitudeRange;
    var v = r.min + rand() * (r.max - r.min);
    if (typeof r.step === 'number' && r.step > 0) v = Math.round(v / r.step) * r.step;
    return Math.round(v * 1000) / 1000; // fixed precision: keeps digests stable
  }

  function resolveDirection(d, opts) {
    if (d.id !== 'BIASED_MEASUREMENT') return null;
    var direction = opts && opts.direction != null ? String(opts.direction).toUpperCase() : 'HIGH';
    if (direction !== 'HIGH' && direction !== 'LOW') {
      throw new Error('ESS.FaultEngine.activate: BIASED_MEASUREMENT direction must be HIGH or LOW');
    }
    return direction;
  }

  function conflictsWith(d, otherFaultId) {
    var other = FAULT_DEFS[otherFaultId];
    return d.conflicts.indexOf(otherFaultId) >= 0 || (other && other.conflicts.indexOf(d.id) >= 0);
  }

  /**
   * Activate one fault instance. Returns a NEW state on success; on a rejected
   * activation (already active, conflicting) the ORIGINAL state is returned
   * unchanged, with accepted:false and a machine-readable reason -- the same
   * accepted/reason shape V3-PLAN's ActionEvent adds, so this composes with
   * dispatch.js when a later stage wires it in.
   */
  function activate(state, graph, opts) {
    opts = opts || {};
    var d = validateActivation(graph, opts.faultId, opts.targetNodeId);
    var cur = state || createState();
    if (findActive(cur, opts.faultId, opts.targetNodeId)) {
      return { state: cur, accepted: false, reason: 'ALREADY_ACTIVE', instance: null };
    }
    var sameTarget = (cur.activeFaults || []).filter(function (f) { return f.targetNodeId === opts.targetNodeId; });
    var conflict = null;
    for (var i = 0; i < sameTarget.length; i++) {
      if (conflictsWith(d, sameTarget[i].faultId)) { conflict = sameTarget[i]; break; }
    }
    if (conflict) {
      return { state: cur, accepted: false, reason: 'CONFLICTS_WITH:' + conflict.faultId, instance: null };
    }
    var instance = {
      instanceId: instanceId(opts.faultId, opts.targetNodeId),
      faultId: d.id,
      targetNodeId: opts.targetNodeId,
      activatedAt: typeof opts.simTime === 'number' ? opts.simTime : null,
      magnitude: resolveMagnitude(d, opts)
    };
    var direction = resolveDirection(d, opts);
    if (direction) instance.direction = direction;
    var next = cloneState(cur);
    next.activeFaults.push(instance);
    next.activeFaults.sort(function (a, b) { return a.instanceId < b.instanceId ? -1 : a.instanceId > b.instanceId ? 1 : 0; });
    return { state: next, accepted: true, reason: null, instance: instance };
  }

  function deactivate(state, opts) {
    opts = opts || {};
    var cur = state || createState();
    var iid = instanceId(opts.faultId, opts.targetNodeId);
    var found = (cur.activeFaults || []).some(function (f) { return f.instanceId === iid; });
    if (!found) return { state: cur, accepted: false, reason: 'NOT_ACTIVE' };
    var next = cloneState(cur);
    next.activeFaults = next.activeFaults.filter(function (f) { return f.instanceId !== iid; });
    return { state: next, accepted: true, reason: null };
  }

  /**
   * Resolve one active BIASED_MEASUREMENT into an engineering-unit offset for a
   * model measurement. Magnitude is percent-of-span per simulated minute; direction
   * is explicit in the fault instance. Old snapshots without direction retain the
   * historical upward-bias default. Pure and deterministic: no state mutation and no
   * random draw.
   */
  function measurementBias(state, targetNodeId, simTime, span) {
    var inst = findActive(state, 'BIASED_MEASUREMENT', targetNodeId);
    if (!inst) return 0;
    var rate = Number(inst.magnitude), width = Number(span), now = Number(simTime);
    if (!isFinite(rate) || !isFinite(width) || !(width > 0) || !isFinite(now) || typeof inst.activatedAt !== 'number') return 0;
    var minutes = Math.max(0, now - inst.activatedAt) / 60000;
    if (minutes === 0) return 0;
    var sign = inst.direction === 'LOW' ? -1 : 1;
    return sign * rate * width / 100 * minutes;
  }

  // ------------------------------------------------------------------ health + projections
  /**
   * Node health overlay for the WHOLE graph (every node id, HEALTHY unless a fault
   * says otherwise). This is where redundancy semantics live: see module header.
   */
  function computeHealth(state, graph) {
    if (!graph || !graph.nodes) throw new Error('ESS.FaultEngine.computeHealth: graph is required');
    var health = {};
    Object.keys(graph.nodes).forEach(function (id) { health[id] = 'HEALTHY'; });
    var active = (state && state.activeFaults) || [];

    // Pass 1: direct marks on the fault's own target(s).
    active.forEach(function (inst) {
      var d = FAULT_DEFS[inst.faultId];
      if (!d) return; // defensive: only engine-produced state should ever reach here
      var targets = d.groupWide ? groupMembersOfNode(graph, inst.targetNodeId) : [inst.targetNodeId];
      targets.forEach(function (tid) {
        if (!graph.nodes[tid]) return;
        health[tid] = worseOf(health[tid], d.healthEffect);
      });
    });

    // Pass 2: propagation. GROUP_AWARE only propagates once every member of the
    // target's redundancy group is FAILED (common-cause); BLAST always propagates;
    // NONE never does. Re-checks health (post pass 1) so multiple simultaneous
    // faults on sibling paths correctly combine into a full-group failure.
    var sources = {};
    active.forEach(function (inst) {
      var d = FAULT_DEFS[inst.faultId];
      if (!d || d.propagate === 'NONE') return;
      var targets = d.groupWide ? groupMembersOfNode(graph, inst.targetNodeId) : [inst.targetNodeId];
      targets.forEach(function (tid) {
        if (!graph.nodes[tid]) return;
        var g = groupOf(graph, tid);
        if (d.propagate === 'GROUP_AWARE' && g) {
          var members = membersOfGroup(graph, g);
          var allFailed = members.length > 0 && members.every(function (m) { return health[m] === 'FAILED'; });
          if (!allFailed) return; // a healthy sibling still carries the signal -- no propagation
        }
        sources[tid] = true;
      });
    });
    Object.keys(sources).forEach(function (tid) {
      forwardReachable(graph, tid).forEach(function (rid) { health[rid] = worseOf(health[rid], 'DEGRADED'); });
    });

    return health;
  }

  function symptomText(health) {
    if (health === 'FAILED') return 'Not responding. Treat data and commands through this node as suspect until it clears.';
    if (health === 'DEGRADED') return 'Degraded. Still producing data, but reduced margin or reduced redundancy should be assumed.';
    if (health === 'UNKNOWN') return 'Health could not be determined from the checks available here.';
    return null;
  }

  /**
   * Trainee view. SYMPTOMS ONLY: health plus generic, health-derived prose keyed by
   * node id. Never places a fault id, an instance id, a domain, or the string
   * "INSTRUCTOR_ONLY" anywhere in its return value -- see the leakage test.
   */
  function healthProjection(state, graph) {
    if (!graph || !graph.nodes) throw new Error('ESS.FaultEngine.healthProjection: graph is required');
    var health = computeHealth(state, graph);
    var nodes = {};
    Object.keys(graph.nodes).sort().forEach(function (id) {
      var n = graph.nodes[id];
      var h = health[id] || 'HEALTHY';
      var symptoms = [];
      var s = symptomText(h);
      if (s) symptoms.push(s);
      nodes[id] = { id: id, layer: n.layer, kind: n.kind, label: n.label, health: h, symptoms: symptoms };
    });
    return { nodeCount: Object.keys(nodes).length, nodes: nodes };
  }

  /**
   * Authored architecture-drill indications. The engine knows the active cause, but
   * the projection emits only root-detached drill cues: the definition's authored
   * symptom prose and, where topology provides it, a process-tag or unit scope. It
   * explicitly grades these as simulated indications, not measured process values. It
   * deliberately omits the exact target-node id and never attaches an observation
   * to a structural map node; either would turn the map into an answer marker.
   */
  function symptomProjection(state, graph, opts) {
    if (!graph || !graph.nodes) throw new Error('ESS.FaultEngine.symptomProjection: graph is required');
    opts = opts || {};
    var badPvByTag = opts.badPvByTag || {};
    var seen = {}, observations = [];
    ((state && state.activeFaults) || []).forEach(function (f) {
      var d = FAULT_DEFS[f.faultId], n = graph.nodes[f.targetNodeId];
      if (!d || !n) return;
      var refs = (n.pointRefs || []).slice().sort();
      // A redundant-path annunciator identifies the affected member; withholding A/B
      // would make A6/A7's required comparison a coin flip. This is an observable
      // indicator label, not a fault id or a truth marker attached to the graph.
      var scope = n.kind === 'NET_PATH' ? n.label : (refs.length ? refs.join(', ') : (n.unit || 'PLANT'));
      var authored = d.observableSymptoms.slice();
      if (f.faultId === 'FROZEN_MEASUREMENT' && refs.some(function (tag) { return badPvByTag[tag] === true; })) {
        authored = authored.filter(function (s) { return !/quality flag stays GOOD/i.test(s); });
        authored.push('quality flag reports BADPV and the loop sheds according to its configured response');
      }
      authored.forEach(function (s) {
        var text = scope + ' — ' + s;
        if (!seen[text]) { seen[text] = true; observations.push({ scope: scope, text: text }); }
      });
    });
    observations.sort(function (a, b) { return a.text < b.text ? -1 : a.text > b.text ? 1 : 0; });
    return { grade: 'SIMULATED_ARCHITECTURE_INDICATION', observations: observations };
  }

  /** Instructor view. Root causes: which faults are active, where, and how bad. */
  function truthProjection(state, graph) {
    if (!graph || !graph.nodes) throw new Error('ESS.FaultEngine.truthProjection: graph is required');
    var health = computeHealth(state, graph);
    var active = (state && state.activeFaults) || [];
    var faults = active.map(function (f) {
      var d = FAULT_DEFS[f.faultId];
      return {
        instanceId: f.instanceId, faultId: f.faultId, domain: d.domain,
        targetNodeId: f.targetNodeId, activatedAt: f.activatedAt, magnitude: f.magnitude,
        direction: f.direction || null,
        truthVisibility: d.truthVisibility, recovery: d.recovery,
        observableSymptoms: d.observableSymptoms.slice()
      };
    });
    return { activeFaults: faults, nodeHealth: health };
  }

  function snapshot(state) { return cloneState(state); }
  function restore(json) { return cloneState(json); }

  return {
    FAULT_IDS: FAULT_IDS, FAULT_DEFS: FAULT_DEFS, getFaultDef: getFaultDef,
    createState: createState, activate: activate, deactivate: deactivate,
    isActive: isActive, listActive: listActive,
    measurementBias: measurementBias,
    computeHealth: computeHealth, healthProjection: healthProjection,
    symptomProjection: symptomProjection, truthProjection: truthProjection,
    snapshot: snapshot, restore: restore
  };
});
