// @artifact production
// Shared complete station semantics, extracted from the simulator at 3aad769.
(function(root,factory){
  if(typeof module === "object" && module.exports) module.exports=factory({"AlarmHelp":require("./alarm-help.js"),"BoundaryDof":require("./boundary-dof.js"),"Dispatch":require("./dispatch.js"),"Pid":require("./pid.js"),"Palette":require("./palette.js"),"SignalPath":require("./signal-path.js"),"Philosophy":require("./philosophy.js"),"Instructor":require("./instructor.js"),"CauseEffect":require("./cause-effect.js"),"Debrief":require("./debrief.js"),"AlarmEngine":require("./alarm-engine.js"),"Models":require("./models.js"),"DrillArch":require("./drill-arch.js"),"Kpi":require("./kpi.js"),"FaultEngine":require("./fault-engine.js"),"Training":require("./training.js"),"Process":require("./process.js"),"Topology":require("./topology.js"),"UpsetBridge":require("./upset-bridge.js")});
  else root.ESS.PlantCore=factory(root.ESS);
})(typeof globalThis!=="undefined"?globalThis:this,function(ESS){
  "use strict";
  return function(Base){ return class PlantCore extends Base {
  initSim(atTime){
    const now = typeof atTime==='number'?atTime:0;
    const P = (o)=>Object.assign({kind:'pid',mode:'AUTO',modeAttr:'OPERATOR',T2:0,ophilm:100,oplolm:0,opexhi:105,opexlo:-5,safeop:0,shed:'SHEDHOLD',badPv:false,init:false,dec:1,tgtLo:null,tgtHi:null,pvtrack:false,_as:{}}, o);
    this.L = {
      FI100: {kind:'ind',tag:'FI100',desc:'UNIT FEED SUPPLY FLOW',eu:'M3/H',lo:0,hi:150,dec:1,pv:60,cm:'CM0_FI100',alm:{},tgtLo:50,tgtHi:70,_as:{}},
      LIC101:P({tag:'LIC101',desc:'FEED TANK TK-101 LEVEL',eu:'%',lo:0,hi:100,pv:50,sp:50,op:50,K:1.5,T1:3,act:'DIR',sphilm:95,splolm:5,slave:'FIC102',cm:'CM1_LIC101',alm:{PVLL:[10,'Urgent'],PVLO:[20,'Low'],PVHI:[80,'High'],PVHH:[90,'Urgent']}}),
      // SPHILM 80 is the R-201 feed limit: the CSTR's jacket margin is about +33 % of design feed (src/models.js cstr), so the
      // LIC101 cascade may not run the reactor into its trip to empty the tank; TK-101 absorbs a surge as a surge tank should.
      FIC102:P({tag:'FIC102',desc:'TK-101 OUTLET / REACTOR FEED FLOW',eu:'M3/H',lo:0,hi:120,pv:60,sp:60,op:50,K:0.4,T1:0.15,act:'REV',mode:'CAS',master:'LIC101',pvtrack:true,sphilm:80,splolm:0,cm:'CM2_FIC102',alm:{PVLL:[5,'Urgent'],PVLO:[15,'Low'],PVHI:[95,'High'],PVHH:[110,'Urgent']}}),
      P101:  {kind:'motor',tag:'P101',desc:'FEED PUMP P-101',eu:'',lo:0,hi:1,dec:0,pv:1,cm:'CM2A_P101',run:true,cmd:'START',lock:0,trip:false,alm:{},_as:{}},
      TIC201:P({tag:'TIC201',desc:'REACTOR R-201 TEMPERATURE',eu:'DEG C',lo:0,hi:200,pv:150,sp:150,op:50,K:2,T1:8,T2:0.5,act:'REV',sphilm:170,splolm:100,slave:'TIC202',cm:'CM3_TIC201',alm:{PVLL:[130,'Urgent'],PVLO:[140,'Low'],PVHI:[165,'High'],PVHH:[175,'Urgent'],DEVHI:[15,'High']}}),
      AI205: {kind:'ind',tag:'AI205',desc:'R-201 REACTOR CONVERSION',eu:'%',lo:0,hi:100,dec:1,pv:85,cm:'CM3A_AI205',alm:{},tgtLo:75,tgtHi:95,_as:{}},
      TIC202:P({tag:'TIC202',desc:'R-201 JACKET COOLANT TEMP',eu:'DEG C',lo:0,hi:100,pv:40,sp:40,op:74,K:1.2,T1:1.5,act:'DIR',mode:'CAS',master:'TIC201',pvtrack:true,sphilm:80,splolm:5,cm:'CM4_TIC202',alm:{PVLL:[10,'Journal'],PVLO:[20,'Low'],PVHI:[70,'High'],PVHH:[85,'Urgent'],DEVHI:[12,'High']}}),
      TIC301:P({tag:'TIC301',desc:'E-301 FLASH PREHEAT OUTLET TEMP',eu:'DEG C',lo:0,hi:250,pv:180,sp:180,op:50,K:1.8,T1:4,T2:0.3,act:'REV',sphilm:210,splolm:120,cm:'CM5_TIC301',alm:{PVLL:[150,'Journal'],PVLO:[165,'Low'],PVHI:[200,'High'],PVHH:[215,'Urgent']}}),
      LIC401:P({tag:'LIC401',desc:'FLASH DRUM V-401 LEVEL',eu:'%',lo:0,hi:100,pv:45,sp:45,op:73,K:1.2,T1:2.5,act:'DIR',sphilm:90,splolm:10,cm:'CM6_LIC401',alm:{PVLL:[10,'Urgent'],PVLO:[20,'Low'],PVHI:[75,'High'],PVHH:[90,'Urgent']}}),
      PIC401:P({tag:'PIC401',desc:'V-401 OVERHEAD PRESSURE',eu:'KPA',lo:0,hi:1000,dec:0,pv:600,sp:600,op:40,K:0.8,T1:0.8,act:'DIR',sphilm:850,splolm:200,cm:'CM7_PIC401',alm:{PVLL:[350,'Urgent'],PVLO:[450,'Low'],PVHI:[800,'High'],PVHH:[900,'Urgent']}}),
      FIC211:P({tag:'FIC211',desc:'R-202 MONOMER FEED FLOW',eu:'M3/H',lo:0,hi:40,pv:0,sp:0,op:0,K:0.4,T1:0.15,act:'REV',sphilm:30,splolm:0,cm:'CM10_FIC211',almDelay:30,alm:{PVHI:[28,'High']}}),
      TIC212:P({tag:'TIC212',desc:'R-202 BATCH REACTOR TEMP',eu:'DEG C',lo:0,hi:150,pv:25,sp:40,op:8,K:1.8,T1:6,T2:0.4,act:'REV',mode:'MAN',slave:'TIC213',sphilm:95,splolm:20,cm:'CM11_TIC212',alm:{PVHI:[95,'High'],PVHH:[105,'Urgent']}}),
      TIC213:P({tag:'TIC213',desc:'R-202 JACKET MEDIUM TEMP',eu:'DEG C',lo:0,hi:130,pv:20,sp:20,op:45,K:1.2,T1:1.2,act:'REV',mode:'CAS',master:'TIC212',pvtrack:true,sphilm:120,splolm:5,cm:'CM12_TIC213',alm:{PVHI:[115,'High']}}),
      PI214: {kind:'ind',tag:'PI214',desc:'R-202 VAPOR PRESSURE',eu:'KPA',lo:0,hi:600,dec:0,pv:100,cm:'CM13_PI214',alm:{PVHI:[420,'High'],PVHH:[520,'Urgent']},tgtLo:80,tgtHi:320,_as:{}},
      LI215: {kind:'ind',tag:'LI215',desc:'R-202 BATCH LEVEL',eu:'%',lo:0,hi:100,dec:1,pv:12,cm:'CM14_LI215',alm:{PVHI:[85,'High']},tgtLo:10,tgtHi:80,_as:{}},
      TI216: {kind:'ind',tag:'TI216',desc:'R-202 ADIABATIC END TEMP',eu:'DEG C',lo:0,hi:200,dec:1,pv:25,cm:'CM14A_TI216',alm:{PVHI:[100,'High'],PVHH:[106,'Urgent']},tgtLo:20,tgtHi:95,_as:{}},
      M202:  {kind:'motor',tag:'M202',desc:'R-202 AGITATOR',eu:'',lo:0,hi:1,dec:0,pv:1,cm:'CM15_M202',run:true,cmd:'START',lock:0,trip:false,alm:{},_as:{}},
      FIC310:P({tag:'FIC310',desc:'R-310 FRESH FEED FLOW',eu:'M3/H',lo:0,hi:80,pv:40,sp:40,op:50,K:0.4,T1:0.15,act:'REV',sphilm:70,splolm:0,cm:'CM16_FIC310',alm:{PVLO:[10,'Low'],PVHI:[65,'High']}}),
      TIC311:P({tag:'TIC311',desc:'H-310 PREHEATER OUTLET TEMP',eu:'DEG C',lo:0,hi:500,dec:0,pv:320,sp:320,op:40,K:1.0,T1:2.5,T2:0.2,act:'REV',sphilm:380,splolm:150,cm:'CM17_TIC311',alm:{PVLO:[260,'Low'],PVHI:[360,'High'],PVHH:[400,'Urgent']}}),
      TI312: {kind:'ind',tag:'TI312',desc:'R-310 CATALYST BED HOTSPOT',eu:'DEG C',lo:0,hi:600,dec:0,pv:380,cm:'CM18_TI312',alm:{PVHI:[440,'High'],PVHH:[480,'Urgent']},tgtLo:360,tgtHi:420,_as:{}},
      TI314: {kind:'ind',tag:'TI314',desc:'H-310 PASS 1 TUBE SKIN TEMP',eu:'DEG C',lo:0,hi:700,dec:0,pv:364,cm:'CM17A_TI314',alm:{PVHI:[440,'High'],PVHH:[490,'Urgent']},tgtLo:330,tgtHi:400,_as:{}},
      TI315: {kind:'ind',tag:'TI315',desc:'H-310 PASS 2 TUBE SKIN TEMP',eu:'DEG C',lo:0,hi:700,dec:0,pv:378,cm:'CM17B_TI315',alm:{PVHI:[450,'High'],PVHH:[500,'Urgent']},tgtLo:340,tgtHi:410,_as:{}},
      AI316: {kind:'ind',tag:'AI316',desc:'H-310 FLUE GAS EXCESS O2',eu:'%',lo:0,hi:21,dec:1,pv:3,cm:'CM17C_AI316',almDelay:10,alm:{PVLO:[1.5,'Low']},tgtLo:2,tgtHi:5,_as:{}},
      FIC313:P({tag:'FIC313',desc:'R-310 QUENCH FLOW',eu:'M3/H',lo:0,hi:40,pv:10,sp:10,op:25,K:0.5,T1:0.2,act:'REV',sphilm:38,splolm:0,cm:'CM19_FIC313',alm:{PVLO:[4,'Low'],PVLL:[2,'Urgent']}}),
      // ---- Unit 04: two-chamber weir separator V-502 (docs/dev/U4-SEPARATOR-CONTRACT.md section 2) ----
      TIC502:P({tag:'TIC502',desc:'E-502 SEPARATOR INLET TEMP',eu:'DEG C',lo:0,hi:200,pv:45,sp:45,op:60,K:1.2,T1:2.0,T2:0.2,act:'DIR',sphilm:90,splolm:25,cm:'CM20_TIC502',alm:{PVLO:[30,'Low'],PVHI:[60,'High'],PVHH:[80,'Urgent']}}),
      LIC503:P({tag:'LIC503',desc:'V-502 OIL CHAMBER LEVEL',eu:'%',lo:0,hi:100,pv:50,sp:50,op:50,K:1.2,T1:2.5,act:'DIR',sphilm:85,splolm:15,cm:'CM21_LIC503',alm:{PVLL:[10,'Urgent'],PVLO:[25,'Low'],PVHI:[75,'High'],PVHH:[90,'Urgent']}}),
      LIC504:P({tag:'LIC504',desc:'V-502 WATER INTERFACE LEVEL',eu:'%',lo:0,hi:100,pv:25,sp:25,op:45,K:1.5,T1:3.0,act:'DIR',sphilm:45,splolm:8,cm:'CM22_LIC504',alm:{PVLL:[5,'Urgent'],PVLO:[12,'Low'],PVHI:[40,'High'],PVHH:[48,'Urgent']}}),
      PIC505:P({tag:'PIC505',desc:'V-502 SEPARATOR PRESSURE',eu:'KPA',lo:0,hi:1500,dec:0,pv:800,sp:800,op:40,K:0.8,T1:0.8,act:'DIR',sphilm:1000,splolm:500,cm:'CM23_PIC505',alm:{PVLL:[400,'Urgent'],PVLO:[600,'Low'],PVHI:[950,'High'],PVHH:[1050,'Urgent']}}),
      AI509: {kind:'ind',tag:'AI509',desc:'V-502 WATER IN OIL DRAW',eu:'%',lo:0,hi:20,dec:2,pv:0.3,cm:'CM24_AI509',alm:{PVHI:[2,'High'],PVHH:[5,'Urgent']},tgtLo:0,tgtHi:1,_as:{}},
      AI510: {kind:'ind',tag:'AI510',desc:'V-502 OIL IN WATER DRAW',eu:'%',lo:0,hi:20,dec:2,pv:0.2,cm:'CM25_AI510',alm:{PVHI:[2,'High']},tgtLo:0,tgtHi:1,_as:{}}
    };
    for(const k in this.L){ const l=this.L[k]; if(l.kind==='pid'){ l.I=l.op; l.lastPv=l.pv; } l._am={}; l.almOff={}; for(const c in l.alm){ if(l.alm[c].length<3) l.alm[c][2]=this.subprioDefault(c); } }
    this.V = { FV102:{pos:.5,stuck:false,fail:0}, TV202:{pos:.74,stuck:false,fail:1}, TV301:{pos:.5,stuck:false,fail:0}, PV401:{pos:.4,stuck:false,fail:1}, LV401:{pos:.73,stuck:false,fail:0}, MV211:{pos:0,stuck:false,fail:0}, JV213:{pos:.45,stuck:false,fail:0}, FV310:{pos:.5,stuck:false,fail:0}, FV311:{pos:.4,stuck:false,fail:0}, QV313:{pos:.25,stuck:false,fail:1}, TV502:{pos:.6,stuck:false,fail:1}, LV503:{pos:.5,stuck:false,fail:0}, WV504:{pos:.45,stuck:false,fail:0}, PV505:{pos:.4,stuck:false,fail:1} };
    // process state and dynamics come from ESS.Models (Henson/Seborg CSTR, Lucia/Engell semi-batch, Badgwell fired heater; RESOURCES 4.4, 4.1, 4.2)
    this.P = ESS.Models.createState(now);
    // Architecture fault-engine state (V3-PLAN S2): instructor-scheduled engine faults
    // that carry no legacy P.faults flag of their own (none yet -- the twelve legacy
    // upsets stay authoritative in P.faults/P.faultT/V[x].stuck per decision D1; this is
    // the seat for a future panel-injected fault). Lives in P, not on the Component or in
    // this.instr, so it travels through snapshot/restore/replay for free -- makeSnapshot's
    // clone(src.P) and restoreSnapshot's I.clone(snap.P) round-trip it with no edit to
    // src/instructor.js (advisory Q3(B)). Defaulted below in restoreSnapshot() for a
    // snapshot taken before this field existed.
    this.P.archFaults = ESS.FaultEngine.createState();
    // W2: the C&E recorder. Lives on the Component, NOT on P -- it must stay out of the process
    // state for the same reason W1's notes do (tests/_fixture.js endState() digests P and the v2
    // event count; the recorder is neither). Re-created here so a reset or a preset starts it
    // clean, and so a restored snapshot does not inherit another run's trips.
    this.ceRec = (typeof ESS!=='undefined'&&ESS.CauseEffect) ? ESS.CauseEffect.createRecorder() : null;
    // The panel's own schedule ledger (V3-PLAN S2, DO item 1): archPending holds
    // instructor-scheduled engine faults not yet at their onset time; archMeta carries,
    // per active instanceId, the STEP/RAMP mode, ramp length, target magnitude and optional
    // expiry that the fixed FaultEngine instance shape has no room for. Both are plain P
    // keys outside tests/_fixture.js's endState() picked-field list, so -- like archFaults
    // itself -- they are invisible to every golden and travel through snapshot/restore/
    // replay for free (advisory Q3(B)). See archFireFault()/archFaultTick().
    this.P.archPending = [];
    this.P.archMeta = {};
    // S3: "explicitly inspected" and the evidence/hypothesis training state (V3-PLAN
    // section 6, addendum Q5). Both are P-resident so ESS.Instructor.clone's JSON round
    // trip snapshots/restores/replays them for free -- a Set would silently serialize to
    // {} on clone, so this is a plain object keyed by node id, never a Set (advisory Q5).
    // archInspected records EVERY node id a trainee has explicitly opened (selectNode);
    // dispatch.js's MARK_EVIDENCE/VERIFY validate() fails closed against exactly this map
    // via ctx.wasInspected. training is ESS.Dispatch's own plain-JSON shape
    // ({evidence,pins,hypotheses,verifications}) so trainingStateOf(ctx) mutates it in
    // place and nothing here needs to know that shape's internals.
    this.P.archInspected = {};
    this.P.training = ESS.Dispatch.createTrainingState();
    // The A-drill lane (V3-PLAN S3, architect addendum Q4): a PARALLEL lane to the legacy
    // D-series this.state.drill -- drillWatch/dHook/dAct/dTrip/endDrill/scoreDrill all read
    // D-shaped def fields (rel, act, stable, trips, q, a) an A-series DrillDefinition does
    // not have, so reusing that slot mis-scores or crashes. null when no A-drill is armed;
    // see startADrill()/aDrillWatch()/endADrill(). Lives on P (not this.state) so it
    // travels through snapshot/restore/replay and is reset to null by every initSim(),
    // including the one applyPreset() runs internally -- no drill survives a preset load.
    this.P.aDrill = null;
    this.P.archFaultLog = [];
    this._lastADrill = null;
    // Instructor station state survives a process reset (snapshots, password, hidden flag, seed); the run-bound parts
    // (backtrack ring, action journal, replay) start fresh. Every random draw goes through the seeded generator so a
    // run, a snapshot and a replay are reproducible (cstr-ots seeded determinism, RESOURCES 4.9).
    if(!this.instr) this.instr = ESS.Instructor.create();
    ESS.Instructor.resetRun(this.instr);
    // The v3 command/event boundary (V3-PLAN section 4): survives a process reset the same
    // way this.instr does, so a snapshot/replay taken before a reset still has a live
    // dispatcher to route through afterward. Guarded so a reset never registers the same
    // handler twice on the same registry.
    if(!this.dispatcher){ this.dispatcher = ESS.Dispatch.create(); this.registerDispatchHandlers(); }
    this.seed = this.instr.seed;
    this.rand = ESS.Models.createRand(this.seed);
    // Unit 04 draws its measurement noise from its OWN seeded stream so the v2 units' trajectories
    // (and every v2 golden) are byte-identical with or without it (U4-SEPARATOR-CONTRACT rule 0.2).
    this.rand4 = ESS.Models.createRand((this.seed ^ 0x5eed4) >>> 0);
    this.vLag = {};                // valve id -> seconds the valve has not followed its controller output (assistant symptom)
    this.callouts = {};            // tag -> {txt, until}: inline operator callouts (write rejections), shown ~5 s
    this.phaseSet = null;          // applied U2 state-based alarm limit set (phaseSetKey())
    this.tadShed = false;          // TI216 Urgent interlock latched
    // ISA-18.2 engine (RESOURCES 2.5, 2.9); 60 min shelve cap and 15 min default are this sim's alarm-philosophy choice
    this.alarmEngine=ESS.AlarmEngine.createEngine({maxShelveMs:60*60000, defaultShelveMs:15*60000, foldWindowMs:10*60000, dasRules:this.dasRules()});
    this.events=[]; this.msgs=[]; this.hist={}; this.eid=1;
    this.alarmLog=[]; this.t0=now;   // raise / rtn / ack history for the KPI display (ESS.Kpi, RESOURCES 2.7, 2.8)
    // Training and audit state that outlives a process reset: the session's task-done set (coverage matrix), the
    // last 20 drill results (training record), the configuration change count (MOC) and the disabled-asset set.
    if(!this.tasksDone) this.tasksDone=new Set();
    if(!this.trainingRecords) this.trainingRecords=[];
    if(this.mocCount==null) this.mocCount=0;
    this.disabledAssets=new Set();
    this._lastPhase='IDLE';
    this.histTags().forEach(t=>this.hist[t]=[]);
    this.addEvent('SYSTEM','STN01','OPERATOR STATION STARTED — SIMULATION MODE','','');
    this.applyPhaseSet(this.phaseSetKey(),true);
    // ARCH view (V3-PLAN S1): the topology graph is derived from L/V, which initSim just
    // rebuilt, so cache it here rather than in renderVals() (runs at every setState, not
    // just 2 Hz) — see CODE-MAP / advisory Q2. Re-cached at restoreSnapshot() too, which
    // replaces L/V wholesale.
    this.topo = ESS.Topology.build({L:this.L, V:this.V, assetTree:this.assetTree(), unitOf:(t)=>this.unitOf(t)});
    // The graph contract (src/topology.js validate) was a genuine check that nothing called
    // at runtime. A violation is a build defect -- a new tag with no unit, a valve with no
    // command path -- not a runtime condition, so it fails loudly here, where every app-level
    // test passes through, rather than filing itself under U1 and teaching that to a trainee.
    const topoProblems=ESS.Topology.validate(this.topo);
    if(topoProblems.length) throw new Error('TOPOLOGY CONTRACT VIOLATED — '+topoProblems.join('; '));
    this.publishCoach();
  }
  step(dt){
    // Due replay entries are applied BEFORE P and L are captured. A replayed DRILL / ADRILL
    // entry rebuilds the plant (applyPreset -> initSim -> restoreSnapshot replaces this.P,
    // this.L and this.V wholesale); capturing first ran the rest of this step against the
    // orphaned objects and advanced the seeded generator one step out of phase, so the
    // replay completed, matched the clock, and reproduced a different trajectory
    // (22 of 24 points). Found by the verify pass; release gate 3.
    this.applyReplayDue();
    const P=this.P, L=this.L;
    ESS.Models.advanceClock(P,dt);
    ESS.Models.stepU1(P,L,this.V,dt,this.modelCtx());
    L.AI205.pv=P.x*100+this.noise(0.2);          // reactor conversion from the CSTR balance (indication)
    this.stepU2(dt);
    this.stepU3(dt);
    this.stepU4(dt);
    this.pids(dt);
    this.scan(dt);
    this.interlocks();
    this.alarmTick();
    this.valveWatch(dt);
    this.drillWatch(dt);
    this.aDrillWatch(dt);
    this.archFaultTick();
    const historyGap=ESS.FaultEngine.listActive(P.archFaults||ESS.FaultEngine.createState())
      .some(f=>f.faultId==='HISTORIAN_GAP');
    if(!historyGap){
      for(const k of this.histTags()){ const l=L[k]; const h=this.hist[k]; h.push([P.t, l.pv, l.sp??0, l.op??0]); if(h.length>(this.historyLimit||7200)) h.shift(); }
    }
    this.backtrackTick();
    this.replayCheckDone();
  }
  seqCmd(cmd,silent){
    const b=this.P.b;
    if(cmd==='START'){ if(b.phase!=='IDLE'){ this.msgZone('SEQUENCE ALREADY RUNNING'); return; } if(!silent && !this.can('OPER')) return; b.phase='CHARGE'; b.pt=0; b.Cm=0; b.held=false; this.addEvent(silent?'SYSTEM':'OPERATOR','SCM202','BATCH SEQUENCE STARTED','IDLE','CHARGE'); }
    if(cmd==='HOLD'){ if(b.phase==='IDLE'){ this.msgZone('SEQUENCE IS IDLE'); return; } if(!this.can('OPER')) return; if(b.held && this.tadShed){ this.confirmInterlockHold(); return; } b.held=!b.held; this.addEvent('OPERATOR','SCM202',b.held?'SEQUENCE HELD — FEED STOPPED':'SEQUENCE RESUMED','',''); this.dAct('HOLD','SCM202','',0); }
    if(cmd==='ABORT'){ if(b.phase==='IDLE'){ this.msgZone('SEQUENCE IS IDLE'); return; } if(!this.can('OPER')) return; b.phase='COOL'; b.pt=0; b.held=false; this.L.FIC211.sp=0; this.L.TIC212.sp=40; this.addEvent('OPERATOR','SCM202','SEQUENCE ABORTED → COOL','',''); this.dAct('HOLD','SCM202','',0); }
    if(!silent) this.taskDone({START:'bat.start',HOLD:'bat.hold',ABORT:'bat.abort'}[cmd]);
    this.syncPhaseSet();
    if(!silent) this.journal('SEQ','SCM202',cmd);
  }
  motorCmd(tag,start){
    const m=this.L[tag]; if(!m||!this.can('OPER')) return;
    if(start){
      if(m.run) return;
      if(m.lock>0){ this.msgZone('START INHIBITED — LOCKOUT '+Math.ceil(m.lock)+' S'); return; }
      if(tag==='P101' && this.P.tankL<5){ this.raiseA('P101','CMDFAIL','High',0,'','START PERMISSIVE NOT MET — TK-101 LEVEL LOW'); this.msgZone('PERMISSIVE NOT MET: TK-101 LEVEL < 5%'); return; }
      const wasTrip=!!m.trip;
      m.run=true; m.trip=false; m.cmd='START'; this.addEvent('OPERATOR',tag,'START COMMAND','STOP','RUN'); if(tag==='P101') this.clearA('P101','CMDFAIL'); this.dAct('START',tag,'',0); this.journal('START',tag);
      if(wasTrip) this.archSynthEvent('INTERLOCK.DEFEAT','DRV-'+tag,null);
    } else {
      if(!m.run) return;
      m.run=false; m.cmd='STOP'; m.lock=15; this.addEvent('OPERATOR',tag,'STOP COMMAND','RUN','STOP'); this.journal('STOP',tag);
    }
    this.taskDone('ctl.motor');
  }
  ackAlarm(a){
    if(!this.can('OPER')) return;
    const r=this.alarmEngine.get(a); if(!r) return;
    const evs=this.alarmEngine.ack(r,this.P.t);
    if(!evs.length){ this.msgZone('ALARM ALREADY ACKNOWLEDGED'); return; }
    this.logAlarmEvents(evs);
    this.dHook('ACK',r.tag);
    this.journal('ACK',r.tag,r.key);
    this.taskDone('alm.ack');
    // Safety-gate/scoring lane: this app has no NEW dispatch action for "acknowledge" --
    // it reuses the existing alarm ack. drill-arch's own ACK action (V3-PLAN section 6's
    // "stabilize" category) targets the drill's primary topology node, e.g. 'XMTR-FIC102'
    // for A1, so an accepted ack is mapped to that point's FIELD-layer node id the same
    // way topology.js derives it (id('XMTR',tag) for a measured point, id('DRV',tag) for a
    // motor). This only credits drills whose fault is wired to real physics (A1's legacy
    // 'xmtr' upset raises FIC102 BADPV; the nine engine-only faults raise no alarm at all
    // -- see the S3 report) but never fabricates a match: matchAction still requires the
    // exact node id, so acking an unrelated alarm during an unrelated drill scores nothing.
    this.archSynthEvent('ACK',(this.L[r.tag]&&this.L[r.tag].kind==='motor'?'DRV-':'XMTR-')+r.tag,null);
  }
  confirmMsg(id){
    const m=this.msgs.find(x=>x.id===id); if(!m||!m.confirm){ this.msgZone('MESSAGE DOES NOT REQUIRE CONFIRMATION'); return false; }
    if(m.confirmed){ this.msgZone('MESSAGE ALREADY CONFIRMED'); return false; }
    if(!this.can('OPER')) return false;
    m.confirmed=true; m.confirmedBy=this.operName(); m.confirmT=this.P.t;
    this.addEvent('OPERATOR',m.src,'MESSAGE CONFIRMED — '+m.txt,'',m.confirmedBy);
    this.journal('CONFIRM',m.src,m.txt);   // by text: message ids are fresh after a restore, the text is not
    this.taskDone('msg.confirm');
    if(m.src==='SCM202') this.taskDone('bat.confirm');
    return true;
  }
  setUpset(k,on){
    this.dispatcher.dispatch(
      {journalAdd:(entry)=>ESS.Instructor.journalAdd(this.instr,entry)},
      {type:ESS.Dispatch.TYPES.FAULT_INJECT,actor:'INSTRUCTOR',target:k,payload:!!on,simTime:this.P.t}
    );
  }
  setVariable(k,v){
    const def=ESS.Instructor.variableDefs().find(d=>d.k===k); const n=Number(v); if(!def||!isFinite(n)) return;
    const val=Math.max(def.min,Math.min(def.max,n));
    ESS.Instructor.setPath(this.P,def.path,val);
    this.instrNote('VARIABLE '+def.label.toUpperCase()+' = '+this.fmt(val,def.dec)+(def.eu?' '+def.eu:''));
    this.journal('VAR',k,val,{instr:true});
  }
  setMagnitude(key,v){ const n=Number(v); if(!isFinite(n)) return; this.P.mag[key]=n; this.instrNote('UPSET MAGNITUDE '+key.toUpperCase()+' = '+n); this.journal('MAG',key,n,{instr:true}); }
  setArchFault(faultId,targetNodeId,opts){
    const o=opts||{};
    this.dispatcher.dispatch(
      {journalAdd:(entry)=>ESS.Instructor.journalAdd(this.instr,entry)},
      {type:'ARCH_FAULT_ACTIVATE',actor:'INSTRUCTOR',target:targetNodeId,
        payload:{faultId,targetNodeId,delaySec:o.delaySec||0,durationSec:(o.durationSec==null||o.durationSec==='')?null:o.durationSec,
          mode:o.mode==='RAMP'?'RAMP':'STEP',rampSec:o.rampSec||0,magnitude:o.magnitude==null?null:o.magnitude},
        simTime:this.P.t}
    );
  }
  clearArchFault(faultId,targetNodeId){
    this.dispatcher.dispatch(
      {journalAdd:(entry)=>ESS.Instructor.journalAdd(this.instr,entry)},
      {type:'ARCH_FAULT_CLEAR',actor:'INSTRUCTOR',target:targetNodeId,payload:{faultId,targetNodeId},simTime:this.P.t}
    );
  }
  subprioDefault(cond){ const m={TRIP:15,PVHH:12,PVLL:12,PVHI:8,PVLO:8,DEVHI:6,CMDFAIL:4,BADPV:10}; if(m[cond]!=null) return m[cond]; return /TRIP|PSV/.test(cond)?15:0; }
  registerDispatchHandlers(){
    const self=this;
    // S3: the four evidence/hypothesis commands (MARK_EVIDENCE, PIN_COMPARE,
    // SUBMIT_HYPOTHESIS, VERIFY), registered exactly the way tests/dispatch-training.test.js
    // models it -- one call, on the dispatcher this same guard creates once (initSim).
    ESS.Dispatch.registerTraining(this.dispatcher);
    this.dispatcher.register(ESS.Dispatch.TYPES.FAULT_INJECT,{
      validate:(ctx,cmd)=>{
        const k=cmd.target;
        if(!ESS.Instructor.upsetDefs().some(d=>d.k===k)) return 'unknown upset: '+k;
        return true;
      },
      apply:(ctx,cmd)=>{
        const k=cmd.target, on=!!cmd.payload;
        self.injectFault(k,on);                          // D1: the one, unchanged physics path
        if(k==='drift'&&!on) self.P.driftOff=0;
        const def=ESS.Instructor.upsetDefs().find(d=>d.k===k);
        self.instrLog('UPSET '+(on?'ON':'OFF')+': '+(def?def.label:k)+(self.instr.hidden?' (HIDDEN)':''));
        return on;
      },
      journal:(ctx,cmd)=>({op:'UPSET',tag:cmd.target,arg:cmd.payload?'ON':'OFF',instr:true})
    });
    // Architecture panel (V3-PLAN S2, DO item 1): instructor-scheduled engine faults on
    // topology nodes the twelve legacy upsets do not already own. Deliberately separate
    // TYPE strings from FAULT_INJECT/FAULT_CLEAR (ESS.Dispatch.TYPES) -- those names are
    // reserved for later stages by dispatch.js's own header comment, and FAULT_INJECT is
    // already bound to the legacy-upset handler above with a different cmd.target shape
    // (an upset key, not a node id); re-registering it here would silently replace that
    // handler. Every check that can fail lives in validate() (dispatch.js's CONTRACT note
    // on apply()); apply() only replays a trial FE.activate() that validate() already
    // proved will succeed against the CURRENT engine state, so it cannot itself throw.
    this.dispatcher.register('ARCH_FAULT_ACTIVATE',{
      validate:(ctx,cmd)=>self.archValidateActivate(cmd.payload||{}),
      apply:(ctx,cmd)=>{
        const p=cmd.payload;
        self.scheduleArchFault(p);
        self.instrLog('ARCH FAULT '+(Number(p.delaySec)>0?'SCHEDULED (+'+Number(p.delaySec)+'S)':'ACTIVATED')+': '+self.archFaultDisplayName(p.faultId)+' @ '+self.archFaultTargetLabel(p.targetNodeId)+(self.instr.hidden?' (HIDDEN)':''));
        // Configuration numbers (magnitude, onset delay, duration, ramp) are plant-condition
        // detail, never mirrored to the trainee regardless of the hidden switch -- the same
        // rule setMagnitude()/setVariable() already follow (advisory Q5).
        self.instrNote('ARCH FAULT CONFIG '+p.faultId+' @ '+p.targetNodeId+': mode='+(p.mode==='RAMP'?'RAMP '+p.rampSec+'S':'STEP')+
          ' onset=+'+(Number(p.delaySec)||0)+'S duration='+(p.durationSec==null||p.durationSec===''?'INDEFINITE':p.durationSec+'S')+
          (p.magnitude==null?'':' magnitude='+p.magnitude));
        return true;
      },
      journal:(ctx,cmd)=>{
        const p=cmd.payload, def=ESS.FaultEngine.getFaultDef(p.faultId);
        return {op:'ARCHFAULT',tag:p.targetNodeId,arg:p.faultId,instr:true,
          delaySec:Number(p.delaySec)||0,
          durationSec:(p.durationSec==null||p.durationSec==='')?null:Number(p.durationSec),
          mode:p.mode==='RAMP'?'RAMP':'STEP',
          rampSec:p.mode==='RAMP'?(Number(p.rampSec)||0):0,
          magnitude:(def&&def.magnitudeRange)?Number(p.magnitude):null};
      }
    });
    this.dispatcher.register('ARCH_FAULT_CLEAR',{
      validate:(ctx,cmd)=>self.archValidateClear(cmd.payload||{}),
      apply:(ctx,cmd)=>{
        const p=cmd.payload;
        self.archClearNow(p.faultId,p.targetNodeId);
        self.instrLog('ARCH FAULT CLEARED: '+self.archFaultDisplayName(p.faultId)+' @ '+self.archFaultTargetLabel(p.targetNodeId)+(self.instr.hidden?' (HIDDEN)':''));
        return true;
      },
      journal:(ctx,cmd)=>({op:'ARCHCLEAR',tag:cmd.payload.targetNodeId,arg:cmd.payload.faultId,instr:true})
    });
  }
  dasRules(){
    return {
      'P101.TRIP':['FIC102.PVLO','FIC102.PVLL','LIC101.PVHI','LIC101.PVHH'],
      'TK-101.HIHI TRIP':['LIC101.PVHI','LIC101.PVHH'],
      'R-201.HI TEMP TRIP':['TIC201.DEVHI','TIC202.DEVHI','TIC202.PVHI','FIC102.PVLO','FIC102.PVLL'],
      'R-202.HI TEMP TRIP':['TIC212.PVHI','TIC212.PVHH'],
      'M202.TRIP':['TIC213.PVHI'],
      'R-310.HI TEMP TRIP':['TIC311.PVLO'],
      'V-502.PSV LIFT':['PIC505.PVHI','PIC505.PVHH'],
      'LIC504.PVHH':['AI509.PVHI','AI509.PVHH']   // the interface at the crest is the cause; water in the product draw is its consequence (U4-SEPARATOR-CONTRACT section 5)
    };
  }
  histTags(){ return ['FI100','LIC101','FIC102','AI205','TIC201','TIC202','TIC301','LIC401','PIC401','FIC211','TIC212','TIC213','PI214','LI215','TI216','FIC310','TIC311','TI312','FIC313','TI314','TI315','AI316','TIC502','LIC503','LIC504','PIC505','AI509','AI510']; }
  addEvent(type,src,desc,oldV,newV,meta){ const m=meta||{}; this.events.unshift({id:this.eid++, t:this.P?this.P.t:0, type, src, desc, oldV:oldV===undefined?'':String(oldV), newV:newV===undefined?'':String(newV), lvl:m.lvl||this.state.sec, who:m.who||this.operName()}); if(this.events.length>600) this.events.length=600; }
  applyPhaseSet(key,silent){
    const set=this.phaseSets()[key]; if(!set) return;
    const prev=this.phaseSet; const parts=[];
    for(const tag in set){ const l=this.L[tag]; if(!l) continue;
      for(const cond in set[tag]){ const v=set[tag][cond];
        if(v){ const old=l.alm[cond]||l.almOff[cond]; const sub=(old&&old[2]!=null)?old[2]:this.subprioDefault(cond); l.alm[cond]=[v[0],v[1],sub]; delete l.almOff[cond]; parts.push(tag+' '+cond+' '+this.fmt(v[0],l.dec)+' '+v[1][0]); }
        else { if(l.alm[cond]){ l.almOff[cond]=l.alm[cond]; delete l.alm[cond]; } if(l._as[cond]){ this.clearA(tag,cond,l.pv); l._as[cond]=false; } if(l._am) delete l._am[cond]; parts.push(tag+' '+cond+' OFF'); }
      }
    }
    this.phaseSet=key;
    if(!silent) this.configChange('SCM202','ALARM LIMIT SET '+key+' — '+parts.join(' · '),prev||'',key,'STATE-BASED LIMITS',{program:'SCM202'});
  }
  phaseSetKey(){ const b=this.P.b; return (b.phase==='FEED'&&b.held)?'HELD':b.phase; }
  assetTree(){
    return [
      {id:'PLANT',label:'PLANT',depth:0},
      {id:'U1',label:'UNIT 01 CONTINUOUS',depth:1,unit:'U1'},
      {id:'TK-101',label:'TK-101 FEED TANK',depth:2,unit:'U1',tags:['FI100','LIC101','P101','TK-101']},
      {id:'R-201',label:'R-201 REACTOR',depth:2,unit:'U1',tags:['FIC102','TIC201','AI205','TIC202','R-201']},
      {id:'V-401',label:'V-401 FLASH DRUM',depth:2,unit:'U1',tags:['TIC301','LIC401','PIC401','V-401']},
      {id:'U2',label:'UNIT 02 BATCH',depth:1,unit:'U2'},
      {id:'R-202',label:'R-202 BATCH RX',depth:2,unit:'U2',tags:['FIC211','TIC212','TIC213','PI214','LI215','TI216','M202','R-202','SCM202']},
      {id:'U3',label:'UNIT 03 FIRED RX',depth:1,unit:'U3'},
      {id:'H-310',label:'H-310 PREHEATER',depth:2,unit:'U3',tags:['FIC310','TIC311','TI314','TI315','AI316','H-310']},
      {id:'R-310',label:'R-310 FIXED BED',depth:2,unit:'U3',tags:['TI312','FIC313','R-310']},
      {id:'U4',label:'UNIT 04 SEPARATION',depth:1,unit:'U4'},
      {id:'E-502',label:'E-502 TRIM COOLER',depth:2,unit:'U4',tags:['TIC502','E-502']},
      {id:'V-502',label:'V-502 WEIR SEPARATOR',depth:2,unit:'U4',tags:['LIC503','LIC504','PIC505','AI509','AI510','V-502']}
    ];
  }
  unitOf(tag){
    if(['FIC211','TIC212','TIC213','PI214','LI215','TI216','M202','R-202','SCM202'].includes(tag)) return 'U2';
    if(['FIC310','TIC311','TI312','FIC313','TI314','TI315','AI316','R-310','H-310'].includes(tag)) return 'U3';
    if(['TIC502','LIC503','LIC504','PIC505','AI509','AI510','V-502','E-502'].includes(tag)) return 'U4';
    // U1 is listed like the others, not caught by "anything else in L": a tag added to the
    // database and to no unit list now returns null, Topology.build() records it as
    // unplaced, validate() reports it and initSim() refuses to start (Stage 1 foundation).
    if(['FI100','LIC101','FIC102','P101','TIC201','AI205','TIC202','TIC301','LIC401','PIC401','TK-101','R-201','V-401'].includes(tag)) return 'U1';
    return null;
  }
  applyReplayDue(){
    const r=this.instr&&this.instr.replay; if(!r) return;
    const due=ESS.Instructor.replayDue(r,this.P.t);
    this._replayApplying=true;
    try{ for(const e of due) this.applyJournalEntry(e); } finally{ this._replayApplying=false; }
    // Complete HERE, at the head of the step, the moment the last entry has been applied and the
    // clock has reached toT -- before advanceClock runs. Completing only at the tail
    // (replayCheckDone) let the replay take ONE MORE step than the live run did, so it finished
    // at toT + dt while the live exercise finished at toT: same actions, one extra step of
    // physics, and every trajectory digest differed. The live run's final step is the one that
    // BROUGHT the clock to toT; the replay must stop at the same instant, not after it.
    this.replayCheckDone();
  }
  modelCtx(){
    if(this._ctx) return this._ctx;
    this._ctx={
      raise:(src,cond,prio,val,eu,desc)=>this.raiseA(src,cond,prio,val,eu,desc),
      clear:(src,cond)=>this.clearA(src,cond),
      tripMotor:(tag,why)=>this.tripMotor(tag,why),
      addEvent:(type,src,desc,oldV,newV)=>this.addEvent(type,src,desc,oldV,newV),
      rand:()=>this.rand(),
      rand4:()=>this.rand4?this.rand4():0,                 // Unit 04 only; zero if absent
      shed:(l)=>this.applyShed(l),
      message:(t)=>this.msgZone(t),
      // W2: the C&E recorder chains onto the EXISTING seam. dTrip runs first and
      // unconditionally, so D-series drill scoring is byte-identical; the recorder is
      // read-only and writes only to its own log. The guard means a missing recorder is a
      // no-op, so nothing here can ever be the reason a trip is not scored.
      onTrip:(src,cond)=>{ this.dTrip(src,cond); if(this.ceRec) this.ceRec.observe(src,cond,this.P.t); },
      measurementBias:(tag,simTime,span)=>ESS.FaultEngine.measurementBias(
        this.P.archFaults||ESS.FaultEngine.createState(),'XMTR-'+tag,simTime,span)
    };
    return this._ctx;
  }
  noise(k){ return (this.modelCtx().rand()-0.5)*k; }
  stepU2(dt){
    const P=this.P, L=this.L;
    ESS.Models.stepU2(P,L,this.V,dt,this.modelCtx());
    L.TI216.pv=P.b.Tad+this.noise(0.15);
    this.scmRestoreModes();
    this.syncPhaseSet();
    this.scmPrompts();
  }
  stepU3(dt){
    const P=this.P, L=this.L;
    ESS.Models.stepU3(P,L,this.V,dt,this.modelCtx());
    L.TI314.pv=P.h.ts1+this.noise(0.6);
    L.TI315.pv=P.h.ts2+this.noise(0.6);
    L.AI316.pv=P.h.o2+this.noise(0.05);
    if(P.trips.skin && P.h.ts1<400 && P.h.ts2<400){ P.trips.skin=false; this.clearA('H-310','TUBE SKIN TRIP'); }
  }
  stepU4(dt){ ESS.Models.stepU4(this.P,this.L,this.V,dt,this.modelCtx()); }
  pids(dt){ const ctx=this.pidCtx(); for(const k of this.pidOrder()) ESS.Pid.stepPid(this.L[k],dt,ctx); }
  scan(dt){
    if(dt==null) dt=0.5;
    const L=this.L, E=this.alarmEngine;
    for(const k in L){ const l=L[k];
      if(!l._am) l._am={};
      for(const cond in l.alm){
        const [tp,prio]=l.alm[cond];
        const isLo=cond==='PVLO'||cond==='PVLL';
        const v=cond==='DEVHI'?(l.pv-l.sp):l.pv;
        const memo=l._am[cond]||(l._am[cond]={raw:false,active:false,onT:0,offT:0});
        const act=E.evaluateLimit({pv:v,trip:tp,kind:isLo?'LO':'HI',deadband:this.almDeadband(l),onDelaySec:this.almDelay(l),dt,memo}).active;
        if(act && !l._as[cond]) this.raiseA(l.tag,cond,prio,l.pv,l.eu,l.desc);
        if(!act && l._as[cond]) this.clearA(l.tag,cond,l.pv);
        l._as[cond]=act;
      }
    }
    for(const mt of ['P101','M202']){ const m=L[mt];
      if(m.trip && !m._as.TRIP){ this.raiseA(mt,'TRIP','Urgent',0,'',m.desc+' — '+(m.tripWhy||'TRIP')); m._as.TRIP=true; }
      if(!m.trip && m._as.TRIP){ this.clearA(mt,'TRIP'); m._as.TRIP=false; }
    }
  }
  interlocks(){
    const P=this.P, L=this.L, b=P.b;
    if(L.TI216._as.PVHH){
      if(!this.tadShed) this.latchTadShed();
      this.enforceTadShed();
    } else if(this.tadShed) this.releaseTadShed();
    if(!P.trips.skin && (L.TI314._as.PVHH || L.TI315._as.PVHH)){
      P.trips.skin=true;
      this.raiseA('H-310','TUBE SKIN TRIP','Urgent',Math.max(P.h.ts1,P.h.ts2),'DEG C','TUBE SKIN OVERTEMP — FUEL GAS SHUT OFF');
      this.dTrip('H-310','TUBE SKIN TRIP');
    }
  }
  alarmTick(){ this.logAlarmEvents(this.alarmEngine.tick(this.P.t)); }
  valveWatch(dt){ const map=this.valveMap(); for(const tag in map){ const id=map[tag]; const miss=Math.abs(this.valveTarget(tag,id)-this.V[id].pos)>0.12; this.vLag[id]=miss?(this.vLag[id]||0)+dt:0; } }
  drillWatch(dt){
    const d=this.state.drill; if(!d) return;
    const P=this.P,L=this.L,m=d.m,def=d.def;
    if(!d.injected && P.t>=d.ti && (!def.when || def.when(P))){ d.injected=true; d.tInj=P.t; this.injectFault(def.fault,true); }
    // gated drills (a 'when' condition, e.g. D11 waiting for the FEED phase) count their 12-minute limit from the
    // injection, so arming from IDLE still gives the trainee the full window; ungated drills count from arming as before
    if(!d.injected){ if(def.when && P.t-d.t0>3600000) this.endDrill('INJECTION CONDITION NOT REACHED'); return; }
    if(def.peak){ const v=this.peakOf(def.peak); m.peak=Math.max(m.peak||0,v); }
    if(!m.tAlarm){ const a=this.alarmEngine.active().find(x=>def.rel.includes(x.tag)); if(a) m.tAlarm=a.lastT; }
    if((m.tAlarm||(def.proactive&&m.tAct)) && !m.tStable){
      let ok=false;
      const proactive=!!def.proactive&&!!m.tAct&&(!m.tAlarm||m.tAct<m.tAlarm);
      if(proactive){ ok=!m.trip&&!this.alarmEngine.active().some(x=>def.rel.includes(x.tag)&&!x.shelved)&&def.proactive.check(this); }
      else if(def.stable==='contain'){ ok = L.FIC102.mode==='MAN' && !this.alarmEngine.unacked().some(x=>def.rel.includes(x.tag)); }
      else { ok = m.tAck && !this.alarmEngine.active().some(x=>def.rel.includes(x.tag)&&!x.shelved); }
      d.stableFor = ok ? d.stableFor+dt : 0;
      const stableNeed=proactive?def.proactive.holdSec:60;
      if(d.stableFor>=stableNeed){ m.tStable=P.t; this.endDrill('STABILIZED'); return; }
    }
    if(P.t-(def.when?(d.tInj||d.t0):d.t0)>720000) this.endDrill('TIME LIMIT REACHED');
  }
  aDrillWatch(dt){
    const d=this.P.aDrill; if(!d) return;
    const def=ESS.DrillArch.drillById(d.id); if(!def) return;
    const elapsed=this.P.t-d.startedAt;
    (def.faultTimeline||[]).forEach((step,i)=>{
      if(d.fired.indexOf(i)>=0) return;
      if(elapsed>=step.tSec*1000){
        d.fired.push(i);
        if(this.aDrillFire(step)) d.events.push({seq:d.events.length+1,simTime:this.P.t,actor:'SYSTEM',
          actionType:ESS.DrillArch.ACTION.FAULT_PRESENT,target:d.id,payload:{timelineIndex:i},accepted:true});
      }
    });
  }
  archFaultTick(){
    const FE=ESS.FaultEngine, P=this.P;
    if(P.archPending&&P.archPending.length){
      const due=P.archPending.filter(e=>e.fireAt<=P.t);
      if(due.length){
        P.archPending=P.archPending.filter(e=>e.fireAt>P.t);
        for(const e of due){
          const ok=this.archFireFault(e.faultId,e.targetNodeId,e.mode,e.rampSec,e.durationSec,e.magnitude,P.t);
          this.instrLog('ARCH FAULT ONSET'+(ok?'':' REFUSED (STATE CHANGED SINCE SCHEDULING)')+': '+this.archFaultDisplayName(e.faultId)+' @ '+this.archFaultTargetLabel(e.targetNodeId)+(this.instr.hidden?' (HIDDEN)':''));
        }
      }
    }
    const meta=P.archMeta||{};
    for(const iid in meta){
      const m=meta[iid];
      const inst=(P.archFaults.activeFaults||[]).find(f=>f.instanceId===iid);
      if(!inst){ delete meta[iid]; continue; } // cleared some other way; defensive, never expected
      if(m.mode==='RAMP'&&m.targetMagnitude!=null){
        const elapsed=P.t-m.startedAt, frac=m.rampSec>0?Math.min(1,elapsed/(m.rampSec*1000)):1;
        const v=Math.round(frac*m.targetMagnitude*1000)/1000;
        if(inst.magnitude!==v) inst.magnitude=v;
      }
      if(m.expiresAt!=null&&P.t>=m.expiresAt){
        const r=FE.deactivate(P.archFaults,{faultId:inst.faultId,targetNodeId:inst.targetNodeId});
        if(r.accepted){
          P.archFaults=r.state; delete meta[iid];
          this.archFaultLogPush(inst.faultId,inst.targetNodeId,'CLEAR');
          if(inst.faultId==='REDUNDANCY_SWITCHOVER'){
            const n=this.topo.nodes[inst.targetNodeId];
            this.addEvent('SYSTEM','ARCH',(n&&n.unit?n.unit+' ':'')+'CONTROLLER REDUNDANCY SWITCHOVER COMPLETE — PROCESS CONTROL REMAINED AVAILABLE','','');
          }
          this.instrLog('ARCH FAULT AUTO-CLEARED (DURATION ELAPSED): '+this.archFaultDisplayName(inst.faultId)+' @ '+this.archFaultTargetLabel(inst.targetNodeId)+(this.instr.hidden?' (HIDDEN)':''));
        }
      }
    }
  }
  backtrackTick(){ const I=ESS.Instructor; if(this.P.t-this.instr.lastRingT>=I.RING_MS){ const snap=this.snapshotData(''); if(snap) I.pushRing(this.instr,snap,this.P.t); } }
  replayCheckDone(){ const r=this.instr&&this.instr.replay; if(r&&this.P.t>=r.toT&&r.i>=r.entries.length){ this.instr.replay=null; this.instrLog('REPLAY COMPLETE'); } }
  msgZone(t){ this.setState({msg:t, msgT:this.P.t}); }
  can(need){ if(this._replayApplying) return true; if(this.rank(this.state.sec)>=this.rank(need)) return true; this.msgZone('HIGHER SECURITY LEVEL REQUIRED ('+need+')'); return false; }
  confirmInterlockHold(){
    this.msgZone('SEQUENCE ALREADY HELD — TI216 INTERLOCK, RESUME AFTER IT CLEARS');
    this.addEvent('OPERATOR','SCM202','HOLD CONFIRMED — SEQUENCE ALREADY HELD BY TI216 INTERLOCK','','');
    this.dAct('HOLD','SCM202','',0);
  }
  dAct(type,tag,val,delta){
    const d=this.state.drill; if(!d||!d.injected||d.m.tAct) return;
    const A=d.def.act; let hit=false;
    if(A==='OUTFLOW') hit=(tag==='FIC102'&&(type==='SP'||type==='OP')&&delta>0)||(tag==='LIC101'&&type==='SP'&&delta<0);
    if(A==='CUTFEED') hit=(tag==='FIC102'&&(type==='OP'||type==='SP')&&val<=25);
    if(A==='MAN202') hit=(tag==='TIC202'&&type==='MODE'&&val==='MAN');
    if(A==='AUTO401') hit=(tag==='PIC401'&&type==='MODE'&&val==='AUTO');
    if(A==='START') hit=(tag==='P101'&&type==='START');
    if(A==='CUTMONO') hit=(tag==='FIC211'&&(type==='OP'||type==='SP')&&val<=2)||(tag==='SCM202'&&type==='HOLD');
    if(A==='QUENCH') hit=(tag==='FIC313'&&(type==='SP'||type==='OP')&&delta>0)||(tag==='TIC311'&&type==='SP'&&delta<0);
    if(hit) d.m.tAct=this.P.t;
  }
  taskDone(id){ if(this.tasksDone) this.tasksDone.add(id); }
  syncPhaseSet(){ const k=this.phaseSetKey(); if(k!==this.phaseSet) this.applyPhaseSet(k,false); }
  journal(op,tag,arg,extra){ ESS.Instructor.journalAdd(this.instr,Object.assign({t:this.P.t,op,tag:tag||'',arg:arg==null?'':arg},extra||{})); }
  raiseA(src,cond,prio,val,eu,desc){
    const spec={tag:src,cond,prio,subprio:this.subprioOf(src,cond),val,eu,desc,tripValue:this.tripPointOf(src,cond)};
    const dis=this.assetDisabled(src); if(dis) this.parkDisabled(src,cond,'ASSET:'+dis,spec);
    this.logAlarmEvents(this.alarmEngine.raise(Object.assign({t:this.P.t},spec)));
  }
  clearA(src,cond,val){ this.logAlarmEvents(this.alarmEngine.rtn(src,cond,this.P.t,val)); }
  archSynthEvent(actionType,target,payload){
    if(!this.P.aDrill) return;
    this.P.aDrill.events.push({seq:this.P.aDrill.events.length+1, simTime:this.P.t, actor:'TRAINEE',
      actionType, target, payload:payload==null?null:payload, accepted:true});
  }
  logAlarmEvents(evs){
    let horn=false;
    for(const e of evs){
      const P=e.prio.toUpperCase(), sub=e.journal?'':' '+e.subprio;
      switch(e.type){
        case 'ALARM': this.addEvent('ALARM',e.tag,e.cond+' ALARM '+P+sub+(e.journal?' (JOURNAL)':'')+(e.escalated?' ESCALATED':'')+(e.folded?' REPEAT':''),'',this.fmt(e.val,1)); break;
        case 'RTN': if(e.from!=='OOSRV') this.addEvent('ALARM',e.tag,e.cond+' RETURN TO NORMAL','',this.fmt(e.val,1)); break;
        case 'ACK': this.addEvent('OPERATOR',e.tag,e.cond+' ACKNOWLEDGED',e.from,e.to); break;
        case 'SHELVE': this.addEvent('OPERATOR',e.tag,e.cond+' SHELVED '+Math.round(e.durationMs/60000)+' MIN — '+e.reason,e.from,'SHLVD'); break;
        case 'UNSHELVE': if(e.auto) this.addEvent('SYSTEM',e.tag,e.cond+' SHELVE PERIOD EXPIRED — '+(e.to==='UNACK'?'ALARM RE-ANNUNCIATED':e.to==='DSUPR'?'STILL SUPPRESSED':'ALARM CLEARED'),'SHLVD',e.to); else this.addEvent('OPERATOR',e.tag,e.cond+' UNSHELVED','SHLVD',e.to); break;
        case 'SUPPRESS': this.addEvent('SYSTEM',e.tag,e.cond+' SUPPRESSED BY '+e.suppressedBy+' (DAS)',e.from,'DSUPR'); break;
        case 'UNSUPPRESS': this.addEvent('SYSTEM',e.tag,e.cond+' SUPPRESSION RELEASED'+(e.to==='UNACK'?' — ALARM ANNUNCIATED':''),'DSUPR',e.to); break;
        case 'OOS': this.addEvent('OPERATOR',e.tag,e.cond+' OUT OF SERVICE',e.from,'OOSRV'); break;
        case 'RTS': this.addEvent('OPERATOR',e.tag,e.cond+' RETURNED TO SERVICE'+(e.to==='UNACK'?' — ALARM ANNUNCIATED':''),'OOSRV',e.to); break;
      }
      if(e.to==='UNACK' && e.prio!=='Journal') horn=true;
      const kt=e.type==='ALARM'?'raise':e.type==='RTN'?'rtn':e.type==='ACK'?'ack':null;
      if(kt){ this.alarmLog.push({t:e.t,key:e.key,tag:e.tag,cond:e.cond,prio:e.prio,type:kt}); if(this.alarmLog.length>5000) this.alarmLog.splice(0,this.alarmLog.length-5000); }
    }
    if(horn) this.hornNew();
  }
  dHook(kind,tag){
    const d=this.state.drill; if(!d||!d.injected) return;
    const m=d.m;
    if(d.def.rel.includes(tag)||!tag){
      if(kind==='SIL'&&!m.tSil&&m.tAlarm) m.tSil=this.P.t;
      if(kind==='ACK'&&!m.tAck&&m.tAlarm){ m.tAck=this.P.t; if(d.def.act==='ACK'&&!m.tAct) m.tAct=this.P.t; }
    }
  }
  operName(){ return (this.state.oper||'OPERATOR').trim()||'OPERATOR'; }
  instrNote(txt){ ESS.Instructor.logAdd(this.instr,this.P.t,txt); }
  fmt(v,dec){ return (v==null||isNaN(v))?'—':Number(v).toFixed(dec); }
  phaseSets(){
    const T=(hi,hh)=>({PVHI:[hi,'High'],PVHH:[hh,'Urgent']});
    return {
      IDLE:  {TIC212:T(95,105), TIC213:{PVHI:[115,'High']}, LI215:{PVLO:null,PVHI:[85,'High']}, FIC211:{PVLO:null,PVHI:[8,'High']}, TI216:T(100,106)},
      CHARGE:{TIC212:T(95,105), TIC213:{PVHI:[115,'High']}, LI215:{PVLO:null,PVHI:[85,'High']}, FIC211:{PVLO:null,PVHI:[8,'High']}, TI216:T(100,106)},
      HEATUP:{TIC212:T(95,105), TIC213:{PVHI:[115,'High']}, LI215:{PVLO:[30,'Low'],PVHI:[85,'High']}, FIC211:{PVLO:null,PVHI:[8,'High']}, TI216:T(100,106)},
      FEED:  {TIC212:T(90,102), TIC213:{PVHI:[100,'High']}, LI215:{PVLO:[30,'Low'],PVHI:[85,'High']}, FIC211:{PVLO:[8,'Low'],PVHI:[28,'High']}, TI216:T(100,106)},
      HELD:  {TIC212:T(90,102), TIC213:{PVHI:[100,'High']}, LI215:{PVLO:[30,'Low'],PVHI:[85,'High']}, FIC211:{PVLO:null,PVHI:[8,'High']}, TI216:T(100,106)},
      REACT: {TIC212:T(88,100), TIC213:{PVHI:[100,'High']}, LI215:{PVLO:[60,'Low'],PVHI:[85,'High']}, FIC211:{PVLO:null,PVHI:[8,'High']}, TI216:T(98,105)},
      COOL:  {TIC212:T(95,105), TIC213:{PVHI:[115,'High']}, LI215:{PVLO:[60,'Low'],PVHI:[85,'High']}, FIC211:{PVLO:null,PVHI:[8,'High']}, TI216:T(100,106)},
      DRAIN: {TIC212:T(95,105), TIC213:{PVHI:[115,'High']}, LI215:{PVLO:null,PVHI:[85,'High']}, FIC211:{PVLO:null,PVHI:[8,'High']}, TI216:T(100,106)}
    };
  }
  configChange(src,what,oldV,newV,reason,meta){
    const m=meta||{};
    if(!m.program) this.mocCount=(this.mocCount||0)+1;
    this.addEvent('CONFIG',src,what+(reason?' — '+reason:''),oldV,newV,m.program?{who:m.program,lvl:'PROGRAM'}:undefined);
  }
  applyJournalEntry(e){
    switch(e.op){
      case 'MODE': this.setMode(e.tag,e.arg); break;
      case 'STORE': this.storeEntry(e.tag,e.param,Number(e.arg)); break;
      case 'RAISE': this.raiseLower(e.tag,1); break;
      case 'LOWER': this.raiseLower(e.tag,-1); break;
      case 'START': this.motorCmd(e.tag,true); break;
      case 'STOP': this.motorCmd(e.tag,false); break;
      case 'SEQ': this.seqCmd(e.arg); break;
      case 'ACK': { const a=this.alarmEngine.get(e.arg); if(a) this.ackAlarm(a); break; }
      case 'ACKPAGE': this.ackKeys(e.keys||[]); break;
      case 'SIL': this.silence(); break;
      case 'SHELVE': this.shelveAlarm(e.arg,e.mins,e.reason); break;
      case 'UNSHELVE': this.unshelveAlarm(e.arg); break;
      case 'UPSET': this.setUpset(e.tag,e.arg==='ON'); break;
      // Architecture panel (V3-PLAN S2): only the instructor's SCHEDULING command is
      // journaled (advisory Q3(B)); re-calling setArchFault here recomputes fireAt as
      // P.t (= the entry's own simTime during a deterministic replay) + delaySec, so the
      // automatic onset/ramp/expiry archFaultTick() drives from P.t reproduces itself with
      // no separate journal entry for the firing, same as a drill's armed injection.
      case 'ARCHFAULT': this.setArchFault(e.arg,e.tag,{delaySec:e.delaySec,durationSec:e.durationSec,mode:e.mode,rampSec:e.rampSec,magnitude:e.magnitude}); break;
      case 'ARCHCLEAR': this.clearArchFault(e.arg,e.tag); break;
      case 'MAG': this.setMagnitude(e.tag,e.arg); break;
      case 'VAR': this.setVariable(e.tag,e.arg); break;
      case 'SEED': this.setSeed(e.arg); break;
      case 'DRILL': {
        const d=this.drillDefs().find(x=>x.id===e.tag);
        if(!d){ this.replayRefuse('LEGACY DRILL IS UNKNOWN','journal names unknown legacy drill '+e.tag+'.'); break; }
        if(e.startMode==='CANONICAL'){
          if(!e.preset||typeof e.presetBaseT!=='number'){
            this.instr.replay=null; this.msgZone('REPLAY REFUSED — CANONICAL DRILL BASELINE IS MISSING');
            this.instrNote('REPLAY REFUSED: canonical drill '+e.tag+' has no deterministic preset receipt.'); break;
          }
          if(!this.applyPreset(e.preset,{baseTime:e.presetBaseT,preserveReplay:true})){
            this.instr.replay=null; this.msgZone('REPLAY REFUSED — CANONICAL PRESET IS UNKNOWN');
            this.instrNote('REPLAY REFUSED: canonical drill '+e.tag+' names unknown preset '+e.preset+'.'); break;
          }
          if(this.P.t!==e.t){
            this.instr.replay=null; this.msgZone('REPLAY REFUSED — CANONICAL PRESET TIME DIVERGED');
            this.instrNote('REPLAY REFUSED: canonical drill '+e.tag+' rebuilt at '+this.P.t+' instead of '+e.t+'.'); break;
          }
        }
        this.startDrill(d,{startMode:e.startMode,preset:e.preset,presetBaseT:e.presetBaseT,applySetup:e.startMode==='CANONICAL'});
        break;
      }
      case 'DRILLEND': this.endDrill(e.arg||'ENDED BY INSTRUCTOR'); break;
      // A-drill lane (V3-PLAN S3): same shape as DRILL/DRILLEND above, its own op codes so
      // applyJournalEntry's switch (which silently ignores an op it does not recognise)
      // does not confuse the two lanes.
      case 'ADRILL':
        if(!ESS.DrillArch.drillById(e.tag)){
          this.replayRefuse('ARCHITECTURE DRILL IS UNKNOWN','journal names unknown architecture drill '+e.tag+'.'); break;
        }
        if(e.preset){
          if(typeof e.presetBaseT!=='number'){
            this.instr.replay=null; this.msgZone('REPLAY REFUSED — ARCHITECTURE DRILL BASELINE IS MISSING');
            this.instrNote('REPLAY REFUSED: architecture drill '+e.tag+' has no deterministic preset receipt.'); break;
          }
          if(!this.applyPreset(e.preset,{baseTime:e.presetBaseT,preserveReplay:true})){
            this.instr.replay=null; this.msgZone('REPLAY REFUSED — ARCHITECTURE PRESET IS UNKNOWN');
            this.instrNote('REPLAY REFUSED: architecture drill '+e.tag+' names unknown preset '+e.preset+'.'); break;
          }
          if(this.P.t!==e.t){
            this.instr.replay=null; this.msgZone('REPLAY REFUSED — ARCHITECTURE PRESET TIME DIVERGED');
            this.instrNote('REPLAY REFUSED: architecture drill '+e.tag+' rebuilt at '+this.P.t+' instead of '+e.t+'.'); break;
          }
        }
        this.startADrill(e.tag,{preset:e.preset,presetBaseT:e.presetBaseT}); break;
      case 'ADRILLEND': this.endADrill(e.arg||'ENDED BY INSTRUCTOR'); break;
      // Scoring commands are journaled as op === Dispatch type (TRAINING.MARK_EVIDENCE
      // etc.). Re-dispatch through the same path that retains ActionEvents. During
      // replay, archTrainingCtx.replaying skips Diagnose/inspect gates: those were
      // already passed live. Spectator archMode is debrief (startReplay).
      case 'TRAINING.MARK_EVIDENCE':
      case 'TRAINING.PIN_COMPARE':
      case 'TRAINING.SUBMIT_HYPOTHESIS':
      case 'TRAINING.VERIFY':
      case 'TRAINING.DEBRIEF':
        this.dispatchTraining(e.op, e.tag===''?null:e.tag, (e.arg===''||e.arg==null)?null:e.arg);
        break;
      case 'CTLACTN': this.setCtlAction(e.tag,e.arg); break;
      case 'PVTRACK': this.setPvTrack(e.tag,e.arg==='ON'); break;
      case 'OOS': this.setOos(e.tag,e.cond,e.arg==='ON'); break;
      case 'PRIO': this.setPriority(e.tag,e.cond,e.arg); break;
      case 'COMMENT': this.commentAlarmKey(e.arg,e.text); break;
      case 'CONFIRM': { const m=this.msgs.find(x=>x.confirm&&!x.confirmed&&x.txt===e.arg); if(m) this.confirmMsg(m.id); break; }
      case 'ASSET': this.disableAssetAlarms(e.tag,e.arg==='ON',e.reason||''); break;
      default:
        this.replayRefuse('JOURNAL OPERATION IS UNSUPPORTED','journal operation '+String(e.op)+' has no replay handler.');
        break;
    }
  }
  tripMotor(tag,why){
    const m=this.L[tag]; if(!m||!m.run) return;
    m.run=false; m.trip=true; m.tripWhy=why; m.lock=30;
    this.addEvent('SYSTEM',tag,(tag==='P101'?'PUMP':'AGITATOR')+' TRIPPED — '+why,'RUN','STOP');
  }
  applyShed(l){
    if(l.shed==='NOSHED') return;
    const old=l.mode; l.mode='MAN';
    if(l.shed==='SHEDLOW') l.op=l.opexlo; else if(l.shed==='SHEDHIGH') l.op=l.opexhi; else if(l.shed==='SHEDSAFE') l.op=l.safeop;
    if(old!=='MAN') this.addEvent('SYSTEM',l.tag,'BAD PV — SHED '+l.shed.replace('SHED','')+' · MODE '+old+' → MAN','','');
  }
  dTrip(src,cond){
    const d=this.state.drill; if(!d||!d.injected) return;
    const key=this.tripKeyOf(src), rel=!d.def.trips||!src||d.def.trips.includes(key);
    if(rel){ d.m.trip=true; return; }
    d.m.otherTrips=(d.m.otherTrips||0)+1;
    (d.m.otherTripList=d.m.otherTripList||[]).push(src+(cond?' '+cond:''));
  }
  scmRestoreModes(){
    const f=this.L.FIC211;
    if(f.modeAttr!=='PROGRAM' || f.mode==='AUTO' || f.badPv || this.tadShed) return;
    const r=ESS.Pid.transferMode(f,'AUTO',this.pidCtx());
    if(r.ok) this.addEvent('SYSTEM','SCM202','FIC211 MODE RESTORED BY SEQUENCE ('+r.from+' → AUTO)',r.from,'AUTO');
  }
  scmPrompts(){
    const ph=this.P.b.phase; if(ph===this._lastPhase) return;
    if(this._lastPhase==='CHARGE'&&ph==='HEATUP') this.postMsg('SCM202: CONFIRM CHARGE COMPLETE — LEVEL '+this.fmt(this.P.b.lvl,0)+' %, HEATUP STARTED',{confirm:true,src:'SCM202'});
    if(this._lastPhase==='DRAIN'&&ph==='IDLE') this.postMsg('SCM202: CONFIRM BATCH COMPLETE — REACTOR DRAINED',{confirm:true,src:'SCM202'});
    this._lastPhase=ph;
  }
  pidCtx(){
    if(!this._pidCtx) this._pidCtx={ loops:this.L,
      casMap:{ FIC102:(op)=>op*1.2, TIC202:(op)=>10+0.6*op, TIC213:(op)=>op*1.3 },
      invMap:{ FIC102:(sp)=>sp/1.2, TIC202:(sp)=>(sp-10)/0.6, TIC213:(sp)=>sp/1.3 } };
    if(this._pidCtx.loops!==this.L) this._pidCtx.loops=this.L;
    return this._pidCtx;
  }
  pidOrder(){ return ['LIC101','TIC201','TIC212','FIC102','TIC202','TIC213','TIC301','LIC401','PIC401','FIC211','FIC310','TIC311','FIC313','TIC502','LIC503','LIC504','PIC505']; }
  almDeadband(l){ return l.almDb!=null ? l.almDb : ((l.hi-l.lo)||1)*0.01; }
  almDelay(l){ if(l.almDelay!=null) return l.almDelay; if(l.tag[0]==='F') return 15; if(l.tag[0]==='L') return 60; return 0; }
  latchTadShed(){
    const L=this.L, b=this.P.b, f=L.FIC211, oldMode=f.mode;
    this.tadShed=true;
    const heldNow = b.phase==='FEED' && !b.held;
    if(heldNow) b.held=true;
    this.addEvent('SYSTEM','TI216','ADIABATIC END TEMP URGENT — FIC211 SHED (MODE '+oldMode+' → MAN, MV-211 CLOSED)'+(heldNow?' · SCM202 HOLD':''),'','');
    this.msgZone('TI216 URGENT — MONOMER FEED SHED'+(heldNow?', SEQUENCE HELD':''));
    this.postMsg('INTERLOCK: TI216 URGENT — MONOMER FEED SHED (FIC211 MAN, MV-211 CLOSED)'+(heldNow?', SCM202 HELD':'')+' — confirm',{confirm:true,src:'TI216'});
    this.enforceTadShed();
    this.syncPhaseSet();
  }
  enforceTadShed(){
    const f=this.L.FIC211, b=this.P.b;
    if(f.mode!=='MAN') f.mode='MAN';
    f.op=0; f.I=0; f.sp=0;
    if(b.phase==='FEED' && !b.held){ b.held=true; this.syncPhaseSet(); }
  }
  releaseTadShed(){
    this.tadShed=false;
    this.addEvent('SYSTEM','TI216','ADIABATIC END TEMP URGENT CLEARED — FIC211 SHED RELEASED'+(this.P.b.held?', RESUME PERMITTED':''),'','');
    this.msgZone('TI216 URGENT CLEARED — FIC211 SHED RELEASED');
  }
  valveMap(){ return {FIC102:'FV102',TIC202:'TV202',TIC301:'TV301',PIC401:'PV401',LIC401:'LV401',FIC211:'MV211',TIC213:'JV213',FIC310:'FV310',TIC311:'FV311',FIC313:'QV313',TIC502:'TV502',LIC503:'LV503',LIC504:'WV504',PIC505:'PV505'}; }
  valveTarget(tag,id){ const P=this.P; if(id==='FV102'&&P.trips.rx) return 0; if((id==='MV211'||id==='JV213')&&P.trips.batch) return 0; if(id==='FV311'&&(P.trips.bed||P.trips.skin)) return 0; return this.L[tag].op/100; }
  injectFault(k,on){
    const P=this.P,V=this.V,L=this.L;
    P.faults[k]=on; if(on) P.faultT[k]=P.t; else delete P.faultT[k];
    if(k==='pump'){ if(on){ this.tripMotor('P101','UNCOMMANDED STOP'); P.faults.pump=false; } }
    if(k==='agit'){ if(on){ this.tripMotor('M202','UNCOMMANDED STOP'); P.faults.agit=false; } }
    if(k==='stick') V.TV202.stuck=on;   // the reaction load of the stuck valve lives in the model (PARAMS.U1.stickHeat)
    if(k==='xmtr' && !on){ /* heal handled in step */ }
  }
  endDrill(reason){
    const d=this.state.drill; if(!d) return;
    // every fault a drill can inject is cleared (drillFaults() is derived from the definitions, so a new drill fault
    // cannot be left behind); 'stick' carries a reaction load in the model (PARAMS.U1.stickHeat), so it must go too
    for(const k of this.drillFaults()) this.injectFault(k,false);
    d.reason=reason; d.tEnd=this.P.t;
    if(reason==='ENDED BY INSTRUCTOR') this.journal('DRILLEND',d.def.id,reason,{instr:true});   // automatic ends are reproduced by the replay itself
    this.setState({drill:null, dlg:{type:'debrief',drill:d}, debAns:-1});
    this.instrNote('DRILL '+d.def.id+' ENDED — '+reason);
    if(!this.instr.hidden) this.postMsg('INSTRUCTOR: drill '+d.def.id+' ended — '+reason,{confirm:true,src:'INSTR'});   // hidden: the trainee sees only the debrief
  }
  peakOf(k){ const P=this.P; return ({tankL:P.tankL,rT:P.rT,drumP:P.drumP,T212:P.b.T,bed:P.h.bed,hw:P.s?P.s.hw:0,h2:P.s?P.s.h2:0,pres:P.s?P.s.pres:0})[k]??0; }
  aDrillFire(step){
    let accepted=true;
    (step.targets||[]).forEach(target=>{
      const k=this.aDrillReservedUpsetKey(step.faultId,target);
      if(k){ this.injectFault(k,true); this.archFaultLogPush(step.faultId,target,'ACTIVE'); return; }
      const def=ESS.FaultEngine.getFaultDef(step.faultId);
      // Magnitude-bearing engine faults (BIASED_MEASUREMENT, NOISY_MEASUREMENT) refuse
      // activate() without an explicit number or a seeded rand. A-drills never hand the
      // live generator to the engine (that would shift every later noise sample). Prefer
      // the step's own magnitude; otherwise the range midpoint, same as archStageSelect.
      let mag=step.magnitude;
      if(mag==null){
        if(def&&def.magnitudeRange){
          const r=def.magnitudeRange;
          mag=Math.round(((r.min+r.max)/2)/r.step)*r.step;
        }
      }
      const durationSec=def&&def.activation&&def.activation.defaultDurationMs
        ?def.activation.defaultDurationMs/1000:null;
      if(!this.archFireFault(step.faultId,target,'STEP',0,durationSec,mag==null?null:mag,this.P.t,step.direction)) accepted=false;
      else {
        const n=this.topo.nodes[target];
        if(step.faultId==='OPEN_INPUT_BAD_QUALITY'){
          (n&&n.pointRefs||[]).forEach(tag=>{ const l=this.L[tag]; if(l){ l.badPv=true; this.applyShed(l); } });
        }
        if(step.faultId==='ASSISTANT_LOSS') this.coachSetUnavailable();
        if(step.faultId==='REDUNDANCY_SWITCHOVER'){
          this.addEvent('SYSTEM','ARCH',(n&&n.unit?n.unit+' ':'')+'CONTROLLER REDUNDANCY SWITCHOVER — STANDBY TAKEOVER IN PROGRESS','','');
        }
      }
    });
    // Sustained faults remain in the engine, so their current projection is the cue.
    // Retaining that onset snapshot made later model-backed changes contradictory (A1
    // kept its initial GOOD-quality prose beside the later BADPV). Only transient A4
    // needs a retained cue after its 15-second engine instance clears itself.
    const firedDef=ESS.FaultEngine.getFaultDef(step.faultId);
    if(accepted&&this.P.aDrill&&firedDef&&firedDef.activation.style==='TRANSIENT'){
      this.P.aDrill.cues=this.archTraineeSymptoms().observations.map(o=>({scope:o.scope,text:o.text,source:'DRILL_CUE'}));
    }
    return accepted;
  }
  archFireFault(faultId,targetNodeId,mode,rampSec,durationSec,magnitude,simTimeNow,direction){
    const FE=ESS.FaultEngine, def=FE.getFaultDef(faultId);
    const startMag=(mode==='RAMP'&&def&&def.magnitudeRange)?0:magnitude;
    const r=FE.activate(this.P.archFaults,this.topo,{faultId,targetNodeId,simTime:simTimeNow,
      magnitude:startMag==null?undefined:startMag,direction:direction==null?undefined:direction});
    if(!r.accepted) return false;
    this.P.archFaults=r.state;
    this.P.archMeta[r.instance.instanceId]={mode,rampSec:mode==='RAMP'?rampSec:0,targetMagnitude:magnitude,
      startedAt:simTimeNow,expiresAt:durationSec?simTimeNow+durationSec*1000:null};
    this.archFaultLogPush(faultId,targetNodeId,'ACTIVE');
    return true;
  }
  instrLog(txt){
    ESS.Instructor.logAdd(this.instr,this.P.t,txt);
    if(!this.instr.hidden) this.addEvent('SYSTEM','INSTR',txt,'','');
  }
  archFaultDisplayName(faultId){
    return String(faultId||'').replace(/_/g,' ');
  }
  archFaultTargetLabel(targetNodeId){
    const n=this.topo&&this.topo.nodes[targetNodeId];
    return n?n.label:targetNodeId;
  }
  archFaultLogPush(faultId,targetNodeId,phase){
    if(!this.P.archFaultLog) this.P.archFaultLog=[];
    this.P.archFaultLog.push({t:this.P.t, faultId:faultId, targetNodeId:targetNodeId, phase:phase||'ACTIVE'});
  }
  snapshotData(name,wall){
    const r=this.rand;
    try{
      return ESS.Instructor.makeSnapshot({t:this.P.t,wall:wall||0,P:this.P,L:this.L,V:this.V,alarms:this.alarmEngine.snapshot(),
        eventsCount:this.events.length,journalSeq:this.instr.seq,tadShed:this.tadShed,phaseSet:this.phaseSet,disabledAssets:[...this.disabledAssets],
        seed:(r&&r.seed)||this.seed,randState:(r&&r.getState)?r.getState():null,randState4:(this.rand4&&this.rand4.getState)?this.rand4.getState():null,drill:this.drillData()},name);
    }catch(err){ this.instrNote('SNAPSHOT REFUSED — '+String(err.message).toUpperCase()); this.msgZone('SNAPSHOT REFUSED: PROCESS STATE IS NOT FINITE'); return null; }
  }
  rank(l){ return {VIEW:0,OPER:1,SUPV:2,ENGR:3,MNGR:4}[l]??0; }
  subprioOf(tag,cond){ const l=this.L[tag]; const tup=l&&l.alm&&l.alm[cond]; return (tup&&tup[2]!=null)?tup[2]:this.subprioDefault(cond); }
  tripPointOf(tag,cond){ const l=this.L[tag]; const tup=l&&l.alm&&l.alm[cond]; if(tup) return tup[0]; const eq=ESS.AlarmHelp.EQUIPMENT_TRIPS[tag+'.'+cond]; return eq?eq.value:undefined; }
  assetDisabled(tag){ for(const id of this.disabledAssets) if(this.assetMatch(id,tag)) return id; return null; }
  parkDisabled(tag,cond,by,spec){
    const E=this.alarmEngine, l=this.L[tag];
    if(!spec) spec=l&&l.alm[cond]?{tag,cond,prio:l.alm[cond][1],subprio:this.subprioOf(tag,cond),eu:l.eu,desc:l.desc,tripValue:l.alm[cond][0],val:l.pv}:undefined;
    const evs=E.oos(tag+'.'+cond,this.P.t,spec);
    const r=E.get(tag+'.'+cond); if(r) r.disabledBy=by;
    evs.forEach(e=>{ if(e.type==='OOS') this.addEvent('SYSTEM',e.tag,e.cond+' DISABLED — '+by,e.from,'DISABLED'); });
  }
  hornNew(){ this.setState({silenced:false}); }
  setMode(tag,m){
    const l=this.L[tag];
    if(!this.can('OPER')) return;
    if(!this.operatorMayWrite(tag,'MODE')) return;
    if(l.mode===m) return;
    const r=ESS.Pid.transferMode(l,m,this.pidCtx());   // bumpless: integrator re-initialised so the first output equals the current OP
    if(!r.ok){ this.msgZone(r.reason); return; }
    this.addEvent('OPERATOR',tag,'MODE CHANGE','',''); this.events[0].oldV=r.from; this.events[0].newV=m;
    this.dAct('MODE',tag,m,0);
    this.journal('MODE',tag,m);
    this.taskDone('ctl.mode');
    // Safety gate live (V3-PLAN section 6, DO item 4): only reached once transferMode has
    // actually accepted the change (the two early returns above -- security level, program
    // ownership, and `!r.ok` -- all exit before this line), so a refused MODE change never
    // produces an event to score against. A1/A4/A6/A8/A9/A10/A11's gates are all MODE.SET.
    this.archSynthEvent('MODE.SET','CM-'+l.cm,{mode:m});
  }
  storeEntry(tag,param,v){
    const l=this.L[tag]; if(!l) return true;
    if((param==='SP'||param==='OP') && !this.operatorMayWrite(tag,param)) return true;
    const done=(oldV,apply,evName)=>{ apply(); this.addEvent('OPERATOR',tag,evName+' CHANGE','',''); this.events[0].oldV=this.fmt(oldV,2); this.events[0].newV=this.fmt(v,2); this.journal('STORE',tag,this.fmt(v,3),{param}); };
    // configuration stores are MOC entries (CONFIG event with old / new, name, level, reason); tuning and trip points are signed
    const cfg=(oldV,apply,what,reason)=>{ apply(); this.configChange(tag,what+' CHANGE',this.fmt(oldV,2),this.fmt(v,2),reason||''); this.journal('STORE',tag,this.fmt(v,3),{param}); };
    if(param==='SP'){ if(v>l.sphilm||v<l.splolm){ this.msgZone('ENTRY REJECTED — SP LIMITS '+this.fmt(l.splolm,l.dec)+' TO '+this.fmt(l.sphilm,l.dec)); return false; } const o=l.sp; done(o,()=>{l.sp=v;},'SP'); this.dAct('SP',tag,v,v-o); this.taskDone('ctl.sp'); return true; }
    if(param==='OP'){ if(v>l.ophilm||v<l.oplolm){ this.msgZone('ENTRY REJECTED — OP LIMITS '+this.fmt(l.oplolm,1)+' TO '+this.fmt(l.ophilm,1)); return false; } const o=l.op; done(o,()=>{l.op=v;l.I=v;},'OP'); this.dAct('OP',tag,v,v-o); this.taskDone('ctl.op');
      if(tag==='TIC202'&&this.V.TV202.stuck&&Math.abs(v-o)>=8){ this.V.TV202.stuck=false; this.P.faults.stick=false; this.addEvent('SYSTEM','TIC202','TV-202 FREED BY MANUAL STROKE','',''); this.msgZone('TV-202 RESPONDING AGAIN'); } return true; }
    if(param.startsWith('TP:')){ const c=param.slice(3); if(!l.alm[c]) return true; const o=l.alm[c][0]; if(o===v) return true; this.withSignature('TRIP POINT '+tag+' '+c+' '+this.fmt(o,l.dec)+' → '+this.fmt(v,l.dec),'ENGR',(reason)=>{ cfg(o,()=>{l.alm[c][0]=v;},c+' TRIP POINT',reason); this.taskDone('ctl.trip'); }); return true; }
    if(param==='TGTHI'||param==='TGTLO'){ const b=this.limitBand(l); const lo=param==='TGTLO'?v:b.tgtLo, hi=param==='TGTHI'?v:b.tgtHi; const o=param==='TGTLO'?b.tgtLo:b.tgtHi; if(!this.setTargetBand(l,lo,hi)) return false; cfg(o,()=>{},param==='TGTLO'?'TARGET LOW':'TARGET HIGH'); return true; }
    if(param==='ALMDB'){ if(!(v>=0)){ this.msgZone('ENTRY REJECTED — DEADBAND MUST BE 0 OR MORE'); return false; } const o=this.almDeadband(l); cfg(o,()=>{ l.almDb=v; this.resetLimitTimers(l); },'ALARM DEADBAND'); return true; }
    if(param==='ALMDELAY'){ if(!(v>=0)){ this.msgZone('ENTRY REJECTED — ON-DELAY MUST BE 0 OR MORE'); return false; } const o=this.almDelay(l); cfg(o,()=>{ l.almDelay=v; this.resetLimitTimers(l); },'ALARM ON-DELAY'); return true; }
    const key=param.toLowerCase(); const map={k:'K',t1:'T1',t2:'T2',sphilm:'SPHILM',splolm:'SPLOLM',ophilm:'OPHILM',oplolm:'OPLOLM',safeop:'SAFEOP'};
    const o=l[key]??l[param]; if(o===v) return true;
    const apply=()=>{ if(key==='k')l.K=v; else if(key==='t1')l.T1=v; else if(key==='t2')l.T2=v; else l[key]=v; };
    if(key==='k'||key==='t1'||key==='t2'){ this.withSignature('PID TUNING '+tag+' '+map[key]+' '+this.fmt(o,2)+' → '+this.fmt(v,2),'ENGR',(reason)=>{ cfg(o,apply,map[key],reason); this.taskDone('ctl.tune'); }); return true; }
    cfg(o,apply,map[key]||param);
    return true;
  }
  raiseLower(tag,dir){
    const l=this.L[tag]; if(!this.can('OPER')) return;
    const p = l.mode==='MAN'?'OP':(l.mode==='AUTO'?'SP':null);
    if(!p){ this.msgZone('CAS MODE — RAISE/LOWER NOT PERMITTED ON SP'); return; }
    if(!this.operatorMayWrite(tag,p)) return;
    if(p==='SP'){ const step=(l.hi-l.lo)/100; const o=l.sp; const nv=Math.max(l.splolm,Math.min(l.sphilm,o+dir*step)); l.sp=nv; this.addEvent('OPERATOR',tag,'SP CHANGE','',''); this.events[0].oldV=this.fmt(o,l.dec); this.events[0].newV=this.fmt(nv,l.dec); this.dAct('SP',tag,nv,nv-o); }
    else { const o=l.op; const nv=Math.max(l.oplolm,Math.min(l.ophilm,o+dir)); l.op=nv; l.I=nv; this.addEvent('OPERATOR',tag,'OP CHANGE','',''); this.events[0].oldV=this.fmt(o,1); this.events[0].newV=this.fmt(nv,1); this.dAct('OP',tag,nv,nv-o); }
    this.journal(dir>0?'RAISE':'LOWER',tag);
    this.taskDone('ctl.raiselower');
  }
  ackKeys(keys){
    let n=0; const done=[];
    for(const key of keys){ const a=this.alarmEngine.get(key); if(!a||a.ack) continue; const evs=this.alarmEngine.ack(a,this.P.t); if(evs.length){ n++; done.push(key); this.logAlarmEvents(evs); this.dHook('ACK',a.tag); } }
    this.addEvent('OPERATOR','STN01','PAGE ACKNOWLEDGE ('+n+' ALARMS)','','');
    this.journal('ACKPAGE','','',{keys:done});
    if(n) this.taskDone('alm.ackpage');
  }
  silence(){ this.setState({silenced:true}); this.addEvent('OPERATOR','STN01','ALARMS SILENCED','',''); this.dHook('SIL',null); this.journal('SIL'); this.taskDone('alm.silence'); }
  shelveAlarm(key,mins,reason){
    const a=this.alarmEngine.get(key); if(!a) return false;
    mins=Math.max(1,Math.min(60,Number(mins)));
    const evs=this.alarmEngine.shelve(a,{reason,durationMs:mins*60000,t:this.P.t});
    if(!evs.length){ this.msgZone('ALARM CANNOT BE SHELVED IN STATE '+a.state); return false; }
    this.logAlarmEvents(evs);
    this.postMsg('ALARM SHELVED '+mins+' MIN: '+a.tag+' '+a.cond+' — '+reason);
    this.journal('SHELVE',a.tag,a.key,{mins,reason});
    this.taskDone('alm.shelve');
    return true;
  }
  unshelveAlarm(key){ const a=this.alarmEngine.get(key); if(!a||!a.shelved) return; this.logAlarmEvents(this.alarmEngine.unshelve(a,this.P.t,false)); this.journal('UNSHELVE',a.tag,a.key); this.taskDone('alm.unshelve'); }
  setSeed(n){
    const seed=(Number(n)>>>0)||ESS.Instructor.DEFAULT_SEED;
    this.instr.seed=seed; this.seed=seed; this.rand=ESS.Models.createRand(seed); this.rand4=ESS.Models.createRand((seed ^ 0x5eed4) >>> 0);
    this.instrNote('RANDOM SEED SET '+seed);
    this.journal('SEED','',seed,{instr:true});
    this.setState({instrSeedTxt:''});
  }
  drillDefs(){
    return [
      {id:'D1',name:'Flow transmitter failure (FIC102)',basePreset:'U1_SS',fault:'xmtr',rel:['FIC102'],act:'ACK',stable:'contain',
       q:'FIC102 PV went BAD. What did the PID do (shed option SHEDHOLD)?',opts:['Shed to MAN and held OP at the last good value','Drove OP to SAFEOP and stayed in AUTO','Closed the valve immediately','Kept controlling on the bad PV'],a:0},
      {id:'D2',name:'Feed surge — tank level rising',basePreset:'U1_SS',fault:'surge',rel:['LIC101','FIC102','TK-101'],trips:['ovf','rx'],act:'OUTFLOW',stable:'alarms',peak:'tankL',
       q:'Best first control action for rising level?',opts:['Increase outlet flow (raise FIC102/LIC101 output)','Shelve the level alarms','Stop the feed pump','Lower the outlet flow setpoint'],a:0},
      {id:'D3',name:'Feed pump trip',basePreset:'U1_SS',fault:'pump',rel:['P101','FIC102','LIC101','TK-101'],act:'START',stable:'alarms',
       q:'Correct restart sequence?',opts:['FIC102 to MAN / OP 0, START P-101 after lockout, restore AUTO','Immediately drive FIC102 OP to 100%','Repeatedly press START until it holds','Shelve the TRIP alarm and wait'],a:0},
      // D4: the reactor is the drill's equipment (trips:['rx']); LIC101 is related because cutting feed fills TK-101 and
      // the trainee must restore feed before the tank reaches high level — a TK-101 trip is an 'other equipment' deduction
      {id:'D4',name:'Cooling water loss — exotherm',basePreset:'U1_SS',fault:'cool',rel:['TIC201','TIC202','R-201','LIC101'],trips:['rx'],act:'CUTFEED',stable:'alarms',peak:'rT',
       debrief:'Expected response: cut reactor feed (FIC102 to MAN, output about 20 %) to arrest the exotherm; when TIC201 is falling and before TK-101 reaches high level (LIC101 PVHI 80 %), restore feed — FIC102 output back toward 60 %, or return it to CAS so LIC101 draws the tank down — and confirm R-201 is cooling on TG01. Feed left cut fills the tank; feed restored while R-201 is still climbing re-lights the exotherm.',
       q:'Reactor temperature climbing with no cooling. Best action?',opts:['Cut feed (FIC102 to MAN, OP low) to arrest the exotherm, then restore feed before TK-101 reaches high level and confirm R-201 is cooling','Raise TIC201 SP to reduce the error','Put TIC202 in MAN with OP 0','Acknowledge the alarms and monitor'],a:0},
      {id:'D6',name:'Stuck coolant valve (stiction)',basePreset:'U1_SS',fault:'stick',rel:['TIC202','TIC201'],trips:['rx'],act:'MAN202',stable:'alarms',peak:'rT',
       q:'TIC202 OP moves but jacket temperature does not. Root cause?',opts:['Control valve TV-202 stuck (stiction)','Transmitter failure on the jacket RTD','Wrong control action configured','Cascade initialization error'],a:0},
      {id:'D9',name:'Flash drum pressure high',basePreset:'U1_SS',fault:'vap',rel:['PIC401','V-401'],trips:['psv'],act:'AUTO401',stable:'alarms',peak:'drumP',
       proactive:{holdSec:180,check:(c)=>c.L.PIC401.mode==='AUTO'&&c.P.drumP<780},
       setup:(c)=>{ const l=c.L.PIC401; if(l.mode!=='MAN'){ ESS.Pid.transferMode(l,'MAN',c.pidCtx()); c.addEvent('SYSTEM','PIC401','MODE LEFT IN MAN BY PREVIOUS SHIFT'+(c.instr.hidden?'':' (DRILL SETUP)'),'AUTO','MAN'); } },
       q:'PIC401 did not respond to rising pressure. Why?',opts:['It had been left in MAN — the vent never moved','The vent valve was stuck','The setpoint was too high','Transmitter drift'],a:0},
      {id:'D11',name:'Agitator trip during semi-batch feed (Unit 02)',basePreset:'U2_FEED',fault:'agit',needBatch:true,when:(P)=>P.b.phase==='FEED'&&P.b.Cm>8,rel:['M202','TIC212','R-202','FIC211','SCM202'],trips:['batch'],act:'CUTMONO',stable:'alarms',peak:'T212',
       q:'The agitator tripped during monomer feed. Why is restarting it later dangerous?',opts:['Accumulated monomer reacts at once when mixing resumes — stop feed and max cooling before restart','It will trip the breaker again','The jacket cannot heat without agitation','It pulls a vacuum in the reactor'],a:0},
      {id:'D12',name:'Catalyst activity surge — bed overtemp (Unit 03)',basePreset:'U3_HILOAD',fault:'bedact',rel:['TI312','TIC311','FIC313','R-310'],trips:['bed'],act:'QUENCH',stable:'alarms',peak:'bed',
       proactive:{holdSec:300,check:(c)=>c.P.h.bed<440&&(c.L.FIC313.sp>=20||c.L.TIC311.sp<=300)},
       q:'Bed temperature climbing at constant preheat. Correct response?',opts:['Raise quench flow and/or lower the preheater SP — the fuel trips at 480 °C','Raise the preheater SP to burn off deposits','Put FIC313 in MAN and close the quench','Increase feed to sweep the heat out'],a:0}
    ];
  }
  replayRefuse(reason,note){
    this.instr.replay=null;
    this.msgZone('REPLAY REFUSED — '+reason);
    this.instrNote('REPLAY REFUSED: '+note);
  }
  applyPreset(id,opts){
    const p=ESS.Instructor.presets().find(x=>x.id===id); if(!p) return;
    const o=opts||{}, replay=o.preserveReplay?this.instr.replay:null;
    this.instr.replay=null;
    if(this.state.drill) this.setState({drill:null});   // an armed drill must not inject during the run-forward below
    this.initSim(typeof o.baseTime==='number'?o.baseTime:undefined);
    if(p.set&&p.set.L) for(const tag in p.set.L) Object.assign(this.L[tag],p.set.L[tag]);
    if(p.set&&p.set.env) Object.assign(this.P.env,p.set.env);
    if(p.batch){ this.seqCmd('START',true); const max=(p.maxRun||3600)*2; for(let i=0;i<max;i++){ this.step(0.5); if(this.P.b.phase===p.waitPhase&&(p.waitLvl==null||this.P.b.lvl>=p.waitLvl)) break; } }
    for(let i=0;i<(p.run||0)*2;i++) this.step(0.5);
    const snap=this.snapshotData('IC '+p.label); if(!snap) return;
    this.restoreSnapshot(snap,'INITIAL CONDITION LOADED: '+p.label);
    this.addEvent('SYSTEM','STN01','INITIAL CONDITION LOADED — '+p.label.toUpperCase(),'','');
    this.setState({fps:[],unit:p.id.slice(0,2)});
    if(o.preserveReplay) this.instr.replay=replay;
    return true;
  }
  startDrill(d,opts){
    if(this.state.drill){ this.msgZone('DRILL ALREADY ACTIVE'); return; }
    const o=opts||{}, startMode=o.startMode==='CANONICAL'?'CANONICAL':'LIVE STATE';
    const preset=startMode==='CANONICAL'?(o.preset||d.basePreset||null):null;
    if(startMode==='CANONICAL'&&d.needBatch&&this.P.b.phase==='IDLE') this.seqCmd('START',true);
    // LIVE STATE is literal: arming cannot secretly manufacture a precondition.
    // Defined setup belongs only to a canonical start and is replayed with it.
    if(o.applySetup&&d.setup) d.setup(this);
    if(!this.dofPreflight('DRILL '+d.id)) return;   // BEFORE the rand() draw below -- see dofPreflight
    const delay=8000+this.modelCtx().rand()*7000;
    this.setState({drill:{def:d,t0:this.P.t,ti:this.P.t+delay,injected:false,m:{},stableFor:0,startMode,preset},dlg:null});
    this.journal('DRILL',d.id,'',{instr:true,startMode,preset,presetBaseT:o.presetBaseT});
    this.instrNote('DRILL '+d.id+' ARMED — '+d.name.toUpperCase()+' — '+startMode+(preset?' '+preset:'')+' — INJECTION AT '+this.fT(this.P.t+delay));
    if(!this.instr.hidden) this.postMsg('INSTRUCTOR: drill '+d.id+' armed — confirm you are at the console',{confirm:true,src:'INSTR'});
  }
  startADrill(id,opts){
    const def=ESS.DrillArch.drillById(id);
    if(!def){ this.msgZone('UNKNOWN ARCHITECTURE DRILL '+id); return; }
    if(this.state.drill){ this.msgZone('A DRILL IS ALREADY ACTIVE — END IT FIRST'); return; }
    if(this.P.aDrill){ this.msgZone('AN ARCHITECTURE DRILL IS ALREADY ACTIVE'); return; }
    const o=opts||{};
    if(!this.dofPreflight('A-DRILL '+id)) return;   // see dofPreflight; startADrill draws no randomness
    this.P.aDrill={id,startedAt:this.P.t,fired:[],events:[],cues:[]};
    this.journal('ADRILL',id,'',{instr:true,preset:o.preset||null,presetBaseT:o.presetBaseT});
    this.instrNote('A-DRILL '+id+' ARMED — '+def.title.toUpperCase());
    if(!this.instr.hidden) this.postMsg('INSTRUCTOR: architecture drill '+id+' armed',{confirm:true,src:'INSTR'});
    this.setState(s=>({tk:s.tk+1}));
  }
  endADrill(reason){
    const d=this.P.aDrill; if(!d) return null;
    const def=ESS.DrillArch.drillById(d.id);
    const recoverCoach=this.coachUnavailable();
    if(def) (def.faultTimeline||[]).forEach(step=>this.aDrillClear(step));
    const score=ESS.DrillArch.scoreDrill(d.id,d.events.slice());
    const rec=this.aDrillRecordShape(score);
    this._lastADrill=rec;
    if(!this._replayApplying){
      ESS.Training.addRecord(this.trainingRecords,ESS.Training.recordFor(this.operName(),d.id,def?def.traineeTitle:d.id,rec,this.P.t,reason),20);
      this.taskDone('abn.drill'); if(rec.pass) this.taskDone('abn.pass');
    }
    this.journal('ADRILLEND',d.id,reason,{instr:true});
    this.P.aDrill=null;
    if(recoverCoach){
      this.setState({coachLive:false,coachStatus:'OFFLINE',coachMood:'off',coachThink:'',
        coachText:'PIP is part of Launch Station.command. LIVE DIAGNOSIS below still works.'});
      this.coachPing();
    }
    this.instrNote('A-DRILL '+d.id+' ENDED — '+reason+' — SCORE '+score.score+'/100 — '+(score.pass?'PASS':'NOT PASSED'));
    if(!this.instr.hidden) this.postMsg('INSTRUCTOR: architecture drill '+d.id+' ended — score '+score.score+'/100',{confirm:true,src:'INSTR'});
    this.setState(s=>({tk:s.tk+1}));
    return score;
  }
  dispatchTraining(type,target,payload){
    const ev=this.dispatcher.dispatch(this.archTrainingCtx(),
      {type,actor:'TRAINEE',target:target==null?null:target,payload:payload==null?null:payload,simTime:this.P.t});
    this.archRetainEvent(ev);
    return ev;
  }
  setCtlAction(tag,act){
    const l=this.L[tag]; if(!l||l.kind!=='pid') return;
    if(!this.can('ENGR')) return;
    act=act==='DIR'?'DIR':'REV'; if(l.act===act) return;
    const o=l.act; l.act=act;
    this.configChange(tag,'CONTROL ACTION CHANGE',o,act,'');
    this.journal('CTLACTN',tag,act);
  }
  setPvTrack(tag,on){
    const l=this.L[tag]; if(!l||l.kind!=='pid') return;
    if(!this.can('ENGR')) return;
    if(!!l.pvtrack===!!on) return;
    l.pvtrack=!!on;
    this.configChange(tag,'PV TRACKING CHANGE',on?'OFF':'ON',on?'ON':'OFF','');
    this.journal('PVTRACK',tag,on?'ON':'OFF');
    this.taskDone('ctl.pvtrack');
  }
  setOos(tag,cond,on){
    if(!this.can('ENGR')) return;
    const l=this.L[tag]; if(!l||!l.alm[cond]) return;
    const key=tag+'.'+cond;
    // Safety gate live (V3-PLAN section 6, DO item 4): a POINT.SUPPRESS ActionEvent is
    // synthesized only on the path that actually mutated state -- withSignature's fn only
    // runs once a real signature has been accepted, so a refused/pending signature never
    // reaches archSynthEvent, which is exactly the outcome-based contract A2/A3's gates
    // depend on (matchAction already drops accepted:false; refusals here never even
    // produce an entry to drop).
    if(on){ this.withSignature('ALARM OUT OF SERVICE '+key,'ENGR',(reason)=>{ if(this.isOos(tag,cond)) return; this.logAlarmEvents(this.alarmEngine.oos(key,this.P.t,{tag,cond,prio:l.alm[cond][1],subprio:this.subprioOf(tag,cond),eu:l.eu,desc:l.desc,tripValue:l.alm[cond][0],val:l.pv})); this.configChange(tag,cond+' SERVICE STATE','IN SERVICE','OUT OF SERVICE',reason); this.journal('OOS',tag,'ON',{cond}); this.taskDone('alm.oos'); this.archSynthEvent('POINT.SUPPRESS','CM-'+l.cm,{arg:'ON'}); }); return; }
    const r=this.alarmEngine.get(key); if(r&&r.disabledBy){ this.msgZone('CONDITION DISABLED BY '+r.disabledBy+' — RE-ENABLE THE ASSET'); return; }
    const evs=this.alarmEngine.rts(key,this.P.t); if(!evs.length) return;
    this.logAlarmEvents(evs);
    this.configChange(tag,cond+' SERVICE STATE','OUT OF SERVICE','IN SERVICE','');
    this.journal('OOS',tag,'OFF',{cond});
    this.taskDone('alm.oos');
    this.archSynthEvent('POINT.SUPPRESS','CM-'+l.cm,{arg:'OFF'});
  }
  setPriority(tag,cond,nv){
    const l=this.L[tag]; if(!l||!l.alm[cond]) return;
    if(!this.can('ENGR')) return;
    const o=l.alm[cond][1]; if(o===nv) return;
    this.withSignature('ALARM PRIORITY '+tag+' '+cond+' '+o.toUpperCase()+' → '+nv.toUpperCase(),'ENGR',(reason)=>{ if(!l.alm[cond]) return; l.alm[cond][1]=nv; this.configChange(tag,cond+' PRIORITY CHANGE',o,nv,reason); this.journal('PRIO',tag,nv,{cond}); });
  }
  commentAlarmKey(key,text){
    const a=this.alarmEngine.get(key); if(!a){ this.msgZone('NO ALARM SELECTED'); return; }
    if(!this.can('OPER')) return;
    text=(text==null?'':String(text)).trim();
    if(!text){ this.msgZone('COMMENT TEXT REQUIRED'); return; }
    const old=a.comment||'';
    this.alarmEngine.comment(a,text);
    this.addEvent('OPERATOR',a.tag,a.cond+' COMMENT: '+text,old,text);
    this.postMsg('ALARM COMMENT '+a.tag+' '+a.cond+': '+text);
    this.journal('COMMENT',a.tag,a.key,{text});
    this.taskDone('alm.comment');
    this.setState({dlg:null,dlgReason:''});
  }
  disableAssetAlarms(id,on,reason){
    if(id==='PLANT'||!this.assetTree().some(n=>n.id===id)){ this.msgZone('SELECT A UNIT OR EQUIPMENT ASSET'); return false; }
    const E=this.alarmEngine, by='ASSET:'+id;
    if(on){
      if(this.disabledAssets.has(id)) return false;
      this.disabledAssets.add(id);
      for(const tag of this.assetTags(id)){ const l=this.L[tag]; if(!l) continue; for(const c in l.alm) this.parkDisabled(tag,c,by); }
      for(const r of E.list()) if(this.assetMatch(id,r.tag)&&r.state!=='OOSRV') this.parkDisabled(r.tag,r.cond,by);
      this.configChange(id,'ALARMS DISABLED FOR ASSET',(this.disabledAssets.size-1)+' DISABLED',this.disabledAssets.size+' DISABLED',reason);
      this.postMsg('ALARMS DISABLED FOR '+id+' BY '+this.operName()+(reason?' — '+reason:''));
    } else {
      if(!this.disabledAssets.has(id)) return false;
      this.disabledAssets.delete(id);
      for(const r of E.list()) if(r.disabledBy===by){ r.disabledBy=''; this.logAlarmEvents(E.rts(r,this.P.t)); }
      this.configChange(id,'ALARMS RE-ENABLED FOR ASSET',(this.disabledAssets.size+1)+' DISABLED',this.disabledAssets.size+' DISABLED',reason);
      this.postMsg('ALARMS RE-ENABLED FOR '+id+' BY '+this.operName());
    }
    this.journal('ASSET',id,on?'ON':'OFF',{reason});
    this.taskDone('abn.disable');
    // Safety gate live (V3-PLAN section 6, DO item 4): OUTCOME-BASED, so a synthesized
    // ActionEvent is appended only on this ACCEPTED path -- every early `return false`
    // above (bad asset id, already in the requested state) never reaches here, exactly
    // the refusal-is-never-retained shape the gate needs. Never journaled a second time:
    // the ASSET op above already journaled once; archSynthEvent only appends to the
    // retained A-drill scoring array, nothing replay-visible. Maps every point under the
    // asset to its control-module node so a POINT.SUPPRESS gate keyed on a specific CM
    // (e.g. A7's) can still be tripped by disabling the whole asset it belongs to.
    for(const tag of this.assetTags(id)){ const l=this.L[tag]; if(l&&l.cm) this.archSynthEvent('POINT.SUPPRESS','CM-'+l.cm,{arg:on?'ON':'OFF'}); }
    return true;
  }
  tripKeyOf(src){ return ({'TK-101':'ovf','R-201':'rx','V-401':'psv','R-202':'batch','R-310':'bed','H-310':'skin'})[src]||src; }
  postMsg(txt,opts){
    this.msgs.unshift(ESS.Training.message(this.P?this.P.t:0,txt,opts||{}));
    // cap 400, but a message awaiting its confirm is never dropped: the oldest non-pending ones go first
    for(let i=this.msgs.length-1;i>=0&&this.msgs.length>400;i--){ const m=this.msgs[i]; if(!(m.confirm&&!m.confirmed)) this.msgs.splice(i,1); }
    return this.msgs[0];
  }
  drillFaults(){ const set=new Set(['rxn']); for(const d of this.drillDefs()) set.add(d.fault); return [...set]; }
  aDrillReservedUpsetKey(faultId,targetNodeId){
    const UB=ESS.UpsetBridge;
    for(const k of ['xmtr','drift','stick']){
      if(UB.faultIdFor(k)!==faultId) continue;
      if(UB.topologyTargets(k,this.topo).indexOf(targetNodeId)>=0) return k;
    }
    return null;
  }
  archTraineeSymptoms(){
    const badPvByTag={};
    Object.keys(this.L||{}).forEach(tag=>{ badPvByTag[tag]=!!this.L[tag].badPv; });
    const current=ESS.FaultEngine.symptomProjection(this.archFaultState(),this.topo,{badPvByTag}).observations;
    const stored=this.P.aDrill&&Array.isArray(this.P.aDrill.cues)?this.P.aDrill.cues:[];
    const seen={}, observations=[];
    stored.concat(current).forEach(o=>{ if(o&&o.text&&!seen[o.text]){ seen[o.text]=true; observations.push({scope:o.scope,text:o.text,source:'DRILL_CUE'}); } });
    observations.sort((a,b)=>a.text.localeCompare(b.text));
    return {grade:'SIMULATED_ARCHITECTURE_INDICATION',observations};
  }
  drillData(){ const d=this.state.drill; return d?{id:d.def.id,t0:d.t0,ti:d.ti,tInj:d.tInj||0,injected:d.injected,m:d.m,stableFor:d.stableFor,startMode:d.startMode||'LIVE STATE',preset:d.preset||null}:null; }
  assetMatch(nodeId,tag){
    if(!nodeId||nodeId==='PLANT') return true;
    const n=this.assetTree().find(x=>x.id===nodeId); if(!n) return true;
    if(n.tags) return n.tags.includes(tag);
    return this.unitOf(tag)===n.unit;
  }
  operatorMayWrite(tag,param){
    const l=this.L[tag]; if(!l||l.kind!=='pid') return true;
    if(this.interlockOwns(tag,param)){ this.rejectWrite(tag,'TI216 URGENT INTERLOCK — '+param+' HELD BY SHED (MAN, OP 0)'); return false; }
    if(ESS.Pid.canOperatorWrite(l,param)) return true;
    this.rejectWrite(tag,ESS.Pid.writeDenial(l,param));
    return false;
  }
  withSignature(desc,need,fn,opts){
    if(this._replayApplying){ fn('REPLAY'); return; }
    const o=opts||{};
    if(this.state.dlg&&this.state.dlg.type==='esig'){ this.msgZone('SIGNATURE PENDING — SIGN OR CANCEL '+this.state.dlg.desc+' FIRST'); return; }
    if(!(o.instr&&this.instructorAllowed())&&!this.can(need)) return;
    const cur=this.state.dlg, prev=cur||null;   // restored by cancelSignature()
    this.setState({dlg:{type:'esig',desc,need,fn,prev,instr:!!o.instr},dlgPw:'',dlgReason:'',menu:null});
  }
  limitBand(l){
    const rangeLo=l.lo, rangeHi=l.hi, span=(rangeHi-rangeLo)||1;
    const tp=(c)=>l.alm&&l.alm[c]?l.alm[c][0]:null;
    const critLo=Math.min(rangeHi,Math.max(rangeLo,tp('PVLL')??rangeLo));
    const critHi=Math.max(critLo,Math.min(rangeHi,tp('PVHH')??rangeHi));
    const stdLo=Math.min(critHi,Math.max(critLo,tp('PVLO')??critLo));
    const stdHi=Math.max(stdLo,Math.min(critHi,tp('PVHI')??critHi));
    const auto=l.tgtLo==null||l.tgtHi==null;
    let tLo=l.tgtLo, tHi=l.tgtHi;
    if(auto){ const c=l.kind==='pid'?l.sp:(stdLo+stdHi)/2, half=span*0.05; tLo=c-half; tHi=c+half; }
    const tgtLo=Math.min(stdHi,Math.max(stdLo,tLo));
    const tgtHi=Math.max(tgtLo,Math.min(stdHi,tHi));
    return {rangeLo,critLo,stdLo,tgtLo,tgtHi,stdHi,critHi,rangeHi,auto};
  }
  setTargetBand(l,lo,hi){
    const b=this.limitBand(l);
    if(!(lo<hi)||lo<b.stdLo||hi>b.stdHi){ this.msgZone('ENTRY REJECTED — TARGET BAND MUST LIE INSIDE '+this.fmt(b.stdLo,l.dec)+' TO '+this.fmt(b.stdHi,l.dec)+' AND LOW < HIGH'); return false; }
    l.tgtLo=lo; l.tgtHi=hi; return true;
  }
  resetLimitTimers(l){ for(const c in (l._am||{})){ const m=l._am[c]; m.onT=0; m.offT=0; } }
  restoreSnapshot(snap,why){
    const I=ESS.Instructor;
    this.P=I.clone(snap.P); this.L=I.clone(snap.L); this.V=I.clone(snap.V);
    // A snapshot taken before V3-PLAN S2 (or an older ring/slot entry) predates this field;
    // absence means all-healthy, the same pattern the architecture-view addendum uses
    // elsewhere for a v2-shaped snapshot. Never overwrites a restored value that IS present.
    if(!this.P.archFaults) this.P.archFaults = ESS.FaultEngine.createState();
    // Same defaulting for the schedule ledger a pre-panel snapshot (or an older ring/slot
    // entry) predates: absent means nothing was pending or ramping/expiring, never crashes
    // archFaultTick(). A restored archFaults WITH archMeta-bearing instances but no archMeta
    // (an old snapshot saved between S2 sub-changes) just falls back to STEP/no-expiry for
    // those instances, which is a safe default, never a thrown error.
    if(!this.P.archPending) this.P.archPending = [];
    if(!this.P.archMeta) this.P.archMeta = {};
    // S3 defaulting, same pattern: a pre-S3 snapshot predates archInspected/training/
    // aDrill entirely. Absent inspection means nothing was explicitly opened (fails
    // closed correctly -- MARK_EVIDENCE/VERIFY simply refuse until re-opened), absent
    // training means no evidence/pins/hypotheses/verifications recorded, and a missing
    // or undefined aDrill means no architecture drill was running.
    if(!this.P.archInspected) this.P.archInspected = {};
    if(!this.P.training) this.P.training = ESS.Dispatch.createTrainingState();
    if(this.P.aDrill===undefined) this.P.aDrill = null;
    if(!this.P.archFaultLog) this.P.archFaultLog = [];
    this.alarmEngine.restore(snap.alarms);
    this.restoreDisabledAssets(snap.disabledAssets);
    this.tadShed=snap.tadShed; this.phaseSet=snap.phaseSet;
    this.seed=snap.seed||this.seed; this.rand=ESS.Models.createRand(this.seed); if(snap.randState!=null) this.rand.setState(snap.randState);
    this.rand4=ESS.Models.createRand((this.seed ^ 0x5eed4) >>> 0); if(snap.randState4!=null) this.rand4.setState(snap.randState4);
    this._ctx=null; this._pidCtx=null; this.callouts={}; this.vLag={}; this._lastPhase=this.P.b.phase;
    // restoreSnapshot replaces this.L/this.V wholesale, so the cached graph must be rebuilt too.
    this.topo = ESS.Topology.build({L:this.L, V:this.V, assetTree:this.assetTree(), unitOf:(t)=>this.unitOf(t)});
    const t=this.P.t;
    for(const k in this.hist){ const h=this.hist[k]; while(h.length&&h[h.length-1][0]>t) h.pop(); }
    this.events=this.events.filter(e=>e.t<=t); this.msgs=this.msgs.filter(m=>m.t<=t); this.alarmLog=this.alarmLog.filter(a=>a.t<=t);
    I.trimAfter(this.instr,t,snap.journalSeq);
    this.setState({drill:this.drillFromData(snap.drill),entry:null,selAlm:null,msg:''});
    this.instrLog((why||'SNAPSHOT RESTORED')+' — SIM TIME '+this.fT(t));
  }
  dofPreflight(what){
    if(this.replaying()) return true;
    if(typeof ESS==='undefined'||!ESS.BoundaryDof) return true;   // module absent: fail open, never block a drill
    const r=ESS.BoundaryDof.check(this.P,this.L);
    this.dofNotesRecord(what,r);
    if(r.ok) return true;
    const why=ESS.BoundaryDof.formatRefusal(r);
    this.msgZone(what+' REFUSED — '+why);
    this.addEvent('SYSTEM','DOF',what+' REFUSED — '+why,'','');
    this.instrNote(what+' REFUSED BY THE PRE-DRILL DOF CHECK — '+why);
    return false;
  }
  fT(ms){ const d=new Date(ms); return ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)+':'+('0'+d.getSeconds()).slice(-2); }
  aDrillClear(step){
    (step.targets||[]).forEach(target=>{
      const k=this.aDrillReservedUpsetKey(step.faultId,target);
      if(k){ this.injectFault(k,false); return; }
      if(step.faultId==='OPEN_INPUT_BAD_QUALITY'){
        const n=this.topo.nodes[target];
        (n&&n.pointRefs||[]).forEach(tag=>{ if(this.L[tag]) this.L[tag].badPv=false; });
      }
      this.archClearNow(step.faultId,target);
    });
  }
  aDrillRecordShape(score){
    return {
      score:score.score, pass:score.pass, passMark:score.passMark,
      breakdown:(score.breakdown||[]).map(r=>({
        label:r.category||r.label, earned:r.earned,
        max:r.weight!=null?r.weight:r.max,
        note:r.note||((r.matched!=null&&r.required!=null)?(r.matched+'/'+r.required):'')
      }))
    };
  }
  archTrainingCtx(){
    return {
      graph:this.topo, training:this.P.training,
      // The CURRENT view mode, and dispatch's requireMode() FAILS CLOSED without it: every
      // scoring command is gated to the mode in which earning it means something, so an
      // absent archMode refuses in Diagnose too and no A-drill can be scored at all. That
      // was the state until this line existed -- the gate was correct and the seam was
      // empty, which reads exactly like a broken gate from either side alone.
      archMode:this.state.archMode,
      replaying:!!this._replayApplying,
      wasInspected:(id)=>!!this.P.archInspected[id],
      journalAdd:(entry)=>ESS.Instructor.journalAdd(this.instr,entry)
    };
  }
  archRetainEvent(ev){ if(this.P.aDrill) this.P.aDrill.events.push(ev); }
  isOos(tag,cond){ const r=this.alarmEngine.get(tag+'.'+cond); return !!r && r.state==='OOSRV'; }
  assetTags(id){ const tags=new Set(); this.assetTree().forEach(n=>{ if(n.tags&&this.assetMatch(id,n.tags[0])) n.tags.forEach(t=>tags.add(t)); }); return [...tags]; }
  archFaultState(){
    const FE=ESS.FaultEngine, UB=ESS.UpsetBridge, G=this.topo;
    let state=FE.snapshot(this.P.archFaults||FE.createState());
    if(!G) return state;
    for(const k of ['xmtr','drift','stick']){
      if(!this.upsetOn(k)) continue;
      const faultId=UB.faultIdFor(k);
      if(!faultId) continue;
      for(const targetNodeId of UB.topologyTargets(k,G)){
        if(FE.isActive(state,faultId,targetNodeId)) continue;
        const opts={faultId,targetNodeId,simTime:(this.P.faultT&&this.P.faultT[k]!=null)?this.P.faultT[k]:this.P.t};
        if(k==='drift') opts.magnitude=this.P.mag.drift;   // BIASED_MEASUREMENT needs an explicit magnitude or a seeded rand -- never hand it the live generator (advisory Q1.8)
        const r=FE.activate(state,G,opts);
        if(r.accepted) state=r.state;
      }
    }
    return state;
  }
  interlockOwns(tag,param){
    return tag==='FIC211' && this.tadShed && (param==='MODE'||param==='OP'||param==='SP');
  }
  rejectWrite(tag,txt){
    this.callouts[tag]={txt,until:this.P.t+5000,untilTk:this.state.tk+10};
    this.addEvent('OPERATOR',tag,'WRITE REJECTED — '+txt,'','');
    this.msgZone(tag+': '+txt);
  }
  instructorAllowed(){ return this.state.sec==='MNGR' || !!(this.instr&&this.instr.auth); }
  restoreDisabledAssets(list){
    const E=this.alarmEngine;
    const ids=Array.isArray(list)?list:E.list().filter(r=>r.disabledBy&&r.disabledBy.startsWith('ASSET:')).map(r=>r.disabledBy.slice(6));
    this.disabledAssets=new Set(ids);
    for(const r of E.list()){ if(!r.disabledBy) continue; const id=r.disabledBy.startsWith('ASSET:')?r.disabledBy.slice(6):''; if(!this.disabledAssets.has(id)){ r.disabledBy=''; E.rts(r,this.P.t); this.addEvent('SYSTEM',r.tag,r.cond+' RE-ENABLED — '+id+' NOT DISABLED IN RESTORED STATE','DISABLED',r.state); } }
  }
  drillFromData(x){ const def=x&&this.drillDefs().find(d=>d.id===x.id); return def?{def,t0:x.t0,ti:x.ti,tInj:x.tInj||0,injected:x.injected,m:x.m||{},stableFor:x.stableFor||0,startMode:x.startMode==='CANONICAL'?'CANONICAL':'LIVE STATE',preset:x.preset||null}:null; }
  replaying(){ return !!(this.instr&&this.instr.replay); }
  dofNotesRecord(what,r){
    const notes=((r&&r.findings)||[]).filter(f=>f&&f.severity==='note');
    if(!notes.length) return;
    for(const n of notes) this.instrNote(what+' — '+n.code+': '+n.detail);
    const ring=this.instr.dofNotes||(this.instr.dofNotes=[]);
    ring.push({t:this.P.t,what,notes:notes.map(n=>({code:n.code,detail:n.detail,tags:(n.tags||[]).slice()}))});
    if(ring.length>24) ring.splice(0,ring.length-24);   // display ring, same discipline as instr.log
  }
  archClearNow(faultId,targetNodeId){
    const pendingIdx=(this.P.archPending||[]).findIndex(e=>e.faultId===faultId&&e.targetNodeId===targetNodeId);
    if(pendingIdx>=0){ this.P.archPending.splice(pendingIdx,1); return; }
    const r=ESS.FaultEngine.deactivate(this.P.archFaults,{faultId,targetNodeId});
    if(r.accepted){ this.P.archFaults=r.state; delete this.P.archMeta[faultId+'@'+targetNodeId]; this.archFaultLogPush(faultId,targetNodeId,'CLEAR'); }
  }
  upsetOn(k){ return !!this.P.faults[k]||(k==='stick'&&this.V.TV202.stuck); }
  archValidateActivate(p){
    const FE=ESS.FaultEngine, def=FE.getFaultDef(p.faultId);
    if(!def) return 'unknown fault id: '+p.faultId;
    const node=this.topo&&this.topo.nodes[p.targetNodeId];
    if(!node) return 'unknown topology node: '+p.targetNodeId;
    if(this.archIsReserved(p.faultId,p.targetNodeId)) return 'reserved for the legacy upset panel above';
    if(this.archLedgerStatus(p.faultId,p.targetNodeId)) return 'already active or pending on this node';
    const mode=p.mode==='RAMP'?'RAMP':'STEP';
    if(mode==='RAMP'&&!(Number(p.rampSec)>0)) return 'ramp mode needs a positive ramp time';
    const delaySec=Number(p.delaySec);
    if(!(delaySec>=0)) return 'onset delay must be zero or greater';
    const durationSec=(p.durationSec==null||p.durationSec==='')?null:Number(p.durationSec);
    if(durationSec!=null&&!(durationSec>0)) return 'duration must be blank (indefinite) or greater than zero';
    let magnitude;
    if(def.magnitudeRange){
      magnitude=Number(p.magnitude);
      if(!isFinite(magnitude)) return 'this fault needs a magnitude';
      if(magnitude<def.magnitudeRange.min||magnitude>def.magnitudeRange.max) return 'magnitude out of range';
    }
    const trial=FE.activate(FE.snapshot(this.P.archFaults),this.topo,{faultId:p.faultId,targetNodeId:p.targetNodeId,simTime:this.P.t,magnitude:magnitude});
    if(!trial.accepted) return 'engine refused: '+trial.reason;
    return true;
  }
  scheduleArchFault(p){
    if(Number(p.delaySec)>0){
      this.P.archPending.push({faultId:p.faultId,targetNodeId:p.targetNodeId,fireAt:this.P.t+Number(p.delaySec)*1000,
        mode:p.mode==='RAMP'?'RAMP':'STEP',rampSec:p.mode==='RAMP'?(Number(p.rampSec)||0):0,
        durationSec:(p.durationSec==null||p.durationSec==='')?null:Number(p.durationSec),
        magnitude:p.magnitude==null?null:Number(p.magnitude)});
      return;
    }
    this.archFireFault(p.faultId,p.targetNodeId,p.mode==='RAMP'?'RAMP':'STEP',p.mode==='RAMP'?(Number(p.rampSec)||0):0,
      (p.durationSec==null||p.durationSec==='')?null:Number(p.durationSec), p.magnitude==null?null:Number(p.magnitude), this.P.t);
  }
  archValidateClear(p){
    if(this.archIsReserved(p.faultId,p.targetNodeId)) return 'reserved for the legacy upset panel above';
    if(!this.archLedgerStatus(p.faultId,p.targetNodeId)) return 'not active or pending';
    return true;
  }
  archIsReserved(faultId,targetNodeId){ return this.archReservedPairs().some(r=>r.faultId===faultId&&r.targetNodeId===targetNodeId); }
  archLedgerStatus(faultId,targetNodeId){
    if(ESS.FaultEngine.isActive(this.P.archFaults,faultId,targetNodeId)) return 'ACTIVE';
    if((this.P.archPending||[]).some(e=>e.faultId===faultId&&e.targetNodeId===targetNodeId)) return 'PENDING';
    return null;
  }
  archReservedPairs(){
    const UB=ESS.UpsetBridge, G=this.topo;
    const out=[];
    for(const k of ['xmtr','drift','stick']){
      const faultId=UB.faultIdFor(k);
      if(!faultId) continue;
      for(const targetNodeId of UB.topologyTargets(k,G||{nodes:{}})) out.push({faultId,targetNodeId});
    }
    return out;
  }
  }; };
});
