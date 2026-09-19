// @artifact production
// Closed semantic command catalog; native checks apply equally to every writer.
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('./pid'),require('./instructor'));else root.ESS.ControlContract=factory(root.ESS.Pid,root.ESS.Instructor);})(typeof globalThis!=='undefined'?globalThis:this,function(Pid,Instructor){
  'use strict';
  const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
  function exact(o,required,optional=[]){return !!o&&typeof o==='object'&&!Array.isArray(o)&&required.every(k=>own(o,k))&&Object.keys(o).every(k=>required.includes(k)||optional.includes(k));}
  const target=call=>call.arguments.target||call.arguments.message_id||'attention';
  const episode=a=>'alarm.'+a.id+'.'+a.lastT;
  function shape(call){
    if(!exact(call,['operation','arguments']))return false;
    const a=call.arguments;
    switch(call.operation){
      case 'loop.set':return exact(a,['target','expected_mode','mode'],['demand'])&&['AUTO','MAN','CAS'].includes(a.mode)&&['AUTO','MAN','CAS'].includes(a.expected_mode)&&(!a.demand||(exact(a.demand,['field','value_milli','unit'])&&Number.isSafeInteger(a.demand.value_milli)&&Math.abs(a.demand.value_milli)<=10000000&&['SP','OP'].includes(a.demand.field)));
      case 'motor.command':return exact(a,['target','command'])&&['P101','M202'].includes(a.target)&&['START','STOP'].includes(a.command);
      case 'sequence.command':return exact(a,['target','command','expected_phase'])&&a.target==='SCM202'&&['START','HOLD','RESUME','ABORT'].includes(a.command);
      case 'alarm.ack':return exact(a,['target','alarm_episode_id']);
      case 'message.ack':return exact(a,['message_id','expected_message_version'])&&Number.isSafeInteger(a.expected_message_version);
      case 'view.focus':return exact(a,['view'],['tag'])&&['U1','U2','U3','U4','ALARMS','TRENDS','BATCH','PRODUCT','ARCH'].includes(a.view);
      case 'instructor.upset':return exact(a,['target','on'])&&typeof a.on==='boolean';
      case 'instructor.variable':return exact(a,['target','value_milli'])&&Number.isSafeInteger(a.value_milli);
      case 'instructor.architecture':return exact(a,['target','fault_id','on','delay_ms','duration_ms'],['magnitude_milli'])&&typeof a.on==='boolean'&&Number.isSafeInteger(a.delay_ms)&&a.delay_ms>=0&&a.delay_ms<=600000&&Number.isSafeInteger(a.duration_ms)&&a.duration_ms>=0&&a.duration_ms<=3600000&&(!own(a,'magnitude_milli')||Number.isSafeInteger(a.magnitude_milli));
      default:return false;
    }
  }
  function validate(c,call,principal,revision){
    if(!shape(call))return 'invalid_call';
    if(!principal||!['subject','operator','instructor'].includes(principal.role))return 'unauthorized';
    const a=call.arguments,t=target(call),l=c.L[t],b=c.P.b;
    if(revision!==undefined&&revision!==(c.revisions[t]||0))return 'stale_control_revision';
    if(call.operation.startsWith('instructor.')){
      if(principal.role!=='instructor')return 'unauthorized';
      if(call.operation==='instructor.architecture'){const p={faultId:a.fault_id,targetNodeId:t,mode:'STEP',delaySec:a.delay_ms/1000,durationSec:a.duration_ms?a.duration_ms/1000:null,magnitude:a.magnitude_milli===undefined?null:a.magnitude_milli/1000};const r=a.on?c.archValidateActivate(p):c.archValidateClear(p);return r===true?null:'architecture_unavailable';}
      if(call.operation==='instructor.upset')return Instructor.upsetDefs().some(d=>d.k===t)?null:'unknown_target';
      const d=Instructor.variableDefs().find(x=>x.k===t);return d&&a.value_milli/1000>=d.min&&a.value_milli/1000<=d.max?null:'variable_outside_limits';
    }
    if(call.operation==='loop.set'){
      if(!l||l.kind!=='pid')return 'unknown_target';
      if(l.mode!==a.expected_mode)return 'stale_mode';
      if(l.modeAttr==='PROGRAM')return 'program_owned';
      if(c.interlockOwns(t,'MODE'))return 'native_interlock';
      if(a.mode==='CAS'&&(!l.master||a.demand))return 'cascade_demand_forbidden';
      const check=Pid.transferMode({...l},a.mode,c.pidCtx());if(!check.ok)return 'mode_unavailable';
      if(a.demand){const d=a.demand,isSP=d.field==='SP',v=d.value_milli/1000;
        if(isSP&&a.mode!=='AUTO'||!isSP&&a.mode!=='MAN')return 'demand_mode_mismatch';
        if(d.unit!==(isSP?l.eu:'%'))return 'wrong_unit';
        if(v<(isSP?l.splolm:l.oplolm)||v>(isSP?l.sphilm:l.ophilm))return 'native_limit';
      }return null;
    }
    if(call.operation==='motor.command'){
      if(a.command==='START'&&!l.run&&(l.lock>0||(t==='P101'&&c.P.tankL<5)))return 'start_permissive';return null;
    }
    if(call.operation==='sequence.command'){
      if(a.expected_phase!==b.phase)return 'stale_phase';
      if(a.command==='START'&&(b.phase!=='IDLE'||c.P.trips.batch||c.tadShed))return 'start_permissive';
      if(a.command==='RESUME'&&(c.tadShed||c.P.trips.batch))return 'native_interlock';
      if(a.command!=='START'&&b.phase==='IDLE')return 'sequence_idle';return null;
    }
    if(call.operation==='alarm.ack'){const alarm=c.alarmEngine.get(t);return alarm&&episode(alarm)===a.alarm_episode_id?null:'stale_alarm_episode';}
    if(call.operation==='message.ack'){const m=c.msgs.find(x=>'message.'+x.id===a.message_id);return m&&m.confirm&&Number(m.confirmed)===a.expected_message_version?null:'stale_message';}
    if(call.operation==='view.focus')return !a.tag||c.L[a.tag]?null:'unknown_visible_tag';
    return 'unknown_operation';
  }
  function values(c,call){
    if(!call||!call.arguments)return null;
    const a=call.arguments,t=target(call),l=c.L[t];
    switch(call.operation){
      case 'loop.set':return l?{mode:l.mode,sp_milli:Math.round(l.sp*1000),op_milli:Math.round(l.op*1000),unit:l.eu}:null;
      case 'motor.command':return l?{running:!!l.run,tripped:!!l.trip,lock_remaining_ms:Math.round(l.lock*1000)}:null;
      case 'sequence.command':return {phase:c.P.b.phase,held:!!c.P.b.held,program_owner:'sequence.scm202'};
      case 'alarm.ack':{const r=c.alarmEngine.get(t);return r?{episode_id:episode(r),active:!!r.live,acknowledged:!!r.ack}:null;}
      case 'message.ack':{const m=c.msgs.find(x=>'message.'+x.id===t);return m?{message_id:t,version:Number(m.confirmed),acknowledged:!!m.confirmed}:null;}
      case 'view.focus':return {...c.focus};
      case 'instructor.architecture':return {state:c.archLedgerStatus(a.fault_id,t)||'inactive'};
      case 'instructor.upset':return {on:c.upsetOn(t)};
      case 'instructor.variable':{const d=Instructor.variableDefs().find(x=>x.k===t);return d?{value_milli:Math.round(Instructor.getPath(c.P,d.path)*1000)}:null;}
      default:return null;
    }
  }
  function reduce(c,call){
    const a=call.arguments,t=target(call),l=c.L[t];
    switch(call.operation){
      case 'loop.set':
        if(l.mode!==a.mode)c.setMode(t,a.mode);
        if(a.demand)c.storeEntry(t,a.demand.field,a.demand.value_milli/1000);
        break;
      case 'motor.command':c.motorCmd(t,a.command==='START');break;
      case 'sequence.command':
        if(a.command==='HOLD'){if(!c.P.b.held)c.seqCmd('HOLD');}
        else if(a.command==='RESUME'){if(c.P.b.held)c.seqCmd('HOLD');}
        else c.seqCmd(a.command);break;
      case 'alarm.ack':c.ackAlarm(c.alarmEngine.get(t));break;
      case 'message.ack':c.confirmMsg(Number(t.slice(8)));break;
      case 'view.focus':c.focus={view:a.view,tag:a.tag||null};break;
      case 'instructor.architecture':if(a.on)c.setArchFault(a.fault_id,t,{mode:'STEP',delaySec:a.delay_ms/1000,durationSec:a.duration_ms?a.duration_ms/1000:null,magnitude:a.magnitude_milli===undefined?null:a.magnitude_milli/1000});else c.clearArchFault(a.fault_id,t);break;
      case 'instructor.upset':c.injectFault(t,a.on);break;
      case 'instructor.variable':c.setVariable(t,a.value_milli/1000);break;
      default:throw Error('unknown_operation');
    }
  }
  return {target,episode,shape,validate,values,reduce};
});
