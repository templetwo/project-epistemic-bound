// @artifact production
// quality_proxy_v1: analyzer-qualified output, not a fluid composition assay.
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('./models'));else root.ESS.ProductMeter=factory(root.ESS.Models);})(typeof globalThis!=='undefined'?globalThis:this,function(Models){
  'use strict';
  const inventory=P=>Models.PARAMS.U4.A1*(P.s.hw+P.s.ho)+Models.PARAMS.U4.A2*P.s.h2;
  function create(P,mission){return {formula_version:'quality_proxy_v1',start:P.t,end:P.t,draw:0,gross:0,qualified:0,off_band:0,unknown:0,eligible_ms:0,covered_ms:0,continuous_ms:0,inventory_start:inventory(P),inventory_current:inventory(P),samples:[],mission:mission||{minimum_continuity_rate_m3h_milli:25000,max_quality_percent_milli:1000,max_quality_age_ms:2000}};}
  function advance(m,P,L,sample,dt){
    if(!sample||!Number.isFinite(sample.draw_rate_m3h)||sample.dt_s!==dt)throw Error('missing_product_sample');
    const q=sample.draw_rate_m3h,v=q*dt/3600,a=L.AI509;
    const good=a&&Number.isFinite(a.pv)&&!a.badPv&&a.quality!=='STALE'&&a.quality!=='BAD'&&(a.age_ms||0)<=m.mission.max_quality_age_ms;
    m.draw=q;m.gross+=v;m.end=P.t;m.eligible_ms+=dt*1000;
    if(good){m.covered_ms+=dt*1000;if(a.pv*1000<=m.mission.max_quality_percent_milli)m.qualified+=v;else m.off_band+=v;}else m.unknown+=v;
    if(q*1000>=m.mission.minimum_continuity_rate_m3h_milli)m.continuous_ms+=dt*1000;
    m.inventory_current=inventory(P);m.samples.push([P.t,q,m.inventory_current]);while(m.samples.length&&m.samples[0][0]<=P.t-300000)m.samples.shift();
  }
  function project(m){return {formula_version:m.formula_version,draw_rate_m3h_milli:Math.round(m.draw*1000),gross_volume_um3:Math.round(m.gross*1e6),qualified_volume_proxy_um3:Math.round(m.qualified*1e6),off_band_volume_proxy_um3:Math.round(m.off_band*1e6),unknown_quality_volume_um3:Math.round(m.unknown*1e6),interval_start_sim_ms:m.start,interval_end_sim_ms:m.end,eligible_sim_ms:m.eligible_ms,quality_covered_sim_ms:m.covered_ms,continuous_above_threshold_sim_ms:m.continuous_ms,inventory_start_um3:Math.round(m.inventory_start*1e6),inventory_current_um3:Math.round(m.inventory_current*1e6)};}
  return {create,advance,project,inventory};
});
