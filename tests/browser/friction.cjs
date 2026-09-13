// Deterministic UI race regressions. Run against tests/browser/fixture_server.py on 8789.
// Every launch and capability request below is intercepted: no inference or paid network call.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const [loginFile, output] = process.argv.slice(2);
if (!loginFile || !output) throw Error('usage: node tests/browser/friction.cjs LOGIN_FILE OUTPUT_DIRECTORY');
const gate = () => { let release; const promise = new Promise(r => { release = r; }); return {promise, release}; };
(async () => {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.PEB_BROWSER_EXECUTABLE});
  const page = await browser.newPage({viewport: {width: 1400, height: 1050}});
  const errors = [], checks = [];
  page.on('pageerror', e => errors.push(e.message));
  const check = (name, value) => { assert.ok(value, name); checks.push(name); console.log('PASS ' + name); };
  const json = (route, value) => route.fulfill({contentType: 'application/json', body: JSON.stringify(value)});
  await page.route('**/api/health', route => {
    const payload = route.request().postDataJSON();
    if (payload?.check_hosted) return json(route, {hosted: {status: 'key_absent', key_env: 'PEB_DEEPSEEK_API_KEY'}});
    if (payload?.ollama_model) return json(route, {ollama_model: {status: 'ok', model: payload.ollama_model, capabilities: ['completion'], family: 'synthetic', advertised_context_length: 8192, configured_num_ctx: null, active_context_length: null, compatibility: 'not_tested'}});
    return json(route, {provider: {endpoint: 'http://127.0.0.1:9', installed_models: ['mock-local']}});
  });
  try {
    await page.goto('http://127.0.0.1:8789');
    await page.fill('#secret', JSON.parse(fs.readFileSync(loginFile, 'utf8')).secret);
    await page.locator('#login-form button').click();
    await page.locator('#runs button').first().waitFor();
    const initial = await page.evaluate(async () => (await (await fetch('/api/runs')).json()).runs);
    const template = await page.evaluate(async id => (await (await fetch(`/api/runs/${id}`)).json()), initial[0].run_id);
    const records = new Map();
    const localId = 'run_' + 'a'.repeat(32), hostedId = 'run_' + 'b'.repeat(32), unrelatedId = 'run_' + 'c'.repeat(32);
    let createCount = 0, startCount = 0, observeCount = 0, previewCount = 0;
    let localPayload, hostedPayload, previewPayload, localPending = false, hostedPending = false;
    const localGate = gate(), hostedGate = gate(), previewGate = gate(), verifyGate = gate();
    let verifySeen = false;
    const hostile = '<img src=x onerror="window.__frictionInjected=1"> unclassified response';
    const event = (seq, type, payload) => ({seq, event_type: type, ts: new Date(Date.now() - 4000).toISOString(), actor: 'subject', payload});
    const record = (id, payload) => {
      const data = structuredClone(template);
      data.status = 'created';
      data.run.manifest = {...data.run.manifest, run_id: id, task_id: payload.task, provider_kind: payload.provider, model_requested: payload.model, profile_id: payload.profile, limits: {max_model_calls: payload.max_model_calls, request_timeout_s: 120}, settings: {format_correction_limit: payload.format_correction_limit, ui_launch_id: payload.ui_launch_id}};
      data.run.events = [event(0, 'run_created', {resources: []})];
      data.reviews = []; data.held = {}; data.run.commitments = []; data.run.corrections = [];
      records.set(id, data); return data;
    };
    const start = data => { data.status = 'running'; data.run.events.push(event(1, 'model_request', {step: 1, model_requested: data.run.manifest.model_requested, message_count: 2})); };
    const finish = (data, invalid) => {
      if (invalid) data.run.events.push(event(2, 'model_response', {step: 1, content: hostile, reasoning: 'retained local thinking', finish_reason: 'stop'}), event(3, 'decision_invalid', {step: 1, reason: 'invalid JSON: expected object', format_correction_scheduled: true, correction_number: 1, correction_limit: 1}), event(4, 'model_request', {step: 2, model_requested: data.run.manifest.model_requested, correction_of_step: 1, correction_number: 1}), event(5, 'model_response', {step: 2, content: '{"kind":"finish"}', finish_reason: 'stop'}));
      else data.run.events.push(event(2, 'model_response', {step: 1, content: '{"kind":"finish"}', finish_reason: 'stop'}));
      data.run.events.push(event(data.run.events.length, 'decision_recorded', {step: invalid ? 2 : 1, kind: 'finish', statement: 'mocked completion'}), event(data.run.events.length + 1, 'run_finished', {status: 'completed', terminal_reason: 'finished', model_calls: invalid ? 2 : 1}));
      data.status = 'completed';
    };
    await page.route('**/api/runs', async route => {
      if (route.request().method() === 'POST') { createCount++; localPayload = route.request().postDataJSON(); record(localId, localPayload); return json(route, {run_id: localId, status: 'created'}); }
      return json(route, {runs: [...initial, ...[...records].map(([id, d]) => ({run_id: id, mode: 'model_observation', status: d.status, ui_launch_id: d.run.manifest.settings.ui_launch_id}))]});
    });
    await page.route('**/api/runs/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/runs/preview') {
        previewCount++; previewPayload = route.request().postDataJSON();
        if (previewCount === 1) await previewGate.promise;
        return json(route, {scope: {...previewPayload, response_format: 'json'}, start_payload: {...previewPayload, confirm: true}, preview_token: 'mock-bound-ticket'});
      }
      if (url.pathname === '/api/runs/observe') {
        observeCount++; hostedPayload = route.request().postDataJSON();
        const d = record(hostedId, hostedPayload); start(d);
        record(unrelatedId, {...hostedPayload, ui_launch_id: 'unrelated-launch'});
        hostedPending = true; await hostedGate.promise; hostedPending = false; finish(d, false);
        return json(route, {run_id: hostedId, status: 'completed'});
      }
      if (url.pathname === `/api/runs/${localId}/start`) {
        startCount++; const d = records.get(localId); start(d); localPending = true;
        await localGate.promise; localPending = false; finish(d, true);
        return json(route, {run_id: localId, status: 'completed', steps_taken: 2});
      }
      if (url.pathname === `/api/runs/${initial[0].run_id}/verify`) {
        verifySeen = true; await verifyGate.promise; return json(route, {run_id: initial[0].run_id, marker: 'STALE VERIFICATION MUST NOT APPEAR'});
      }
      const match = url.pathname.match(/^\/api\/runs\/([^/]+)(\/events)?$/), d = match && records.get(match[1]);
      if (d) {
        if (match[2]) { const cursor = Number(url.searchParams.get('cursor') || 0), limit = Number(url.searchParams.get('limit') || 50); const events = d.run.events.slice(cursor, cursor + limit); return json(route, {events, total: d.run.events.length, next_cursor: cursor + events.length < d.run.events.length ? cursor + events.length : null}); }
        return json(route, d);
      }
      return route.continue();
    });

    await page.locator('#runs button').filter({hasText: initial[0].run_id.slice(0, 18)}).click();
    await page.locator('#run-id').filter({hasText: initial[0].run_id}).waitFor();
    await page.click('#verify');
    for (let i = 0; !verifySeen && i < 100; i++) await page.waitForTimeout(10); assert.ok(verifySeen, 'verify request reached mock');
    await page.locator('#runs button').filter({hasText: initial[1].run_id.slice(0, 18)}).click();
    await page.locator('#run-id').filter({hasText: initial[1].run_id}).waitFor();
    verifyGate.release(); await page.waitForTimeout(100);
    check('verify response discarded after selected-run change', await page.locator('#verification').isHidden());

    await page.locator('.model-panel > summary').click(); await page.selectOption('#model-choice', 'mock-local');
    await page.click('#inspect-model'); await page.locator('#model-capabilities').waitFor({state: 'visible'});
    check('native capability metadata shown without model blacklist', (await page.locator('#model-capability-json').textContent()).includes('completion') && (await page.locator('#model-capabilities').textContent()).includes('does not prove'));
    check('visible correction default is one', await page.inputValue('#format-corrections') === '1');
    await page.check('#approve-start'); await page.click('#start-model');
    await page.locator('#live-state').filter({hasText: 'AWAITING MODEL'}).waitFor();
    check('slow local launch observed before response', localPending && await page.textContent('#run-id') === localId);
    check('elapsed model wait comes from committed timestamp', /[4-9]s|\d{2,}s/.test(await page.textContent('#live-head')));
    check('pause and cancel remain available while inference controls stay disabled', await page.isEnabled('#pause') && await page.isEnabled('#cancel') && !await page.isEnabled('#step') && !await page.isEnabled('#begin'));
    check('launch form stays locked while request pending', !await page.isEnabled('#start-model') && !await page.isEnabled('#provider') && !await page.isEnabled('#approve-start'));
    await page.evaluate(() => document.querySelector('#model-form').dispatchEvent(new SubmitEvent('submit', {bubbles: true, cancelable: true, submitter: document.querySelector('#start-model')})));
    check('duplicate local submit does not relaunch', createCount === 1 && startCount === 1);
    check('correction limit sent in exact local create payload', localPayload.format_correction_limit === 1 && /^[0-9a-f]{32}$/.test(localPayload.ui_launch_id));
    await page.screenshot({path: path.join(output, 'slow-local-launch.png'), fullPage: true});
    localGate.release(); await page.locator('#notice').filter({hasText: 'Run reached a boundary'}).waitFor();
    await page.locator('#live-state').filter({hasText: 'BOUNDARY REACHED'}).waitFor();
    check('draining live events does not re-enable a completed run', await page.textContent('#run-status') === 'completed' && !await page.isEnabled('#step') && !await page.isEnabled('#begin'));
    check('invalid text and validation exposed in selected-run view', (await page.textContent('#response-checks')).includes(hostile) && (await page.textContent('#response-checks')).includes('invalid JSON: expected object'));
    check('recorded correction count and unclassified status shown', (await page.textContent('#response-check-summary')).includes('1 format correction call requested / 1 authorized') && (await page.textContent('#response-checks')).includes('unclassified model text'));
    check('local reasoning retention described without false universal claim', (await page.textContent('#live')).includes('retained local thinking') && !(await page.textContent('#live')).includes('local model never'));
    check('hostile response inert in live and permanent panels', !await page.evaluate(() => window.__frictionInjected) && await page.locator('#live img, #live script, #response-checks img, #response-checks script').count() === 0);
    await page.screenshot({path: path.join(output, 'invalid-response.png'), fullPage: true});

    await page.selectOption('#provider', 'deepseek'); await page.fill('#model', 'mock-hosted');
    await page.click('#check-hosted'); await page.locator('#notice').filter({hasText: "running server's environment"}).waitFor();
    check('credential notice distinguishes server environment from operator login', (await page.textContent('#notice')).includes('operator secret') && (await page.textContent('#notice')).includes('restart that server'));
    await page.click('#preview');
    check('pending preview disables authorization and launch', !await page.isEnabled('#approve-start') && !await page.isEnabled('#start-model') && !await page.isEnabled('#model'));
    previewGate.release(); await page.locator('#scope').waitFor({state: 'visible'}); await page.check('#approve-start');
    await page.fill('#calls', '3');
    check('changed budget invalidates preview and authorization', !await page.isEnabled('#start-model') && !await page.isChecked('#approve-start') && await page.locator('#scope').isHidden());
    await page.click('#preview'); await page.locator('#scope').waitFor({state: 'visible'});
    await page.check('#approve-start'); await page.click('#start-model');
    await page.locator('#run-id').filter({hasText: hostedId}).waitFor(); await page.locator('#live-state').filter({hasText: 'AWAITING MODEL'}).waitFor();
    check('quick preview-authorize-start needs only one launch click', hostedPending && observeCount === 1);
    check('hosted request retains exact preview and correction budget', hostedPayload.preview_token === 'mock-bound-ticket' && hostedPayload.ui_launch_id === previewPayload.ui_launch_id && hostedPayload.format_correction_limit === 1 && hostedPayload.max_model_calls === 3);
    check('hosted observer selects correlated run despite unrelated newest record', await page.textContent('#run-id') === hostedId && !(await page.textContent('#live-head')).includes(unrelatedId));
    await page.evaluate(() => document.querySelector('#model-form').dispatchEvent(new SubmitEvent('submit', {bubbles: true, cancelable: true, submitter: document.querySelector('#start-model')})));
    check('duplicate hosted submit cannot reuse authorization', observeCount === 1 && !await page.isChecked('#approve-start'));
    hostedGate.release(); await page.locator('#notice').filter({hasText: 'Run reached a boundary'}).waitFor();
    check('launch form restores after completion with authorization cleared', await page.isEnabled('#provider') && !await page.isEnabled('#start-model'));
    check('no page errors', errors.length === 0);
    fs.writeFileSync(path.join(output, 'friction-results.json'), JSON.stringify({checks, errors, createCount, startCount, observeCount, previewCount}, null, 2));
    console.log(JSON.stringify({passed: checks.length, checks}, null, 2));
  } catch (error) { console.error('Page errors:', errors, 'Notice:', await page.textContent('#notice')); await page.screenshot({path: path.join(output, 'failure.png'), fullPage: true}); throw error; } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
