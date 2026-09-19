// @artifact production
/*
 * ESS.Topology — the conceptual training architecture: a layered graph of where a
 * signal comes from, what carries it, and what depends on it.
 *
 * THIS IS A TEACHING MODEL, NOT A VENDOR DIAGRAM. It is deliberately a conceptual
 * FIELD -> IO -> CONTROL -> NETWORK -> SERVICE -> HMI -> INFORMATION progression so a
 * trainee can reason about failure DOMAINS. Real installations differ; every surface
 * that renders this graph carries the "conceptual training architecture, simulated"
 * banner. No vendor topology, capacities, diagnostic codes or naming are reproduced.
 * (V3-PLAN sections 1, 3 and rule 1; RESOURCES 2.x for the layer vocabulary.)
 *
 * DERIVED, NOT AUTHORED. The FIELD and CONTROL layers come out of the tag database the
 * simulator already keeps: every point in `L` declares its control module in `cm`, its
 * kind in `kind`, and its alarm conditions in `alm`; every valve in `V` declares a
 * fail-safe direction in `fail`. A derived graph cannot drift from the tag database.
 * A hand-authored one silently will, and the first person to notice would be a trainee
 * being taught something false. Only what is genuinely absent from the data is declared:
 * I/O channels, controllers/CEE, network paths, server services, stations and history.
 *
 * API
 *   LAYERS, KINDS, HEALTH, SEMANTICS, PROFILES   the vocabularies (frozen arrays)
 *   VALVE_OF                                     control module tag -> valve it strokes
 *   build(opts) -> graph                         opts {L, V, assetTree}
 *   validate(graph) -> [problem strings]         graph contract check; [] means valid
 *   node(graph, id) / nodesIn(graph, layer)
 *   dependents(graph, id) -> [nodeId]            what breaks if this node fails
 *   blastRadius(graph, id) -> {nodes, points}    transitive dependents + points affected
 *
 * The graph is DATA. It holds no health, no faults and no live values -- health is
 * applied over it by the fault engine, so the same graph can be projected differently
 * for a trainee (symptoms) and an instructor (truth) without two graphs existing.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Topology = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var LAYERS = ['FIELD', 'IO', 'CONTROL', 'NETWORK', 'SERVICE', 'HMI', 'INFORMATION'];
  var KINDS = ['TRANSMITTER', 'VALVE', 'MOTOR', 'AI_CH', 'AO_CH', 'CONTROLLER', 'CEE',
               'CM', 'SCM', 'NET_PATH', 'SERVER_SVC', 'STATION', 'HISTORY', 'APP'];
  var HEALTH = ['HEALTHY', 'DEGRADED', 'FAILED', 'UNKNOWN'];
  var SEMANTICS = ['PV', 'COMMAND', 'ALARM', 'EVENT', 'HISTORY', 'CONFIG'];
  var PROFILES = ['console', 'flex'];
  var UNITS = ['U1', 'U2', 'U3', 'U4'];

  // Which valve each control module strokes. NOT derivable from the tag database: the
  // coupling lives in the process equations (src/models.js reads V.FV102.pos for the
  // FIC102 flow, and so on), so it is declared here and checked by validate().
  var VALVE_OF = {
    FIC102: 'FV102', TIC202: 'TV202', TIC301: 'TV301', LIC401: 'LV401', PIC401: 'PV401',
    FIC211: 'MV211', TIC213: 'JV213', FIC310: 'FV310', TIC311: 'FV311', FIC313: 'QV313',
    TIC502: 'TV502', LIC503: 'LV503', LIC504: 'WV504', PIC505: 'PV505'
  };

  // Sequence control modules that own a unit's phase logic (U2 batch only today).
  var SCM_OF = { U2: 'SCM202' };

  function id() { return Array.prototype.join.call(arguments, '-'); }

  // Provenance ids, resolved against docs/RESOURCES.md sections. Rule 1 and release
  // gate 5: every vendor-specific CONCEPT this graph teaches must trace to a registered
  // public source, while every word of prose here is our own. These are concept
  // citations, not quotations -- nothing is reproduced from any of them.
  var BASIS = {
    FIELD_MEAS:  ['RESOURCES-4.4', 'RESOURCES-4.1', 'RESOURCES-4.2', 'RESOURCES-4.3'],  // the specific open process models the measurements come from: U1 CSTR, U2 batch, U3 heater, U3 bed / U1 flash
    IO:          ['RESOURCES-2.19'],       // standards, cited by clause only
    CONTROL:     ['RESOURCES-2.16'],       // controller / control-execution concepts
    NETWORK:     ['RESOURCES-2.16'],       // redundant path concepts
    SERVICE:     ['RESOURCES-2.13'],       // server / SCADA architecture concepts
    STATION:     ['RESOURCES-2.1', 'RESOURCES-2.3'],  // station / HMI concepts
    ALARM:       ['RESOURCES-2.5', 'RESOURCES-2.2'],  // ISA-18.2 state model
    HISTORY:     ['RESOURCES-2.13'],
    APP:         ['RESOURCES-2.15'],       // operations-assistant concept
    TRAINING:    ['RESOURCES-2.14']        // training-simulator concepts
  };

  function mkNode(n) {
    return {
      id: n.id, layer: n.layer, kind: n.kind, label: n.label,
      trainingDescription: n.trainingDescription || '',
      assetRef: n.assetRef === undefined ? null : n.assetRef,
      unit: n.unit === undefined ? null : n.unit,
      pointRefs: n.pointRefs ? n.pointRefs.slice() : [],
      diagnostics: n.diagnostics ? n.diagnostics.slice() : [],
      sourceBasis: n.sourceBasis ? n.sourceBasis.slice() : [],
      profile: n.profile === undefined ? null : n.profile,
      redundancyGroup: n.redundancyGroup === undefined ? null : n.redundancyGroup
    };
  }

  function mkEdge(e) {
    return {
      id: e.id || id('E', e.from, e.to, e.semantic),
      from: e.from, to: e.to,
      semantic: e.semantic,
      direction: e.direction || 'FORWARD',
      redundancyGroup: e.redundancyGroup === undefined ? null : e.redundancyGroup,
      pointRef: e.pointRef === undefined ? null : e.pointRef
    };
  }

  /**
   * Build the graph from the live tag database.
   * opts.L  tag database (required)      opts.V  valve map (required)
   * opts.assetTree  the station's asset hierarchy, used only for assetRef (optional)
   * opts.unitOf(tag) -> 'U1'|'U2'|'U3'   optional override; a default is derived
   */
  function build(opts) {
    opts = opts || {};
    var L = opts.L, V = opts.V || {};
    if (!L) throw new Error('ESS.Topology.build: opts.L (tag database) is required');
    var assetTree = opts.assetTree || [];

    var assetOf = function (tag) {
      for (var i = 0; i < assetTree.length; i++) {
        var a = assetTree[i];
        if (a.tags && a.tags.indexOf(tag) >= 0) return a.id;
      }
      return null;
    };
    var unitOf = opts.unitOf || function (tag) {
      var a = assetOf(tag);
      if (a) {
        for (var i = 0; i < assetTree.length; i++) if (assetTree[i].id === a) return assetTree[i].unit || null;
      }
      return null;
    };

    var nodes = {}, edges = [], pointPaths = {};
    var unplaced = [];   // tags unitOf could not place; filed under U1 so the graph stays well-formed, reported by validate()
    var strayValves = Object.keys(V).filter(function (k) {   // valves in V that no control module strokes (VALVE_OF)
      return Object.keys(VALVE_OF).every(function (tag) { return VALVE_OF[tag] !== k; });
    });
    var add = function (n) {
      var m = mkNode(n);
      var prev = nodes[m.id];
      if (prev) {
        // Two points can legitimately share one control module. Replacing would drop the
        // earlier point's reference and silently shrink that node's blast radius, so
        // merge the point references instead. (Found by the SA adversarial pass.)
        m.pointRefs = prev.pointRefs.concat(m.pointRefs.filter(function (t) {
          return prev.pointRefs.indexOf(t) < 0;
        }));
      }
      nodes[m.id] = m;
      return m.id;
    };
    var link = function (e) { edges.push(mkEdge(e)); };

    // ---------------------------------------------------------------- declared spine
    // Absent from the tag database, so declared. One controller + control execution
    // environment per unit, a redundant network path pair per unit, shared services,
    // the two station profiles, history and the assistant application.
    UNITS.forEach(function (u) {
      add({ id: id('CTRL', u), layer: 'CONTROL', kind: 'CONTROLLER', unit: u,
            label: u + ' CONTROLLER', sourceBasis: BASIS.CONTROL,
            trainingDescription: 'Executes the control modules for ' + u + '. If it is lost, every point it executes goes stale together -- a common-cause pattern, not many independent failures.' });
      add({ id: id('CEE', u), layer: 'CONTROL', kind: 'CEE', unit: u,
            label: u + ' CONTROL EXECUTION', sourceBasis: BASIS.CONTROL,
            trainingDescription: 'The execution environment the control modules run inside. Distinguishes "the controller is gone" from "one module is misbehaving".' });
      // HOSTING, in the dependency direction: the controller hosts the execution
      // environment, which executes the control modules. Every edge in this graph points
      // from a thing to the things that BREAK IF IT FAILS, which is what makes
      // blastRadius() a simple forward walk. Dataflow is rendered separately by
      // signal-path.js, which may show a path in reading order; do not conflate the two.
      link({ from: id('CTRL', u), to: id('CEE', u), semantic: 'CONFIG' });
      ['A', 'B'].forEach(function (p) {
        add({ id: id('NET', u, p), layer: 'NETWORK', kind: 'NET_PATH', unit: u,
              label: u + ' NETWORK PATH ' + p, redundancyGroup: id('NET', u), sourceBasis: BASIS.NETWORK,
              trainingDescription: 'One of two redundant paths carrying ' + u + ' data. Losing one degrades redundancy; data keeps flowing. Losing both is a communications partition, which looks like a common stale-data pattern rather than a process upset.' });
      });
      var scm = SCM_OF[u];
      if (scm) {
        add({ id: id('CM', scm), layer: 'CONTROL', kind: 'SCM', unit: u, assetRef: assetOf(scm),
              label: scm + ' SEQUENCE', pointRefs: [], sourceBasis: BASIS.CONTROL,
              trainingDescription: 'Sequence control module driving the ' + u + ' batch phases. Its phase drives state-based alarm limits, so an alarm limit that "changed by itself" usually traces here.' });
        link({ from: id('CM', scm), to: id('CEE', u), semantic: 'CONFIG' });
      }
    });

    add({ id: 'SVC-ALARM', layer: 'SERVICE', kind: 'SERVER_SVC', label: 'ALARM AND EVENT SERVICE', sourceBasis: BASIS.ALARM,
          trainingDescription: 'Processes alarm state changes and keeps the event journal. If it degrades, annunciation and the journal suffer while control itself is unaffected.' });
    add({ id: 'SVC-SERVER', layer: 'SERVICE', kind: 'SERVER_SVC', label: 'DATA SERVER', sourceBasis: BASIS.SERVICE,
          trainingDescription: 'Caches process data for stations running the flex profile. A server fault blinds the flex profile while a console-profile station, which talks to the controller directly, stays correct. This is the classic "is it the server or the controller?" split.' });
    add({ id: 'SVC-HISTORY', layer: 'SERVICE', kind: 'SERVER_SVC', label: 'HISTORY COLLECTION', sourceBasis: BASIS.HISTORY,
          trainingDescription: 'Collects samples into the historian. If it stops, live values stay perfect and only trends and history show a gap for the interval.' });
    UNITS.forEach(function (u) {
      ['A', 'B'].forEach(function (p) {
        link({ from: id('NET', u, p), to: 'SVC-SERVER', semantic: 'PV', redundancyGroup: id('NET', u) });
      });
      link({ from: id('NET', u, 'A'), to: 'SVC-ALARM', semantic: 'ALARM' });
      link({ from: id('NET', u, 'A'), to: 'SVC-HISTORY', semantic: 'HISTORY' });
    });

    add({ id: 'STN-CONSOLE', layer: 'HMI', kind: 'STATION', profile: 'console',
          label: 'STATION (CONSOLE PROFILE)', sourceBasis: BASIS.STATION,
          trainingDescription: 'Console profile: reads process data on the direct controller path. Survives a data-server fault. This simulator has ONE physical station; console and flex are modelled as view profiles on it, not as two machines.' });
    add({ id: 'STN-FLEX', layer: 'HMI', kind: 'STATION', profile: 'flex',
          label: 'STATION (FLEX PROFILE)', sourceBasis: BASIS.STATION,
          trainingDescription: 'Flex profile: reads process data cached by the data server. Goes stale when the server degrades even though control is healthy. Simulated as a view profile, not a second machine.' });
    add({ id: 'HIST-STORE', layer: 'INFORMATION', kind: 'HISTORY', label: 'PROCESS HISTORY', sourceBasis: BASIS.HISTORY,
          trainingDescription: 'Stored samples behind trends. A gap here means the data was never collected; the process itself was never in doubt.' });
    add({ id: 'APP-ASSIST', layer: 'INFORMATION', kind: 'APP', label: 'OPS ASSISTANT', sourceBasis: BASIS.APP,
          trainingDescription: 'Rule-based decision support reading process symptoms. Advisory only: if it is unavailable the operator loses help, never control.' });

    UNITS.forEach(function (u) {
      link({ from: id('NET', u, 'A'), to: 'STN-CONSOLE', semantic: 'PV' });
    });
    link({ from: 'SVC-SERVER', to: 'STN-FLEX', semantic: 'PV' });
    link({ from: 'SVC-ALARM', to: 'STN-CONSOLE', semantic: 'ALARM' });
    link({ from: 'SVC-ALARM', to: 'STN-FLEX', semantic: 'ALARM' });
    link({ from: 'SVC-HISTORY', to: 'HIST-STORE', semantic: 'HISTORY' });
    // Trend read-back reaches BOTH station profiles: a historian gap shows up on a trend
    // whichever profile you are viewing, which is exactly why drill A10 must be diagnosed
    // from the gap itself and not from which station you happen to be sitting at.
    link({ from: 'HIST-STORE', to: 'STN-CONSOLE', semantic: 'HISTORY' });
    link({ from: 'HIST-STORE', to: 'STN-FLEX', semantic: 'HISTORY' });
    link({ from: 'SVC-SERVER', to: 'APP-ASSIST', semantic: 'PV' });

    // ---------------------------------------------------------------- derived per point
    Object.keys(L).sort().forEach(function (tag) {
      var l = L[tag];
      var u = unitOf(tag);
      if (!u) { unplaced.push(tag); u = 'U1'; }
      var asset = assetOf(tag);
      var cmId = id('CM', l.cm || tag);
      var isMotor = l.kind === 'motor';

      // FIELD: the measuring element (or the motor itself for a drive).
      var fieldId = isMotor ? id('DRV', tag) : id('XMTR', tag);
      add({ id: fieldId, layer: 'FIELD', kind: isMotor ? 'MOTOR' : 'TRANSMITTER', unit: u,
            assetRef: asset, pointRefs: [tag],
            label: (isMotor ? 'DRIVE ' : 'TRANSMITTER ') + tag, sourceBasis: BASIS.FIELD_MEAS,
            trainingDescription: isMotor
              ? 'Motor and its starter for ' + tag + '. Run feedback originates here, so a feedback fault and a genuine stop look identical at the station until you check the field.'
              : 'Measuring element for ' + tag + ' (' + (l.desc || '') + '). Every measurement carries noise from here. A fault here can produce a perfectly plausible value with GOOD quality -- which is why quality is not proof of correctness.',
            diagnostics: isMotor ? ['run feedback', 'starter status']
                                 : ['signal level', 'measurement noise', 'quality flag'] });

      // IO: the input channel carrying it.
      var aiId = id('AI', tag);
      add({ id: aiId, layer: 'IO', kind: 'AI_CH', unit: u, assetRef: asset, pointRefs: [tag],
            label: 'INPUT CHANNEL ' + tag, sourceBasis: BASIS.IO,
            trainingDescription: 'Input channel for ' + tag + '. A channel failure reports bad quality and the loop sheds per its SHEDHOLD setting -- distinguishable from a field fault, which usually does not flag quality at all.',
            diagnostics: ['channel status', 'quality'] });

      // CONTROL: the control module.
      add({ id: cmId, layer: 'CONTROL', kind: 'CM', unit: u, assetRef: asset, pointRefs: [tag],
            label: (l.cm || tag) + ' (' + tag + ')', sourceBasis: BASIS.CONTROL,
            trainingDescription: 'Control module holding ' + tag + '. Executes inside the ' + u + ' controller, so it goes stale with every other module there if that controller is lost.',
            diagnostics: ['mode', 'execution state'] });

      link({ from: fieldId, to: aiId, semantic: 'PV', pointRef: tag });
      link({ from: aiId, to: cmId, semantic: 'PV', pointRef: tag });
      // The execution environment executes this module: if the CEE (or the controller
      // above it) is lost, this module is lost with every other module in the unit.
      link({ id: id('E', id('CEE', u), cmId, 'CONFIG'), from: id('CEE', u), to: cmId, semantic: 'CONFIG', pointRef: tag });
      // ...and the module publishes onto both redundant network paths.
      ['A', 'B'].forEach(function (p) {
        link({ id: id('E', cmId, id('NET', u, p), 'PV'), from: cmId, to: id('NET', u, p),
               semantic: 'PV', pointRef: tag, redundancyGroup: id('NET', u) });
      });

      // ALARM edges, one per configured condition on this point.
      Object.keys(l.alm || {}).sort().forEach(function (cond) {
        link({ id: id('E', cmId, 'SVC-ALARM', cond), from: cmId, to: 'SVC-ALARM',
               semantic: 'ALARM', pointRef: tag });
      });
      link({ from: cmId, to: 'SVC-HISTORY', semantic: 'HISTORY', pointRef: tag });

      // COMMAND leg: only points that actually stroke something.
      var valve = VALVE_OF[tag];
      // Reading order for the learner, per V3-PLAN section 4's worked example: the
      // measuring element, the channel that carries it, the controller and execution
      // environment that host the module, the module itself, then the network it
      // publishes onto. The station and service legs are appended per PROFILE by
      // signal-path.js, never hard-coded here.
      var measurement = [fieldId, aiId, id('CTRL', u), id('CEE', u), cmId, id('NET', u, 'A')];
      var command = null;
      if (valve && V[valve]) {
        var aoId = id('AO', tag);
        add({ id: aoId, layer: 'IO', kind: 'AO_CH', unit: u, assetRef: asset, pointRefs: [tag],
              label: 'OUTPUT CHANNEL ' + tag, sourceBasis: BASIS.IO,
              trainingDescription: 'Output channel carrying the ' + tag + ' demand to ' + valve + '.',
              diagnostics: ['channel status', 'output readback'] });
        var vId = id('VLV', valve);
        add({ id: vId, layer: 'FIELD', kind: 'VALVE', unit: u, assetRef: asset, pointRefs: [tag],
              label: 'VALVE ' + valve, sourceBasis: BASIS.FIELD_MEAS,
              trainingDescription: 'Final element for ' + tag + '. On loss of instrument air it goes to its fail-safe position (' + (V[valve].fail ? 'open' : 'closed') + '). If the output moves and neither the position nor the PV follows, the problem is here, not in the controller.',
              diagnostics: ['position vs demand', 'stroke response', 'fail-safe state'] });
        link({ from: cmId, to: aoId, semantic: 'COMMAND', pointRef: tag });
        link({ from: aoId, to: vId, semantic: 'COMMAND', pointRef: tag });
        command = [cmId, aoId, vId];
      } else if (isMotor) {
        var moId = id('AO', tag);
        add({ id: moId, layer: 'IO', kind: 'AO_CH', unit: u, assetRef: asset, pointRefs: [tag],
              label: 'OUTPUT CHANNEL ' + tag, sourceBasis: BASIS.IO,
              trainingDescription: 'Start/stop command channel for ' + tag + '.',
              diagnostics: ['channel status'] });
        link({ from: cmId, to: moId, semantic: 'COMMAND', pointRef: tag });
        link({ from: moId, to: fieldId, semantic: 'COMMAND', pointRef: tag });
        command = [cmId, moId, fieldId];
      }

      pointPaths[tag] = {
        measurement: measurement,
        command: command,
        alarm: [cmId, 'SVC-ALARM'],
        history: [cmId, 'SVC-HISTORY', 'HIST-STORE']
      };
    });

    return {
      nodes: nodes,
      edges: edges,
      pointPaths: pointPaths,
      unplaced: unplaced,
      strayValves: strayValves,
      units: UNITS.slice(),
      profiles: PROFILES.slice()
    };
  }

  // ------------------------------------------------------------------ contracts
  /** Graph contract check. Returns [] when the graph is valid. */
  function validate(graph) {
    var problems = [];
    if (!graph || !graph.nodes) return ['graph is empty'];
    var ids = graph.nodes;

    // A point the app could not place in a unit was filed under U1 so the graph stayed
    // well-formed. That is a build defect (a tag missing from the app's unitOf() and from
    // UNITS), and teaching it as U1 would tell a trainee that losing U1's controller takes
    // it down. Reported here; the app refuses to start on it (initSim).
    (graph.unplaced || []).forEach(function (tag) {
      problems.push(tag + ': resolves no unit -- filed under U1 by default; add it to the app\'s unitOf() and to Topology.UNITS');
    });
    // A valve present in V that no control module strokes has no command path and no
    // graph node at all: the fault engine cannot target it and the trainee cannot trace
    // it. Declare it in VALVE_OF (and in src/models.js VALVE_TARGET) or leave it out of V.
    (graph.strayValves || []).forEach(function (k) {
      problems.push('valve ' + k + ' is in V but no control module strokes it (Topology.VALVE_OF) -- it has no command path');
    });

    Object.keys(ids).forEach(function (k) {
      var n = ids[k];
      if (n.id !== k) problems.push('node key ' + k + ' does not match its id ' + n.id);
      if (n.unit != null && UNITS.indexOf(n.unit) < 0) problems.push(n.id + ': unknown unit ' + n.unit);
      if (LAYERS.indexOf(n.layer) < 0) problems.push(n.id + ': unknown layer ' + n.layer);
      if (KINDS.indexOf(n.kind) < 0) problems.push(n.id + ': unknown kind ' + n.kind);
      if (!n.label) problems.push(n.id + ': missing label');
      if (!n.trainingDescription) problems.push(n.id + ': missing trainingDescription (every node must teach something)');
      if (!n.sourceBasis || !n.sourceBasis.length) problems.push(n.id + ': missing sourceBasis (rule 1 / release gate 5: every concept traces to a registered public source)');
    });

    graph.edges.forEach(function (e) {
      if (!ids[e.from]) problems.push('edge ' + e.id + ': from-node ' + e.from + ' does not exist');
      if (!ids[e.to]) problems.push('edge ' + e.id + ': to-node ' + e.to + ' does not exist');
      if (SEMANTICS.indexOf(e.semantic) < 0) problems.push('edge ' + e.id + ': unknown semantic ' + e.semantic);
      if (ids[e.from] && ids[e.to]) {
        var a = LAYERS.indexOf(ids[e.from].layer), b = LAYERS.indexOf(ids[e.to].layer);
        // A COMMAND edge runs back down the stack; everything else runs up it. Neither
        // may stay still, or the "layers" are not teaching a progression at all.
        if (e.semantic === 'COMMAND') {
          if (b > a) problems.push('edge ' + e.id + ': COMMAND must not run up the layer stack (' + ids[e.from].layer + ' -> ' + ids[e.to].layer + ')');
        } else if (e.semantic === 'HISTORY' || e.semantic === 'CONFIG') {
          // HISTORY is store-and-retrieve: collection runs up the stack, read-back runs
          // down it when a station retrieves a trend. CONFIG is a hosting relationship
          // and is layer-internal. Neither is a progression, so neither is constrained.
        } else if (b < a) {
          problems.push('edge ' + e.id + ': ' + e.semantic + ' must not run down the layer stack (' + ids[e.from].layer + ' -> ' + ids[e.to].layer + ')');
        }
      }
    });

    Object.keys(graph.pointPaths).forEach(function (tag) {
      var p = graph.pointPaths[tag];
      ['measurement', 'command', 'alarm', 'history'].forEach(function (kind) {
        var path = p[kind];
        if (path === null || path === undefined) return;   // command is legitimately absent
        if (!path.length) { problems.push(tag + ': ' + kind + ' path is empty'); return; }
        path.forEach(function (nid) {
          if (!ids[nid]) problems.push(tag + ': ' + kind + ' path references missing node ' + nid);
        });
      });
      if (!p.measurement) problems.push(tag + ': every point must resolve a measurement path');
    });

    Object.keys(VALVE_OF).forEach(function (tag) {
      if (!graph.pointPaths[tag]) problems.push('VALVE_OF names ' + tag + ', which is not a point in the graph');
      else if (!graph.pointPaths[tag].command) problems.push(tag + ' strokes ' + VALVE_OF[tag] + ' but resolved no command path');
    });

    return problems;
  }

  function node(graph, nid) { return graph.nodes[nid] || null; }
  function nodesIn(graph, layer) {
    return Object.keys(graph.nodes).filter(function (k) { return graph.nodes[k].layer === layer; }).sort();
  }

  /** Immediate downstream nodes: what consumes this one. */
  function dependents(graph, nid) {
    var out = [];
    graph.edges.forEach(function (e) { if (e.from === nid && out.indexOf(e.to) < 0) out.push(e.to); });
    return out.sort();
  }

  /**
   * Everything downstream of a node, and which points are affected.
   * This is what the Learn mode reveals and the Diagnose mode asks the trainee to infer.
   */
  function blastRadius(graph, nid) {
    var seen = {}, queue = [nid], order = [];
    while (queue.length) {
      var cur = queue.shift();
      if (seen[cur]) continue;
      seen[cur] = true;
      if (cur !== nid) order.push(cur);
      dependents(graph, cur).forEach(function (d) { if (!seen[d]) queue.push(d); });
    }
    var points = {};
    order.concat([nid]).forEach(function (k) {
      var n = graph.nodes[k];
      if (n) n.pointRefs.forEach(function (t) { points[t] = true; });
    });
    return { nodes: order.sort(), points: Object.keys(points).sort() };
  }

  return {
    LAYERS: LAYERS, KINDS: KINDS, HEALTH: HEALTH, SEMANTICS: SEMANTICS,
    PROFILES: PROFILES, UNITS: UNITS, VALVE_OF: VALVE_OF, SCM_OF: SCM_OF,
    build: build, validate: validate, node: node, nodesIn: nodesIn,
    dependents: dependents, blastRadius: blastRadius
  };
});
