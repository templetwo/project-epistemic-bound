// @artifact production
/*
 * ESS.Debrief — the synchronised debrief timeline (V3-PLAN section 7, Debrief mode;
 * stage S4): "architecture timeline synchronized with process values, alarms,
 * operator and instructor actions, and score during replay."
 *
 * PURE. No DOM, no timers, no globals read, no Math.random, no Date.now, no sibling
 * require. Everything arrives as arguments; the caller (the app, at S4 integration)
 * hands in the journal, the alarm log, the event log, the architecture fault
 * timeline, the trend history and the score, and gets back ONE ordered list of rows.
 * The journal is READ, never mutated: every input array is copied before sorting and
 * no input object is written to (tests deep-freeze the inputs to prove it).
 *
 * API
 *   build(input, opts) -> { rows, refusals, summary, score, t0, t1, projection, lanes }
 *     input.journal        [{seq, t, op, tag, arg, instr?, actor?, accepted?, reason?}]
 *                          (ESS.Instructor.journalAdd shape; ESS.Dispatch adds actor,
 *                          accepted, reason). Only an EXPLICIT accepted:false is a
 *                          refusal — undefined means applied, exactly as replayPlan reads it.
 *     input.alarmLog       [{t, key, tag, cond, prio, type:'raise'|'rtn'|'ack'}]  (preferred)
 *     input.alarms         [{t, tag, cond, prio, ackT, rtnT, ...}]  (fallback when no alarmLog)
 *     input.events         [{id, t, type, src, desc, ...}]  src 'INSTR' = instructor row
 *     input.faultTimeline  [{t, faultId, targetNodeId, phase?, health?}]  architecture
 *                          health changes; phase defaults to ACTIVE
 *     input.hist           { TAG: [[t, pv, sp, op], ...] }  trend history, sampled per row
 *     input.score          {score, pass, passMark?, breakdown:[{label, earned, max, note}]}
 *     input.t0 / input.t1  window override (ms); default = min / max t across inputs
 *     opts.projection      'DEBRIEF_REVEALED' (default) | 'TRAINEE_SAFE'
 *                          TRAINEE_SAFE renders architecture rows as health changes only
 *                          and carries NO fault id anywhere in the output (V3-PLAN 7:
 *                          "no trainee-visible surface renders root-cause truth").
 *     opts.tags            process tags to sample beside every row (default: all hist
 *                          tags, sorted, capped at 8; pass [] to disable)
 *     opts.journalText     fn(entry) -> string, e.g. e => ESS.Instructor.journalText(e, fmt)
 *                          (optional; a plain "OP TAG ARG" default is used otherwise)
 *
 *   Row { t, rel, lane, actor, kind, text, ref, accepted, judgment, process }
 *     lane   ARCH | INSTRUCTOR | OPERATOR | SYSTEM | ALARM | EVENT | SCORE
 *     actor  INSTRUCTOR | TRAINEE | SYSTEM | ASSISTANT   (V3-PLAN 4 ActionEvent.actor)
 *     kind   ACTION | REFUSED | RAISE | RTN | ACK | <event type> | REPLAY_MARKER |
 *            FAULT | HEALTH | SCORE
 *     judgment  null, or {verdict:'REFUSED', reason} for an attempted-but-refused
 *               action. The architect's ruling (2026-08-30) is that a refusal does not
 *               trip the drill safety gate but MUST be visible in the debrief; this row
 *               is that visibility. It is additive: nothing here changes how
 *               ESS.DrillArch scores.
 *     process   { TAG: {pv, sp, op} } sampled at the row's t (nearest earlier history row)
 *
 *   Ordering is total and deterministic: t ascending, then lane precedence (LANES
 *   order), then seq / id ascending, then text. Two identical inputs produce
 *   byte-identical output, which is what lets a replay's debrief be compared with a
 *   live run's.
 *
 *   Instructor rows and trainee rows are always distinguishable by `actor` AND by
 *   `lane`, because a debrief is shown after the exercise, when truth is allowed and
 *   the learner needs to see which moves were theirs.
 *
 *   REPLAY marker events ("REPLAY FROM SNAPSHOT", "REPLAY STARTED", "REPLAY COMPLETE")
 *   are kept as rows but flagged kind REPLAY_MARKER and excluded from summary.counts,
 *   because a replay that logs itself can never match a live run's event count and
 *   that is honest, not a defect (seat 3/3 diagnosis, 2026-08-31).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Debrief = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var LANES = ['ARCH', 'INSTRUCTOR', 'OPERATOR', 'SYSTEM', 'ALARM', 'EVENT', 'SCORE'];
  var ACTORS = ['INSTRUCTOR', 'TRAINEE', 'SYSTEM', 'ASSISTANT'];
  var PROJECTIONS = ['DEBRIEF_REVEALED', 'TRAINEE_SAFE'];
  // Legacy journal ops that are instructor acts even when an entry carries neither
  // `instr:true` nor an `actor` (defensive: the app stamps instr:true on all of them today).
  var INSTRUCTOR_OPS = ['SEED', 'UPSET', 'VAR', 'SNAPSHOT', 'RESTORE', 'REPLAY', 'HIDDEN', 'SPEED',
    'FAULT_INJECT', 'FAULT_CLEAR', 'ARCH_FAULT_ACTIVATE', 'ARCH_FAULT_CLEAR', 'DRILL_START', 'DRILL_END', 'SNAPSHOT_RESTORE'];
  var MAX_DEFAULT_TAGS = 8;

  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function str(v) { return v == null ? '' : String(v); }
  function laneRank(l) { var i = LANES.indexOf(l); return i < 0 ? LANES.length : i; }

  function isReplayMarker(desc) { return /^REPLAY\b/.test(str(desc)); }

  function actorOfEntry(e) {
    if (e.actor && ACTORS.indexOf(e.actor) >= 0) return e.actor;
    if (e.instr === true) return 'INSTRUCTOR';
    if (INSTRUCTOR_OPS.indexOf(str(e.op)) >= 0) return 'INSTRUCTOR';
    return 'TRAINEE';
  }
  function laneOfActor(a) {
    if (a === 'INSTRUCTOR') return 'INSTRUCTOR';
    if (a === 'TRAINEE') return 'OPERATOR';
    return 'SYSTEM';
  }

  /** ESS.Dispatch has TWO record shapes (seat 2/3 finding, 2026-08-31): it JOURNALS the
   *  legacy {t, op, tag, arg, actor?, accepted?, reason?} that journalText/replayPlan read,
   *  and RETURNS an ActionEvent {seq, simTime, actor, actionType, target, payload, accepted,
   *  reason?}. Feeding the wrong one to a consumer that keys on the other silently yields
   *  nothing. This module accepts either, so an S4 integrator cannot lose rows by shape. */
  function normalizeEntry(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var t = isNum(raw.t) ? raw.t : (isNum(raw.simTime) ? raw.simTime : null);
    if (t == null) return null;
    return {
      t: t, seq: raw.seq, instr: raw.instr, actor: raw.actor, accepted: raw.accepted, reason: raw.reason, param: raw.param,
      op: raw.op != null ? raw.op : raw.actionType,
      tag: raw.tag != null ? raw.tag : raw.target,
      arg: raw.arg != null ? raw.arg : (raw.payload != null && typeof raw.payload !== 'object' ? raw.payload : (raw.payload != null ? JSON.stringify(raw.payload) : raw.arg))
    };
  }

  function defaultJournalText(e) {
    var parts = [str(e.op), str(e.tag), e.param != null ? str(e.param) : '', str(e.arg)].filter(function (s) { return s !== ''; });
    return parts.join(' ');
  }

  /** Nearest history row at or before t: rows are [t, pv, sp, op], ascending in t. */
  function sampleAt(rows, t) {
    if (!rows || !rows.length || !isNum(t)) return null;
    var lo = 0, hi = rows.length - 1, best = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (rows[mid][0] <= t) { best = mid; lo = mid + 1; } else hi = mid - 1;
    }
    if (best < 0) return null;
    var r = rows[best];
    return { pv: r[1] == null ? null : r[1], sp: r[2] == null ? null : r[2], op: r[3] == null ? null : r[3] };
  }

  function chooseTags(hist, opts) {
    if (opts && Array.isArray(opts.tags)) return opts.tags.slice();
    if (!hist) return [];
    return Object.keys(hist).sort().slice(0, MAX_DEFAULT_TAGS);
  }

  function row(t, lane, actor, kind, text, ref, accepted, judgment) {
    return { t: t, rel: 0, lane: lane, actor: actor, kind: kind, text: text, ref: ref || {}, accepted: accepted, judgment: judgment || null, process: {} };
  }

  function build(input, opts) {
    input = input || {}; opts = opts || {};
    var projection = PROJECTIONS.indexOf(opts.projection) >= 0 ? opts.projection : 'DEBRIEF_REVEALED';
    var reveal = projection === 'DEBRIEF_REVEALED';
    var fmt = typeof opts.journalText === 'function' ? opts.journalText : defaultJournalText;
    var rows = [], refusals = [];
    var counts = { operator: 0, instructor: 0, system: 0, refused: 0, alarms: 0, acks: 0, events: 0, replayMarkers: 0, arch: 0 };

    // --- journal: operator and instructor actions, refusals as judgment notes
    (input.journal || []).forEach(function (raw) {
      var e = normalizeEntry(raw);
      if (!e) return;
      var actor = actorOfEntry(e), lane = laneOfActor(actor);
      var refused = e.accepted === false;
      var text = str(fmt(e));
      var judgment = null;
      if (refused) {
        judgment = { verdict: 'REFUSED', reason: str(e.reason) || 'refused' };
        text = 'REFUSED — ' + text + (e.reason ? ' (' + str(e.reason) + ')' : '');
        counts.refused++;
      } else if (lane === 'OPERATOR') counts.operator++;
      else if (lane === 'INSTRUCTOR') counts.instructor++;
      else counts.system++;
      var r = row(e.t, lane, actor, refused ? 'REFUSED' : 'ACTION', text, { seq: e.seq == null ? null : e.seq, op: str(e.op), tag: str(e.tag) }, !refused, judgment);
      rows.push(r);
      if (refused) refusals.push(r);
    });

    // --- alarms: the alarm log is the timeline; the alarm list is the fallback
    if (input.alarmLog && input.alarmLog.length) {
      input.alarmLog.forEach(function (a) {
        if (!a || !isNum(a.t)) return;
        var type = str(a.type || 'raise').toLowerCase();
        var kind = type === 'ack' ? 'ACK' : type === 'rtn' ? 'RTN' : 'RAISE';
        if (kind === 'RAISE') counts.alarms++; else if (kind === 'ACK') counts.acks++;
        rows.push(row(a.t, 'ALARM', kind === 'ACK' ? 'TRAINEE' : 'SYSTEM', kind,
          'ALARM ' + kind + ' ' + str(a.tag) + ' ' + str(a.cond) + (a.prio ? ' ' + str(a.prio) : ''),
          { key: str(a.key || (str(a.tag) + '.' + str(a.cond))) }, true, null));
      });
    } else {
      (input.alarms || []).forEach(function (a) {
        if (!a || !isNum(a.t)) return;
        var key = str(a.key || (str(a.tag || a.src) + '.' + str(a.cond)));
        counts.alarms++;
        rows.push(row(a.t, 'ALARM', 'SYSTEM', 'RAISE', 'ALARM RAISE ' + str(a.tag || a.src) + ' ' + str(a.cond) + (a.prio ? ' ' + str(a.prio) : ''), { key: key }, true, null));
        if (isNum(a.ackT) && a.ackT > 0) { counts.acks++; rows.push(row(a.ackT, 'ALARM', 'TRAINEE', 'ACK', 'ALARM ACK ' + str(a.tag || a.src) + ' ' + str(a.cond), { key: key }, true, null)); }
        if (isNum(a.rtnT) && a.rtnT > 0) rows.push(row(a.rtnT, 'ALARM', 'SYSTEM', 'RTN', 'ALARM RTN ' + str(a.tag || a.src) + ' ' + str(a.cond), { key: key }, true, null));
      });
    }

    // --- events: system log; INSTR-sourced rows are instructor rows; REPLAY markers flagged
    (input.events || []).forEach(function (ev) {
      if (!ev || !isNum(ev.t)) return;
      var marker = isReplayMarker(ev.desc);
      var actor = ev.src === 'INSTR' ? 'INSTRUCTOR' : 'SYSTEM';
      if (marker) counts.replayMarkers++; else counts.events++;
      rows.push(row(ev.t, 'EVENT', actor, marker ? 'REPLAY_MARKER' : str(ev.type || 'EVENT'),
        str(ev.type) + ' ' + str(ev.src) + ' ' + str(ev.desc), { id: ev.id == null ? null : ev.id, src: str(ev.src) }, true, null));
    });

    // --- architecture: fault timeline, revealed or trainee-safe
    (input.faultTimeline || []).forEach(function (f) {
      if (!f || !isNum(f.t)) return;
      counts.arch++;
      var node = str(f.targetNodeId || f.nodeId || f.node);
      var phase = str(f.phase || 'ACTIVE').toUpperCase();
      if (reveal) {
        rows.push(row(f.t, 'ARCH', 'INSTRUCTOR', 'FAULT', 'ARCH ' + phase + ' ' + str(f.faultId) + ' @ ' + node + (f.health ? ' → ' + str(f.health) : ''),
          { faultId: str(f.faultId), targetNodeId: node, phase: phase }, true, null));
      } else {
        var health = str(f.health || (phase === 'CLEARED' || phase === 'EXPIRED' ? 'HEALTHY' : 'DEGRADED'));
        rows.push(row(f.t, 'ARCH', 'SYSTEM', 'HEALTH', 'ARCH ' + node + ' health ' + health, { targetNodeId: node, health: health }, true, null));
      }
    });

    // --- window
    var ts = rows.map(function (r) { return r.t; });
    var t0 = isNum(input.t0) ? input.t0 : (ts.length ? Math.min.apply(null, ts) : 0);
    var t1 = isNum(input.t1) ? input.t1 : (ts.length ? Math.max.apply(null, ts) : t0);

    // --- score, pinned to the end of the window
    var score = null;
    if (input.score && isNum(input.score.score)) {
      var s = input.score;
      score = { score: s.score, pass: !!s.pass, passMark: isNum(s.passMark) ? s.passMark : null,
        breakdown: (s.breakdown || []).map(function (b) { return { label: str(b.label), earned: b.earned, max: b.max, note: str(b.note) }; }) };
      rows.push(row(t1, 'SCORE', 'SYSTEM', 'SCORE', 'SCORE ' + s.score + (isNum(s.passMark) ? ' / pass mark ' + s.passMark : '') + ' — ' + (s.pass ? 'PASS' : 'NOT PASSED'),
        { breakdown: score.breakdown }, true, null));
    }

    // --- total, deterministic order
    rows.sort(function (a, b) {
      if (a.t !== b.t) return a.t - b.t;
      var la = laneRank(a.lane), lb = laneRank(b.lane); if (la !== lb) return la - lb;
      var ia = a.ref.seq != null ? a.ref.seq : (a.ref.id != null ? a.ref.id : 0);
      var ib = b.ref.seq != null ? b.ref.seq : (b.ref.id != null ? b.ref.id : 0);
      if (ia !== ib) return ia - ib;
      return a.text < b.text ? -1 : a.text > b.text ? 1 : 0;
    });

    // --- process values beside every row
    var tags = chooseTags(input.hist, opts);
    rows.forEach(function (r) {
      r.rel = r.t - t0;
      tags.forEach(function (tag) { var v = sampleAt(input.hist && input.hist[tag], r.t); if (v) r.process[tag] = v; });
    });

    return { rows: rows, refusals: refusals, lanes: LANES.slice(), projection: projection, t0: t0, t1: t1, score: score,
      summary: { t0: t0, t1: t1, durationMs: t1 - t0, counts: counts, refused: refusals.length, pass: score ? score.pass : null, tags: tags } };
  }

  return { LANES: LANES, ACTORS: ACTORS, PROJECTIONS: PROJECTIONS, INSTRUCTOR_OPS: INSTRUCTOR_OPS, build: build, sampleAt: sampleAt, isReplayMarker: isReplayMarker, normalizeEntry: normalizeEntry };
});
