// @artifact production
/*
 * ESS.Pid — the sim's Experion-style PID as a pure, testable module.
 *
 * Operates on the same loop record the app keeps in `this.L[tag]`
 * (CODE-MAP 2.4/2.5): pv, sp, op, I, lastPv, K, T1, T2, act, mode, modeAttr,
 * master, slave, init, sphilm, splolm, ophilm, oplolm, badPv, lo, hi, tag.
 * Optional extra fields this module reads/writes: pvtrack (bool),
 * dFilter (seconds, derivative filter time constant), dState (filtered
 * derivative memory, %/s).
 *
 * Equation (error in % of span, times in minutes, ISA standard form):
 *   e  = (pv - sp) / span * 100   for DIR,  (sp - pv) for REV
 *   OP = K * e  +  I  +  D,   I += K * e * dt / (T1 * 60),
 *   D  = -K * T2 * 60 * d(pv%)/dt   (derivative on PV, optionally filtered)
 * OP is clamped to [OPLOLM, OPHILM]; the integral is back-calculated so
 * the sum equals the clamped value (anti-reset-windup, Kantor CBE30338
 * "PID control with anti-windup", RESOURCES 4.6) and integration is skipped
 * while the error would push further into the active limit.
 *
 * API
 *   stepPid(loop, dt, ctx) -> loop      one control interval (dt seconds).
 *     ctx = { loops: {tag: loop}, casMap: {slaveTag: masterOp -> slaveSp},
 *             invMap: {slaveTag: slaveSp -> masterOp}, dFilter?: seconds }
 *     - primaries (loop.slave set) run INITMAN back-calculation when the
 *       slave is not in CAS: op tracks invMap(slave.sp), init = true.
 *     - CAS loops take sp = clamp(casMap[tag](master.op), SPLOLM, SPHILM).
 *     - MAN / bad PV: no control action; integrator tracks op so a later
 *       transfer to AUTO is bumpless; with pvtrack the SP tracks PV
 *       (PVTRACK-style option: SP follows PV in MAN so AUTO starts at
 *       zero error).
 *   transferMode(loop, newMode, ctx) -> {ok, reason}   bumpless MAN->AUTO,
 *     AUTO->CAS, etc.: the integrator is re-initialised so the first AUTO/
 *     CAS output equals the current OP. Does not gate on security; the
 *     app does that. Refuses CAS without a master and non-MAN with bad PV.
 *   canOperatorWrite(loop, param) -> boolean   PROGRAM mode attribute:
 *     while modeAttr is 'PROGRAM' the sequence owns SP, OP and MODE, so
 *     operator writes to those are denied; engineering parameters (K, T1,
 *     T2, limits, trip points) stay writable. (EXP-01 objectives list
 *     "PV tracking, and program" as control conventions, RESOURCES 2.12.)
 *   writeDenial(loop, param) -> string    message-zone text for a denial.
 *   isaForm(K, T1, T2) -> {Kc, Ti, Td, TiSec, TdSec, Kp, Ki, Kd}
 *     the loop's tuning expressed as ISA standard form (minutes and
 *     seconds) and as parallel/independent gains for the Loop Tune tab.
 *   loopError(loop) -> error in % of span, signed for the control action.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Pid = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var OPERATOR_OWNED = { SP: true, OP: true, MODE: true };

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function span(loop) { var s = loop.hi - loop.lo; return s > 0 ? s : 100; }

  function loopError(loop) {
    var raw = loop.act === 'DIR' ? (loop.pv - loop.sp) : (loop.sp - loop.pv);
    return raw / span(loop) * 100;
  }

  function clampSp(loop, sp) {
    var lo = typeof loop.splolm === 'number' ? loop.splolm : loop.lo;
    var hi = typeof loop.sphilm === 'number' ? loop.sphilm : loop.hi;
    return clamp(sp, lo, hi);
  }

  function clampOp(loop, op) {
    var lo = typeof loop.oplolm === 'number' ? loop.oplolm : 0;
    var hi = typeof loop.ophilm === 'number' ? loop.ophilm : 100;
    return clamp(op, lo, hi);
  }

  function mapFn(table, tag) {
    if (!table) return null;
    var f = table[tag];
    return typeof f === 'function' ? f : null;
  }

  // Derivative of PV in %/s, optionally through a first-order filter
  // (derivative-on-measurement filter, Kantor CBE30338, RESOURCES 4.6).
  function pvDerivative(loop, dt, ctx) {
    var raw = ((loop.pv - loop.lastPv) / span(loop)) * 100 / dt;
    var tau = typeof loop.dFilter === 'number' ? loop.dFilter : (ctx && typeof ctx.dFilter === 'number' ? ctx.dFilter : 0);
    if (!(tau > 0)) { loop.dState = raw; return raw; }
    var prev = typeof loop.dState === 'number' ? loop.dState : raw;
    var filtered = prev + (raw - prev) * dt / (tau + dt);
    loop.dState = filtered;
    return filtered;
  }

  function derivativeTerm(loop, dt, ctx) {
    if (!(loop.T2 > 0) || !(dt > 0)) return 0;
    return -loop.K * loop.T2 * 60 * pvDerivative(loop, dt, ctx);
  }

  // Hold the integrator so that a later transfer to AUTO reproduces the
  // current OP (I = OP - P - D with D taken as zero at rest).
  function trackIntegrator(loop) {
    loop.I = loop.op - loop.K * loopError(loop);
    loop.lastPv = loop.pv;
    loop.dState = 0;
  }

  function runInitman(loop, ctx) {
    var slave = ctx && ctx.loops ? ctx.loops[loop.slave] : null;
    if (!slave) { loop.init = false; return false; }
    loop.init = slave.mode !== 'CAS';
    if (!loop.init) return false;
    var inv = mapFn(ctx.invMap, loop.slave);
    var target = inv ? inv(slave.sp) : slave.sp;
    loop.op = clampOp(loop, target);
    trackIntegrator(loop);
    return true;
  }

  function followMaster(loop, ctx) {
    var master = ctx && ctx.loops ? ctx.loops[loop.master] : null;
    if (!master) return;
    var cas = mapFn(ctx.casMap, loop.tag);
    loop.sp = clampSp(loop, cas ? cas(master.op) : master.op);
  }

  // A bad PV must never drag the SP with it (the shed already holds the loop in MAN).
  function applyPvTracking(loop) {
    if (loop.pvtrack && !loop.badPv) loop.sp = clampSp(loop, loop.pv);
  }

  function stepPid(loop, dt, ctx) {
    ctx = ctx || {};
    if (loop.kind && loop.kind !== 'pid') return loop;
    if (typeof loop.lastPv !== 'number') loop.lastPv = loop.pv;
    if (typeof loop.I !== 'number') loop.I = loop.op;

    if (loop.slave && runInitman(loop, ctx)) { applyPvTracking(loop); return loop; }
    if (loop.mode === 'CAS' && loop.master) followMaster(loop, ctx);
    if (loop.mode === 'MAN' || loop.badPv) { applyPvTracking(loop); trackIntegrator(loop); return loop; }

    var e = loopError(loop);
    var P = loop.K * e;
    var D = derivativeTerm(loop, dt, ctx);
    var lo = typeof loop.oplolm === 'number' ? loop.oplolm : 0;
    var hi = typeof loop.ophilm === 'number' ? loop.ophilm : 100;

    var unclamped = P + loop.I + D;
    var pushingHigh = unclamped >= hi && e > 0;
    var pushingLow = unclamped <= lo && e < 0;
    if (loop.T1 > 0 && !pushingHigh && !pushingLow) loop.I += loop.K * e * dt / (loop.T1 * 60);

    var op = P + loop.I + D;
    if (op > hi) { op = hi; loop.I = op - P - D; }
    if (op < lo) { op = lo; loop.I = op - P - D; }
    loop.op = op;
    loop.lastPv = loop.pv;
    return loop;
  }

  function transferMode(loop, newMode, ctx) {
    ctx = ctx || {};
    if (loop.badPv && newMode !== 'MAN') return { ok: false, reason: 'PV BAD — SHED ACTIVE, MODE CHANGE DENIED' };
    if (newMode === 'CAS' && !loop.master) return { ok: false, reason: 'NO CASCADE CONNECTION CONFIGURED' };
    if (loop.mode === newMode) return { ok: true, reason: '' };
    var old = loop.mode;
    loop.mode = newMode;
    if (newMode === 'CAS') followMaster(loop, ctx);
    if (newMode !== 'MAN') trackIntegrator(loop);
    return { ok: true, reason: '', from: old };
  }

  function canOperatorWrite(loop, param) {
    if (!loop || loop.modeAttr !== 'PROGRAM') return true;
    return !OPERATOR_OWNED[String(param).toUpperCase()];
  }

  function writeDenial(loop, param) {
    if (canOperatorWrite(loop, param)) return '';
    return 'MODE ATTRIBUTE PROGRAM — ' + String(param).toUpperCase() + ' OWNED BY SEQUENCE';
  }

  function isaForm(K, T1, T2) {
    var Ti = T1 > 0 ? T1 : Infinity;
    var Td = T2 > 0 ? T2 : 0;
    return {
      Kc: K, Ti: Ti, Td: Td,
      TiSec: Ti === Infinity ? Infinity : Ti * 60, TdSec: Td * 60,
      Kp: K, Ki: Ti === Infinity ? 0 : K / (Ti * 60), Kd: K * Td * 60
    };
  }

  return { stepPid: stepPid, transferMode: transferMode, canOperatorWrite: canOperatorWrite, writeDenial: writeDenial, isaForm: isaForm, loopError: loopError };
});
