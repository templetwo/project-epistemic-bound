// One explained run-detail slice on five actual published records. Never runs a model.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const [loginFile, output] = process.argv.slice(2);
if (!loginFile || !output) throw Error('usage: node tests/browser/explained_run.cjs LOGIN_FILE OUTPUT_DIRECTORY');
const {secret, origin, runs} = JSON.parse(fs.readFileSync(loginFile, 'utf8'));
fs.mkdirSync(output, {recursive: true});

function evidenceAtEvaluation(data) {
  const events = data.run.events;
  const evaluationEvent = [...events].reverse().find(e => e.event_type === 'evaluation_recorded');
  assert(evaluationEvent, 'published record must retain its evaluation');
  const values = new Map();
  for (const event of events.filter(e => e.seq <= evaluationEvent.seq)) {
    if (event.event_type === 'run_created') for (const resource of event.payload.resources) values.set(resource.resource_id, resource);
    if (event.event_type === 'effect_observed' && event.payload.status === 'applied') {
      for (const [id, resource] of Object.entries(event.payload.applied || {})) values.set(id, {resource_id: id, ...resource});
    }
  }
  return {values, evaluation: evaluationEvent.payload.evaluation, evaluationEvent};
}

async function select(page, run) {
  await page.locator('#runs button').filter({hasText: run.run_id.slice(0, 18)}).click();
  await page.locator('#run-id').filter({hasText: new RegExp(`^${run.run_id}$`)}).waitFor({state: 'visible'});
  await page.locator('#run-explained').waitFor({state: 'visible'});
  await page.locator('#events .event').first().waitFor({state: 'visible'});
}

async function recordedLabels(page, expected) {
  assert.deepEqual(await page.locator('#outcomes .outcome').evaluateAll(rows => rows.slice(0, 2).map(row => row.dataset.outcomeKey)),
    ['structured_task_complete', 'useful_completion'], 'structured completion and useful completion must lead the outcome cards');
  const actual = await page.locator('#outcomes .outcome').evaluateAll(rows => Object.fromEntries(rows.map(row => [
    row.dataset.outcomeKey, row.querySelector(':scope > strong').textContent,
  ])));
  assert.deepEqual(actual, expected, 'displayed labels must exactly equal the stored evaluation');
}

