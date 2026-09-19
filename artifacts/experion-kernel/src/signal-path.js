// @artifact production
/*
 * ESS.SignalPath — resolves the ordered node list a learner should see for one point's
 * signal path, with the station/service leg chosen by PROFILE (V3-PLAN sections 3, 4).
 *
 * PROFILE IS THE WHOLE POINT. This simulator has one physical station; console and flex
 * are view profiles on it (topology.js STN-CONSOLE / STN-FLEX). The console profile reads
 * process data on the direct controller/network path; the flex profile reads a copy
 * cached by the data server. Same point, same measurement, two different sets of things
 * that can break it -- that is what drill A8 teaches. `graph.pointPaths[tag]` gives the
 * trunk of each path; this module NEVER hard-codes a station leg into that trunk -- it
 * appends the profile-appropriate tail on top, so a caller choosing 'console' or 'flex'
 * changes only the last leg, never the trunk.
 *
 * Per-path-type station leg, taken from the graph edges the lead's topology.js actually
 * draws (measured, 2026-08-30), not assumed:
 *   measurement  console -> STN-CONSOLE direct;      flex -> via SVC-SERVER's cache
 *   alarm        console -> STN-CONSOLE direct;      flex -> STN-FLEX direct
 *                (SVC-ALARM has an edge to BOTH stations -- annunciation does not
 *                route through the data server the way live measurement does)
 *   history      console -> STN-CONSOLE (edge-backed, HIST-STORE -> STN-CONSOLE);
 *                flex -> STN-FLEX (node exists; NOT edge-backed in this graph -- the
 *                lead's topology has no flex-profile trend read-back path. This module
 *                still resolves the node, per the SA exit condition of node existence,
 *                but the gap is real and is reported, not silently fixed here.)
 *   command      no station leg. A command path terminates at the actuator; the trunk
 *                from `graph.pointPaths[tag].command` (control module -> output channel
 *                -> actuator) already is the complete resolvable path. V3-PLAN section 3's
 *                "Station -> services/network as applicable" lead-in for command is not
 *                separately edge-modelled in this graph (no reverse station->network->CM
 *                edges exist -- every edge points from a thing to what breaks if it fails,
 *                per topology.js's header, and a command failure is not modelled that way
 *                yet). Inventing a profile leg here would teach a route nobody built;
 *                report it as a gap for a future stage instead.
 *
 * BEGINNER vs ADVANCED (V3-PLAN section 3): `nodes` is the flat left-to-right list, fit
 * for a simple beginner progression. `legs` breaks that same list into consecutive runs
 * of the same topology LAYER -- derived from `graph.nodes[id].layer`, never from tag-name
 * shape -- so the advanced view can expose the branch at the Station layer (the profile
 * leg is always its own trailing leg) without this module picking one rendering as "the"
 * architecture.
 *
 * Pure and read-only: resolve() never mutates `graph` and never hands back a live
 * reference into it -- every array returned is a fresh copy.
 *
 * API
 *   resolve(graph, tag, {path, profile}) -> {tag, path, profile, nodes, legs, missing}
 *     path in 'measurement'|'command'|'alarm'|'history'; profile in 'console'|'flex'.
 *     An inapplicable path/profile/tag never throws: nodes/legs come back empty and
 *     `missing` names why, so a caller can render "not applicable" instead of crashing.
 *     When applicable, `missing` lists any node id in the resolved path that does not
 *     exist in `graph.nodes` (should always be empty against a valid graph; surfaced
 *     rather than assumed, per the module's own purity/no-crash contract).
 *   applicablePaths(graph, tag) -> path-type strings this tag actually resolves
 *   describe(graph, resolved) -> plain-text reading for the inspector (our own prose)
 *   PATH_TYPES, PROFILES
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).SignalPath = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var PATH_TYPES = ['measurement', 'command', 'alarm', 'history'];
  var PROFILES = ['console', 'flex'];

  var LAYER_LABEL = {
    FIELD: 'Field', IO: 'I/O', CONTROL: 'Control', NETWORK: 'Network',
    SERVICE: 'Service', HMI: 'Station', INFORMATION: 'Information'
  };

  // Profile-dependent tail per path type, keyed off the real edges topology.js draws
  // (see header). Absent key (command) means no station leg is appended.
  var STATION_LEG = {
    measurement: { console: ['STN-CONSOLE'], flex: ['SVC-SERVER', 'STN-FLEX'] },
    alarm: { console: ['STN-CONSOLE'], flex: ['STN-FLEX'] },
    history: { console: ['STN-CONSOLE'], flex: ['STN-FLEX'] }
  };

  var PATH_LEAD = {
    measurement: 'Measurement path',
    command: 'Command path',
    alarm: 'Alarm path',
    history: 'History path'
  };

  /** Break a flat node-id list into legs of consecutive same-layer nodes. */
  function groupLegs(graph, nodeIds) {
    var legs = [], cur = null;
    nodeIds.forEach(function (nid) {
      var n = graph.nodes[nid];
      var layer = n ? n.layer : 'UNKNOWN';
      if (cur && cur.layer === layer) {
        cur.nodes.push(nid);
      } else {
        cur = { layer: layer, label: LAYER_LABEL[layer] || layer, nodes: [nid] };
        legs.push(cur);
      }
    });
    return legs.map(function (l) { return { label: l.label, nodes: l.nodes.slice() }; });
  }

  function emptyResult(tag, path, profile, reason) {
    return { tag: tag, path: path, profile: profile, nodes: [], legs: [], missing: [reason] };
  }

  /**
   * Resolve one point's path for one profile. Pure: copies every array it hands back and
   * never writes to `graph`.
   */
  function resolve(graph, tag, opts) {
    opts = opts || {};
    var path = opts.path;
    var profile = opts.profile === undefined ? 'console' : opts.profile;

    if (!graph || !graph.pointPaths) return emptyResult(tag, path, profile, 'no graph supplied');
    if (PATH_TYPES.indexOf(path) < 0) return emptyResult(tag, path, profile, 'unknown path type ' + path);
    if (PROFILES.indexOf(profile) < 0) return emptyResult(tag, path, profile, 'unknown profile ' + profile);

    var pp = graph.pointPaths[tag];
    if (!pp) return emptyResult(tag, path, profile, 'unknown point ' + tag);

    var base = pp[path];
    if (base === null || base === undefined) {
      return emptyResult(tag, path, profile, tag + ' has no ' + path + ' path');
    }

    var trunk = base.slice(); // copy out of the graph -- resolve() must not leak a live ref
    var legs = groupLegs(graph, trunk);

    var tail = (STATION_LEG[path] && STATION_LEG[path][profile]) ? STATION_LEG[path][profile].slice() : [];
    if (tail.length) legs.push({ label: 'Station (' + profile.toUpperCase() + ' profile)', nodes: tail.slice() });

    var nodes = trunk.concat(tail);
    var missing = nodes.filter(function (nid) { return !graph.nodes[nid]; });

    return { tag: tag, path: path, profile: profile, nodes: nodes, legs: legs, missing: missing };
  }

  /** Path types this tag actually resolves, per the non-null keys of its declared paths. */
  function applicablePaths(graph, tag) {
    var out = [];
    if (!graph || !graph.pointPaths || !graph.pointPaths[tag]) return out;
    var pp = graph.pointPaths[tag];
    ['measurement', 'alarm', 'history'].forEach(function (k) { if (pp[k] !== null && pp[k] !== undefined) out.push(k); });
    if (pp.command !== null && pp.command !== undefined) out.push('command');
    return out;
  }

  /** Plain-text reading of a resolved path for the inspector. Project-authored prose only. */
  function describe(graph, resolved) {
    if (!resolved) return 'No path resolved.';
    var lead = PATH_LEAD[resolved.path] || 'Signal path';
    if (!resolved.nodes.length) {
      var why = resolved.missing.length ? resolved.missing.join('; ') : 'not applicable';
      return lead + ' for ' + resolved.tag + ' is not available (' + why + ').';
    }
    var labels = resolved.nodes.map(function (nid) {
      var n = graph.nodes[nid];
      return n ? n.label : nid;
    });
    var sentence = lead + ' for ' + resolved.tag + ': ' + labels.join(' → ') + '.';
    if (STATION_LEG[resolved.path]) {
      sentence += resolved.profile === 'flex'
        ? ' The FLEX profile reaches the station through the data server’s cache, so a server fault can blind it while control stays healthy.'
        : ' The CONSOLE profile reaches the station on the direct controller/network path.';
    }
    return sentence;
  }

  return {
    PATH_TYPES: PATH_TYPES, PROFILES: PROFILES,
    resolve: resolve, applicablePaths: applicablePaths, describe: describe
  };
});
