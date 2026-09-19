// @artifact production
// ESS.Models — process dynamics for the three simulated units.
//
// Drop-in replacement for the inline models in the Component (CODE-MAP 2.6).
// Pure logic: no DOM, no timers, no globals other than the ESS namespace.
//
// API
//   createState(now?)                  -> P   fresh process state (superset of the
//                                              Component's this.P shape, see below)
//   createRand(seed)                   -> fn  deterministic mulberry32 generator in [0,1);
//                                              fn.seed, fn.getState(), fn.setState(v) expose the
//                                              cursor so a snapshot can resume the same sequence
//   envDefaults() / magDefaults()      -> the instructor variable / upset magnitude defaults
//   advanceClock(P, dt)                        P.t += dt*1000, P.up += dt
//   stepU1(P, L, V, dt, ctx)                   feed tank, pump, valves, R-201 CSTR,
//                                              fouling, E-301, V-401 flash drum,
//                                              U1 measurements, P101 lockout/pump fault
//   stepU2(P, L, V, dt, ctx)                   R-202 semi-batch reactor + SCM202 sequence
//   stepU3(P, L, V, dt, ctx)                   H-310 two-pass fired heater + R-310 bed
//   stepU4(P, L, V, dt, ctx)                   E-502 trim cooler + V-502 two-chamber weir separator
//   step(P, L, V, dt, ctx)                     advanceClock + stepU1 + stepU2 + stepU3 + stepU4
//   PARAMS                                     the calibrated parameter sets (read-only use)
//
// Arguments
//   L    tag database (this.L), V valves (this.V), dt seconds (the app uses 0.5).
//   ctx  callbacks so the module never touches the Component:
//        raise(src, cond, prio, val, eu, desc)   required  (Component.raiseA)
//        clear(src, cond)                        required  (Component.clearA)
//        tripMotor(tag, why)                     required  (Component.tripMotor)
//        addEvent(type, src, desc, oldV, newV)   required  (Component.addEvent)
//        rand()                                  optional  uniform [0,1), default Math.random
//        rand4()                                 optional  uniform [0,1), Unit 04 measurement noise ONLY. A SECOND
//                                                          generator, so adding Unit 04 cannot shift the stream
//                                                          U1-U3 draw from and the v2 goldens cannot move. Absent
//                                                          means Unit 04 noise is exactly zero -- it never falls
//                                                          back to rand() and never to Math.random.
//        shed(point)                             optional  bad-PV shed (Component.applyShed);
//                                                          default: mode -> MAN, hold OP
//        message(txt)                            optional  message zone (Component.msgZone)
//        onTrip(src, cond)                       optional  called once per equipment trip with the alarm source and condition
//                                                          (Component.dTrip for drill scoring)
//        measurementBias(tag, simTime, span)      optional  deterministic engineering-unit measurement offset;
//                                                          applied before PID and alarm evaluation, default 0
//
// Calibration notes (B4 verification round 2):
//   - Feed concentration is fixed (Henson/Seborg Caf); it no longer scales with
//     flow. Throughput acts through the residence time, so the reactor takes
//     about +33 % feed before the jacket runs out of margin (the app limits the
//     FIC102 setpoint to 80 m3/h for that reason). P.conc is an indication only.
//   - The 'stick' fault carries its own heat-of-reaction step (PARAMS.U1.stickHeat)
//     instead of the full 'rxn' fault, so putting TIC202 in MAN keeps R-201 under
//     its trip while the stuck valve is dealt with (drill D6).
//   - PARAMS.U1.surge is the 'surge' fault magnitude (m3/h).
//
// Behaviour preserved from the inline models (the app's tunings, alarm limits,
// drills and graphics depend on it): PV ranges written into L, trip thresholds
// (TK-101 98 %, P-101 cavitation < 2 %, R-201 185 C, V-401 PSV 950 kPa,
// R-202 110 C, R-310 480 C) and their reset points, fault keys and semantics
// (surge, xmtr, cool, rxn, foul, vap, air, pump, agit, stick, bedact), the
// SCM202 phase sequence CHARGE > HEATUP > FEED > REACT > COOL > DRAIN > IDLE with
// modeAttr PROGRAM handling, and every field read by renderVals()/diagnose().
//
// New readable fields (all engineering units, none are written into L here):
//   Instructor inputs (B5, Forge PTS instructor variables and upset magnitudes, RESOURCES 2.14):
//       P.env  {feedConc, Tamb, foulRate, catAct, monoPurity}   plant variables, 1 / 25 C / 1 / 1 / 1 at design
//       P.mag  {surge, coolLoss, bedact, drift}                  magnitude of the surge / cool / bedact / drift upsets
//       P.driftOff  accumulated LIC101 transmitter drift, % of span (the 'drift' upset)
//       Cooling water supply temperature is P.Tcw (already read by U1 and U2).
//   U1  P.Ca    reactor reactant concentration, fraction of design feed (0..1.6)
//       P.x     reactor conversion 0..1                (design 0.85)
//       P.Tjo   jacket coolant outlet temperature, C   (Tj is the jacket supply)
//       P.Qr    reaction heat release, % of design duty
//   U2  P.b.Tad  adiabatic end temperature, C  = T + dTad * accumulated monomer
//       P.b.accM monomer fed this batch, kmol
//       P.b.mP   polymer formed this batch, kmol
//       P.b.Ts   reactor wall (steel) temperature, C
//       P.b.Tehe external heat exchanger outlet temperature, C
//       P.b.conv batch monomer conversion 0..1
//   Trips read here but raised by the app: P.trips.skin (H-310 tube-skin trip,
//   TI314/TI315 Urgent) closes the fuel valve exactly like P.trips.bed.
//   U3  P.h.fb   firebox temperature, C
//       P.h.t1, P.h.t2   pass 1 / pass 2 outlet temperatures, C (pre = mixed outlet)
//       P.h.ts1, P.h.ts2 pass 1 / pass 2 tube-skin temperatures, C
//       P.h.air  combustion air, relative to stoichiometric fuel demand
//       P.h.o2   flue-gas excess oxygen, vol %
//       P.h.dT   bed rise above heater outlet, C
//
// Sources (RESOURCES.md section 4), re-implemented here from the published
// equations, not copied from any repository:
//   U1  Henson and Seborg exothermic CSTR as used in APMonitor PDC / pc-gym
//       (E/R = 8750 K, first-order Arrhenius kinetics, lumped jacket); Kantor
//       CBE30338 notes on the jacket energy balance; LearnChemE flash drum.
//   U2  Lucia, Finkler and Engell 2013 semi-batch polymerization (do-mpc
//       industrial_poly): monomer / polymer / water mass balances, Arrhenius
//       rate with polymer-fraction (gel) factor, reactor / steel wall / jacket
//       / external heat exchanger energy balances, adiabatic temperature and
//       accumulated-monomer safety variables.
//   U3  Badgwell fired heater case study (APMonitor): fuel gas to firebox,
//       two tube passes with outlet and tube-skin temperatures, combined
//       outlet; LearnChemE parametric sensitivity of a PFR with heat exchange
//       for the exponential hot-spot growth of the fixed bed.
//   U4  Arnold and Stewart bucket-and-weir three-phase separator, sized the way API
//       Spec 12J thinks about separators (minutes of liquid retention per chamber), with
//       the weir overflow in the Francis 3/2-power form (RESOURCES 4.12). Correlation
//       only, no property package: the unit 4 header lists what is invented outright.
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Models = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  // first-order lag toward a target: x += (target - x) * dt / tau
  const lag = (x, target, tau, dt) => x + (target - x) * dt / tau;

  function measurementBias(ctx, tag, simTime, span) {
    if (!ctx || typeof ctx.measurementBias !== 'function') return 0;
    const value = Number(ctx.measurementBias(tag, simTime, span));
    return Number.isFinite(value) ? value : 0;
  }

  // ---------------------------------------------------------------- parameters
  const PARAMS = {
    U1: {
      // Henson/Seborg activation energy; the pre-exponential is re-anchored to
      // the sim's operating point (150 C) so the design point is unchanged.
      E_R: 8750,            // K
      Tref: 423.15,         // K  (150 C)
      kRef: 0.0189,         // 1/s  rate constant at Tref (design k*tau = 5.67, conversion 0.85)
      tauRes: 300,          // s   residence time at design feed 60 m3/h
      designFlow: 60,       // m3/h
      J: 1.717e6,           // scaled -dH*Caf/(rho*Cp): design duty 4868 heat units
      Qdesign: 4868,        // reaction duty at the design point (for P.Qr in %)
      UA: 30,               // jacket heat-transfer coefficient, heat units per C
      Ufeed: 0.2,           // feed sensible-heat coefficient per m3/h
      Uloss: 2,             // ambient loss coefficient
      Tfeed: 40, Tamb: 25,  // C
      Cth: 20000,           // reactor thermal capacity (sim heat units per C/s)
      coolBackupMs: 180000, // 'cool' upset: the instructor's coolLoss fraction is lost for this long (3 min), then
      coolBackup: 1.0,      //   backup cooling restores this fraction of the jacket effectiveness (1 = spare pump gives
                            //   full cooling back). Final QA 2026-08-29: at 5 min / 0.75 the exotherm peaked within
                            //   2 C of the 185 C trip even with feed cut at the first alarm, and TIC201 stayed saturated
                            //   on the 75 % jacket, so drill D4 could not be passed by its own recommended action.
      tauJ: 15, tauJo: 20,  // s jacket supply / outlet lags
      NTUj: 0.35,           // jacket outlet approach
      // 'rxn' fault = off-spec feed: richer, more exothermic, faster kinetics
      rxnConc: 1.2, rxnHeat: 1.15, rxnRate: 1.3,
      // 'stick' fault (drill D6) carries only a heat-of-reaction step: the stuck valve is the
      // lesson, so the load must stay inside the jacket margin with TIC202 in MAN
      stickHeat: 1.15,
      surge: 50,            // m3/h feed inflow step of the 'surge' fault (8 min)
      foulBaseRate: 0.02,   // E-301 baseline fouling: fraction of duty lost per hour at env.foulRate 1 (never cleans itself)
      tripT: 185, resetT: 160,
    },
    U2: {
      E_R: 3000,            // K (calibrated for sim time compression; L/E form)
      Tref: 353.15,         // K  (80 C)
      kRef: 0.054,          // 1/s at Tref, well mixed
      gel: 0.35,            // k_U2/k_U1 polymer-fraction factor, well mixed (L/E gel effect)
      gelUnmixed: 2.0,      // unmixed: bulk-phase auto-acceleration (Trommsdorff effect)
      agitRate: 0.45,       // rate factor with agitator stopped (mixing limited)
      agitUA: 0.08,         // wall heat-transfer factor with agitator stopped
      dH: 1.2,              // C per kmol reacted (times 0.5 integrator gain)
      gain: 0.5,            // sim integrator gain (matches previous reactor time scale)
      kWall: 0.11,          // reactor <-> steel wall
      kJacket: 0.11,        // steel wall <-> jacket medium
      gSteel: 0.76,         // wall thermal gain (about 6 s time constant)
      gJacket: 0.1,         // jacket medium thermal gain
      tauJacket: 10,        // s jacket medium lag to tempered-water supply
      kEhe: 0.006,          // external heat exchanger duty per C
      eheOpen: 0.35,        // EHE coolant admitted as the jacket valve closes below this
      tauEhe: 25,           // s
      loss: 0.004,
      feedKmol: 0.05,       // kmol per (m3/h) per s (sim compression)
      lvlPerFlow: 0.012,    // % level per (m3/h) per s
      medMin: 15, medSpan: 105,   // tempered-water supply C = medMin + medSpan*JV213
      tripT: 110, resetT: 70,
    },
    U3: {
      Tin: 150, Tamb: 25,   // C
      G: 1175, n: 0.83,     // firebox: Tfb = Tamb + G * fuelEff^n
      h: 10.2,              // tube-pass NTU numerator (per m3/h)
      split: [0.49, 0.51],  // pass heat bias
      skin: [0.18, 0.22],   // tube-skin fraction of (firebox - pass outlet)
      excessAir: 1.17,      // air/fuel relative to stoichiometric (about 3 % O2)
      airMin: 0.05,         // register minimum opening (purge air with the fuel valve shut)
      tauFb: 10, tauPass: 22, tauSkin: 15, tauAir: 12, tauFlow: 3,
      bedGain: 92, bedRef: 380, bedScale: 150, quench: 3.2, tauBed: 35,
      bedactGain: 1.35,
      bedRelKnee: 300, bedRelMax: 600,   // C of hot-spot rise: linear below the knee, saturating at the adiabatic rise
      bedLightOff: 200, bedLightW: 25,   // C: inlet temperature below which the bed extinguishes, and its width
      tripT: 480, resetT: 400,
    },
    // Unit 04, V-502 two-chamber weir separator (RESOURCES 4.12). Every number is this
    // simulator's own and was calibrated by running the model, not assumed: the design
    // point -- U3 feed 40 m3/h, weirH 55 %, TV-502 0.60, LV-503 0.50, WV-504 0.45,
    // PV-505 0.40 -- is a steady state at hw 25 %, h2 50 %, pres 800 kPa, Tin 45 C,
    // AI509 0.3 %, AI510 0.2 %. Lines marked CALIBRATED were moved from the build
    // contract's first cut because that value could not hold the design point; the note
    // says what the value has to be and why.
    U4: {
      waterFrac: 0.15,     // m3 of water made per m3 of U3 feed at full catalyst activity (HDO stoichiometry,
                           //   scaled): 40 m3/h feed splits 6.0 water / 34.0 oil
      gasFrac: 3.3333e-5,  // CALIBRATED (contract first cut 0.004): light gas made per m3 of feed at 45 C.
                           //   qg_in = qfeed*gasFrac*3600 = 4.80 m3/h at design, exactly what PV-505 passes at
                           //   0.40 with Cg 12, so the vessel holds 800 kPa. At 0.004 the make was 576 m3/h and
                           //   a shut vent drove the PSV inside one second -- no drill window at all.
      A1: 0.12, A2: 0.07,  // CALIBRATED (first cut 0.30 / 0.18): chamber areas, m3 per % of height, chamber 1
                           //   the wider one. 12 m3 and 7 m3 hold 6.7 and 3.5 m3 of liquid at the design levels,
                           //   which is 10.0 minutes of retention on the 40 m3/h feed and 6.2 on the 34 m3/h
                           //   product draw -- the band API Spec 12J is written around (RESOURCES 4.12), and the
                           //   reason to size a separator that way. At
                           //   0.30 / 0.18 the retention was 25 and 16 minutes: the design point was still steady,
                           //   but the interface crept at 0.33 %/min and a water-carry-over exercise took over an
                           //   hour of simulated time before the analyser moved, which is no drill at all.
      Cweir: 80,           // CALIBRATED (first cut 6.0): weir coefficient in q_over = Cweir*max(0,h1-W)^1.5, the
                           //   Francis 3/2 power (RESOURCES 4.12). At 80 the design crest head is 0.57 % of
                           //   height, so the design oil layer stays essentially at the contract's s.ho 30 (h1
                           //   sits on the crest) instead of standing 3.2 % above it. It is also inside the bound
                           //   Cweir <= A1*3600/(10*dt) = 86, under which one explicit 0.5 s step can never drain
                           //   more head than exists for any head up to 100 %, so a weir dropped live empties over
                           //   the crest without overshooting chamber 2 past the level the dump can actually fill.
      Cw: 18.86,           // CALIBRATED (first cut 30): water draw, m3/h at full valve and 50 % head. WV-504 at
                           //   its design 0.45 with hw 25 draws 6.001 m3/h, the water the feed makes, so the
                           //   interface sits still. At 30 the draw was 9.5 m3/h and the boot emptied.
      Cp: 68,              // CALIBRATED (first cut 45): product draw, same form. LV-503 at its design 0.50 with
                           //   h2 50 draws 34.0 m3/h, the weir overflow, so chamber 2 sits still. At 45 it drew
                           //   22.5 and chamber 2 filled to the PVHH.
      carryBand: 10,       // INVENTED: water starts going over the weir when hw > W - carryBand (% of height)
      thinBand: 8,         // INVENTED: oil starts leaving down the water draw when hw < thinBand
      kP: 0.9,             // INVENTED: kPa per (m3/h of gas imbalance) per second
      Cg: 12,              // vent capacity, m3/h at full valve and the design dP (800 - 100 kPa). The pressure
                           //   time constant is 1400/(kP*0.4*Cg) = 324 s at the design point.
      Pdown: 100,          // off-gas header pressure, kPa
      coolK: 507,          // CALIBRATED, as the contract directs: C of cooling at full TV-502. The measured design
                           //   inlet is Thot = (h.pre 320.0 + h.bed 378.1)/2 = 349.06 C, so TV-502 at 0.60 lands
                           //   349.06 - 0.60*507 = 44.86 C against the 45 C design (0.3 % low).
      tauT: 45,            // s, E-502 outlet temperature lag
      psvSet: 1100, psvReset: 1000,   // PSV-502 lift and reseat, kPa
    },
  };

  // ---------------------------------------------------------------- utilities
  function createRand(seed) {
    let a = (seed >>> 0) || 1;
    const fn = function () {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    fn.seed = (seed >>> 0) || 1;
    fn.getState = () => a;
    fn.setState = (v) => { a = (v >>> 0) || 1; };
    return fn;
  }

  // Instructor variables (plant conditions the trainee cannot see) and upset magnitudes; both live in P so
  // they travel with snapshots and initial conditions (cstr-ots architecture notes, RESOURCES 4.9).
  function envDefaults() { return { feedConc: 1, Tamb: 25, foulRate: 1, catAct: 1, monoPurity: 1, weirH: 55 }; }
  function magDefaults() { return { surge: 50, coolLoss: 1, bedact: 1.35, drift: 1 }; }
  // V-502 process state. Its own factory so createState and the pre-U4-snapshot default
  // below cannot drift apart (the env/mag pattern above).
  function sepDefaults() { return { Tin: 45, hw: 25, ho: 30, h2: 50, pres: 800, qover: 0, wcarry: 0, ocarry: 0 }; }
  const envOf = (P) => P.env || (P.env = envDefaults());
  const magOf = (P) => P.mag || (P.mag = magDefaults());
  const sepOf = (P) => P.s || (P.s = sepDefaults());
  // A snapshot taken before Unit 04 has an env with no weirH; treat it as the design weir
  // rather than integrating NaN into every level from there on.
  const weirOf = (P) => { const w = envOf(P).weirH; return Number.isFinite(w) ? w : 55; };

  function noiseFn(ctx) {
    const r = (ctx && ctx.rand) || Math.random;
    return (k) => (r() - 0.5) * k;
  }

  function createState(now) {
    return {
      t: now === undefined ? Date.now() : now, up: 0,
      qin: 60, tankL: 50, flow: 60, conc: 1, rT: 150, Tj: 40, Tcw: 8, hxT: 180,
      drumL: 45, drumP: 600, foulF: 1, foulBase: 1,
      Ca: 0.15, x: 0.85, Tjo: 72.5, Qr: 100,
      trips: {}, faults: {}, faultT: {}, driftOff: 0,
      env: envDefaults(), mag: magDefaults(),
      b: { phase: 'IDLE', pt: 0, Cm: 0, lvl: 12, T: 25, Tj: 20, mf: 0, held: false,
           Ts: 25, Tehe: 25, mP: 0, accM: 0, Tad: 25, conv: 0, _last: 'IDLE' },
      h: { f: 40, pre: 320, bed: 380, q: 10, fb: 575, t1: 318, t2: 322, ts1: 364, ts2: 378,
           air: 0.468, o2: 3.0, dT: 60 },
      s: sepDefaults(),
    };
  }

  function raiseTrip(ctx, src, cond, val, eu, desc) {
    ctx.raise(src, cond, 'Urgent', val, eu, desc);
    if (ctx.onTrip) ctx.onTrip(src, cond);
  }

  function defaultShed(l, ctx) {
    if (l.shed === 'NOSHED') return;
    const old = l.mode; l.mode = 'MAN';
    if (l.shed === 'SHEDLOW') l.op = l.opexlo; else if (l.shed === 'SHEDHIGH') l.op = l.opexhi; else if (l.shed === 'SHEDSAFE') l.op = l.safeop;
    if (old !== 'MAN') ctx.addEvent('SYSTEM', l.tag, 'BAD PV — SHED ' + l.shed.replace('SHED', '') + ' · MODE ' + old + ' → MAN', '', '');
  }

  // ---------------------------------------------------------------- unit 1
  function feedDisturbance(P, n) {
    const F = P.faults;
    let qin = 60 + 2 * Math.sin(P.up / 120) + n(0.6) + (F.surge ? magOf(P).surge : 0);
    if (F.surge && P.t - P.faultT.surge > 480000) F.surge = false;
    if (P.trips.ovf) qin = 0;
    P.qin = qin;
    return qin;
  }

  // Which loop output (or protective trip) each valve follows. One entry per valve the
  // process equations read. The key list is exported as MODEL_VALVES so the app's V,
  // Topology.VALVE_OF and this table are pinned equal by test (tests/models-valves.test.js)
  // instead of drifting apart silently: a valve present in V with no entry here used to
  // integrate `undefined` into NaN, after which makeSnapshot refused every snapshot,
  // backtrack and replay. Such a valve now HOLDS its position (or goes to its fail
  // position on air loss) and the test names it.
  const VALVE_TARGET = {
    FV102: (P, L) => P.trips.rx ? 0 : L.FIC102.op / 100,
    TV202: (P, L) => L.TIC202.op / 100,
    TV301: (P, L) => L.TIC301.op / 100,
    PV401: (P, L) => L.PIC401.op / 100,
    LV401: (P, L) => L.LIC401.op / 100,
    MV211: (P, L) => P.trips.batch ? 0 : L.FIC211.op / 100,
    JV213: (P, L) => P.trips.batch ? 0 : L.TIC213.op / 100,
    FV310: (P, L) => L.FIC310.op / 100,
    FV311: (P, L) => (P.trips.bed || P.trips.skin) ? 0 : L.TIC311.op / 100,
    QV313: (P, L) => L.FIC313.op / 100,
    TV502: (P, L) => L.TIC502.op / 100,
    LV503: (P, L) => L.LIC503.op / 100,
    WV504: (P, L) => L.LIC504.op / 100,
    PV505: (P, L) => L.PIC505.op / 100,
  };
  const MODEL_VALVES = Object.freeze(Object.keys(VALVE_TARGET));

  function moveValves(P, L, V, dt) {
    const F = P.faults;
    for (const k in V) {
      const v = V[k], target = VALVE_TARGET[k];
      let g = F.air ? v.fail : (target ? target(P, L) : v.pos); if (v.stuck) g = v.pos;
      v.pos = clamp(v.pos + (g - v.pos) * dt / 3, 0, 1);
    }
  }

  // Feed tank, pump and valve: the sqrt-of-head discharge form of the gravity-drained tank
  // (Kantor CBE30338, RESOURCES 4.6) applied as a gain on a pumped, valve-throttled line.
  function feedTank(P, L, V, dt, ctx, qin) {
    const pumpF = L.P101.run ? 1 : 0;
    const flowSS = 120 * V.FV102.pos * pumpF * Math.sqrt(Math.max(P.tankL, 0) / 50);
    P.flow = lag(P.flow, flowSS, 4, dt); if (P.flow < 0.05 && flowSS === 0) P.flow = 0;
    P.tankL = clamp(P.tankL + (qin - P.flow) * 0.0023148 * dt, 0, 100);
    if (P.tankL >= 98 && !P.trips.ovf) { P.trips.ovf = true; raiseTrip(ctx, 'TK-101', 'HIHI TRIP', P.tankL, '%', 'FEED TANK OVERFLOW PROTECTION — FEED ISOLATED'); }
    if (P.trips.ovf && P.tankL < 90) { P.trips.ovf = false; ctx.clear('TK-101', 'HIHI TRIP'); }
    if (P.tankL < 2 && L.P101.run) ctx.tripMotor('P101', 'CAVITATION — LOW SUCTION LEVEL');
  }

  // Henson/Seborg CSTR (RESOURCES 4.4): dCa/dt = (Caf - Ca)/tau - k(T) Ca;
  // dT/dt = feed + reaction - jacket - loss, k(T) = kRef exp(-E/R (1/T - 1/Tref)).
  function cstr(P, L, V, dt, ctx) {
    const c = PARAMS.U1, F = P.faults, env = envOf(P);
    P.conc = Math.max(0, lag(P.conc, Math.min(P.flow / c.designFlow, 1.6), 45, dt));   // feed loading, relative to design (indication only)
    const TK = P.rT + 273.15;
    const k = c.kRef * Math.exp(-c.E_R * (1 / TK - 1 / c.Tref)) * (F.rxn ? c.rxnRate : 1);
    const tau = c.tauRes * c.designFlow / Math.max(P.flow, 1);
    // Feed concentration is a property of the feed, not of the flow (Henson/Seborg: Caf fixed). Throughput acts through
    // the residence time only: more feed = less conversion = more unreacted reactant = more heat, and more sensible cooling.
    const Caf = (F.rxn ? c.rxnConc : 1) * env.feedConc;
    P.Ca = Math.max(0, P.Ca + ((Caf - P.Ca) / tau - k * P.Ca) * dt);
    P.x = Caf > 1e-6 ? clamp(1 - P.Ca / Caf, 0, 1) : 0;
    // jacket: tempered coolant supply, effectiveness from valve position (previous calibration)
    // 'cool' upset: the instructor's coolLoss fraction is lost for PARAMS.U1.coolBackupMs, then backup cooling restores coolBackup
    const eEff = F.cool ? ((P.t - P.faultT.cool > c.coolBackupMs) ? c.coolBackup : 1 - magOf(P).coolLoss) : 1;
    const e = 0.9 * Math.sqrt(Math.max(V.TV202.pos, 0)) * eEff;
    P.Tj = lag(P.Tj, P.Tcw * e + P.rT * (1 - e), c.tauJ, dt);
    P.Tjo = lag(P.Tjo, P.Tj + (P.rT - P.Tj) * (1 - Math.exp(-c.NTUj)), c.tauJo, dt);
    const Qr = c.J * k * P.Ca * (F.rxn ? c.rxnHeat : F.stick ? c.stickHeat : 1);
    P.Qr = Qr / c.Qdesign * 100;
    const dTdt = (Qr - c.UA * (P.rT - P.Tj) - c.Ufeed * P.flow * (P.rT - c.Tfeed) - c.Uloss * (P.rT - env.Tamb)) / c.Cth;
    P.rT += dTdt * dt;
    if (P.rT >= c.tripT && !P.trips.rx) { P.trips.rx = true; raiseTrip(ctx, 'R-201', 'HI TEMP TRIP', P.rT, 'DEG C', 'REACTOR HIGH TEMPERATURE TRIP — FEED VALVE CLOSED'); }
    if (P.trips.rx && P.rT < c.resetT) { P.trips.rx = false; ctx.clear('R-201', 'HI TEMP TRIP'); }
  }

  function exchangerAndDrum(P, V, dt, ctx) {
    const F = P.faults;
    // fouling: a slow baseline scaled by the instructor's env.foulRate (foulBase, a plant condition that never cleans
    // itself) and the 'foul' upset, a fast progression on top of it that recovers to the baseline when cleared
    const fr = envOf(P).foulRate;
    P.foulBase = Math.max(0.6, (P.foulBase == null ? 1 : P.foulBase) - dt / 3600 * PARAMS.U1.foulBaseRate * fr);
    P.foulF = F.foul ? Math.max(0.6, P.foulF - dt / 600 * 0.4 * fr) : Math.max(0.6, Math.min(P.foulBase, P.foulF + dt / 300));
    P.hxT = lag(P.hxT, P.rT + 60 * V.TV301.pos * P.foulF, 90, dt);
    // flash drum: vapour fraction rises with feed temperature (LearnChemE flash, RESOURCES 4.3)
    const vapf = clamp(0.02 + (P.hxT - 165) * 0.004, 0, 0.3);
    const Ql = P.flow * (1 - vapf);
    const Qo = 80 * V.LV401.pos * Math.sqrt(Math.max(P.drumL, 1) / 50);
    P.drumL = clamp(P.drumL + (Ql - Qo) * 0.001852 * dt, 0, 100);
    // 'vap' fault = vapour surge for 5 min. Calibrated (B4) so that PIC401 left in MAN reaches its PVHI
    // limit inside the drill window while AUTO holds the drum with the vent open (the original 1.9 never alarmed).
    const vap = P.flow * vapf * (F.vap ? 2.6 : 1);
    if (F.vap && P.t - P.faultT.vap > 300000) F.vap = false;
    const vent = 0.02 * V.PV401.pos * P.drumP;
    P.drumP += (vap - vent) * dt / 8;
    if (P.drumP > 950) {
      if (!P.trips.psv) { P.trips.psv = true; raiseTrip(ctx, 'V-401', 'PSV LIFT', P.drumP, 'KPA', 'RELIEF VALVE LIFTED TO FLARE'); }
      P.drumP -= (P.drumP - 950) * 0.5 * dt;
    }
    if (P.trips.psv && P.drumP < 900) { P.trips.psv = false; ctx.clear('V-401', 'PSV LIFT'); }
    P.drumP = clamp(P.drumP, 0, 1100);
  }

  function measureU1(P, L, dt, ctx, n) {
    const F = P.faults;
    L.FI100.pv = P.qin + n(0.2);
    // 'drift' upset: the level transmitter walks upward at mag.drift % of span per minute; clearing it recalibrates
    P.driftOff = F.drift ? P.driftOff + magOf(P).drift / 60 * dt : 0;
    L.LIC101.pv = clamp(P.tankL + P.driftOff, 0, 100) + n(0.12);
    if (F.xmtr) {
      const ft = P.t - P.faultT.xmtr;
      if (ft > 5000 && !L.FIC102.badPv) {
        L.FIC102.badPv = true; ctx.raise('FIC102', 'BADPV', 'High', L.FIC102.pv, 'M3/H', L.FIC102.desc);
        if (ctx.shed) ctx.shed(L.FIC102); else defaultShed(L.FIC102, ctx);
      }
      if (ft > 5000) L.FIC102.pv = lag(L.FIC102.pv, 0, 10, dt);
    } else {
      if (L.FIC102.badPv) { L.FIC102.badPv = false; ctx.clear('FIC102', 'BADPV'); if (ctx.message) ctx.message('FIC102 PV RESTORED'); }
      L.FIC102.pv = P.flow + n(0.25);
    }
    // The offset is part of the measurement path, not the process state: the PID and
    // alarm scan consume the biased PV later in the same Component step, so a low
    // reading can causally drive the master/slave jacket cascade while P.rT remains
    // the independent physical truth. No callback means byte-identical v2 behavior.
    L.TIC201.pv = P.rT + measurementBias(ctx, 'TIC201', P.t, L.TIC201.hi - L.TIC201.lo) + n(0.15);
    L.TIC202.pv = P.Tj + n(0.12);
    L.TIC301.pv = P.hxT + n(0.2);
    L.LIC401.pv = P.drumL + n(0.15);
    L.PIC401.pv = P.drumP + n(1.2);
    L.P101.pv = L.P101.run ? 1 : 0;
    if (L.P101.lock > 0) L.P101.lock = Math.max(0, L.P101.lock - dt);
    if (F.pump && L.P101.run) ctx.tripMotor('P101', 'UNCOMMANDED STOP');
  }

  function stepU1(P, L, V, dt, ctx) {
    const n = noiseFn(ctx);
    const qin = feedDisturbance(P, n);
    moveValves(P, L, V, dt);
    feedTank(P, L, V, dt, ctx, qin);
    cstr(P, L, V, dt, ctx);
    exchangerAndDrum(P, V, dt, ctx);
    measureU1(P, L, dt, ctx, n);
  }

  // ---------------------------------------------------------------- unit 2
  function sequence(P, L, dt, ctx) {
    const b = P.b;
    b.pt += dt;
    const setPh = (ph) => { b.phase = ph; b.pt = 0; ctx.addEvent('SYSTEM', 'SCM202', 'PHASE → ' + ph, '', ''); };
    if (b.phase === 'CHARGE') { b.lvl += 0.5 * dt; if (b.lvl >= 40) { L.TIC212.mode = 'AUTO'; L.TIC212.sp = 80; setPh('HEATUP'); } }
    else if (b.phase === 'HEATUP') { if (b.T >= 76) setPh('FEED'); }
    else if (b.phase === 'FEED') { if (b.lvl >= 75) setPh('REACT'); }
    else if (b.phase === 'REACT') { if (b.Cm <= 2) { L.TIC212.sp = 40; setPh('COOL'); } }
    else if (b.phase === 'COOL') { if (b.T <= 45) setPh('DRAIN'); }
    else if (b.phase === 'DRAIN') { b.lvl = Math.max(10, b.lvl - 0.8 * dt); if (b.lvl <= 10) { L.TIC212.mode = 'MAN'; L.TIC212.op = 8; setPh('IDLE'); } }
    const seqOn = b.phase !== 'IDLE';
    if (b.phase === 'FEED') L.FIC211.sp = (b.held || P.trips.batch) ? 0 : 20; else if (seqOn) L.FIC211.sp = 0;
    L.FIC211.modeAttr = (b.phase === 'FEED' && !b.held) ? 'PROGRAM' : 'OPERATOR';
    L.TIC212.modeAttr = seqOn ? 'PROGRAM' : 'OPERATOR';
  }

  function resetBatchInventory(b) {
    if (b._last !== 'CHARGE' && b.phase === 'CHARGE') { b.mP = 0; b.accM = 0; b.conv = 0; }
    b._last = b.phase;
  }

  // Lucia/Finkler/Engell 2013 semi-batch structure (RESOURCES 4.1): monomer,
  // polymer, water masses; Arrhenius rate with polymer-fraction (gel) factor;
  // reactor / steel / jacket / external HX energy balances; T_adiab and
  // accumulated monomer as safety variables.
  function batchReactor(P, L, V, dt, ctx) {
    const c = PARAMS.U2, b = P.b, M = L.M202;
    const mfSS = 40 * V.MV211.pos * (P.trips.batch ? 0 : 1);
    b.mf = lag(b.mf, mfSS, 3, dt);
    if (b.phase === 'FEED' && b.mf > 0.1) b.lvl = Math.min(100, b.lvl + b.mf * c.lvlPerFlow * dt);
    const feedIn = b.mf * c.feedKmol * envOf(P).monoPurity; // kmol/s of reactive monomer
    // heat capacity relative to the charged water; unmixed, the reaction is confined to the
    // monomer-rich layer and the water heel is no longer an effective heat sink
    const cap = M.run ? Math.max(0.3, b.lvl / 40) : 1;
    const agit = M.run ? 1 : c.agitRate;
    const p = b.mP / Math.max(1e-6, b.mP + b.Cm);           // polymer fraction
    const TK = b.T + 273.15;
    const gel = M.run ? c.gel : c.gelUnmixed;
    const k = c.kRef * Math.exp(-c.E_R * (1 / TK - 1 / c.Tref)) * (1 - p + gel * p) * agit;
    const r = k * b.Cm;                                     // kmol/s
    b.Cm = clamp(b.Cm + (feedIn - r) * dt, 0, 99);
    b.mP += r * dt;
    if (b.phase !== 'IDLE') b.accM += feedIn * dt;
    b.conv = b.accM > 1e-6 ? clamp(b.mP / b.accM, 0, 1) : 0;
    // energy: jacket medium from tempered-water supply, steel wall between medium and contents,
    // external heat exchanger on the recirculation loop (active when the agitator/pump runs)
    const med = c.medMin + c.medSpan * V.JV213.pos;
    const UA = M.run ? 1 : c.agitUA;
    const qWall = c.kWall * UA * (b.T - b.Ts);
    const qJacket = c.kJacket * (b.Ts - b.Tj);
    const eheDemand = clamp((c.eheOpen - V.JV213.pos) / c.eheOpen, 0, 1) * (M.run ? 1 : 0);
    const qEhe = c.kEhe * eheDemand * (b.T - b.Tehe);
    b.Ts += (qWall - qJacket) * c.gSteel * dt;
    b.Tj += ((med - b.Tj) / c.tauJacket + qJacket * c.gJacket) * dt;
    b.Tehe = lag(b.Tehe, P.Tcw + (b.T - P.Tcw) * 0.6, c.tauEhe, dt);
    const heat = c.dH * r / cap;
    const loss = c.loss * (b.T - 25);
    b.T = Math.max(12, b.T + (heat - qWall - qEhe - loss) * dt * c.gain);
    b.Tad = b.T + c.gain * c.dH * b.Cm / cap;
    if (b.T >= c.tripT && !P.trips.batch) {
      P.trips.batch = true;
      raiseTrip(ctx, 'R-202', 'HI TEMP TRIP', b.T, 'DEG C', 'BATCH REACTOR OVERTEMP — FEED CUT, JACKET FULL COLD');
      if (b.phase === 'FEED' || b.phase === 'REACT' || b.phase === 'HEATUP') { b.phase = 'COOL'; b.pt = 0; L.TIC212.sp = 40; }
    }
    if (P.trips.batch && b.T < c.resetT) { P.trips.batch = false; ctx.clear('R-202', 'HI TEMP TRIP'); }
  }

  function measureU2(P, L, dt, n) {
    const b = P.b;
    L.FIC211.pv = b.mf + n(0.15);
    L.TIC212.pv = b.T + n(0.12);
    L.TIC213.pv = b.Tj + n(0.1);
    L.PI214.pv = 100 + Math.max(0, b.T - 25) * 3.4 + n(1.5);
    L.LI215.pv = b.lvl + n(0.1);
    L.M202.pv = L.M202.run ? 1 : 0;
    if (L.M202.lock > 0) L.M202.lock = Math.max(0, L.M202.lock - dt);
  }

  function stepU2(P, L, V, dt, ctx) {
    const n = noiseFn(ctx);
    sequence(P, L, dt, ctx);
    resetBatchInventory(P.b);
    batchReactor(P, L, V, dt, ctx);
    measureU2(P, L, dt, n);
  }

  // ---------------------------------------------------------------- unit 3
  // Badgwell fired heater (RESOURCES 4.2): fuel gas -> firebox -> two tube passes,
  // each with an outlet and a tube-skin temperature; combined outlet feeds the bed.
  function firedHeater(P, V, dt) {
    const c = PARAMS.U3, h = P.h;
    h.f = lag(h.f, 80 * V.FV310.pos, c.tauFlow, dt);
    const fuel = V.FV311.pos;
    h.air = lag(h.air, Math.max(c.airMin, fuel * c.excessAir), c.tauAir, dt);
    const lambda = h.air / Math.max(fuel, 1e-3);
    h.o2 = lambda > 1 ? 21 * (lambda - 1) / lambda : 0;
    const fuelEff = fuel * Math.min(1, lambda);             // sub-stoichiometric firing wastes fuel
    h.fb = lag(h.fb, envOf(P).Tamb + c.G * Math.pow(fuelEff, c.n), c.tauFb, dt);
    const fi = Math.max(h.f / 2, 0.5);
    const outs = c.split.map((s) => {
      const eff = 1 - Math.exp(-c.h * 2 * s / fi);
      return c.Tin + eff * (h.fb - c.Tin);
    });
    h.t1 = lag(h.t1, outs[0], c.tauPass, dt);
    h.t2 = lag(h.t2, outs[1], c.tauPass, dt);
    h.ts1 = lag(h.ts1, h.t1 + c.skin[0] * (h.fb - h.t1), c.tauSkin, dt);
    h.ts2 = lag(h.ts2, h.t2 + c.skin[1] * (h.fb - h.t2), c.tauSkin, dt);
    h.pre = (h.t1 + h.t2) / 2;
  }

  // fixed bed: exponential hot-spot growth with bed temperature (LearnChemE PFR
  // parametric sensitivity, RESOURCES 4.3) plus a quench loop.
  // Two physical bounds keep the exponential from running away: the heat release cannot exceed full conversion of the
  // feed (a smooth cap at bedRelMax, linear up to bedRelKnee so the nominal and trip trajectories are untouched), and a
  // feed entering far below the light-off temperature does not react, so a fuel trip that drops the preheat quenches
  // the hot spot instead of leaving it self-sustaining.
  function hotSpotRise(c, h, act) {
    const raw = c.bedGain * act * Math.exp((h.bed - c.bedRef) / c.bedScale) * (h.f / 40);
    const lit = 1 / (1 + Math.exp(-(h.pre - c.bedLightOff) / c.bedLightW));
    const r = raw * lit;
    if (r <= c.bedRelKnee) return r;
    const span = c.bedRelMax - c.bedRelKnee;
    return c.bedRelKnee + span * Math.tanh((r - c.bedRelKnee) / span);
  }

  function fixedBed(P, V, dt, ctx) {
    const c = PARAMS.U3, h = P.h;
    h.q = lag(h.q, 40 * V.QV313.pos, c.tauFlow, dt);
    const act = envOf(P).catAct * (P.faults.bedact ? magOf(P).bedact : 1);
    // Floored at the inlet less a small mixing dip: quench cools the bed toward the inlet, it
    // cannot carry the hot spot below what enters (TI312 read 232 C against a 320 C inlet
    // under full quench before this; CHANGELOG 3.1.0, re-captured D12 / air / bedact).
    const bedSS = Math.max(h.pre + hotSpotRise(c, h, act) - c.quench * h.q, h.pre - 5);
    h.bed = lag(h.bed, bedSS, c.tauBed, dt);
    h.dT = h.bed - h.pre;
    if (h.bed >= c.tripT && !P.trips.bed) { P.trips.bed = true; raiseTrip(ctx, 'R-310', 'HI TEMP TRIP', h.bed, 'DEG C', 'BED OVERTEMP — FUEL GAS SHUT OFF'); }
    if (P.trips.bed && h.bed < c.resetT) { P.trips.bed = false; ctx.clear('R-310', 'HI TEMP TRIP'); }
  }

  function measureU3(P, L, n) {
    const h = P.h;
    L.FIC310.pv = h.f + n(0.2);
    L.TIC311.pv = h.pre + n(0.4);
    L.TI312.pv = h.bed + n(0.5);
    L.FIC313.pv = h.q + n(0.1);
  }

  function stepU3(P, L, V, dt, ctx) {
    const n = noiseFn(ctx);
    firedHeater(P, V, dt);
    fixedBed(P, V, dt, ctx);
    measureU3(P, L, n);
  }

  // ---------------------------------------------------------------- unit 4
  // V-502, a horizontal three-phase separator split by an internal weir plate: the
  // bucket-and-weir arrangement of Arnold and Stewart, sized the way API Spec 12J thinks
  // about separators, with the overflow in the Francis 3/2-power form (RESOURCES 4.12).
  // Mixed liquid from U3 is trim-cooled in E-502 and enters chamber 1; water settles under
  // the oil and is drawn from the bottom (LIC504 -> WV-504); the oil overflows the weir
  // into chamber 2, whose level sets the product draw (LIC503 -> LV-503); gas leaves
  // overhead on pressure control (PIC505 -> PV-505). The weir height is an instructor
  // plant variable (env.weirH), so the operating window moves under the trainee.
  //
  // This is a training-fidelity correlation of that arrangement, NOT a property package:
  // there is no VLE, no droplet-settling criterion, no water chemistry and no emulsion
  // band. INVENTED outright -- this simulator's own, calibrated against nothing but its
  // own design point: carryBand and thinBand and the linear carry-over ramps they define,
  // gasFrac and the (1 + dT/40) vapour term, kP, the 0.3 % / 0.2 % analyser floors and
  // their 30 s lag, and every capacity coefficient (Cweir, Cw, Cp, Cg, coolK).
  //
  // Unit 04 draws its measurement noise from ctx.rand4, a SECOND seeded generator, so that
  // adding this unit cannot shift the shared stream U1-U3 consume and the v2 goldens
  // cannot move (U4-SEPARATOR-CONTRACT section 0). No rand4 in the ctx means no noise at
  // all: never ctx.rand, never Math.random.
  function noise4Fn(ctx) {
    const r = ctx && ctx.rand4;
    if (typeof r !== 'function') return () => 0;
    return (k) => (r() - 0.5) * k;
  }

  // A valve set that predates Unit 04 (module tests built on the v2 V, and any pre-U4
  // snapshot) reads as the design position instead of throwing, so Models.step stays
  // callable with a v2 V and every existing test keeps passing. moveValves only strokes
  // valves that are actually present in V.
  const vpos = (V, k, d) => (V && V[k] && Number.isFinite(V[k].pos)) ? V[k].pos : d;

  // Returns the water draw, which measureU4 needs for the AI510 ratio.
  function separator(P, L, V, dt, ctx) {
    const c = PARAMS.U4, env = envOf(P), s = sepOf(P), W = weirOf(P);
    const qfeed = Math.max(0, P.h.f);                       // U3 fresh feed, m3/h (read only)
    const act = env.catAct * (P.faults.bedact ? magOf(P).bedact : 1);   // the activity U3 uses (read only)
    const qwIn = qfeed * c.waterFrac * act;
    const qoIn = Math.max(0, qfeed - qwIn);

    // E-502 trim cooler on cooling water. TV-502 fails OPEN, so an air loss over-cools.
    const Thot = 0.5 * (P.h.pre + P.h.bed);
    s.Tin = lag(s.Tin, Math.max(30, Thot - c.coolK * vpos(V, 'TV502', 0.6)), c.tauT, dt);

    // chamber 1. Interface near the crest carries water over with the oil; an interface
    // run thin lets the water draw pull oil under it.
    s.wcarry = qwIn * clamp((s.hw - (W - c.carryBand)) / c.carryBand, 0, 1);
    const qwOut = c.Cw * vpos(V, 'WV504', 0.45) * Math.sqrt(Math.max(s.hw, 0) / 50);
    s.ocarry = qwOut * clamp((c.thinBand - s.hw) / c.thinBand, 0, 1);
    const h1 = s.hw + s.ho;
    s.qover = c.Cweir * Math.pow(Math.max(0, h1 - W), 1.5);
    s.hw = clamp(s.hw + (qwIn - s.wcarry - qwOut) / c.A1 / 3600 * dt, 0, 100);
    s.ho = clamp(s.ho + (qoIn - s.ocarry - s.qover) / c.A1 / 3600 * dt, 0, 100);

    // chamber 2: what came over the weir, less the product draw
    const qp = c.Cp * vpos(V, 'LV503', 0.5) * Math.sqrt(Math.max(s.h2, 0) / 50);
    if (ctx.productSample) ctx.productSample({draw_rate_m3h:qp,dt_s:dt});
    s.h2 = clamp(s.h2 + (s.qover + s.wcarry - qp) / c.A2 / 3600 * dt, 0, 100);

    // overhead gas: more vapour when the inlet runs warm, out through PV-505 and, once
    // PSV-502 has lifted, through the relief as well until the vessel is back below reseat
    const qgIn = qfeed * c.gasFrac * (1 + Math.max(0, s.Tin - 45) / 40) * 3600;
    const cap = c.Cg * vpos(V, 'PV505', 0.4) + (P.trips.psv502 ? c.Cg * 1.5 : 0);
    const qgOut = cap * Math.sqrt(Math.max(s.pres - c.Pdown, 0) / 700);
    s.pres = clamp(s.pres + c.kP * (qgIn - qgOut) * dt, 0, 1500);
    if (s.pres >= c.psvSet && !P.trips.psv502) {
      P.trips.psv502 = true;
      raiseTrip(ctx, 'V-502', 'PSV LIFT', s.pres, 'KPA', 'SEPARATOR RELIEF — VENTING TO FLARE');
    }
    if (P.trips.psv502 && s.pres < c.psvReset) { P.trips.psv502 = false; ctx.clear('V-502', 'PSV LIFT'); }
    return qwOut;
  }

  // The four noise draws happen whether or not the points exist, so the rand4 cursor
  // advances the same way on a tag database that predates Unit 04. A missing point is
  // simply not written -- Models.step stays callable with the v2 L.
  function measureU4(P, L, dt, n4, qwOut) {
    const s = sepOf(P);
    const nT = n4(0.3), nH2 = n4(0.2), nHw = n4(0.2), nP = n4(2);
    if (L.TIC502) L.TIC502.pv = s.Tin + nT;
    if (L.LIC503) L.LIC503.pv = s.h2 + nH2;
    if (L.LIC504) L.LIC504.pv = s.hw + nHw;
    if (L.PIC505) L.PIC505.pv = s.pres + nP;
    // Draw-quality analysers: the carried fraction of each draw over a 0.3 % / 0.2 % floor
    // (the clean product is never reported as bone dry), on a 30 s analyser lag.
    if (L.AI509) {
      const prev = Number.isFinite(L.AI509.pv) ? L.AI509.pv : 0.3;
      L.AI509.pv = lag(prev, Math.max(0.3, 100 * s.wcarry / Math.max(s.qover + s.wcarry, 0.01)), 30, dt);
    }
    if (L.AI510) {
      const prev = Number.isFinite(L.AI510.pv) ? L.AI510.pv : 0.2;
      L.AI510.pv = lag(prev, Math.max(0.2, 100 * s.ocarry / Math.max(qwOut, 0.01)), 30, dt);
    }
  }

  function stepU4(P, L, V, dt, ctx) {
    const n4 = noise4Fn(ctx);
    const qwOut = separator(P, L, V, dt, ctx);
    measureU4(P, L, dt, n4, qwOut);
  }

  // ---------------------------------------------------------------- combined
  function advanceClock(P, dt) { P.t += dt * 1000; P.up += dt; }

  function step(P, L, V, dt, ctx) {
    advanceClock(P, dt);
    stepU1(P, L, V, dt, ctx);
    stepU2(P, L, V, dt, ctx);
    stepU3(P, L, V, dt, ctx);
    stepU4(P, L, V, dt, ctx);
  }

  return { createState, createRand, envDefaults, magDefaults, advanceClock, stepU1, stepU2, stepU3, stepU4, step, PARAMS, MODEL_VALVES };
});
