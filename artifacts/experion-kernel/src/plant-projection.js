// @artifact production
// Subject data is built from an allowlist. Instructor truth is a separate projection.
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('./product-meter'),require('./control-contract'));else root.ESS.PlantProjection=factory(root.ESS.ProductMeter,root.ESS.ControlContract);})(typeof globalThis!=='undefined'?globalThis:this,function(Meter,Control){
 'use strict';
 const milli=v=>Number.isFinite(v)?Math.round(v*1000):null;
 function project(s,role,ownership){
  if(!['subject','operator','instructor','evaluator'].includes(role))throw Error('unknown_role');
  const f=s.fields,L=f.L,P=f.P,owners=ownership||{};
  const points=Object.values(L).map(l=>({tag:l.tag,value_milli:milli(l.pv),unit:l.eu||'STATE',quality:l.badPv?'BAD':'GOOD',sample_tick:s.tick,sample_sim_time_ms:P.t,age_sim_ms:0,mode:l.mode||null,sp_milli:milli(l.sp),op_milli:milli(l.op),control_revision:s.revisions[l.tag]||0,owner:owners[l.tag]||owners['*']||(l.modeAttr==='PROGRAM'?'PROGRAM':'SUBJECT')}));
  const alarms=s.alarms.recs.filter(a=>a.state!=='NORM').sort((a,b)=>({Urgent:0,High:1,Low:2,Journal:3}[a.prio]-{Urgent:0,High:1,Low:2,Journal:3}[b.prio])||b.lastT-a.lastT);
  const board={tick:s.tick,sim_time_ms:P.t,points,product:Meter.project(s.product),batch:{phase:P.b.phase,held:!!P.b.held,program_owner:'sequence.scm202'},alarms:alarms.slice(0,64).map(a=>({episode_id:Control.episode(a),target:a.key,condition:a.cond,priority:a.prio,active:!!a.live,acknowledged:!!a.ack,first_observed_sim_ms:a.t})),alarms_total_matched:alarms.length,alarms_omitted:Math.max(0,alarms.length-64),trend_windows:['TIC201','TI312','LIC503'].map(tag=>({tag,interval_start_sim_ms:Math.max(f.t0,P.t-300000),interval_end_sim_ms:P.t,samples:(f.hist[tag]||[]).slice(-600).map(x=>({tick:Math.round((x[0]-f.t0)/500),sim_time_ms:x[0],value_milli:milli(x[1]),quality:'UNKNOWN'}))})),public_messages:f.msgs.filter(m=>m.src==='SCM202'||m.src==='TI216'||m.src==='OPERATOR').slice(0,16).map(m=>({message_id:'message.'+m.id,version:Number(m.confirmed),text:m.txt.slice(0,2000),interpretation:'untrusted_data'}))};
  if(role==='subject')return board;
  return {...board,focus:s.focus,station:{L:f.L,V:f.V,P:f.P,hist:f.hist,alarms:s.alarms,events:f.events,msgs:f.msgs,tadShed:f.tadShed,phaseSet:f.phaseSet,vLag:f.vLag},product_detail:{label:'Analyzer-qualified output proxy',rolling_5min_m3h:s.product.samples.length?s.product.samples.reduce((sum,x)=>sum+x[1],0)/s.product.samples.length:0,inventory_delta_m3:s.product.inventory_current-s.product.inventory_start},instructor:role==='instructor'||role==='evaluator'?{faults:P.faults,variables:P.env,architecture:P.archFaults}:undefined};
 }
 return {project};
});