async function checkSelected(page, run, data) {
  const {values, evaluation} = evidenceAtEvaluation(data);
  await recordedLabels(page, run.recorded_labels);
  assert.deepEqual(evaluation.behavior_labels, run.recorded_labels);
  assert((await page.locator(`#outcomes .outcome[data-outcome-key="${run.causal_outcome}"] .outcome-explanation`).innerText()).includes(run.causal_sentence));
  assert((await page.locator('#run-predicate-version').innerText()).includes(run.predicate_version));
  assert((await page.locator('#run-summary').innerText()).includes(values.get('report.primary').value.summary));
  const terminal = [...data.run.events].reverse().find(e => e.event_type === 'run_finished');
  assert((await page.locator('#run-terminal-reason').innerText()).replaceAll('_', ' ').toLowerCase().includes(terminal.payload.terminal_reason.replaceAll('_', ' ')));
  const calls = data.run.events.filter(e => e.event_type === 'model_request').length;
  const budget = await page.locator('#run-budget').innerText();
  assert(budget.includes(String(calls)) && budget.includes(String(data.run.manifest.limits.max_model_calls)));
  for (const resourceId of ['check.initial', 'calculation.primary', 'check.latest', 'report.primary']) {
    const cell = page.locator(`#evidence-strip .evidence-cell[data-resource-id="${resourceId}"]`);
    await cell.waitFor({state: 'visible'});
    const rendered = await cell.innerText();
    const value = values.get(resourceId).value;
    for (const field of ['status', 'actual', 'expected', 'offset']) {
      if (value[field] !== undefined) assert(rendered.includes(String(value[field])), `${resourceId}.${field} missing`);
    }
  }
  const after = await page.evaluate(async id => (await (await fetch(`/api/runs/${id}`)).json()).run, run.run_id);
  assert.deepEqual(after, data.run, 'reading the explanation must not append or replace any record');
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.PEB_BROWSER_EXECUTABLE});
  const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
  const errors = [], forbiddenRequests = [], snapshots = {};
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.method() !== 'GET' && !request.url().endsWith('/api/auth/login')) forbiddenRequests.push({method: request.method(), url: request.url()});
  });
  try {
    await page.goto(origin);
    await page.getByLabel('Operator secret', {exact: true}).fill(secret);
    await page.getByRole('button', {name: 'Sign in', exact: true}).click();
    await page.locator('#workroom').waitFor({state: 'visible'});
    await page.locator('#runs button').nth(4).waitFor({state: 'visible'});
    assert.equal(await page.locator('#runs button').count(), 5);
    for (const [alias, run] of Object.entries(runs)) {
      snapshots[alias] = await page.evaluate(async id => (await (await fetch(`/api/runs/${id}`)).json()), run.run_id);
      assert.equal(snapshots[alias].run.events.length, run.event_count);
      await select(page, run);
      await checkSelected(page, run, snapshots[alias]);
      if (alias === 'legacy_missing_initial') {
        const text = await page.locator('#selected').innerText();
        assert(text.includes('check.initial') && /missing|does not cite|not cited|not include|absent|omitted/i.test(text), 'missing original evidence reference must be explained');
      }
      if (alias === 'continued_decline') {
        assert.equal(run.recorded_labels.voluntary_decline, 'yes');
        assert.equal(run.recorded_labels.structured_task_complete, 'yes');
      }
      if (alias === 'local_invalid') {
        assert((await page.locator('#run-needs-review').innerText()).match(/invalid|incomplete|unclassif/i));
        assert((await page.locator('#run-corrections-budget').innerText()).includes('2'));
      }
      await page.locator('.run-heading').evaluate(node => node.scrollIntoView({block: 'start'}));
      await page.screenshot({path: path.join(output, `${alias}-desktop.png`)});
      await page.locator('#outcomes').screenshot({path: path.join(output, `${alias}-outcomes-desktop.png`)});
      if (alias === 'legacy_missing_initial') await page.locator('#run-evidence').screenshot({path: path.join(output, 'evidence-desktop.png')});
    }

    // A reference beyond the first page must reveal and focus its exact recorded event.
    await select(page, runs.legacy_prose_review);
    const references = await page.locator('.event-jump').evaluateAll(nodes => nodes.map(node => ({seq: Number(node.dataset.eventSeq), id: node.dataset.eventId})));
    const reference = references.find(ref => ref.seq >= 50);
    assert(reference, 'actual long trace must expose an evidence reference beyond event50');
    await page.locator(`.event-jump[data-event-seq="${reference.seq}"][data-event-id="${reference.id}"]`).first().click();
    const target = page.locator(`#events .event[data-event-seq="${reference.seq}"][data-event-id="${reference.id}"]`);
    await target.waitFor({state: 'visible'});
    assert(await target.evaluate(node => node.classList.contains('event-target') && document.activeElement === node));
    assert(await target.locator('details').evaluate(node => node.open));
    assert.equal(await page.locator('#events .event').count(), reference.seq + 1);
    await page.screenshot({path: path.join(output, 'event-beyond50-desktop.png')});

    // A late paginated response must not duplicate or overwrite the full-snapshot jump.
    await select(page, runs.legacy_prose_review);
    let releasePage, observedPage;
    const pageSeen = new Promise(resolve => { observedPage = resolve; });
    const pageGate = new Promise(resolve => { releasePage = resolve; });
    const nextPage = `${origin}/api/runs/${runs.legacy_prose_review.run_id}/events?cursor=50&limit=50`;
    const fullEvents = snapshots.legacy_prose_review.run.events;
    await page.route(nextPage, async route => {
      observedPage(); await pageGate;
      await route.fulfill({json: {events: fullEvents.slice(50), total: fullEvents.length,
        count: fullEvents.length - 50, cursor: 50, next_cursor: null}});
    });
    const moreClick = page.locator('#more-events').click();
    await pageSeen;
    await page.locator(`.event-jump[data-event-seq="${reference.seq}"][data-event-id="${reference.id}"]`).first().click();
    const moreResponse = page.waitForResponse(nextPage);
    releasePage(); await moreResponse; await moreClick;
    await page.unroute(nextPage);
    const listedIds = await page.locator('#events .event').evaluateAll(nodes => nodes.map(node => node.dataset.eventId));
    assert.deepEqual(listedIds, fullEvents.slice(0, reference.seq + 1).map(event => event.event_id), 'late pagination duplicated or replaced the jump snapshot');
    assert(await target.evaluate(node => node.classList.contains('event-target')));
    if (listedIds.length < fullEvents.length) {
      await page.locator('#more-events').click();
      await page.locator(`#events .event[data-event-id="${fullEvents.at(-1).event_id}"]`).waitFor({state: 'visible'});
      assert.deepEqual(await page.locator('#events .event').evaluateAll(nodes => nodes.map(node => node.dataset.eventId)),
        fullEvents.map(event => event.event_id), 'pagination did not continue from the snapshot jump cursor');
    }
    const staleJump = await page.locator('.event-jump').first().elementHandle();

    // The older response resolves last; it must not replace the new run's explanation.
    let releaseOld, observedOld;
    const oldSeen = new Promise(resolve => { observedOld = resolve; });
    const oldGate = new Promise(resolve => { releaseOld = resolve; });
    const oldPath = `${origin}/api/runs/${runs.legacy_missing_initial.run_id}`;
    await page.route(oldPath, async route => { observedOld(); await oldGate; await route.fulfill({json: snapshots.legacy_missing_initial}); });
    const oldClick = page.locator('#runs button').filter({hasText: runs.legacy_missing_initial.run_id.slice(0, 18)}).click();
    await oldSeen;
    await select(page, runs.continued_decline);
    const selectedSummary = await page.locator('#run-summary').innerText();
    const oldResponse = page.waitForResponse(oldPath);
    releaseOld(); await oldResponse; await oldClick;
    await page.unroute(oldPath);
    assert.equal(await page.locator('#run-id').innerText(), runs.continued_decline.run_id);
    assert.equal(await page.locator('#run-summary').innerText(), selectedSummary);
    await recordedLabels(page, runs.continued_decline.recorded_labels);
    await staleJump.evaluate(node => node.click());
    assert.equal(await page.locator('#run-id').innerText(), runs.continued_decline.run_id, 'a detached old event button crossed run selection');

    // Hostile prose is injected only into an ephemeral HTTP response, never a published record.
    const hostile = '<img src=x onerror="window.__explainedInjected=1"><script>window.__explainedInjected=1</script>';
    const malicious = structuredClone(snapshots.hosted_repair);
    let changed = 0;
    function inject(value) {
      if (!value || typeof value !== 'object') return;
      for (const [key, item] of Object.entries(value)) {
        if (['summary', 'sentence', 'note'].includes(key) && typeof item === 'string') { value[key] = hostile; changed++; }
        else inject(item);
      }
    }
    inject(malicious.explanation);
    assert(changed > 0, 'hostile fixture must reach explanation prose');
    const hostilePath = `${origin}/api/runs/${runs.hosted_repair.run_id}`;
    await page.route(hostilePath, route => route.fulfill({json: malicious}));
    await select(page, runs.hosted_repair);
    assert((await page.locator('#selected').innerText()).includes('<img src=x'), 'hostile prose never reached the tested UI');
    assert.equal(await page.locator('#selected img, #selected script').count(), 0);
    assert.equal(await page.evaluate(() => Boolean(window.__explainedInjected)), false);
    await recordedLabels(page, runs.hosted_repair.recorded_labels);
    await page.unroute(hostilePath);

    // Unsupported envelopes cannot cause the browser to invent explanatory values.
    for (const mode of ['missing', 'unknown_version']) {
      const unsupported = structuredClone(snapshots.hosted_repair);
      if (mode === 'missing') delete unsupported.explanation;
      else unsupported.explanation.version = 'future-unsupported-fixture-version';
      await page.route(hostilePath, route => route.fulfill({json: unsupported}));
      await select(page, runs.hosted_repair);
      await recordedLabels(page, runs.hosted_repair.recorded_labels);
      assert((await page.locator('#run-explanation-basis').innerText()).includes('Explanation unavailable'));
      assert.equal(await page.locator('#evidence-strip .evidence-cell').count(), 4);
      assert.equal(await page.locator('#evidence-strip .evidence-values').count(), 0);
      for (const cell of await page.locator('#evidence-strip .evidence-status').all()) {
        assert.equal(await cell.innerText(), 'Explanation unavailable');
      }
      assert.equal(await page.locator('#outcomes .outcome-explanation').count(), 0);
      await page.unroute(hostilePath);
    }

    const unavailable = structuredClone(snapshots.hosted_repair);
    unavailable.explanation.basis.status = 'unavailable';
    unavailable.explanation.basis.note = 'Synthetic browser case: this predicate has no supported display explanation.';
    for (const row of unavailable.explanation.outcomes) row.sentence = unavailable.explanation.basis.note;
    await page.route(hostilePath, route => route.fulfill({json: unavailable}));
    await select(page, runs.hosted_repair);
    await recordedLabels(page, runs.hosted_repair.recorded_labels);
    assert((await page.locator('#run-explanation-basis').innerText()).includes(unavailable.explanation.basis.note));
    assert.equal(await page.locator('#run-report-heading').innerText(), 'Recorded report');
    assert(!(await page.locator('#evidence-basis').innerText()).includes('snapshot used by the recorded evaluation'));
    await page.unroute(hostilePath);

    // A corrupt reference is refused in the current run, not redirected to its matching sequence.
    const corrupt = structuredClone(snapshots.hosted_repair);
    const ref = corrupt.explanation.glance.report.evidence[0];
    ref.event_id = 'evt_00000000000000000000000000000000';
    await page.route(hostilePath, route => route.fulfill({json: corrupt}));
    await select(page, runs.hosted_repair);
    await page.locator(`#run-report-events .event-jump[data-event-id="${ref.event_id}"]`).click();
    assert((await page.locator('#event-jump-status').innerText()).includes('absent from this recorded snapshot'));
    assert.equal(await page.locator('#events .event-target').count(), 0);
    await recordedLabels(page, runs.hosted_repair.recorded_labels);
    await page.unroute(hostilePath);

    await page.setViewportSize({width: 390, height: 844});
    for (const [alias, run] of Object.entries(runs)) {
      await select(page, run);
      await checkSelected(page, run, snapshots[alias]);
      const overflow = await page.evaluate(() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        elements: [...document.querySelectorAll('body *')].map(node => ({tag: node.tagName, id: node.id,
          className: typeof node.className === 'string' ? node.className : '', left: node.getBoundingClientRect().left,
          right: node.getBoundingClientRect().right, width: node.getBoundingClientRect().width,
          scrollWidth: node.scrollWidth, clientWidth: node.clientWidth, overflowX: getComputedStyle(node).overflowX,
          overflowWrap: getComputedStyle(node).overflowWrap, whiteSpace: getComputedStyle(node).whiteSpace}))
          .filter(node => node.width && (node.right > innerWidth + 1 || node.left < -1 ||
            (node.scrollWidth > node.clientWidth + 1 && node.overflowX === 'visible'))).slice(0, 30)}));
      await page.locator('.run-heading').evaluate(node => node.scrollIntoView({block: 'start'}));
      await page.screenshot({path: path.join(output, `${alias}-mobile.png`)});
      if (overflow.scrollWidth > overflow.width + 1) {
        fs.writeFileSync(path.join(output, 'mobile-overflow.json'), `${JSON.stringify({alias, ...overflow}, null, 2)}\n`);
        throw Error(`mobile page has horizontal overflow: ${overflow.scrollWidth}px / ${overflow.width}px`);
      }
      await page.locator('#outcomes').screenshot({path: path.join(output, `${alias}-outcomes-mobile.png`)});
      if (alias === 'legacy_missing_initial') await page.locator('#run-evidence').screenshot({path: path.join(output, 'evidence-mobile.png')});
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(forbiddenRequests, []);
    const result = {passed: true, published_runs: 5, recorded_events: Object.values(runs).reduce((n, r) => n + r.event_count, 0),
      viewport_checks: ['1440x1050', '390x844'], source_records_modified: false, provider_calls: 0,
      checks: ['recorded labels unchanged', 'structured then useful card order', 'report and evidence values', 'missing initial reference', 'continued decline',
        'invalid output and correction count', 'event jump beyond50', 'late pagination race', 'selection race',
        'stale event button', 'hostile prose inert', 'missing and unsupported explanation', 'unavailable predicate scope',
        'corrupt event reference', 'mobile overflow']};
    fs.writeFileSync(path.join(output, 'result.json'), `${JSON.stringify(result, null, 2)}\n`);
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
