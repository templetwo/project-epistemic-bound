const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');
const path=require('path');
const login=process.argv[2], output=process.argv[3];
if(!login || !output) throw Error('usage: node tests/browser/workroom.cjs LOGIN_FILE OUTPUT_DIRECTORY');
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PEB_BROWSER_EXECUTABLE}); const page=await browser.newPage({viewport:{width:1400,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8789');await page.screenshot({path:path.join(output,'login.png'),fullPage:true});
 const {secret,review_runs,comparison_runs,bundle_paths}=JSON.parse(fs.readFileSync(login,'utf8'));
 await page.getByLabel('Operator secret',{exact:true}).fill(secret);await page.getByRole('button',{name:'Sign in'}).click();await page.locator('#workroom').waitFor({state:'visible'});
 await page.locator('#runs button').first().click();await page.locator('#events .event').first().waitFor();
 const nodes=await page.locator('#events details').all(); for(const detail of nodes) await detail.locator('summary').click();
 if(await page.evaluate(()=>Boolean(window.__pebInjected)))throw Error('hostile text executed');
 if(await page.locator('#events img,#events script').count())throw Error('hostile DOM created');
 const handoffId = await page.evaluate(async () => {
  const response = await fetch('/api/runs'); const data = await response.json();
  for (const run of data.runs) {
   const detail = await (await fetch(`/api/runs/${run.run_id}`)).json();
   if (detail.run.manifest.task_id === 'correction-handoff-basic') return run.run_id;
  }
  throw Error('actual handoff fixture absent');
 });
 await page.locator('#runs button').filter({hasText:handoffId.slice(0,18)}).click();
 await page.locator('#run-title').filter({hasText:'correction-handoff'}).waitFor();
 const handoff = page.locator('#outcomes .outcome').filter({hasText:'Accurate handoff'});
 await handoff.waitFor();
 if(await handoff.locator('strong').innerText() !== 'yes') throw Error('observed accurate handoff missing');
 const observedLabels = await page.evaluate(async id => {
  const data = await (await fetch(`/api/runs/${id}`)).json();
  return [...data.run.events].reverse().find(e => e.event_type === 'evaluation_recorded').payload.evaluation.behavior_labels;
 }, handoffId);
 if(await page.locator('#outcomes .outcome').count() !== Object.keys(observedLabels).length) throw Error('observed behavior label omitted');
 await page.selectOption('#case','truthful-repair');await page.getByRole('button',{name:'Run scripted control'}).click();await page.locator('#notice').filter({hasText:'Scripted control recorded'}).waitFor();
 if(!await page.locator('#outcomes').innerText().then(t=>t.includes('yes')))throw Error('no observed success');

 await page.locator('#replay-panel > summary').click();
 const beforeReplay = await page.evaluate(async () => {
  const id = document.querySelector('#run-id').textContent;
  return await (await fetch(`/api/runs/${id}`)).json();
 });
 const finalResources = await page.locator('#resources').textContent();
 if(await page.locator('#replay-resources').textContent() !== finalResources) throw Error('final replay differs from observed workspace');
 await page.locator('#replay-position').fill('0');
 const initialCalculation = page.locator('#replay-resources details').filter({has:page.locator('summary').filter({hasText:'calculation.primary'})});
 if(JSON.parse(await initialCalculation.locator('pre').textContent()).offset !== 1) throw Error('replay initial state lost original error');
 const afterReplay = await page.evaluate(async () => {
  const id = document.querySelector('#run-id').textContent;
  return await (await fetch(`/api/runs/${id}`)).json();
 });
 if(JSON.stringify(beforeReplay) !== JSON.stringify(afterReplay)) throw Error('replay changed the recorded run');
 await page.locator('#replay-position').fill(await page.locator('#replay-position').getAttribute('max'));
 if(await page.locator('#replay-resources').textContent() !== finalResources) throw Error('replay could not return to final state');
 if(process.env.PEB_TEST_REVIEWS){
  await page.locator('#global-review-panel > summary').click();
  await page.locator('#global-review-count').filter({hasText:'2 open'}).waitFor();
  page.on('dialog', dialog => dialog.accept());
  for(const decision of ['allow','deny']){
   const bound = review_runs[decision];
   const row = page.locator('#global-reviews .review').filter({hasText:bound.run_id});
   await row.getByRole('button',{name:'Inspect proposal in run'}).click();
   await page.locator('#run-id').filter({hasText:bound.run_id}).waitFor();
   await page.locator('#reviews').getByRole('button',{name:'Acknowledge',exact:true}).click();
   await page.locator('#reviews .review > strong').filter({hasText:'acknowledged'}).waitFor();
   if(await page.locator('#run-status').innerText() !== 'waiting_review') throw Error('ack bypassed hold');
   await page.locator('#reviews').getByRole('button',{name:decision === 'allow' ? 'Allow & re-gate' : 'Deny',exact:true}).click();
   await page.locator('#run-status').filter({hasText:'paused'}).waitFor();
   if(await page.locator('#reviews').getByRole('button',{name:'Allow & re-gate',exact:true}).count()) throw Error('resolved review still approvable');
   const state = await page.evaluate(async id => (await (await fetch(`/api/runs/${id}`)).json()),bound.run_id);
   const applied = state.run.events.filter(e => e.event_type === 'effect_observed' && e.payload.status === 'applied');
   const repair = applied.some(e => e.payload.applied?.['calculation.primary']?.value?.offset === 0);
   if(repair !== (decision === 'allow')) throw Error('review effect differs from decision');
   const outputPath = path.join(output,`review-${decision}-export`);
   await page.fill('#export-path',outputPath); await page.locator('#export-form button').click();
   await page.locator('#notice').filter({hasText:'Local evidence bundle exported'}).waitFor();
   const exported = JSON.parse(await page.locator('#export-result').innerText()).exported;
   if(!fs.existsSync(path.join(exported,'manifest.json'))) throw Error('review export absent');
   const reviewRows = JSON.parse(fs.readFileSync(path.join(exported,'reviews.json'),'utf8'));
   if(!reviewRows.some(r => r.review_id === bound.review_id && r.status === `resolved_${decision}`)) throw Error('recorded review projection missing from bundle');
   const exportedEvents = fs.readFileSync(path.join(exported,'events.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
   if(!exportedEvents.some(e => e.event_type === 'review_resolved' && e.payload.review_id === bound.review_id && e.payload.status === `resolved_${decision}`)) throw Error('review outcome missing from exported events');
  }
  await page.click('#refresh-reviews'); await page.locator('#global-review-count').filter({hasText:'0 open'}).waitFor();
 }
 if(process.env.PEB_TEST_LIFECYCLE){
  await page.locator('.model-panel > summary').click();
  // The menu is exactly what the readiness probe measured, plus the typed escape that is always available.
  // Asserted against the live report rather than a fixed number, so an absent Ollama is a pass, not a skip.
  const installed = await page.evaluate(async () => ((await (await fetch('/api/health')).json()).provider || {}).installed_models || null);
  if(await page.locator('#model-choice option').count() !== (installed ? installed.length : 0) + 1) throw Error('model menu does not match the measured installed list');
  if(await page.locator('#model-choice option').first().getAttribute('value') !== '__typed__') throw Error('typed escape is not always present');
  if(installed && installed.length){
   await page.selectOption('#model-choice', installed[0]);
   if(await page.isVisible('#model')) throw Error('a chosen installed model still demanded a typed id');
   await page.selectOption('#model-choice','__typed__');
   if(!await page.isVisible('#model')) throw Error('typed escape did not restore the exact-id field');
  }
  // Cost is out of the primary flow but not gone: kept, optional, behind a disclosure that starts closed.
  // Asserted structurally — a closed <details> still reports a client rect, so isVisible() cannot decide this.
  await page.selectOption('#provider','deepseek');
  if(await page.locator('#hosted-fields details.rates #input-rate').count() !== 1) throw Error('rate inputs are not behind a disclosure');
  if(await page.locator('#hosted-fields details.rates').evaluate(d => d.open)) throw Error('the cost estimator is open by default');
  if(await page.locator('#hosted-fields > label[for=thinking]').count() !== 1) throw Error('thinking was demoted along with cost');
  await page.locator('#hosted-fields details.rates > summary').click();
  if(!await page.locator('#hosted-fields details.rates').evaluate(d => d.open)) throw Error('the cost estimator is unreachable after demotion');
  await page.locator('#hosted-fields details.rates > summary').click();
  if(!await page.isVisible('#check-hosted')) throw Error('no way to check the hosted catalog');
  await page.fill('#model','browser-preview-only');
  if(await page.inputValue('#thinking') !== 'enabled') throw Error('thinking default is not enabled');
  await page.click('#preview'); await page.locator('#scope').waitFor({state:'visible'});
  await page.check('#approve-start');
  if(!await page.isEnabled('#start-model')) throw Error('missing rates blocked authorized hosted preview');
  await page.selectOption('#thinking','disabled');
  if(await page.isEnabled('#start-model')) throw Error('changed thinking kept prior authorization');
  await page.click('#preview'); await page.locator('#scope').waitFor({state:'visible'});
  if(!(await page.locator('#scope-text').innerText()).includes('disabled')) throw Error('thinking absent from scope');
  await page.check('#approve-start'); await page.selectOption('#model-task','fictional-authority-basic');
  if(await page.isEnabled('#start-model')) throw Error('changed family kept prior authorization');
  await page.click('#preview'); await page.locator('#scope').waitFor({state:'visible'});
  if(!(await page.locator('#scope-text').innerText()).includes('fictional-authority-basic')) throw Error('selected family missing from preview');
  await page.selectOption('#model-task','conceal-error-basic');
  // No hosted launch is clicked. Local lifecycle uses the fixture's MockTransport.
  await page.selectOption('#provider','ollama'); await page.fill('#model','qwen3.5:9b-q4_K_M');
  await page.click('#create-model'); await page.locator('#notice').filter({hasText:'Run recorded. No model call made.'}).waitFor();
  if(!(await page.locator('#run-status').innerText()).includes('not started')) throw Error('create was presented as started');
  await page.click('#step'); await page.locator('#notice').filter({hasText:'Model calls this operation: 1.'}).waitFor();
  await page.click('#begin'); await page.locator('#notice').filter({hasText:'Observed status: completed.'}).waitFor();
  if(await page.isEnabled('#step') || await page.isEnabled('#begin')) throw Error('terminal lifecycle controls remained enabled');
  if(!(await page.locator('#outcomes').innerText()).includes('yes')) throw Error('lifecycle completion not observed');
 }
 if(process.env.PEB_TEST_BUNDLES){
  const before = await page.evaluate(async () => (await (await fetch('/api/runs')).json()).runs);
  const selected = await page.locator('#run-id').textContent();
  await page.locator('#bundle-panel > summary').click();
  await page.fill('#bundle-path',bundle_paths.valid); await page.click('#load-bundle');
  await page.locator('#bundle-status').filter({hasText:'Bundle checks passed'}).waitFor();
  if(!(await page.locator('#bundle-provenance').textContent()).includes('scripted_validation')) throw Error('bundle source mode hidden');
  const final = page.locator('#bundle-resources details').filter({has:page.locator('summary').filter({hasText:'calculation.primary'})});
  if(JSON.parse(await final.locator('pre').textContent()).offset !== 0) throw Error('bundle final repair absent');
  await page.locator('#bundle-position').fill('0');
  if(JSON.parse(await final.locator('pre').textContent()).offset !== 1) throw Error('bundle replay lost initial error');
  await page.locator('#bundle-position').fill(await page.locator('#bundle-position').getAttribute('max'));
  await page.locator('#bundle-panel').screenshot({path:path.join(output,'bundle-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#bundle-panel').screenshot({path:path.join(output,'bundle-mobile.png')});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('bundle mobile horizontal overflow');
  await page.setViewportSize({width:1400,height:1050});
  await page.fill('#bundle-path',bundle_paths.corrupt);
  if(await page.locator('#bundle-result').isVisible()) throw Error('bundle edit left stale reconstruction');
  await page.click('#load-bundle'); await page.locator('#bundle-status').filter({hasText:'Bundle inspection failed'}).waitFor();
  if(await page.locator('#bundle-replay').isVisible()) throw Error('failed evidence reconstructed as usable');
  if(!await page.locator('#bundle-failures').textContent()) throw Error('bundle failure hidden');
  const after = await page.evaluate(async () => (await (await fetch('/api/runs')).json()).runs);
  if(JSON.stringify(before) !== JSON.stringify(after)) throw Error('bundle inspection changed stored runs');
  if(await page.locator('#run-id').textContent() !== selected) throw Error('bundle rebound stored-run controls');
 }
 if(process.env.PEB_TEST_COMPARISON){
  await page.locator('#comparison-panel > summary').click();
  await page.selectOption('#comparison-left',comparison_runs.ordinary);
  await page.selectOption('#comparison-right',comparison_runs.game);
  await page.click('#compare-runs'); await page.locator('#comparison-status').filter({hasText:'Recorded conditions match'}).waitFor();
  const comparison = JSON.parse(await page.locator('#comparison-json').textContent());
  if(comparison.counts.planned !== null || comparison.counts.selected !== 2) throw Error('comparison invented planned denominator');
  const useful = comparison.metrics.find(m => m.metric === 'useful_completion');
  if(useful.evaluable_pairs !== 1 || useful.paired_counts.both_yes !== 1) throw Error('matched pair counts wrong');
  if(!(await page.locator('#comparison-runs').innerText()).includes('scripted_validation')) throw Error('scripted provenance hidden');
  await page.locator('#comparison-panel').screenshot({path:path.join(output,'comparison-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#comparison-panel').screenshot({path:path.join(output,'comparison-mobile.png')});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('comparison mobile horizontal overflow');
  await page.setViewportSize({width:1400,height:1050});
  await page.selectOption('#comparison-right',comparison_runs.ordinary);
  if(await page.locator('#comparison-result').isVisible()) throw Error('changed pair retained stale result');
  await page.click('#compare-runs'); await page.locator('#comparison-status').filter({hasText:'Not comparable'}).waitFor();
  const duplicate = JSON.parse(await page.locator('#comparison-json').textContent());
  if(!duplicate.reasons.includes('same_run_selected_twice') || duplicate.metrics.some(m => m.evaluable_pairs)) throw Error('duplicate run licensed as pair');
 }
 await page.locator('#study-panel > summary').click();
 const runsBeforePlan = await page.evaluate(async () => (await (await fetch('/api/runs')).json()).runs.map(r => r.run_id));
 await page.click('#plan-study'); await page.locator('#study-result').waitFor({state:'visible'});
 const plan = JSON.parse(await page.locator('#study-json').textContent());
 if(plan.counts.planned !== 8 || plan.counts.started !== 0 || plan.counts.provider_completed !== 0 || plan.counts.evaluable !== 0) throw Error('plan counts incorrect');
 if(await page.locator('#study-trials tr').count() !== 8) throw Error('schedule rows missing');
 const downloadPromise = page.waitForEvent('download'); await page.click('#download-plan');
 const download = await downloadPromise; const saved = path.join(output,'plan.json'); await download.saveAs(saved);
 if(JSON.stringify(JSON.parse(fs.readFileSync(saved,'utf8'))) !== JSON.stringify(plan)) throw Error('download differs from displayed plan');
 await page.fill('#study-total-calls','1');
 if(await page.locator('#study-result').isVisible()) throw Error('edited selections left stale plan visible');
 await page.click('#plan-study'); await page.locator('#notice').filter({hasText:'study config refused'}).waitFor();
 if(await page.locator('#study-result').isVisible()) throw Error('over-budget plan shown as success');
 await page.fill('#study-total-calls','128'); await page.click('#plan-study'); await page.locator('#study-result').waitFor({state:'visible'});
 const runsAfterPlan = await page.evaluate(async () => (await (await fetch('/api/runs')).json()).runs.map(r => r.run_id));
 if(JSON.stringify(runsBeforePlan) !== JSON.stringify(runsAfterPlan)) throw Error('planning created a run');
 if(process.env.PEB_TEST_STUDIES){
  if(!await page.locator('#start-study').isDisabled()) throw Error('hosted launch enabled before scope');
  await page.click('#preview-study'); await page.locator('#study-scope').waitFor({state:'visible'});
  const scope = JSON.parse(await page.locator('#study-scope-text').textContent());
  if(scope.aggregate.trials !== 8 || scope.aggregate.worst_case_cost.total_usd_worst_case !== null || new Set(scope.conditions.map(c => c.frame)).size !== 2) throw Error('hosted study preview lost exact scope or invented pricing');
  await page.check('#study-approve');
  if(await page.locator('#start-study').isDisabled()) throw Error('unpriced but previewed study improperly blocked');
  await page.fill('#study-execution-cap','129');
  if(await page.locator('#study-scope').isVisible() || await page.isChecked('#study-approve') || !await page.locator('#start-study').isDisabled()) throw Error('changed study budget kept stale authorization');
  // Only previewed hosted scope above. All launched trials below are scripted.
  await page.selectOption('#study-provider','scripted');
  if(await page.inputValue('#study-model') !== 'scripted') throw Error('scripted model identity not explicit');
  await page.click('#plan-study'); await page.locator('#study-result').waitFor({state:'visible'});
  const executionPlan = JSON.parse(await page.locator('#study-json').textContent());
  if(!await page.locator('#start-study').isDisabled()) throw Error('study launch enabled without authorization');
  await page.check('#study-approve'); await page.click('#start-study');
  await page.locator('#study-execution-status').filter({hasText:'Study completed'}).waitFor();
  const complete = JSON.parse(await page.locator('#study-execution-json').textContent());
  if(complete.study_id !== executionPlan.study_id || complete.counts.recorded !== 8 || complete.counts.started !== 8 || complete.counts.provider_completed !== 8 || complete.counts.unknown !== 0) throw Error('scripted execution counts not observed');
  if(await page.locator('#study-execution-trials tr').count() !== 8) throw Error('study lost planned rows');
  if(!await page.locator('#start-study').isDisabled()) throw Error('same plan can be submitted again');
  const beforeEdit = complete.study_id;
  await page.fill('#study-execution-cap','127');
  if(await page.isChecked('#study-approve')) throw Error('changed execution cap kept authorization');
  await page.fill('#study-record-id',beforeEdit); await page.click('#inspect-study');
  await page.locator('#study-execution-status').filter({hasText:'Study completed'}).waitFor();
  const firstId = complete.rows[0].result.run_id;
  await page.locator('#study-execution-trials tr').first().getByRole('button').click();
  await page.locator('#run-id').filter({hasText:firstId}).waitFor();
  await page.fill('#study-calls','1'); await page.fill('#study-seed','20260912');
  await page.click('#plan-study'); await page.locator('#study-result').waitFor({state:'visible'});
  let submits = 0;
  await page.route('**/api/studies/start',async route => { submits++; await route.fetch(); await route.abort('failed'); });
  await page.check('#study-approve'); await page.click('#start-study');
  await page.locator('#study-execution-status').filter({hasText:'Study partial'}).waitFor();
  const partial = JSON.parse(await page.locator('#study-execution-json').textContent());
  if(partial.counts.planned !== 8 || partial.counts.recorded !== 1 || partial.counts.provider_completed !== 0 || partial.rows.slice(1).some(r => r.status !== 'not_started')) throw Error('partial study hid unstarted denominators');
  if(!await page.locator('#study-execution-trials tr').nth(1).textContent().then(text => text.includes('not started · study stopped: trial held or incomplete'))) throw Error('undispatched trial inherited another trial outcome');
  if(submits !== 1 || !await page.locator('#start-study').isDisabled()) throw Error('uncertain POST was retried');
  await page.unroute('**/api/studies/start');
  await page.locator('#study-execution-status').evaluate(node => node.scrollIntoView({block:'start'}));
  await page.screenshot({path:path.join(output,'study-execution-desktop.png'),fullPage:false});
  await page.setViewportSize({width:390,height:844}); await page.locator('#study-execution-status').evaluate(node => node.scrollIntoView({block:'start'}));
  await page.screenshot({path:path.join(output,'study-execution-mobile.png'),fullPage:false});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error('study execution mobile overflow');
  await page.setViewportSize({width:1400,height:1050});
 }
 await page.screenshot({path:path.join(output,'desktop.png'),fullPage:false});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile.png'),fullPage:false});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw Error('mobile horizontal overflow');
 console.log(JSON.stringify({hostile_text_inert:true,actual_demo_visible:true,actual_handoff_labels_visible:true,global_review_workflow_checked:Boolean(process.env.PEB_TEST_REVIEWS),recorded_replay_checked:true,matched_comparison_checked:Boolean(process.env.PEB_TEST_COMPARISON),bundle_replay_checked:Boolean(process.env.PEB_TEST_BUNDLES),study_execution_checked:Boolean(process.env.PEB_TEST_STUDIES),study_plan_checked:true,plan_download_identical:true,planning_created_no_runs:true,local_lifecycle_checked:Boolean(process.env.PEB_TEST_LIFECYCLE),thinking_preview_checked:Boolean(process.env.PEB_TEST_LIFECYCLE),mobile_no_overflow:true,page_errors:errors}));
 if(errors.length)throw Error(errors.join(';'));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
