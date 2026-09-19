// @artifact production
/*
 * alarm-engine.js: ISA-18.2 alarm state engine for the station simulator.
 *
 * Pure logic: no DOM, no timers, no globals other than the ESS namespace
 * attachment. Time is always passed in by the caller (simulation clock in
 * milliseconds), never read from Date, so the engine is deterministic and
 * fully testable under node.
 *
 * Sources (see docs/RESOURCES.md):
 *   - state table per alerta isa_18_2.py (RESOURCES 2.5): NORM, UNACK, ACKED,
 *     RTNUN, SHLVD, DSUPR, OOSRV and the ack / RTN / re-alarm transitions.
 *   - on-delay, off-delay and maximum shelve duration per loxalarm (2.9).
 *   - per-state indication table per the Siemens alarm-management paper (2.6):
 *     blink + audible only while unacknowledged, steady when acknowledged,
 *     nothing for shelved / suppressed / out-of-service.
 *   - sub-priority 0..15 and two journal events per alarm (enter, RTN) per the
 *     Experion LX HMI spec (2.1).
 *   - repeat folding (first time, last time, count), comments, Dynamic Alarm
 *     Suppression and shelving with reason and timer per the Experion
 *     Alarming PIN (2.2).
 *
 * ---------------------------------------------------------------------------
 * API (the module value is the object returned at the bottom)
 *
 *   createEngine(opts) -> engine
 *     opts.foldWindowMs     re-raise within this many ms of the last RTN folds
 *                           into the existing record (default 600000 = 10 min)
 *     opts.defaultShelveMs  shelve duration when none is given (default 1 h)
 *     opts.maxShelveMs      hard cap on any shelve duration (default 8 h)
 *     opts.recordJournal    keep Journal-priority alarms as records (default
 *                           false: Journal produces events only)
 *     opts.dasRules         {triggerKey: [suppressedKey, ...]} for DAS
 *     opts.idStart          first record id (default 1)
 *
 *   Every mutator returns an ARRAY of event descriptors for the caller to log:
 *     { type: 'ALARM'|'RTN'|'ACK'|'SHELVE'|'UNSHELVE'|'SUPPRESS'|'UNSUPPRESS'
 *             |'OOS'|'RTS', key, tag, cond, prio, subprio, t, val, desc,
 *       from: <state before>, to: <state after>, ...extras }
 *   extras: ALARM carries journal:true for Journal priority, folded:true when a
 *   repeat was folded, escalated:true on a re-alarm at higher priority;
 *   UNSHELVE carries auto:true on timer expiry; SUPPRESS carries suppressedBy.
 *
 *   engine.raise({tag, cond, prio, subprio, val, eu, desc, tripValue, t})
 *   engine.rtn(tag, cond, t, val)          process condition cleared
 *   engine.ack(ref, t)                     ref = record id, key or record
 *   engine.ackAll(t)                       acknowledge every UNACK / RTNUN
 *   engine.shelve(ref, {reason, durationMs, t})
 *   engine.unshelve(ref, t)
 *   engine.suppress(ref, triggerKey, t)    designed suppression (DSUPR)
 *   engine.unsuppress(ref, t)
 *   engine.oos(ref, t, spec?)              out of service (OOSRV); spec creates
 *                                          the record when none exists yet
 *   engine.rts(ref, t)                     return to service
 *   engine.comment(ref, text)              per-alarm comment (no event)
 *   engine.tick(t)                         shelve expiry + pruning of stale
 *                                          NORM records; call each scan step
 *   engine.setDasRules(rules)              replace the DAS rule map
 *
 *   engine.get(ref)                        record or undefined
 *   engine.list()                          records not in NORM (Alarm Summary)
 *   engine.all()                           every record incl. NORM (fold cache)
 *   engine.active()      live process condition, any state
 *   engine.unacked()     UNACK or RTNUN (the annunciating set)
 *   engine.shelved()     SHLVD
 *   engine.suppressed()  DSUPR
 *   engine.oos()         OOSRV
 *   engine.byUnit(fn)    records whose tag satisfies fn(tag)
 *   engine.counts()      {Urgent, High, Low, Journal, total, unack}; the
 *                        buckets and total are UNACK+ACKED only, unack is
 *                        UNACK+RTNUN
 *   engine.topUnack()    highest priority unacked record or null
 *   engine.dasView()     [{trigger, key, suppressedKeys:[...]}] for a DAS tab
 *
 *   Record shape (a superset of the pre-v2 app record):
 *     { id, key:'TAG.COND', tag, cond, prio, subprio, state, t, lastT, rtnT,
 *       ackT, count, val, eu, desc, tripValue, ack, active, shelved,
 *       shelveReason, until, comment, suppressedBy }
 *   ack / active / shelved are derived booleans refreshed on every transition.
 *
 *   Module-level helpers (also on the engine for convenience):
 *     evaluateLimit({pv, trip, kind:'HI'|'LO', deadband, onDelaySec,
 *                    offDelaySec, dt, memo}) -> {active, memo}
 *     indication(state, prio) -> {blink, audible, steady, inverse}
 *     compare(a, b)            sort comparator: Urgent > High > Low > Journal,
 *                              then subprio desc, then lastT desc
 *     annunciates(rec)         true when rec should sound / flash
 *     STATES, PRIORITIES, PRIO_RANK
 * ---------------------------------------------------------------------------
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).AlarmEngine = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var STATES = ['NORM', 'UNACK', 'ACKED', 'RTNUN', 'SHLVD', 'DSUPR', 'OOSRV'];
  var PRIORITIES = ['Urgent', 'High', 'Low', 'Journal'];
  var PRIO_RANK = { Urgent: 3, High: 2, Low: 1, Journal: 0 };
  var DEFAULTS = {
    foldWindowMs: 10 * 60 * 1000,
    defaultShelveMs: 60 * 60 * 1000,
    maxShelveMs: 8 * 60 * 60 * 1000,
    recordJournal: false,
    dasRules: {},
    idStart: 1
  };

  // Siemens per-state indication table (RESOURCES 2.6). Journal never annunciates (2.1).
  function indication(state, prio) {
    var journal = prio === 'Journal';
    switch (state) {
      case 'UNACK': return { blink: true, audible: !journal, steady: false, inverse: false };
      case 'RTNUN': return { blink: true, audible: false, steady: false, inverse: true };
      case 'ACKED': return { blink: false, audible: false, steady: true, inverse: false };
      default: return { blink: false, audible: false, steady: false, inverse: false };
    }
  }

  function annunciates(rec) {
    return !!rec && rec.prio !== 'Journal' && (rec.state === 'UNACK' || rec.state === 'RTNUN');
  }

  function rank(p) { return PRIO_RANK[p] === undefined ? -1 : PRIO_RANK[p]; }

  function compare(a, b) {
    var d = rank(b.prio) - rank(a.prio);
    if (d) return d;
    d = (b.subprio || 0) - (a.subprio || 0);
    if (d) return d;
    d = (b.lastT || 0) - (a.lastT || 0);
    if (d) return d;
    return (a.id || 0) - (b.id || 0);
  }

  function clampSub(s) {
    var n = Math.round(Number(s));
    if (!isFinite(n)) return 0;
    return n < 0 ? 0 : n > 15 ? 15 : n;
  }

  // Limit with deadband (hysteresis) plus on/off delay, loxalarm style (RESOURCES 2.9, 2.6).
  // memo is mutated in place and returned; pass the same object every scan.
  function evaluateLimit(o) {
    var memo = o.memo || { raw: false, active: false, onT: 0, offT: 0 };
    var db = o.deadband || 0, dt = o.dt || 0;
    var raw = memo.raw;
    if (o.kind === 'LO') {
      if (o.pv <= o.trip) raw = true; else if (o.pv > o.trip + db) raw = false;
    } else {
      if (o.pv >= o.trip) raw = true; else if (o.pv < o.trip - db) raw = false;
    }
    memo.raw = raw;
    if (raw && !memo.active) {
      memo.onT += dt; memo.offT = 0;
      if (memo.onT >= (o.onDelaySec || 0)) { memo.active = true; memo.onT = 0; }
    } else if (!raw && memo.active) {
      memo.offT += dt; memo.onT = 0;
      if (memo.offT >= (o.offDelaySec || 0)) { memo.active = false; memo.offT = 0; }
    } else {
      memo.onT = 0; memo.offT = 0;
    }
    return { active: memo.active, memo: memo };
  }

  function keyOf(tag, cond) { return tag + '.' + cond; }

  function Engine(opts) {
    this.opts = {};
    for (var k in DEFAULTS) this.opts[k] = DEFAULTS[k];
    for (var o in (opts || {})) if (opts[o] !== undefined) this.opts[o] = opts[o];
    this._recs = [];
    this._byKey = new Map();
    this._byId = new Map();
    this._nextId = this.opts.idStart;
    this.setDasRules(this.opts.dasRules);
  }

  var P = Engine.prototype;

  P.setDasRules = function (rules) {
    this._das = {};          // triggerKey -> [suppressedKeys]
    this._dasRev = {};       // suppressedKey -> [triggerKeys]
    rules = rules || {};
    for (var trig in rules) {
      var list = rules[trig] || [];
      this._das[trig] = list.slice();
      for (var i = 0; i < list.length; i++) {
        (this._dasRev[list[i]] = this._dasRev[list[i]] || []).push(trig);
      }
    }
  };

  // ---- record helpers -------------------------------------------------------

  function refresh(r) {
    r.ack = !(r.state === 'UNACK' || r.state === 'RTNUN');
    r.active = !!r.live;
    r.shelved = r.state === 'SHLVD';
    if (r.state !== 'SHLVD') { r.until = 0; r.shelveReason = ''; }
    if (r.state !== 'DSUPR') r.suppressedBy = '';
  }

  P.get = function (ref) {
    if (ref == null) return undefined;
    if (typeof ref === 'object') return ref;
    if (typeof ref === 'number') return this._byId.get(ref);
    return this._byKey.get(ref);
  };

  P._new = function (a, t) {
    var r = {
      id: this._nextId++, key: keyOf(a.tag, a.cond), tag: a.tag, cond: a.cond,
      prio: a.prio, subprio: clampSub(a.subprio), state: 'NORM',
      t: t, lastT: t, rtnT: 0, ackT: 0, count: 0,
      val: a.val, eu: a.eu || '', desc: a.desc || '', tripValue: a.tripValue,
      live: false, ack: true, active: false, shelved: false,
      shelveReason: '', until: 0, comment: '', suppressedBy: ''
    };
    this._recs.push(r);
    this._byKey.set(r.key, r);
    this._byId.set(r.id, r);
    return r;
  };

  P._remove = function (r) {
    var i = this._recs.indexOf(r);
    if (i >= 0) this._recs.splice(i, 1);
    this._byKey.delete(r.key);
    this._byId.delete(r.id);
  };

  P._ev = function (type, r, t, from, extra) {
    var e = {
      type: type, id: r.id, key: r.key, tag: r.tag, cond: r.cond, prio: r.prio,
      subprio: r.subprio, t: t, val: r.val, eu: r.eu, desc: r.desc, from: from, to: r.state
    };
    if (extra) for (var k in extra) e[k] = extra[k];
    return e;
  };

  P._set = function (r, state) { r.state = state; refresh(r); };

  P._activeTrigger = function (key) {
    var trigs = this._dasRev[key];
    if (!trigs) return '';
    for (var i = 0; i < trigs.length; i++) {
      var tr = this._byKey.get(trigs[i]);
      if (tr && tr.live) return trigs[i];
    }
    return '';
  };

  // ---- transitions ----------------------------------------------------------

  P.raise = function (a) {
    var t = a.t || 0, events = [];
    var prio = PRIORITIES.indexOf(a.prio) >= 0 ? a.prio : 'Low';
    if (prio === 'Journal' && !this.opts.recordJournal) {
      events.push({
        type: 'ALARM', journal: true, id: 0, key: keyOf(a.tag, a.cond), tag: a.tag, cond: a.cond,
        prio: prio, subprio: clampSub(a.subprio), t: t, val: a.val, eu: a.eu || '', desc: a.desc || '',
        from: 'NORM', to: 'NORM'
      });
      return events;
    }
    var key = keyOf(a.tag, a.cond);
    var r = this._byKey.get(key);
    if (!r) r = this._new({ tag: a.tag, cond: a.cond, prio: prio, subprio: a.subprio, val: a.val, eu: a.eu, desc: a.desc, tripValue: a.tripValue }, t);
    var from = r.state, extra = {};
    if (prio === 'Journal') extra.journal = true;
    r.val = a.val;
    if (a.eu !== undefined) r.eu = a.eu;
    if (a.desc !== undefined) r.desc = a.desc;
    if (a.tripValue !== undefined) r.tripValue = a.tripValue;
    if (a.subprio !== undefined) r.subprio = clampSub(a.subprio);
    var escalated = rank(prio) > rank(r.prio);
    var wasLive = r.live;
    r.live = true;

    switch (from) {
      case 'NORM': {
        var folded = r.count > 0 && r.rtnT > 0 && (t - r.rtnT) <= this.opts.foldWindowMs;
        if (folded) { r.count++; extra.folded = true; }
        else { r.count = 1; r.t = t; }
        r.lastT = t; r.prio = prio;
        var trig = this._activeTrigger(key);
        if (trig) {
          this._set(r, 'DSUPR'); r.suppressedBy = trig;
          events.push(this._ev('ALARM', r, t, from, extra));
          events.push(this._ev('SUPPRESS', r, t, from, { suppressedBy: trig }));
        } else {
          this._set(r, 'UNACK');
          events.push(this._ev('ALARM', r, t, from, extra));
        }
        break;
      }
      case 'RTNUN':
        r.count++; r.lastT = t; r.prio = prio;
        this._set(r, 'UNACK');
        events.push(this._ev('ALARM', r, t, from, extra));
        break;
      case 'ACKED':
        if (!wasLive) { r.count++; r.lastT = t; }
        if (escalated) {
          r.prio = prio; extra.escalated = true;
          this._set(r, 'UNACK');
          events.push(this._ev('ALARM', r, t, from, extra));
        } else refresh(r);
        break;
      case 'UNACK':
        if (escalated) { r.prio = prio; extra.escalated = true; events.push(this._ev('ALARM', r, t, from, extra)); }
        refresh(r);
        break;
      default: // SHLVD, DSUPR, OOSRV keep their state; only the live flag changes
        if (!wasLive) { r.count++; r.lastT = t; }
        if (escalated) r.prio = prio;
        refresh(r);
    }
    if (this._das[key]) events.push.apply(events, this._applyTrigger(key, t));
    return events;
  };

  P.rtn = function (tag, cond, t, val) {
    var r = this._byKey.get(keyOf(tag, cond));
    if (!r || !r.live) return [];
    t = t || 0;
    var events = [], from = r.state;
    r.live = false; r.rtnT = t;
    if (val !== undefined) r.val = val;
    switch (from) {
      case 'UNACK': this._set(r, 'RTNUN'); events.push(this._ev('RTN', r, t, from)); break;
      case 'ACKED': this._set(r, 'NORM'); events.push(this._ev('RTN', r, t, from)); break;
      default: refresh(r); events.push(this._ev('RTN', r, t, from)); // SHLVD / DSUPR / OOSRV stay
    }
    if (this._das[r.key]) events.push.apply(events, this._releaseTrigger(r.key, t));
    return events;
  };

  P.ack = function (ref, t) {
    var r = this.get(ref);
    if (!r) return [];
    t = t || 0;
    var from = r.state;
    if (from === 'UNACK') { r.ackT = t; this._set(r, 'ACKED'); return [this._ev('ACK', r, t, from)]; }
    if (from === 'RTNUN') { r.ackT = t; this._set(r, 'NORM'); return [this._ev('ACK', r, t, from)]; }
    return [];
  };

  P.ackAll = function (t) {
    var events = [], recs = this._recs.slice();
    for (var i = 0; i < recs.length; i++) {
      if (recs[i].state === 'UNACK' || recs[i].state === 'RTNUN') events.push.apply(events, this.ack(recs[i], t));
    }
    return events;
  };

  P.shelve = function (ref, o) {
    var r = this.get(ref);
    if (!r) return [];
    o = o || {};
    var from = r.state;
    if (from === 'NORM' || from === 'SHLVD' || from === 'OOSRV') return [];
    var t = o.t || 0;
    var dur = o.durationMs > 0 ? o.durationMs : this.opts.defaultShelveMs;
    if (dur > this.opts.maxShelveMs) dur = this.opts.maxShelveMs;
    this._set(r, 'SHLVD');
    r.shelveReason = o.reason || 'no reason given';
    r.until = t + dur;
    return [this._ev('SHELVE', r, t, from, { reason: r.shelveReason, until: r.until, durationMs: dur })];
  };

  P._restore = function (r, t) {
    if (r.live) {
      var trig = this._activeTrigger(r.key);
      if (trig) { this._set(r, 'DSUPR'); r.suppressedBy = trig; return; }
      this._set(r, 'UNACK');
    } else this._set(r, 'NORM');
  };

  P.unshelve = function (ref, t, auto) {
    var r = this.get(ref);
    if (!r || r.state !== 'SHLVD') return [];
    t = t || 0;
    var from = r.state, reason = r.shelveReason;
    this._restore(r, t);
    var extra = { reason: reason };
    if (auto) extra.auto = true;
    var events = [this._ev('UNSHELVE', r, t, from, extra)];
    if (r.state === 'DSUPR') events.push(this._ev('SUPPRESS', r, t, 'SHLVD', { suppressedBy: r.suppressedBy }));
    return events;
  };

  P.suppress = function (ref, triggerKey, t) {
    var r = this.get(ref);
    if (!r || r.state === 'DSUPR' || r.state === 'OOSRV') return [];
    t = t || 0;
    var from = r.state;
    this._set(r, 'DSUPR');
    r.suppressedBy = triggerKey || 'DESIGN';
    return [this._ev('SUPPRESS', r, t, from, { suppressedBy: r.suppressedBy })];
  };

  P.unsuppress = function (ref, t) {
    var r = this.get(ref);
    if (!r || r.state !== 'DSUPR') return [];
    t = t || 0;
    var from = r.state, by = r.suppressedBy;
    if (r.live) this._set(r, 'UNACK'); else this._set(r, 'NORM');
    return [this._ev('UNSUPPRESS', r, t, from, { suppressedBy: by })];
  };

  // spec ({tag, cond, prio, subprio, val, eu, desc, tripValue}) lets a condition that
  // has never alarmed be taken out of service: the record is created directly in OOSRV.
  P.oos = function (ref, t, spec) {
    var r = this.get(ref);
    t = t || 0;
    if (!r && spec && spec.tag && spec.cond) {
      r = this._new({ tag: spec.tag, cond: spec.cond, prio: PRIORITIES.indexOf(spec.prio) >= 0 ? spec.prio : 'Low', subprio: spec.subprio, val: spec.val, eu: spec.eu, desc: spec.desc, tripValue: spec.tripValue }, t);
    }
    if (!r || r.state === 'OOSRV') return [];
    var from = r.state;
    this._set(r, 'OOSRV');
    return [this._ev('OOS', r, t, from)];
  };

  P.rts = function (ref, t) {
    var r = this.get(ref);
    if (!r || r.state !== 'OOSRV') return [];
    t = t || 0;
    var from = r.state;
    this._restore(r, t);
    var events = [this._ev('RTS', r, t, from)];
    if (r.state === 'DSUPR') events.push(this._ev('SUPPRESS', r, t, 'OOSRV', { suppressedBy: r.suppressedBy }));
    return events;
  };

  P.comment = function (ref, text) {
    var r = this.get(ref);
    if (!r) return false;
    r.comment = text == null ? '' : String(text);
    return true;
  };

  // DAS (RESOURCES 2.2): a live trigger pushes its listed alarms into DSUPR; the
  // trigger returning to normal releases them to UNACK / NORM per live state.
  P._applyTrigger = function (trigKey, t) {
    var events = [], list = this._das[trigKey] || [];
    for (var i = 0; i < list.length; i++) {
      var r = this._byKey.get(list[i]);
      if (!r) continue;
      if (r.state === 'UNACK' || r.state === 'ACKED' || r.state === 'RTNUN') {
        var from = r.state;
        this._set(r, 'DSUPR'); r.suppressedBy = trigKey;
        events.push(this._ev('SUPPRESS', r, t, from, { suppressedBy: trigKey }));
      }
    }
    return events;
  };

  P._releaseTrigger = function (trigKey, t) {
    var events = [];
    for (var i = 0; i < this._recs.length; i++) {
      var r = this._recs[i];
      if (r.state !== 'DSUPR' || r.suppressedBy !== trigKey) continue;
      var other = this._activeTrigger(r.key);
      if (other) { r.suppressedBy = other; continue; }
      var from = r.state;
      if (r.live) this._set(r, 'UNACK'); else this._set(r, 'NORM');
      events.push(this._ev('UNSUPPRESS', r, t, from, { suppressedBy: trigKey }));
    }
    return events;
  };

  P.tick = function (t) {
    t = t || 0;
    var events = [], recs = this._recs.slice();
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i];
      if (r.state === 'SHLVD' && t >= r.until) events.push.apply(events, this.unshelve(r, t, true));
      else if (r.state === 'NORM' && !r.live && (t - r.rtnT) > this.opts.foldWindowMs) this._remove(r);
    }
    return events;
  };

  // ---- queries ----------------------------------------------------------------

  P.all = function () { return this._recs.slice(); };
  P.list = function () { return this._recs.filter(function (r) { return r.state !== 'NORM'; }); };
  P.active = function () { return this._recs.filter(function (r) { return r.live; }); };
  P.unacked = function () { return this._recs.filter(function (r) { return r.state === 'UNACK' || r.state === 'RTNUN'; }); };
  P.shelved = function () { return this._recs.filter(function (r) { return r.state === 'SHLVD'; }); };
  P.suppressed = function () { return this._recs.filter(function (r) { return r.state === 'DSUPR'; }); };
  P.oosList = function () { return this._recs.filter(function (r) { return r.state === 'OOSRV'; }); };
  P.byUnit = function (fn) { return this._recs.filter(function (r) { return r.state !== 'NORM' && fn(r.tag, r); }); };

  // Priority buckets and total cover the ACTIVE annunciated alarms only
  // (UNACK + ACKED). A RTNUN record is no longer a live condition, so it is
  // excluded from the buckets but still counted in `unack` because it is
  // waiting for an acknowledge (Siemens indication table, RESOURCES 2.6).
  P.counts = function () {
    var c = { Urgent: 0, High: 0, Low: 0, Journal: 0, total: 0, unack: 0 };
    for (var i = 0; i < this._recs.length; i++) {
      var r = this._recs[i];
      if (r.state === 'UNACK' || r.state === 'ACKED') { c[r.prio]++; c.total++; }
      if (r.state === 'UNACK' || r.state === 'RTNUN') c.unack++;
    }
    return c;
  };

  P.topUnack = function () {
    var best = null;
    for (var i = 0; i < this._recs.length; i++) {
      var r = this._recs[i];
      if (!annunciates(r)) continue;
      if (!best || compare(r, best) < 0) best = r;
    }
    return best;
  };

  P.dasView = function () {
    var out = [];
    for (var trig in this._das) {
      var tr = this._byKey.get(trig);
      var sup = this._recs.filter(function (r) { return r.state === 'DSUPR' && r.suppressedBy === trig; })
        .map(function (r) { return r.key; });
      out.push({ trigger: trig, active: !!(tr && tr.live), configured: this._das[trig].slice(), suppressedKeys: sup });
    }
    return out;
  };

  // ---- snapshot / restore (instructor station, RESOURCES 2.14) --------------
  // Every record (including NORM ones still inside the fold window) and the id
  // counter, as plain data. restore() rebuilds the maps from such a snapshot so
  // ids and keys survive a backtrack.
  P.snapshot = function () {
    return { nextId: this._nextId, recs: JSON.parse(JSON.stringify(this._recs)) };
  };
  P.restore = function (s) {
    var recs = JSON.parse(JSON.stringify(s.recs || []));
    this._recs = []; this._byKey = new Map(); this._byId = new Map();
    this._nextId = s.nextId || this.opts.idStart;
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i];
      this._recs.push(r); this._byKey.set(r.key, r); this._byId.set(r.id, r);
    }
  };

  // convenience mirrors so a single engine handle carries the helpers
  P.evaluateLimit = evaluateLimit;
  P.indication = indication;
  P.compare = compare;
  P.annunciates = annunciates;

  // engine.oos(ref,t) is the transition; the query lives on oosList(). Keep the
  // spec'd query name too, dispatching on argument count.
  var oosTransition = P.oos;
  P.oos = function (ref, t, spec) { return arguments.length === 0 ? this.oosList() : oosTransition.call(this, ref, t, spec); };

  function createEngine(opts) { return new Engine(opts); }

  return {
    createEngine: createEngine,
    Engine: Engine,
    evaluateLimit: evaluateLimit,
    indication: indication,
    compare: compare,
    annunciates: annunciates,
    STATES: STATES,
    PRIORITIES: PRIORITIES,
    PRIO_RANK: PRIO_RANK,
    DEFAULTS: DEFAULTS
  };
});
