// @artifact production
/*
 * ESS.ArchitectureViewModel -- turns architecture state into the flat render data the
 * ARCH display's renderVals() hands to the template (V3-PLAN sections 3, 4, 7; S1 exit
 * condition: read-only, no state mutation from the view).
 *
 * PURE. No DOM, no timers, no globals read, no Math.random, no Date.now. Every input
 * arrives as an argument to build(); every array in the output is a fresh copy, never a
 * live reference into the graph or the health projection it was built from.
 *
 * NO SIBLING REQUIRES. This module does not require ESS.Topology, ESS.SignalPath or
 * ESS.FaultEngine, for the same reason fault-engine.js gives for not requiring
 * ESS.Topology: src/*.js are plain <script> tags in the browser and in the standalone,
 * not modules, so a require() would not survive there. Two consequences:
 *   - It re-declares the tiny slice of Topology's vocabulary it needs (LAYERS, a local
 *     one-hop `dependents` walk and a local transitive `blastRadius` walk) as a
 *     deliberate, self-contained duplicate over the same {nodes, edges} shape both
 *     modules receive as plain data -- exactly the pattern fault-engine.js's own header
 *     documents for its forward-reachability walk.
 *   - It does not call ESS.SignalPath.resolve/applicablePaths/describe itself. The APP
 *     calls those (it already has ESS.SignalPath loaded as a script-tag global) and
 *     hands the results in through `opts.selection` -- see SELECTION SHAPE below. This
 *     keeps every cross-module boundary in this codebase the same shape: data in, data
 *     out, never a require of a co-loaded global.
 *
 * DIAGNOSE SAFETY BY CONSTRUCTION, NOT BY CHECKING A FLAG. build() has no parameter that
 * can carry instructor truth: no fault list, no FaultDefinition, no truthProjection. The
 * only per-node fact it reads is `opts.health.nodes[id].health` / `.symptoms`, which is
 * exactly ESS.FaultEngine.healthProjection()'s trainee-safe output shape -- health plus
 * generic, health-derived prose, never a fault id, an instance id, a domain or the
 * string "INSTRUCTOR_ONLY" (fault-engine.js's own header makes that guarantee about its
 * output; this module cannot leak what it was never given). What mode DOES gate is a
 * separate, non-safety-critical concern: pedagogy. Diagnose mode withholds the full
 * transitive blast radius for the selected node (V3-PLAN section 7: "Diagnose asks the
 * learner to infer it") even though that radius is pure topology and not fault truth --
 * revealing it would hand the trainee the shortcut the drill is testing for. See the
 * MODE GATING note below for exactly what each mode changes.
 *
 * MODE GATING.
 *   learn     layers + edges (the whole graph), blast radius for `selectedNode`,
 *             inspector for `selectedNode`. `path` is not this mode's concern.
 *   trace     layers + edges for context, `path` resolved for `tag` via `selection`,
 *             inspector for `selectedNode` (independent of `tag` -- clicking any node
 *             in the graph opens its inspector in any mode). Blast still available if
 *             `selectedNode` is set: trace is not the diagnostic challenge, learn is.
 *   diagnose  same as trace, except: blast is always null, and inspector.dependsOn
 *             degrades from the full transitive list to the one-hop structural list
 *             (still true, still non-fabricated, just not the whole answer).
 *   debrief   S4 territory (replay timeline). Rendered the same as trace for now so the
 *             mode is representable and never crashes; a real timeline is not built
 *             here -- there is no journal/replay input to this module yet.
 *
 * SELECTION SHAPE (opts.selection, built by the caller from ESS.SignalPath):
 *   {
 *     applicable: [pathType, ...],            // SignalPath.applicablePaths(graph, tag)
 *     resolved:   { pathType: SignalPath.resolve(graph, tag, {path, profile}) , ... },
 *     describe:   { pathType: SignalPath.describe(graph, resolved[pathType]), ... }  // optional
 *   }
 * Any path type missing from `resolved`, or resolved with an empty `nodes` list (an
 * inapplicable path/profile per signal-path.js's own no-throw contract), renders as an
 * unavailable branch, never a crash.
 *
 * COLOUR. This module emits semantic tokens only -- `health` values from
 * ESS.Topology.HEALTH's vocabulary (HEALTHY|DEGRADED|FAILED|UNKNOWN) and `layer` values
 * from the LAYERS vocabulary -- never a hex value. src/palette.js is the app's only
 * colour source (V3-PLAN section 7); mapping a semantic token to a fill/stroke belongs
 * in the app's renderVals(), the same place colours() already maps priority tokens to
 * hex today. This module cannot do that mapping itself: it has no sibling require of
 * ESS.Palette (see NO SIBLING REQUIRES above), and inventing hex here would be exactly
 * the "invented colour" the spec forbids. `healthLabel` / layer `label` fields below are
 * plain-English renderings of the token for display text, not colour.
 *
 * API
 *   MODES, PROFILES, LAYERS, BANNER          frozen vocabularies / the required banner
 *   build(opts) -> view                      see the module docstring above for opts and
 *                                             docs/dev/V3-PLAN.md section 7 for the shape
 *
 * Exported as BOTH `ESS.ArchitectureViewModel` and `ESS.ArchViewModel` (same object) --
 * the assignment's REQUIREMENTS section names the latter, the architect's addendum names
 * the former for this same file. Rather than guess which the app-integration stage will
 * import, both aliases point at one object; see the stage report for this discrepancy.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    var mod = factory();
    root.ESS = root.ESS || {};
    root.ESS.ArchitectureViewModel = mod;
    root.ESS.ArchViewModel = mod;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var MODES = Object.freeze(['learn', 'trace', 'diagnose', 'debrief']);
  var PROFILES = Object.freeze(['console', 'flex']);
  var LAYERS = Object.freeze(['FIELD', 'IO', 'CONTROL', 'NETWORK', 'SERVICE', 'HMI', 'INFORMATION']);
  var BANNER = 'Conceptual training architecture. Simulated; not a Honeywell diagnostic display.';

  var MODE_LABEL = { learn: 'LEARN', trace: 'TRACE', diagnose: 'DIAGNOSE', debrief: 'DEBRIEF' };
  var PROFILE_LABEL = { console: 'CONSOLE', flex: 'FLEX' };
  var LAYER_LABEL = {
    FIELD: 'Field', IO: 'I/O', CONTROL: 'Control', NETWORK: 'Network',
    SERVICE: 'Service', HMI: 'Station', INFORMATION: 'Information'
  };
  var HEALTH_LABEL = { HEALTHY: 'Healthy', DEGRADED: 'Degraded', FAILED: 'Failed', UNKNOWN: 'Unknown' };
  // Same rank order as fault-engine.js's HEALTH_RANK (self-contained duplicate, not a
  // require -- see the module docstring's NO SIBLING REQUIRES note).
  var HEALTH_RANK = { HEALTHY: 0, UNKNOWN: 1, DEGRADED: 1, FAILED: 2 };

  var NODE_W = 132, NODE_H = 22, COL_GAP = 150, ROW_GAP = 26, PAD = 10;

  function worseHealth(a, b) {
    var ra = HEALTH_RANK[a] === undefined ? 0 : HEALTH_RANK[a];
    var rb = HEALTH_RANK[b] === undefined ? 0 : HEALTH_RANK[b];
    return rb > ra ? b : a;
  }

  // ------------------------------------------------------------------ local graph reads
  // Deliberate self-contained duplicates of topology.js's dependents()/blastRadius(),
  // operating only on the plain {nodes, edges} shape -- see NO SIBLING REQUIRES.

  function localDependents(graph, nid) {
    var out = [];
    graph.edges.forEach(function (e) { if (e.from === nid && out.indexOf(e.to) < 0) out.push(e.to); });
    return out.sort();
  }

  function localPredecessors(graph, nid) {
    var out = [];
    graph.edges.forEach(function (e) { if (e.to === nid && out.indexOf(e.from) < 0) out.push(e.from); });
    return out.sort();
  }

  function localBlastRadius(graph, nid) {
    var seen = {}, queue = [nid], order = [];
    while (queue.length) {
      var cur = queue.shift();
      if (seen[cur]) continue;
      seen[cur] = true;
      if (cur !== nid) order.push(cur);
      localDependents(graph, cur).forEach(function (d) { if (!seen[d]) queue.push(d); });
    }
    var points = {};
    order.concat([nid]).forEach(function (k) {
      var n = graph.nodes[k];
      if (n && n.pointRefs) n.pointRefs.forEach(function (t) { points[t] = true; });
    });
    return { nodes: order.sort(), points: Object.keys(points).sort() };
  }

  // ------------------------------------------------------------------ layout + summaries

  /** Deterministic grid layout: one column per layer, one row per node within it. */
  function layoutGraph(graph) {
    var byLayer = {};
    LAYERS.forEach(function (l) { byLayer[l] = []; });
    Object.keys(graph.nodes).sort().forEach(function (id) {
      var n = graph.nodes[id];
      var l = LAYERS.indexOf(n.layer) >= 0 ? n.layer : null;
      if (l) byLayer[l].push(id);
    });
    var pos = {};
    LAYERS.forEach(function (layer, li) {
      byLayer[layer].forEach(function (id, ni) {
        var x = PAD + li * COL_GAP, y = PAD + ni * ROW_GAP;
        pos[id] = { x: x, y: y, w: NODE_W, h: NODE_H, cx: x + NODE_W / 2, cy: y + NODE_H / 2 };
      });
    });
    return { byLayer: byLayer, pos: pos };
  }

  function nodeSummary(graph, id, healthOf, symptomsOf, pos, selectedNode) {
    var n = graph.nodes[id];
    if (!n) return null;
    var h = healthOf(id);
    var p = pos[id] || { x: 0, y: 0, w: NODE_W, h: NODE_H };
    return {
      id: id, label: n.label, layer: n.layer, kind: n.kind,
      health: h, healthLabel: HEALTH_LABEL[h] || h,
      symptoms: symptomsOf(id),
      pointCount: n.pointRefs ? n.pointRefs.length : 0,
      selected: !!selectedNode && selectedNode === id,
      x: p.x, y: p.y, w: p.w, h: p.h
    };
  }

  function buildLayers(graph, layout, healthOf, symptomsOf, selectedNode) {
    return LAYERS.map(function (layer) {
      var ids = layout.byLayer[layer] || [];
      return {
        id: layer, label: LAYER_LABEL[layer] || layer,
        nodes: ids.map(function (id) { return nodeSummary(graph, id, healthOf, symptomsOf, layout.pos, selectedNode); })
      };
    });
  }

  function buildEdges(graph, layout, healthOf) {
    var pos = layout.pos;
    var out = [];
    graph.edges.forEach(function (e) {
      var a = pos[e.from], b = pos[e.to];
      if (!a || !b) return; // defensive: never crash on a dangling edge, just omit it from the drawing
      out.push({
        id: e.id, from: e.from, to: e.to, semantic: e.semantic,
        health: worseHealth(healthOf(e.from), healthOf(e.to)),
        x1: a.cx, y1: a.cy, x2: b.cx, y2: b.cy
      });
    });
    return out;
  }

  // ------------------------------------------------------------------ inspector

  function labelledList(graph, ids) {
    return ids.map(function (id) {
      var n = graph.nodes[id];
      return { id: id, label: n ? n.label : id };
    });
  }

  function evidenceForNode(evidence, nodeId) {
    return evidence.filter(function (e) { return e && (e.target === nodeId || e.nodeId === nodeId); });
  }

  function buildInspector(graph, selectedNode, mode, healthOf, symptomsOf, evidence) {
    var n = graph.nodes[selectedNode];
    if (!n) return null;

    var inputs = labelledList(graph, localPredecessors(graph, selectedNode));
    var outputs = labelledList(graph, localDependents(graph, selectedNode));
    var dependsOn = mode === 'diagnose'
      ? outputs.slice()
      : labelledList(graph, localBlastRadius(graph, selectedNode).nodes);

    var health = healthOf(selectedNode);
    var healthLabel = HEALTH_LABEL[health] || health;
    var symptoms = symptomsOf(selectedNode);
    var observable = (n.diagnostics || []).slice();
    var nodeEvidence = evidenceForNode(evidence, selectedNode);

    var rows = [
      { label: 'Role', value: n.trainingDescription || '' },
      { label: 'Inputs', value: inputs.length ? inputs.map(function (i) { return i.label; }).join(', ') : 'None' },
      { label: 'Outputs', value: outputs.length ? outputs.map(function (o) { return o.label; }).join(', ') : 'None' },
      { label: 'What depends on it', value: dependsOn.length ? dependsOn.map(function (d) { return d.label; }).join(', ') : 'Nothing directly' },
      { label: 'Observable symptoms when degraded', value: observable.length ? observable.join('; ') : 'None documented' },
      { label: 'Current simulated health', value: symptoms.length ? healthLabel + ' — ' + symptoms.join(' ') : healthLabel },
      { label: 'Evidence collected', value: nodeEvidence.length ? nodeEvidence.length + ' item(s) collected' : 'None yet' }
    ];

    return {
      nodeId: selectedNode, title: n.label, layer: n.layer, kind: n.kind,
      role: n.trainingDescription || '',
      inputs: inputs, outputs: outputs, dependsOn: dependsOn,
      observableSymptoms: observable, symptoms: symptoms,
      health: health, healthLabel: healthLabel,
      evidence: nodeEvidence.slice(),
      sourceBasis: (n.sourceBasis || []).slice(),
      rows: rows
    };
  }

  // ------------------------------------------------------------------ signal path

  function pathNodeSummary(graph, id, healthOf, symptomsOf) {
    var n = graph.nodes[id];
    if (!n) return { id: id, label: id, layer: null, kind: null, health: 'UNKNOWN', healthLabel: 'Unknown', symptoms: [] };
    var h = healthOf(id);
    return { id: id, label: n.label, layer: n.layer, kind: n.kind, health: h, healthLabel: HEALTH_LABEL[h] || h, symptoms: symptomsOf(id) };
  }

  /**
   * Resolve the traced signal path for `tag` from the caller-supplied `selection`
   * (see SELECTION SHAPE in the module docstring). Never throws: an absent tag, an
   * absent/empty selection, or an unresolved path type all come back as
   * `resolved: false` with an explanatory `emptyText`, never a crash.
   */
  function buildPath(graph, tag, selection, beginner, healthOf, symptomsOf) {
    if (!tag) {
      return { resolved: false, tag: null, primary: null, branches: [], emptyText: 'No point selected for signal path tracing.' };
    }
    if (!selection || !selection.resolved || typeof selection.resolved !== 'object') {
      return { resolved: false, tag: tag, primary: null, branches: [], emptyText: 'No signal-path selection data supplied for ' + tag + '.' };
    }

    var applicable = Array.isArray(selection.applicable) && selection.applicable.length
      ? selection.applicable.slice()
      : Object.keys(selection.resolved);
    if (!applicable.length) {
      return { resolved: false, tag: tag, primary: null, branches: [], emptyText: tag + ' has no applicable signal path.' };
    }

    var primary = applicable.indexOf('measurement') >= 0 ? 'measurement' : applicable[0];
    // Beginner: one flat left-to-right progression (the primary path only). Advanced:
    // every applicable path type as its own branch, including the separate alarm/
    // history/command legs V3-PLAN section 3 requires never be folded into "the" path.
    var types = beginner ? [primary] : applicable;

    var branches = types.map(function (t) {
      var r = selection.resolved[t];
      var describeText = (selection.describe && selection.describe[t]) || null;
      if (!r || !Array.isArray(r.nodes) || !r.nodes.length) {
        return { type: t, available: false, legs: [], nodes: [], describeText: describeText };
      }
      var legs = (r.legs || []).map(function (leg) {
        return {
          label: leg.label,
          nodes: (leg.nodes || []).map(function (id) { return pathNodeSummary(graph, id, healthOf, symptomsOf); })
        };
      });
      var nodes = r.nodes.map(function (id) { return pathNodeSummary(graph, id, healthOf, symptomsOf); });
      return { type: t, available: true, legs: legs, nodes: nodes, describeText: describeText };
    });

    var anyAvailable = branches.some(function (b) { return b.available; });
    return {
      resolved: anyAvailable, tag: tag, primary: primary, branches: branches,
      emptyText: anyAvailable ? null : (tag + ' has no available ' + types.join('/') + ' path for this selection.')
    };
  }

  // ------------------------------------------------------------------ build()

  /**
   * build(opts) -> view. See the module docstring for the mode-gating and selection
   * contracts. Every field is present on every call (never `undefined`); fields that
   * have nothing to show come back `null` with `empty`/`emptyText` (top-level) or a
   * branch/path-level `emptyText` explaining why, never by throwing.
   *
   * opts:
   *   graph         ESS.Topology's build() output (plain {nodes, edges, pointPaths, ...})
   *   health        ESS.FaultEngine.healthProjection() output, or null/absent (defaults
   *                 every node to HEALTHY with no symptoms -- V3-PLAN addendum section C.3)
   *   mode          one of MODES; invalid/absent defaults to 'learn'
   *   profile       one of PROFILES; invalid/absent defaults to 'console'
   *   beginner      boolean; defaults true
   *   tag           the traced point's tag, or null (Trace/Diagnose/Debrief)
   *   selection     caller-resolved ESS.SignalPath data for `tag` (see SELECTION SHAPE)
   *   selectedNode  a topology node id to inspect, or null (any mode)
   *   evidence      array of already-collected evidence entries; defaults [] (S1 has no
   *                 evidence system yet -- TRAINING.MARK_EVIDENCE lands in S3)
   */
  function build(opts) {
    opts = opts || {};
    var mode = MODES.indexOf(opts.mode) >= 0 ? opts.mode : 'learn';
    var profile = PROFILES.indexOf(opts.profile) >= 0 ? opts.profile : 'console';
    var beginner = opts.beginner === undefined ? true : !!opts.beginner;
    var tag = opts.tag || null;
    var selectedNode = opts.selectedNode || null;
    var evidence = Array.isArray(opts.evidence) ? opts.evidence.slice() : [];

    // Which modes this BUILD STAGE has actually implemented. Defaults to all four so the
    // module's own tests exercise the full surface, but the app declares its scope: S1
    // ships learn + trace, S3 adds diagnose, S4 adds debrief. Unimplemented modes are
    // HIDDEN rather than disabled -- a disabled chip in a training product invites "why
    // can't I click this?" and teaches nothing, and a live chip on an unimplemented mode
    // is a stub a trainee can reach. Making it an argument keeps each stage's scope in
    // code instead of in a plan document. (Architect ruling, 2026-08-30, after seat 3/3
    // flagged four chips visible while V3-PLAN section 9 scopes S1 to Learn and Trace.)
    var available = Array.isArray(opts.availableModes) && opts.availableModes.length
      ? MODES.filter(function (m) { return opts.availableModes.indexOf(m) >= 0; })
      : MODES;
    var modes = available.map(function (m) { return { id: m, label: MODE_LABEL[m], active: m === mode }; });
    var profiles = PROFILES.map(function (p) { return { id: p, label: PROFILE_LABEL[p], active: p === profile }; });

    var graph = opts.graph;
    if (!graph || !graph.nodes || typeof graph.nodes !== 'object' || !graph.edges) {
      return {
        banner: BANNER, mode: mode, modes: modes, profile: profile, profiles: profiles, beginner: beginner,
        layers: [], edges: [], path: null, inspector: null, blast: null,
        empty: true, emptyText: 'No architecture graph supplied.'
      };
    }

    var healthNodes = (opts.health && opts.health.nodes && typeof opts.health.nodes === 'object') ? opts.health.nodes : null;
    function healthOf(id) {
      var h = healthNodes && healthNodes[id];
      return (h && h.health) ? h.health : 'HEALTHY';
    }
    function symptomsOf(id) {
      var h = healthNodes && healthNodes[id];
      return (h && Array.isArray(h.symptoms)) ? h.symptoms.slice() : [];
    }

    var layout = layoutGraph(graph);
    var layers = buildLayers(graph, layout, healthOf, symptomsOf, selectedNode);
    var edges = buildEdges(graph, layout, healthOf);

    var inspector = selectedNode && graph.nodes[selectedNode]
      ? buildInspector(graph, selectedNode, mode, healthOf, symptomsOf, evidence)
      : null;

    // Blast radius: Learn/Trace/Debrief reveal it for the selected node; Diagnose always
    // withholds it (see the module docstring's MODE GATING note).
    var blast = null;
    if (selectedNode && graph.nodes[selectedNode] && mode !== 'diagnose') {
      var br = localBlastRadius(graph, selectedNode);
      blast = { nodeId: selectedNode, nodes: br.nodes.slice(), points: br.points.slice() };
    }

    var path = null;
    var empty = false, emptyText = null;

    // Learn's content IS the graph (layers/edges above): there is nothing to withhold
    // just because no node is selected, so it is never "empty". Trace, diagnose and
    // debrief are all about a traced path at this stage, so all three resolve one the
    // same way; a mode-specific debrief timeline is S4 work (see the module docstring).
    if (mode !== 'learn') {
      path = buildPath(graph, tag, opts.selection, beginner, healthOf, symptomsOf);
      if (!path.resolved) { empty = true; emptyText = path.emptyText; }
    }

    return {
      banner: BANNER,
      mode: mode, modes: modes,
      profile: profile, profiles: profiles,
      beginner: beginner,
      layers: layers, edges: edges,
      path: path,
      inspector: inspector,
      blast: blast,
      empty: empty, emptyText: emptyText
    };
  }

  return { MODES: MODES, PROFILES: PROFILES, LAYERS: LAYERS, BANNER: BANNER, build: build };
});
