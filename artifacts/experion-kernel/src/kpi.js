// @artifact production
/*
 * ESS.Kpi — alarm performance metrics and drill scoring.
 *
 * Metric definitions follow ISA-18.2 / EEMUA 191 as summarised in the exida
 * white paper (RESOURCES 2.7) and UvEternity/alarm-performance-analyser
 * (RESOURCES 2.8): flood = 10 or more alarms in 10 minutes, chattering =
 * 3 or more raises of the same alarm within 60 s, stale/standing = active
 * longer than a threshold (24 h nominal), bad actors = top-10 share of load,
 * priority split target 80/15/5 (Low/High/Urgent; the fourth, highest
 * priority under 1 % when one exists).
 *
 * API
 *   computeMetrics(history, opts) -> metrics
 *     history: array of {t (ms), key ('SRC.COND'), prio ('Urgent'|'High'|
 *       'Low'|'Journal'), type} where type is 'raise' (also accepts 'ALARM'),
 *       'rtn' (or 'RTN'), 'ack'. Only raises count as alarm load; Journal
 *       raises are journal-only and reported separately.
 *     opts: { t0, t1 (ms, window; default first/last event), staleAfterMs
 *       (default 24 h), floodWindowMs (600000), floodCount (10),
 *       chatterWindowMs (60000), chatterCount (3), topN (10) }
 *     returns { window:{t0,t1,minutes}, total, journal, per10min:{avg,peak},
 *       perDay, floods:[{start,end}], floodPct, chattering:[{key,count}],
 *       standing:[{key,prio,since,durationMs}], badActors:[{key,count,pct}],
 *       badActorPct, priority:{counts,pct,target,deviation}, health }
 *   health = { verdict:'GOOD'|'ACCEPTABLE'|'MANAGEABLE'|'OVERLOADED',
 *       checks:[{id,label,value,limit,pass}] }
 *   scoreDrill(metrics, rubric) -> {score, pass, passMark, passLabel, breakdown}
 *     metrics: { tAlarm, tAck, tAct, tStable (ms or null), trip (bool: a trip
 *       on the drill's own equipment), otherTrips (number, optional: trips on
 *       other equipment during the drill; each deducts otherTripPenalty, capped
 *       at otherTripMax, as a 'othertrips' row with max 0), actionCorrect
 *       (bool, default true when tAct set), quizCorrect (bool),
 *       alarmsPer10min (number, load during the drill) }
 *     rubric (all optional): weights {ack,action,trip,stable,load,quiz}
 *       (default 20/25/20/15/10/10), ackFast/ackOk/ackSlow seconds
 *       (30/60/120), actionFast/actionOk seconds (180/360), loadTarget/
 *       loadMax per 10 min (1/10), otherTripPenalty/otherTripMax (10/20),
 *       allowProactive (false), passMark (80). The score is clamped to 0..100.
 *     The 80 % pass mark is the sim's own threshold, labelled independent of
 *     any vendor certification scheme (RESOURCES 2.12).
 *     A correct action that precedes or prevents the first alarm receives full
 *     action credit only when allowProactive is true: tAct proves the action
 *     occurred, while a missing/later tAlarm distinguishes the proactive case.
 *   thresholds -> the exida/ISA numbers used by the health verdict.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Kpi = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var THRESHOLDS = {
    perDayAcceptable: 150, perDayManageable: 300,
    per10minTarget: 1, per10minManageable: 2, per10minMax: 10,
    floodPctMax: 1, top10PctTarget: 1, top10PctMax: 5,
    chatteringMax: 0, standingMax: 5,
    priorityTarget: { Low: 80, High: 15, Urgent: 5 }
  };
  var ALARM_PRIOS = ['Urgent', 'High', 'Low'];

  function isRaise(e) { var t = String(e.type || 'raise').toLowerCase(); return t === 'raise' || t === 'alarm'; }
  function isRtn(e) { var t = String(e.type || '').toLowerCase(); return t === 'rtn' || t === 'return' || t === 'clear'; }
  function pct(n, d) { return d > 0 ? n / d * 100 : 0; }
  function round(v, p) { var m = Math.pow(10, p || 0); return Math.round(v * m) / m; }

  function sortedByTime(history) { return history.slice().sort(function (a, b) { return a.t - b.t; }); }

  function windowOf(events, opts) {
    var t0 = typeof opts.t0 === 'number' ? opts.t0 : (events.length ? events[0].t : 0);
    var t1 = typeof opts.t1 === 'number' ? opts.t1 : (events.length ? events[events.length - 1].t : t0);
    if (t1 < t0) t1 = t0;
    return { t0: t0, t1: t1, minutes: (t1 - t0) / 60000 };
  }

  // Counts of raises in each sliding window [t_i, t_i + width) anchored at a raise.
  function slidingCounts(times, width) {
    var out = [], j = 0;
    for (var i = 0; i < times.length; i++) {
      while (j < times.length && times[j] < times[i] + width) j++;
      out.push(j - i);
    }
    return out;
  }

  function mergeIntervals(iv) {
    iv.sort(function (a, b) { return a.start - b.start; });
    var out = [];
    for (var i = 0; i < iv.length; i++) {
      var last = out[out.length - 1];
      if (last && iv[i].start <= last.end) last.end = Math.max(last.end, iv[i].end);
      else out.push({ start: iv[i].start, end: iv[i].end });
    }
    return out;
  }

  function floodPeriods(times, win, count, cap) {
    var counts = slidingCounts(times, win), iv = [];
    for (var i = 0; i < times.length; i++) if (counts[i] >= count) iv.push({ start: times[i], end: Math.min(times[i] + win, cap) });
    return mergeIntervals(iv);
  }

  function groupByKey(raises) {
    var m = {};
    raises.forEach(function (e) { (m[e.key] = m[e.key] || []).push(e.t); });
    return m;
  }

  function chatteringKeys(byKey, win, count) {
    var out = [];
    Object.keys(byKey).forEach(function (k) {
      var c = slidingCounts(byKey[k], win), best = 0;
      for (var i = 0; i < c.length; i++) if (c[i] > best) best = c[i];
      if (best >= count) out.push({ key: k, count: best });
    });
    return out.sort(function (a, b) { return b.count - a.count; });
  }

  function standingAlarms(events, win, staleAfter) {
    var open = {}, out = [];
    events.forEach(function (e) {
      if (e.t < win.t0 || e.t > win.t1) return;
      if (isRaise(e) && e.prio !== 'Journal') { if (!open[e.key]) open[e.key] = e; }
      else if (isRtn(e)) delete open[e.key];
    });
    Object.keys(open).forEach(function (k) {
      var dur = win.t1 - open[k].t;
      if (dur >= staleAfter) out.push({ key: k, prio: open[k].prio, since: open[k].t, durationMs: dur });
    });
    return out.sort(function (a, b) { return b.durationMs - a.durationMs; });
  }

  function badActors(byKey, total, topN) {
    return Object.keys(byKey).map(function (k) { return { key: k, count: byKey[k].length, pct: round(pct(byKey[k].length, total), 1) }; })
      .sort(function (a, b) { return b.count - a.count || (a.key < b.key ? -1 : 1); }).slice(0, topN);
  }

  function priorityDistribution(raises) {
    var counts = { Urgent: 0, High: 0, Low: 0 }, total = 0;
    raises.forEach(function (e) { if (counts.hasOwnProperty(e.prio)) { counts[e.prio]++; total++; } });
    var p = {}, dev = {};
    ALARM_PRIOS.forEach(function (k) { p[k] = round(pct(counts[k], total), 1); dev[k] = round(p[k] - THRESHOLDS.priorityTarget[k], 1); });
    return { counts: counts, pct: p, target: THRESHOLDS.priorityTarget, deviation: dev, total: total };
  }

  function healthVerdict(m) {
    var T = THRESHOLDS;
    var checks = [
      { id: 'rate', label: 'Average alarms per 10 min', value: m.per10min.avg, limit: T.per10minTarget, pass: m.per10min.avg <= T.per10minTarget },
      { id: 'perDay', label: 'Alarms per day (equivalent)', value: m.perDay, limit: T.perDayAcceptable, pass: m.perDay <= T.perDayAcceptable },
      { id: 'peak', label: 'Peak alarms in any 10 min', value: m.per10min.peak, limit: T.per10minMax, pass: m.per10min.peak <= T.per10minMax },
      { id: 'flood', label: 'Time in flood (%)', value: m.floodPct, limit: T.floodPctMax, pass: m.floodPct < T.floodPctMax },
      { id: 'badActors', label: 'Top-10 share of load (%)', value: m.badActorPct, limit: T.top10PctMax, pass: m.badActorPct <= T.top10PctMax || m.total < 10 },
      { id: 'chattering', label: 'Chattering alarms', value: m.chattering.length, limit: T.chatteringMax, pass: m.chattering.length === 0 },
      { id: 'standing', label: 'Stale / standing alarms', value: m.standing.length, limit: T.standingMax, pass: m.standing.length < T.standingMax }
    ];
    var verdict;
    if (m.perDay > T.perDayManageable || m.per10min.peak > T.per10minMax || m.floodPct >= T.floodPctMax) verdict = 'OVERLOADED';
    else if (m.perDay > T.perDayAcceptable || m.per10min.avg > T.per10minManageable) verdict = 'MANAGEABLE';
    else if (checks.every(function (c) { return c.pass; })) verdict = 'GOOD';
    else verdict = 'ACCEPTABLE';
    return { verdict: verdict, checks: checks };
  }

  function computeMetrics(history, opts) {
    opts = opts || {};
    var events = sortedByTime(history || []);
    var win = windowOf(events, opts);
    var staleAfter = typeof opts.staleAfterMs === 'number' ? opts.staleAfterMs : 24 * 3600000;
    var floodWin = opts.floodWindowMs || 600000, floodN = opts.floodCount || 10;
    var chatWin = opts.chatterWindowMs || 60000, chatN = opts.chatterCount || 3;
    var topN = opts.topN || 10;

    var inWin = events.filter(function (e) { return e.t >= win.t0 && e.t <= win.t1; });
    var raises = inWin.filter(function (e) { return isRaise(e) && e.prio !== 'Journal'; });
    var journal = inWin.filter(function (e) { return isRaise(e) && e.prio === 'Journal'; }).length;
    var times = raises.map(function (e) { return e.t; });
    var total = raises.length;
    var byKey = groupByKey(raises);

    var tenMinBlocks = Math.max(win.minutes / 10, 1e-9);
    var counts = slidingCounts(times, floodWin);
    var peak = counts.reduce(function (a, b) { return Math.max(a, b); }, 0);
    var floods = floodPeriods(times, floodWin, floodN, win.t1);
    var floodMs = floods.reduce(function (a, f) { return a + (f.end - f.start); }, 0);
    var actors = badActors(byKey, total, topN);
    var actorCount = actors.reduce(function (a, b) { return a + b.count; }, 0);

    var m = {
      window: win, total: total, journal: journal,
      per10min: { avg: round(total / tenMinBlocks, 2), peak: peak },
      perDay: round(total / tenMinBlocks * 144, 0),
      floods: floods, floodPct: round(pct(floodMs, win.t1 - win.t0), 2),
      chattering: chatteringKeys(byKey, chatWin, chatN),
      standing: standingAlarms(events, win, staleAfter),
      badActors: actors, badActorPct: round(pct(actorCount, total), 1),
      priority: priorityDistribution(raises)
    };
    m.health = healthVerdict(m);
    return m;
  }

  var DEFAULT_RUBRIC = {
    weights: { ack: 20, action: 25, trip: 20, stable: 15, load: 10, quiz: 10 },
    ackFast: 30, ackOk: 60, ackSlow: 120, actionFast: 180, actionOk: 360,
    loadTarget: THRESHOLDS.per10minTarget, loadMax: THRESHOLDS.per10minMax, passMark: 80,
    otherTripPenalty: 10, otherTripMax: 20, allowProactive: false
  };

  function latencySec(from, to) { return (typeof from === 'number' && typeof to === 'number') ? (to - from) / 1000 : null; }

  function scoreDrill(metrics, rubric) {
    var R = Object.assign({}, DEFAULT_RUBRIC, rubric || {});
    var W = Object.assign({}, DEFAULT_RUBRIC.weights, (rubric && rubric.weights) || {});
    var m = metrics || {};
    var rows = [];

    var ack = latencySec(m.tAlarm, m.tAck);
    var ackFrac = ack == null ? 0 : ack <= R.ackFast ? 1 : ack <= R.ackOk ? 0.7 : ack <= R.ackSlow ? 0.4 : 0.15;
    rows.push({ id: 'ack', label: 'Time to acknowledge', earned: round(W.ack * ackFrac, 1), max: W.ack, note: ack == null ? 'not acknowledged' : round(ack, 0) + ' s' });

    var hasAct = typeof m.tAct === 'number';
    var act = latencySec(m.tAlarm, m.tAct);
    var correct = m.actionCorrect !== false && hasAct;
    var proactive = correct && (act == null || act < 0);
    var proactiveAllowed = proactive && R.allowProactive === true;
    var actFrac = !correct || (proactive && !proactiveAllowed) ? 0 : proactiveAllowed || act <= R.actionFast ? 1 : act <= R.actionOk ? 0.6 : 0.3;
    var actNote = !hasAct ? 'correct action not taken' : m.actionCorrect === false ? 'action taken but incorrect' :
      act == null ? (R.allowProactive ? 'taken proactively — no alarm annunciated' : 'taken without an alarm — drill does not award proactive credit') :
      act < 0 ? (R.allowProactive ? round(-act, 0) + ' s before alarm' : round(-act, 0) + ' s before alarm — drill does not award proactive credit') : round(act, 0) + ' s';
    rows.push({ id: 'action', label: 'Correct action and latency', earned: round(W.action * actFrac, 1), max: W.action, note: actNote });

    rows.push({ id: 'trip', label: 'Trip avoided', earned: m.trip ? 0 : W.trip, max: W.trip, note: m.trip ? 'unit tripped' : 'no trip' });
    rows.push({ id: 'stable', label: 'Process stabilised', earned: m.tStable ? W.stable : 0, max: W.stable, note: m.tStable ? 'stabilised' : 'not stabilised' });

    var load = typeof m.alarmsPer10min === 'number' ? m.alarmsPer10min : null;
    var loadFrac = load == null ? 1 : load <= R.loadTarget ? 1 : load >= R.loadMax ? 0 : 1 - (load - R.loadTarget) / (R.loadMax - R.loadTarget);
    rows.push({ id: 'load', label: 'Alarm load during drill', earned: round(W.load * loadFrac, 1), max: W.load, note: load == null ? 'not measured' : round(load, 1) + ' per 10 min' });

    rows.push({ id: 'quiz', label: 'Debrief question', earned: m.quizCorrect ? W.quiz : 0, max: W.quiz, note: m.quizCorrect ? 'correct' : 'incorrect' });

    // trips on equipment outside the drill's scope (e.g. flooding TK-101 while handling an R-201 exotherm) are not the
    // drill's trip, but they are not free either: a flat deduction per trip, capped, shown as a row with no maximum
    if (typeof m.otherTrips === 'number') {
      var n = Math.max(0, Math.round(m.otherTrips));
      var pen = Math.min(R.otherTripMax, n * R.otherTripPenalty);
      rows.push({ id: 'othertrips', label: 'Other equipment trips', earned: -pen, max: 0, note: n ? n + ' trip' + (n > 1 ? 's' : '') + ' outside the drill scope (−' + pen + ')' : 'none' });
    }

    var max = rows.reduce(function (a, r) { return a + r.max; }, 0);
    var earned = rows.reduce(function (a, r) { return a + r.earned; }, 0);
    var score = Math.max(0, Math.min(100, Math.round(max > 0 ? earned / max * 100 : 0)));
    return { score: score, pass: score >= R.passMark, passMark: R.passMark, passLabel: R.passMark + ' % pass mark (sim-defined; independent of any vendor certification)', breakdown: rows };
  }

  return { computeMetrics: computeMetrics, scoreDrill: scoreDrill, thresholds: THRESHOLDS, DEFAULT_RUBRIC: DEFAULT_RUBRIC };
});
