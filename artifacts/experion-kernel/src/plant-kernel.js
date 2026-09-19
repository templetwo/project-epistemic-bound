// @artifact production
// Complete deterministic checkpoint/candidate boundary. No DOM, timers, eval or network.
(function(root,factory){
  if(typeof module==='object'&&module.exports) module.exports=factory(require('./plant-core'),require('./models'),require('./instructor'),require('./topology'),require('./product-meter'),require('./control-contract'));
  else root.ESS.PlantKernel=factory(root.ESS.PlantCore,root.ESS.Models,root.ESS.Instructor,root.ESS.Topology,root.ESS.ProductMeter,root.ESS.ControlContract);
})(typeof globalThis!=='undefined'?globalThis:this,function(Core,Models,Instructor,Topology,Meter,Control){
  'use strict';
  function stable(value){
    if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
    if(typeof value==='number'){if(!Number.isFinite(value))throw Error('nonfinite_state');return JSON.stringify(Object.is(value,-0)?0:value);}
    if(Array.isArray(value))return '['+value.map(stable).join(',')+']';
    if(typeof value==='object')return '{'+Object.keys(value).sort().filter(k=>value[k]!==undefined).map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}';
    throw Error('nonserializable_state');
  }
  // Copy the JSON state tree directly; encoding/parsing it twice per scan was costly.
  // Keep the same finite-number, undefined-property and negative-zero rules as stable().
  function clone(v){
    if(v===null||typeof v==='string'||typeof v==='boolean')return v;
    if(typeof v==='number'){if(!Number.isFinite(v))throw Error('nonfinite_state');return Object.is(v,-0)?0:v;}
    if(Array.isArray(v)){const out=new Array(v.length);for(let i=0;i<v.length;i++)out[i]=clone(v[i]);return out;}
    if(typeof v==='object'){const out={};for(const k of Object.keys(v))if(v[k]!==undefined)Object.defineProperty(out,k,{value:clone(v[k]),enumerable:true,writable:true,configurable:true});return out;}
    throw Error('nonserializable_state');
  }
  class Memory {
    constructor(){this.historyLimit=600;this.props={};this.state={sec:'OPER',oper:'NATIVE',tk:0,drill:null,archMode:'learn',speed:1,msg:'',silenced:true};}
    setState(update){Object.assign(this.state,typeof update==='function'?update(this.state):update);}
  }
  class Plant extends Core(Memory){
    get alarms(){return this.alarmEngine.list();}
    publishCoach(){}
    coachPing(){}
    coachSetUnavailable(){}
    coachUnavailable(){return "GOVERNED";}
    // UI backtrack slots are not operational rollback. RT checkpoints replace this view feature.
    backtrackTick(){}
    fT(ms){return new Date(ms).toISOString().slice(11,19);}
    postMsg(txt,opts){
      const o=opts||{}; const m={id:this.nextMessage++,t:this.P.t,txt,src:o.src||'STN01',confirm:!!o.confirm,confirmed:false,confirmedBy:'',confirmT:0};
      this.msgs.unshift(m);
      for(let i=this.msgs.length-1;i>=0&&this.msgs.length>400;i--)if(!(this.msgs[i].confirm&&!this.msgs[i].confirmed))this.msgs.splice(i,1);
      return m;
    }
  }
  const fields=['historyLimit','P','L','V','events','msgs','hist','eid','alarmLog','t0','seed','vLag','phaseSet','tadShed','_lastPhase','trainingRecords','mocCount','_lastADrill'];
  function capture(c){
    const data={schema_version:'peb.plant.v1',tick:c.rtTick,nextMessage:c.nextMessage,fields:{},alarms:c.alarmEngine.snapshot(),rand:c.rand.getState(),rand4:c.rand4.getState(),tasksDone:[...c.tasksDone],disabledAssets:[...c.disabledAssets],drill:c.drillData(),product:c.product,revisions:c.revisions,focus:c.focus,ce:c.ceRec?c.ceRec.seen():[],instructor:{}};
    for(const k of fields)if(c[k]!==undefined)data.fields[k]=c[k];
    for(const k of ['hidden','seed','seq','journal','replay','log','runResetSeq'])data.instructor[k]=c.instr[k];
    // Drill scoring reads these semantic fields; screen selections and dialogs are absent.
    data.exercise={};for(const k of ['archMode','drillFeedback','drillResult'])if(c.state[k]!==undefined)data.exercise[k]=c.state[k];
    return clone(data);
  }
  function fresh(options){
    const c=new Plant();c.instr=Instructor.create({seed:options.seed||20260829});c.nextMessage=1;
    c.initSim(options.sim_time_ms||0);c.rtTick=0;c.revisions={};c.focus={view:'U1',tag:null};
    c.product=Meter.create(c.P,options.mission);return c;
  }
  function create(options){return capture(fresh(options||{}));}
  function restore(checkpoint){
    if(checkpoint.schema_version!=='peb.plant.v1')throw Error('checkpoint_version');
    const s=clone(checkpoint),c=fresh({seed:s.fields.seed,sim_time_ms:s.fields.t0});
    Object.assign(c,s.fields);c.rtTick=s.tick;c.nextMessage=s.nextMessage;
    c.alarmEngine.restore(s.alarms);c.rand=Models.createRand(c.seed);c.rand.setState(s.rand);c.rand4=Models.createRand((c.seed^0x5eed4)>>>0);c.rand4.setState(s.rand4);
    c.tasksDone=new Set(s.tasksDone);c.disabledAssets=new Set(s.disabledAssets);Object.assign(c.instr,s.instructor);
    c.state.drill=c.drillFromData(s.drill);Object.assign(c.state,s.exercise);c.product=s.product;c.revisions=s.revisions;c.focus=s.focus;
    c.ceRec.reset();for(const e of s.ce)c.ceRec.observe(e.src,e.cond,e.t);
    c._ctx=null;c._pidCtx=null;c.topo=Topology.build({L:c.L,V:c.V,assetTree:c.assetTree(),unitOf:t=>c.unitOf(t)});
    return c;
  }
  function signature(c,tag){const l=c.L[tag];return stable(l?{mode:l.mode,sp:l.mode==='AUTO'?l.sp:null,op:l.mode==='MAN'?l.op:null,modeAttr:l.modeAttr,badPv:l.badPv,sphilm:l.sphilm,splolm:l.splolm,ophilm:l.ophilm,oplolm:l.oplolm,trip:l.trip,run:l.run,interlock:c.interlockOwns(tag,'MODE')}:{phase:c.P.b.phase,held:c.P.b.held,tadShed:c.tadShed});}
  function advance(state,dt,commands){
    if(dt!==0.5)throw Error('fixed_dt_required');
    const c=restore(state),outcomes=[];
    for(const cmd of commands||[]){
      const before=Control.values(c,cmd.call),rev=c.revisions[Control.target(cmd.call)]||0;
      const reason=Control.validate(c,cmd.call,cmd.principal,cmd.expected_control_revision);
      if(reason){outcomes.push({command_id:cmd.command_id,status:'rejected',reason,before,after:before,revision_before:rev,revision_after:rev});continue;}
      // An exception aborts the whole candidate; the caller owns the committed state.
      c.state.oper=cmd.principal.id;c.state.sec=cmd.principal.role==='instructor'?'MNGR':'OPER';
      Control.reduce(c,cmd.call);if(cmd.principal.role==='subject'&&cmd.call.operation==='loop.set')c.focus={view:c.unitOf(Control.target(cmd.call)),tag:Control.target(cmd.call)};const after=Control.values(c,cmd.call),changed=stable(before)!==stable(after);
      if(changed)c.revisions[Control.target(cmd.call)]=rev+1;
      outcomes.push({command_id:cmd.command_id,status:changed?'applied':'no_effect',reason:changed?'committed':'already_in_requested_state',before,after,revision_before:rev,revision_after:c.revisions[Control.target(cmd.call)]||0});
    }
    c.state.oper='NATIVE';c.state.sec='OPER';
    const targets=[...Object.keys(c.L),'SCM202'];const before=Object.fromEntries(targets.map(t=>[t,signature(c,t)]));
    const ctx=c.modelCtx();let sample=null;ctx.productSample=x=>{sample=x;};
    c.step(dt);c.rtTick++;c.state.tk=c.rtTick;
    for(const t of targets)if(before[t]!==signature(c,t))c.revisions[t]=(c.revisions[t]||0)+1;
    Meter.advance(c.product,c.P,c.L,sample,dt);
    return {state:capture(c),outcomes};
  }
  return {create,restore,capture,advance,stable,clone,fields};
});
