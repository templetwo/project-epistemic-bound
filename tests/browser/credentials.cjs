// Credential UI regression with an invented sentinel; no real key, provider call, or inference.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const [loginFile, output] = process.argv.slice(2);
if (!loginFile || !output) throw Error('usage: node tests/browser/credentials.cjs LOGIN_FILE OUTPUT_DIRECTORY');
const syntheticKey = 'synthetic-ui-credential-NOT-A-REAL-KEY-4831';
const gate = () => { let release; const promise = new Promise(resolve => { release = resolve; }); return {promise, release}; };
(async () => {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.PEB_BROWSER_EXECUTABLE});
  const page = await browser.newPage({viewport: {width: 1400, height: 1000}});
  const checks = []; let pageErrors = 0, saveCount = 0, clearCount = 0, catalogCount = 0, otherMutationCount = 0, postedOnlyKey = true, sentinelSeen = false;
  let entered = false, environment = false, mutationMode = 'success', statusMode = 'success', hold = null, catalogHold = null;
  page.on('pageerror', () => { pageErrors++; });
  const check = (name, value) => { assert.ok(value, name); checks.push(name); console.log('PASS ' + name); };
  const json = (route, body, status = 200) => route.fulfill({status, contentType: 'application/json', body: JSON.stringify(body)});
  const status = () => ({provider: 'deepseek', key: entered || environment ? 'present' : 'absent', source: entered ? 'secure_input' : environment ? 'environment' : 'absent', lifetime: 'server_process', can_clear: entered, note: syntheticKey});
  await page.route('**/api/credentials/**', async route => {
    const request = route.request(), clear = new URL(request.url()).pathname.endsWith('/clear');
    if (request.method() === 'GET') {
      if (statusMode === 'unauthorized') return json(route, {error: {message: syntheticKey}}, 401);
      return json(route, status());
    }
    if (clear) { clearCount++; postedOnlyKey &&= JSON.stringify(request.postDataJSON()) === '{}'; entered = false; }
    else {
      saveCount++; const body = request.postDataJSON();
      postedOnlyKey &&= Object.keys(body).join(',') === 'api_key'; sentinelSeen ||= body.api_key === syntheticKey;
      if (mutationMode !== 'refused') entered = true;
    }
    if (hold) await hold.promise;
    if (mutationMode === 'lost') return route.abort('failed');
    if (mutationMode === 'refused') return json(route, {error: {message: syntheticKey, input: syntheticKey}}, 400);
    return json(route, status());
  });
  await page.route('**/api/health', async route => {
    if (route.request().postDataJSON()?.check_hosted) { catalogCount++; if (catalogHold) await catalogHold.promise; return json(route, {hosted: {status: 'ok', available_models: ['synthetic-hosted'], endpoint_host: 'api.deepseek.com'}}); }
    return json(route, {provider: {endpoint: 'http://127.0.0.1:9', installed_models: ['synthetic-local']}, credentials: {deepseek: {key: entered ? 'present' : 'absent'}}});
  });
  await page.route('**/api/runs/preview', route => { const body = route.request().postDataJSON(); return json(route, {scope: body, start_payload: {...body, confirm: true}, preview_token: 'synthetic-preview'}); });
  page.on('request', request => {
    const pathname = new URL(request.url()).pathname;
    if (request.method() !== 'GET' && !pathname.startsWith('/api/credentials/') && !['/api/auth/login', '/api/auth/logout', '/api/health', '/api/runs/preview'].includes(pathname)) otherMutationCount++;
  });
  const leakFree = async () => page.evaluate(sentinel => {
    const values = [...document.querySelectorAll('input,textarea')].map(input => input.value);
    const productState = {preview, studyPreview, studyPlan, selectedState, replayEvents, bundleEvents, credentialStatus};
    return !document.documentElement.outerHTML.includes(sentinel) && !document.body.textContent.includes(sentinel) && !values.some(value => value.includes(sentinel)) && !JSON.stringify(localStorage).includes(sentinel) && !JSON.stringify(sessionStorage).includes(sentinel) && !JSON.stringify(productState).includes(sentinel) && !document.querySelector('#notice').textContent.includes(sentinel);
  }, syntheticKey);
  const open = async (id = 'open-credentials') => { await page.click('#' + id); await page.locator('#credential-message').filter({hasText: 'Status read from this server'}).waitFor(); };
  const inputCleared = async () => await page.inputValue('#credential-key') === '';
  try {
    await page.goto('http://127.0.0.1:8789');
    check('secure input entry is hidden before operator login', await page.locator('#open-credentials').isHidden());
    await page.fill('#secret', JSON.parse(fs.readFileSync(loginFile, 'utf8')).secret); await page.locator('#login-form button').click(); await page.locator('#runs button').first().waitFor();
    await page.locator('#runs button').first().click(); await page.locator('#events .event').first().waitFor();
    const before = await page.evaluate(async () => {
      const rows = (await (await fetch('/api/runs')).json()).runs;
      return await Promise.all(rows.map(async row => (await (await fetch(`/api/runs/${row.run_id}`)).json())));
    });
    await open();
    check('native accessible dialog focuses masked non-autocomplete input', await page.getByRole('dialog', {name: 'Secure API input'}).isVisible() && await page.locator('#credential-key').getAttribute('type') === 'password' && await page.locator('#credential-key').getAttribute('autocomplete') === 'off' && await page.locator('#credential-key').evaluate(input => input === document.activeElement));
    check('process lifetime and signout distinction visible', (await page.textContent('#credential-lifetime')).includes('signing out does not remove') && (await page.textContent('#credential-lifetime')).includes('server restarts'));
    check('no reveal or copy affordance', await page.getByRole('dialog').getByRole('button', {name: /reveal|copy|show key/i}).count() === 0);
    await page.fill('#credential-key', syntheticKey); await page.keyboard.press('Escape');
    check('Escape clears input and restores opener focus', await inputCleared() && !await page.locator('#credential-dialog').evaluate(dialog => dialog.open) && await page.locator('#open-credentials').evaluate(button => button === document.activeElement));
    await open(); await page.fill('#credential-key', syntheticKey); await page.click('#credential-cancel');
    check('close button clears input without sending key', await inputCleared() && saveCount === 0);
    await open(); await page.fill('#credential-key', syntheticKey); await page.locator('#credential-dialog').evaluate(dialog => dialog.close()); await page.waitForTimeout(50);
    check('native programmatic close clears input', await inputCleared());
    await page.locator('.model-panel > summary').click(); await page.selectOption('#provider', 'deepseek'); await page.fill('#model', 'synthetic-hosted'); await page.click('#check-hosted');
    await page.locator('#notice').filter({hasText: 'currently offered'}).waitFor();
    await page.click('#preview'); await page.locator('#scope').waitFor({state: 'visible'}); await page.check('#approve-start');
    // Build a fake cached study preview too; this is UI data and dispatches nothing.
    await page.evaluate(() => { studyPreview = {preview_token: 'stale-study-preview'}; document.querySelector('#study-scope').hidden = false; document.querySelector('#study-approve').checked = true; });
    catalogHold = gate(); await page.click('#check-hosted');
    await open('hosted-credentials'); await page.fill('#credential-key', syntheticKey); hold = gate(); await page.click('#credential-save');
    check('submit clears DOM before network response and prevents duplicate saves', await inputCleared() && !await page.isEnabled('#credential-save') && !await page.isEnabled('#credential-key'));
    await page.screenshot({path: path.join(output, 'pending-blank-dialog.png')});
    hold.release(); hold = null; await page.locator('#credential-message').filter({hasText: 'Key available for new runs and catalog checks'}).waitFor();
    check('only dedicated credential payload receives synthetic key', sentinelSeen && postedOnlyKey && saveCount === 1);
    check('save uses server memory and makes no catalog or run call', (await page.textContent('#credential-status')).includes('entered for this running server') && catalogCount === 2 && otherMutationCount === 0);
    check('successful save invalidates hosted catalog and both authorizations', await page.evaluate(() => hostedModels === null && preview === null && studyPreview === null && !document.querySelector('#approve-start').checked && !document.querySelector('#study-approve').checked));
    catalogHold.release(); catalogHold = null; await page.waitForTimeout(100);
    check('late catalog response from prior credential cannot restore stale choices', await page.evaluate(() => hostedModels === null));
    check('saved key and reflected status text absent from DOM storage model state and notice', await leakFree());
    await page.screenshot({path: path.join(output, 'saved-blank-dialog.png')});
    environment = true; await page.click('#credential-forget'); await page.locator('#credential-message').filter({hasText: 'Entered key forgotten'}).waitFor();
    check('forget shows environment fallback without exposing a value', clearCount === 1 && (await page.textContent('#credential-status')).includes('inherited from the server environment') && !await page.isEnabled('#credential-forget') && await leakFree());
    mutationMode = 'refused'; await page.fill('#credential-key', syntheticKey); await page.click('#credential-save'); await page.locator('#credential-message').filter({hasText: 'not confirmed; check status'}).waitFor();
    check('reflected credential validation error remains generic and input clears', await inputCleared() && await leakFree());
    mutationMode = 'lost'; await page.fill('#credential-key', syntheticKey); await page.click('#credential-save'); await page.locator('#credential-message').filter({hasText: 'not confirmed; check status'}).waitFor();
    check('unknown network outcome is explicit and not automatically retried', saveCount === 3 && await inputCleared() && await leakFree());
    mutationMode = 'success'; await page.click('#credential-refresh'); await page.locator('#credential-message').filter({hasText: 'Status read from this server'}).waitFor();
    check('status reconciles a lost save response without resubmission', saveCount === 3 && (await page.textContent('#credential-status')).includes('entered for this running server'));
    await page.fill('#credential-key', syntheticKey); await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
    check('pagehide clears input and closes dialog', await inputCleared() && !await page.locator('#credential-dialog').evaluate(dialog => dialog.open));
    await open(); await page.fill('#credential-key', syntheticKey); statusMode = 'unauthorized'; await page.click('#credential-refresh'); await page.locator('#signin').waitFor({state: 'visible'});
    check('401 clears input closes dialog and removes authenticated entry', await inputCleared() && !await page.locator('#credential-dialog').evaluate(dialog => dialog.open) && await page.locator('#open-credentials').isHidden() && await leakFree());
    statusMode = 'success'; await page.fill('#secret', JSON.parse(fs.readFileSync(loginFile, 'utf8')).secret); await page.locator('#login-form button').click(); await page.locator('#open-credentials').waitFor({state: 'visible'});
    await open(); await page.fill('#credential-key', syntheticKey); await page.evaluate(() => document.querySelector('#logout').click()); await page.locator('#signin').waitFor({state: 'visible'});
    check('operator signout clears DOM while process credential remains', await inputCleared() && entered && !await page.locator('#credential-dialog').evaluate(dialog => dialog.open));
    await page.fill('#secret', JSON.parse(fs.readFileSync(loginFile, 'utf8')).secret); await page.locator('#login-form button').click(); await page.locator('#open-credentials').waitFor({state: 'visible'});
    const after = await page.evaluate(async () => {
      const rows = (await (await fetch('/api/runs')).json()).runs;
      return await Promise.all(rows.map(async row => (await (await fetch(`/api/runs/${row.run_id}`)).json())));
    });
    check('credential UI leaves all recorded runs and evidence unchanged', JSON.stringify(before) === JSON.stringify(after) && !JSON.stringify(after).includes(syntheticKey));
    await page.setViewportSize({width: 390, height: 844}); await open();
    check('dialog and new header entry fit mobile width', !await page.evaluate(() => document.documentElement.scrollWidth > innerWidth) && await page.locator('#credential-dialog').evaluate(dialog => dialog.getBoundingClientRect().width <= innerWidth));
    await page.screenshot({path: path.join(output, 'mobile-blank-dialog.png')});
    check('no page errors or unintended mutations', pageErrors === 0 && otherMutationCount === 0);
    fs.writeFileSync(path.join(output, 'credentials-results.json'), JSON.stringify({passed: checks.length, checks, pageErrors, saveCount, clearCount, catalogCount, otherMutationCount}, null, 2));
    console.log(JSON.stringify({passed: checks.length, pageErrors, saveCount, clearCount, catalogCount, otherMutationCount}));
  } catch (error) { await page.evaluate(() => { document.querySelector('#credential-key').value = ''; }); console.error(await page.evaluate(() => ({viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, overflow: [...document.querySelectorAll('body *')].map(node => ({id: node.id, tag: node.tagName, right: node.getBoundingClientRect().right, width: node.getBoundingClientRect().width})).filter(node => node.right > innerWidth).slice(0, 10)}))); await page.screenshot({path: path.join(output, 'failure-blank.png')}); throw error; } finally { await browser.close(); }
})().catch(error => { console.error('Credential UI regression failed; no request or input values logged.'); const location = String(error.stack || '').split('\n').find(line => line.includes('credentials.cjs:')); if (location) console.error(location); process.exitCode = 1; });
