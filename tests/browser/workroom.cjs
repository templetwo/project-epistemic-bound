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
 const {secret}=JSON.parse(fs.readFileSync(login,'utf8'));
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

 if(process.env.PEB_TEST_LIFECYCLE){
  await page.locator('.model-panel > summary').click();
  await page.selectOption('#provider','deepseek'); await page.fill('#model','browser-preview-only');
  if(await page.inputValue('#thinking') !== 'enabled') throw Error('thinking default is not enabled');
  await page.click('#preview'); await page.locator('#scope').waitFor({state:'visible'});
  await page.check('#approve-start');
  if(!await page.isEnabled('#start-model')) throw Error('missing rates blocked authorized hosted preview');
  await page.selectOption('#thinking','disabled');
  if(await page.isEnabled('#start-model')) throw Error('changed thinking kept prior authorization');
  await page.click('#preview'); await page.locator('#scope').waitFor({state:'visible'});
  if(!(await page.locator('#scope-text').innerText()).includes('disabled')) throw Error('thinking absent from scope');
  // No hosted launch is clicked. Local lifecycle uses the fixture's MockTransport.
  await page.selectOption('#provider','ollama'); await page.fill('#model','qwen3.5:9b-q4_K_M');
  await page.click('#create-model'); await page.locator('#notice').filter({hasText:'Run recorded. No model call made.'}).waitFor();
  if(!(await page.locator('#run-status').innerText()).includes('not started')) throw Error('create was presented as started');
  await page.click('#step'); await page.locator('#notice').filter({hasText:'Model calls this operation: 1.'}).waitFor();
  await page.click('#begin'); await page.locator('#notice').filter({hasText:'Observed status: completed.'}).waitFor();
  if(await page.isEnabled('#step') || await page.isEnabled('#begin')) throw Error('terminal lifecycle controls remained enabled');
  if(!(await page.locator('#outcomes').innerText()).includes('yes')) throw Error('lifecycle completion not observed');
 }
 await page.screenshot({path:path.join(output,'desktop.png'),fullPage:false});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile.png'),fullPage:false});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw Error('mobile horizontal overflow');
 console.log(JSON.stringify({hostile_text_inert:true,actual_demo_visible:true,actual_handoff_labels_visible:true,local_lifecycle_checked:Boolean(process.env.PEB_TEST_LIFECYCLE),thinking_preview_checked:Boolean(process.env.PEB_TEST_LIFECYCLE),mobile_no_overflow:true,page_errors:errors}));
 if(errors.length)throw Error(errors.join(';'));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
