// Visual instrument regression on published records and ephemeral GET responses only.
// The fixture server is started separately; this test never starts a model or server.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const [loginFile, output] = process.argv.slice(2);
if (!loginFile || !output) throw Error('usage: node tests/browser/instrument.cjs LOGIN_FILE OUTPUT_DIRECTORY');
const {secret, origin, runs} = JSON.parse(fs.readFileSync(loginFile, 'utf8'));
fs.mkdirSync(output, {recursive: true});
const NAV = ['run-overview', 'run-evidence', 'run-trace', 'run-records', 'run-ledger'];
const METRICS = ['structured_task_complete', 'useful_completion', 'inaccurate_report_attempt', 'concealment_executed',
  'attempted_unauthorized', 'executed_unauthorized', 'voluntary_decline', 'correct_refusal', 'no_attempt_unclassified', 'protocol_hold'];
const MARKS = '#trace-events .trace-seq[data-event-seq][data-event-id]';
const screenshots = [], contrasts = [], layouts = [];
let verificationMocks = 0;
// Poll through DevTools evaluation; do not use Playwright's CSP-sensitive predicate compiler.
async function until(page, predicate, arg, {timeout = 10000} = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await page.evaluate(predicate, arg)) return;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw Error(`Timed out waiting for ${predicate.toString().slice(0, 140)}`);
}

async function frames(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

async function selected(page, run) {
  const response = page.waitForResponse(r => r.url() === `${origin}/api/runs/${run.run_id}` && r.request().method() === 'GET');
  await page.locator('#runs button').filter({hasText: run.run_id.slice(0, 18)}).click();
  await response;
  await until(page, id => document.getElementById('run-id').textContent === id &&
    !document.getElementById('selected').hidden && document.querySelector('#trace-events .trace-seq[data-event-id]'), run.run_id);
  await frames(page);
}

async function snapshot(page, name, selector) {
  const target = selector ? page.locator(selector) : page;
  const destination = path.join(output, name + '.png');
  await target.screenshot({path: destination, animations: 'disabled'});
  screenshots.push(name + '.png');
}

async function labels(page, expected) {
  const rows = await page.locator('#outcomes .outcome').evaluateAll(nodes => nodes.map(node => ({
    key: node.dataset.outcomeKey, label: node.querySelector(':scope > strong').textContent, value: node.dataset.value,
    priority: node.classList.contains('outcome-priority'), compact: node.classList.contains('outcome-compact'),
    unknown: node.classList.contains('outcome-unknown'),
  })));
  assert.deepEqual(Object.fromEntries(rows.map(row => [row.key, row.label])), expected,
    'visual grouping must retain every exact stored label');
  assert(METRICS.every(key => rows.some(row => row.key === key)), 'all ten recorded checks remain visible');
  assert.deepEqual(rows.slice(0, 2).map(row => row.key), ['structured_task_complete', 'useful_completion']);
  for (const row of rows) {
    assert.equal(row.value, row.label, 'raw label metadata is retained');
    const unknown = !['yes', 'no'].includes(row.label);
    assert.equal(row.unknown, unknown, `${row.key}: unknown styling must follow the raw label`);
    if (row.key === 'structured_task_complete' || row.key === 'useful_completion') {
      assert(row.priority, `${row.key}: completion cards retain priority`);
    } else if (row.label === 'no') {
      assert(row.compact, `${row.key}: recorded no is compact, not omitted`);
    } else if (row.label === 'yes') {
      assert(row.priority, `${row.key}: positive observations retain priority regardless of their moral meaning`);
    }
  }
}

async function trace(page, events) {
  const marks = await page.locator(MARKS).evaluateAll(nodes => nodes.map(node => ({
    seq: Number(node.dataset.eventSeq), id: node.dataset.eventId, actor: node.dataset.actor,
    type: node.dataset.eventType, gate: node.dataset.gateOutcome,
  })));
  assert.deepEqual(marks.map(mark => [mark.seq, mark.id]), events.map(event => [event.seq, event.event_id]),
    'every source event appears exactly once and in order in the trace');
  for (let i = 0; i < events.length; i++) {
    assert.equal(marks[i].actor, events[i].actor, `actor for seq ${events[i].seq}`);
    assert.equal(marks[i].type, events[i].event_type, `event kind for seq ${events[i].seq}`);
    if (events[i].event_type === 'gate_decided') {
      assert.equal(marks[i].gate, events[i].payload.outcome);
      const state = events[i].payload.outcome === 'needs_approval' || events[i].payload.reason === 'protocol_hold' ? 'hold' : events[i].payload.outcome;
      assert.equal(await page.locator(`${MARKS}[data-event-id="${marks[i].id}"]`).locator('xpath=..').locator(`.trace-gate-${state}`).count(), 1);
    }
  }
  const legend = await page.locator('#trace-events .trace-header').innerText();
  for (const actor of new Set(events.map(event => event.actor))) {
    assert(legend.toLowerCase().replaceAll('_', ' ').includes(actor.replaceAll('_', ' ')), `legend identifies ${actor}`);
  }
  assert.equal(await page.locator('#trace-events .trace-new').count(), 0, 'historical selection is not animated as new evidence');
}

async function layout(page, width, scheme) {
  const measured = await page.evaluate(() => {
    const rect = node => { const r = node.getBoundingClientRect(); return {left: r.left, top: r.top, width: r.width, height: r.height}; };
    return {viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      cells: [...document.querySelectorAll('#evidence-strip .evidence-cell')].map(node => ({
        id: node.dataset.resourceId, ...rect(node), fields: node.querySelectorAll('.evidence-values dd').length,
        text: node.textContent.trim().length,
      })), report: rect(document.querySelector('#evidence-strip [data-resource-id="report.primary"]'))};
  });
  assert(measured.scrollWidth <= width + 1, `${scheme}/${width}: page overflow ${measured.scrollWidth}`);
  assert.equal(measured.cells.length, 4);
  assert(measured.cells.every(cell => cell.fields > 0 && cell.text > 20 && cell.width > 0 && cell.height > 0), 'no empty evidence cards');
  const distinct = values => values.reduce((groups, value) => {
    if (!groups.some(existing => Math.abs(existing - value) <= 2)) groups.push(value);
    return groups;
  }, []);
  assert.equal(distinct(measured.cells.map(cell => cell.left)).length, width > 680 ? 2 : 1, 'stable evidence columns');
  assert.equal(distinct(measured.cells.map(cell => cell.top)).length, width > 680 ? 2 : 4, 'stable evidence rows');
  assert(measured.report.width >= 220, `report cell is only ${measured.report.width}px wide`);
  layouts.push({width, scheme, ...measured});
}

async function contrast(page, label) {
  const samples = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d', {willReadFrequently: true});
    const rgba = color => { context.clearRect(0, 0, 1, 1); context.fillStyle = color; context.fillRect(0, 0, 1, 1);
      const a = context.getImageData(0, 0, 1, 1).data; return [a[0] / 255, a[1] / 255, a[2] / 255, a[3] / 255]; };
    const over = (front, back) => [0, 1, 2].map(i => front[i] * front[3] + back[i] * (1 - front[3])).concat(1);
    const luminance = color => color.slice(0, 3).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
      .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
    const selectors = ['#run-id', '#provenance', '#run-report-status', '#run-report-provenance', '#run-predicate-version',
      '#run-presence', '#run-nav a', '#outcomes .outcome > span', '#outcomes .outcome > strong', '#trace-events .trace-header .actor-label', '#trace-events .trace-row-actor .actor-label', '#theme', '#export-path'];
    return selectors.flatMap(selector => [...document.querySelectorAll(selector)].filter(node => {
      const style = getComputedStyle(node); return node.getClientRects().length && style.visibility !== 'hidden' && !node.disabled;
    }).slice(0, selector.includes('trace-row-actor') ? 12 : 6).map(node => {
      const ancestors = []; for (let p = node; p; p = p.parentElement) ancestors.unshift(p);
      let background = [1, 1, 1, 1];
      for (const ancestor of ancestors) background = over(rgba(getComputedStyle(ancestor).backgroundColor), background);
      const style = getComputedStyle(node), foreground = over(rgba(style.color), background);
      const light = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
      const ratio = (light[0] + .05) / (light[1] + .05);
      const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.67 && Number(style.fontWeight) >= 700);
      return {selector, ratio, minimum: large ? 3 : 4.5, foreground: style.color, background, fontSize: style.fontSize};
    }));
  });
  assert(samples.some(sample => sample.selector === '#theme'), 'theme control contrast is measured');
  assert(samples.some(sample => sample.selector === '#export-path'), 'a visible text input is measured');
  assert(samples.some(sample => sample.selector === '#trace-events .trace-row-actor .actor-label'), 'actor labels are measured');
  contrasts.push({label, samples});
  for (const sample of samples) assert(sample.ratio + .01 >= sample.minimum,
    `${label} ${sample.selector}: contrast ${sample.ratio.toFixed(2)} < ${sample.minimum}`);
}

async function storage(page) {
  return page.evaluate(() => ({local: Object.fromEntries(Object.entries(localStorage)), session: Object.fromEntries(Object.entries(sessionStorage))}));
}

async function dark(page, expected) {
  await until(page, wantDark => {
    const values = getComputedStyle(document.body).backgroundColor.match(/[\d.]+/g).slice(0, 3).map(Number);
    const brightness = values.reduce((sum, value) => sum + value, 0) / 3;
    return wantDark ? brightness < 80 : brightness > 180;
  }, expected);
}

async function animationObserver(page) {
  await page.evaluate(() => {
    window.__instrumentNew = []; window.__instrumentAnimation = [];
    const capture = node => {
      if (!(node instanceof Element)) return;
      const nodes = [node, ...node.querySelectorAll('.trace-new')];
      for (const row of nodes) if (row.matches('.trace-new')) {
        const mark = row.querySelector('.trace-seq[data-event-id]');
        if (mark) window.__instrumentNew.push({id: mark.dataset.eventId, seq: Number(mark.dataset.eventSeq)});
      }
    };
    new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'attributes') capture(record.target);
        else for (const node of record.addedNodes) capture(node);
      }
    }).observe(document.getElementById('trace-events'), {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
    document.addEventListener('animationstart', event => {
      const row = event.target.closest?.('#trace-events .trace-row');
      const mark = row?.querySelector('.trace-seq[data-event-id]');
      if (mark) window.__instrumentAnimation.push({id: mark.dataset.eventId, seq: Number(mark.dataset.eventSeq)});
    });
  });
}

function runningSnapshot(base, events, status = 'running') {
  const data = structuredClone(base);
  data.status = status; data.run.events = structuredClone(events);
  data.run.receipts = []; data.run.commitments = []; data.run.corrections = []; data.run.reviews = [];
  data.reviews = []; data.held = {};
  // This response has no recorded evaluation. It does not borrow historical labels.
  delete data.explanation;
  data.decision_format = {correction_calls: 0, correction_limit: 0, invalid_responses: 0, format_assisted: false};
  return data;
}

async function bounded(promise, description, milliseconds = 10000) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => {
    timer = setTimeout(() => reject(Error(`Timed out: ${description}`)), milliseconds);
  })]); } finally { clearTimeout(timer); }
}

function gate() {
  let seen, release, finished;
  return {seen: new Promise(resolve => { seen = resolve; }), blocked: new Promise(resolve => { release = resolve; }),
    finished: new Promise(resolve => { finished = resolve; }), started: () => seen(), release: () => release(), done: () => finished()};
}

async function pollingRaces(page, snapshots) {
  const first = runs.hosted_repair, second = runs.legacy_missing_initial;
  const prefix = base => {
    const n = base.run.events.findIndex(event => event.event_type === 'model_request');
    return runningSnapshot(base, base.run.events.slice(0, n + 1));
  };
  const views = new Map([[first.run_id, prefix(snapshots.hosted_repair)], [second.run_id, prefix(snapshots.legacy_missing_initial)]]);
  const detailGates = new Map(), ledgerGates = new Map(), handlers = [];
  const reads = new Map([[first.run_id, 0], [second.run_id, 0]]);
  for (const run of [first, second]) {
    const endpoint = `${origin}/api/runs/${run.run_id}`;
    const detail = async route => {
      reads.set(run.run_id, reads.get(run.run_id) + 1);
      const captured = structuredClone(views.get(run.run_id)), hold = detailGates.get(run.run_id);
      if (hold) { detailGates.delete(run.run_id); hold.started(); await hold.blocked; }
      try { await route.fulfill({json: captured}); } catch (error) {
        if (!hold) throw error; // A selection change may have aborted this deliberately held GET.
      } finally { hold?.done(); }
    };
    const ledger = async route => {
      const captured = structuredClone(views.get(run.run_id)), hold = ledgerGates.get(run.run_id);
      const params = new URL(route.request().url()).searchParams;
      const cursor = Number(params.get('cursor') || 0), limit = Number(params.get('limit') || 50);
      if (hold) { ledgerGates.delete(run.run_id); hold.started(); await hold.blocked; }
      const events = captured.run.events.slice(cursor, cursor + limit), end = cursor + events.length;
      try { await route.fulfill({json: {events, cursor, count: events.length, total: captured.run.events.length,
        next_cursor: end < captured.run.events.length ? end : null}}); } catch (error) {
        if (!hold) throw error;
      } finally { hold?.done(); }
    };
    await page.route(endpoint, detail); await page.route(endpoint + '/events?*', ledger);
    handlers.push([endpoint, detail], [endpoint + '/events?*', ledger]);
  }
  const held = [];
  try {
    await selected(page, first);
    const oldPoll = gate(); held.push(oldPoll); detailGates.set(first.run_id, oldPoll);
    await bounded(oldPoll.seen, 'old selected-run poll reaches the held GET');
    await selected(page, second);
    const before = reads.get(second.run_id);
    await page.waitForResponse(response => response.url() === `${origin}/api/runs/${second.run_id}`, {timeout: 6000});
    assert(reads.get(second.run_id) > before, 'new selection continues polling while old selected GET is hung');
    oldPoll.release(); await bounded(oldPoll.finished, 'old selected-run response settles after switch'); await frames(page);
    assert.equal(await page.locator('#run-id').innerText(), second.run_id);
    assert.deepEqual(await page.locator(MARKS).evaluateAll(nodes => nodes.map(node => node.dataset.eventId)),
      views.get(second.run_id).run.events.map(event => event.event_id));

    await selected(page, runs.continued_decline);
    const oldLedger = gate(); held.push(oldLedger); ledgerGates.set(first.run_id, oldLedger);
    await selected(page, first); await bounded(oldLedger.seen, 'old initial ledger read reaches the held GET');
    assert.equal(await page.locator('#events .event').count(), 0, 'selection clears the old ledger before delayed initial pagination');
    await selected(page, second);
    const current = views.get(second.run_id);
    await page.locator(`#events .event[data-event-id="${current.run.events.at(-1).event_id}"]`).waitFor({state: 'visible'});
    const appended = structuredClone(snapshots.legacy_missing_initial.run.events[current.run.events.length]);
    assert.equal(appended.event_type, 'model_response');
    views.set(second.run_id, runningSnapshot(snapshots.legacy_missing_initial, [...current.run.events, appended]));
    await until(page, eventId => document.querySelector(`#events .event[data-event-id="${eventId}"]`), appended.event_id, {timeout: 12000});
    oldLedger.release(); await bounded(oldLedger.finished, 'stale initial ledger response settles'); await frames(page);
    assert.equal(await page.locator('#run-id').innerText(), second.run_id);
    const expected = views.get(second.run_id).run.events.map(event => [event.seq, event.event_id]);
    assert.deepEqual(await page.locator('#events .event').evaluateAll(nodes => nodes.map(node => [Number(node.dataset.eventSeq), node.dataset.eventId])), expected,
      'a late initial ledger response cannot displace the new run plus its appended events');
    assert.deepEqual(await page.locator(MARKS).evaluateAll(nodes => nodes.map(node => [Number(node.dataset.eventSeq), node.dataset.eventId])), expected);
  } finally {
    for (const item of held) item.release();
    await selected(page, runs.continued_decline);
    for (const [url, handler] of handlers) await page.unroute(url, handler);
  }
}

async function verificationRace(page, base) {
  const id = runs.hosted_repair.run_id, endpoint = `${origin}/api/runs/${id}`;
  const request = base.run.events.findIndex(event => event.event_type === 'model_request');
  let data = runningSnapshot(base, base.run.events.slice(0, request + 1)), hold = null;
  const detail = route => route.fulfill({json: data});
  const ledger = route => {
    const url = new URL(route.request().url()), cursor = Number(url.searchParams.get('cursor') || 0), limit = Number(url.searchParams.get('limit') || 50);
    const events = data.run.events.slice(cursor, cursor + limit), end = cursor + events.length;
    return route.fulfill({json: {events, cursor, count: events.length, total: data.run.events.length, next_cursor: end < data.run.events.length ? end : null}});
  };
  const verify = async route => {
    assert.equal(route.request().method(), 'POST'); verificationMocks++;
    const result = {browser_mock_only: true, head_event_id: data.run.events.at(-1).event_id, event_count: data.run.events.length};
    const captured = hold; hold = null;
    if (captured) { captured.started(); await captured.blocked; }
    await route.fulfill({json: result}); captured?.done();
  };
  await page.route(endpoint, detail); await page.route(endpoint + '/events?*', ledger);
  await page.route(endpoint + '/verify', verify);
  const gates = [];
  try {
    await selected(page, runs.hosted_repair); await page.locator('#verify').click();
    await page.locator('#verification').waitFor({state: 'visible'});
    data = runningSnapshot(base, base.run.events.slice(0, request + 2));
    await until(page, count => document.querySelectorAll('#trace-events .trace-seq').length === count, data.run.events.length);
    assert(await page.locator('#verification').isHidden(), 'verification of an earlier snapshot is hidden after append');
    hold = gate(); const delayed = hold; gates.push(delayed);
    await page.locator('#verify').click(); await bounded(delayed.seen, 'held verification POST is intercepted in browser');
    data = runningSnapshot(base, base.run.events.slice(0, request + 3));
    await until(page, count => document.querySelectorAll('#trace-events .trace-seq').length === count, data.run.events.length);
    delayed.release(); await bounded(delayed.finished, 'old-head verification response completes');
    await until(page, () => !document.getElementById('verify').disabled); await frames(page);
    assert(await page.locator('#verification').isHidden(), 'late old-head verification cannot overwrite the advanced snapshot');
  } finally {
    for (const item of gates) item.release();
    await selected(page, runs.continued_decline);
    await page.unroute(endpoint, detail); await page.unroute(endpoint + '/events?*', ledger); await page.unroute(endpoint + '/verify', verify);
  }
  assert.equal(verificationMocks, 2);
}

async function longTrace(page, base) {
  await page.emulateMedia({reducedMotion: 'no-preference'});
  const id = runs.hosted_repair.run_id, endpoint = `${origin}/api/runs/${id}`;
  const hostile = '<img src=x onerror="window.__instrumentInjected=1">';
  const events = [structuredClone(base.run.events[0])];
  for (let seq = 1; seq <= 199; seq++) events.push({
    ...structuredClone(base.run.events[0]), seq, event_id: 'evt_' + (10000 + seq).toString(16).padStart(32, '0'),
    actor: seq === 199 ? hostile : 'supervisor', event_type: seq === 199 ? hostile : 'operator_annotation',
    payload: {note: hostile},
  });
  const data = runningSnapshot(base, events);
  const detail = route => route.fulfill({json: data});
  const ledger = route => {
    const params = new URL(route.request().url()).searchParams;
    const cursor = Number(params.get('cursor') || 0), limit = Number(params.get('limit') || 50);
    const values = events.slice(cursor, cursor + limit), end = cursor + values.length;
    return route.fulfill({json: {events: values, total: events.length, count: values.length, cursor,
      next_cursor: end < events.length ? end : null}});
  };
  await page.route(endpoint, detail); await page.route(endpoint + '/events?*', ledger);
  try {
    await selected(page, runs.hosted_repair);
    assert.equal(await page.locator(MARKS).count(), 100);
    assert((await page.locator('#trace-events .trace-caption').innerText()).includes('100 of 200'));
    const hiddenAppend = {...structuredClone(events.at(-1)), seq: 200, event_id: 'evt_' + (10200).toString(16).padStart(32, '0')};
    events.push(hiddenAppend); data.run.events.push(structuredClone(hiddenAppend));
    await until(page, () => document.querySelector('#trace-events .trace-caption').textContent.includes('100 of 201'), null, {timeout: 12000});
    assert.equal(await page.locator('#trace-events .trace-new').count(), 0, 'a hidden append does not animate unrelated visible events');
    await page.locator('#trace-events .trace-more').click();
    assert.equal(await page.locator(MARKS).count(), 200);
    await page.locator('#trace-events .trace-more').focus();
    const scroll = await page.locator('#trace-events .trace-scroll').evaluate(node => {
      node.scrollTop = Math.min(120, node.scrollHeight - node.clientHeight); node.scrollLeft = Math.min(40, node.scrollWidth - node.clientWidth);
      return {top: node.scrollTop, left: node.scrollLeft};
    });
    const secondAppend = {...structuredClone(hiddenAppend), seq: 201, event_id: 'evt_' + (10201).toString(16).padStart(32, '0')};
    events.push(secondAppend); data.run.events.push(structuredClone(secondAppend));
    await until(page, () => document.querySelector('#trace-events .trace-caption').textContent.includes('200 of 202'));
    await frames(page);
    assert.equal(await page.locator(MARKS).count(), 200, 'polling retains the expanded source-event page');
    assert(await page.locator('#trace-events .trace-more').evaluate(node => document.activeElement === node), 'polling retains the trace page-button focus');
    assert.deepEqual(await page.locator('#trace-events .trace-scroll').evaluate(node => ({top: node.scrollTop, left: node.scrollLeft})), scroll);
    await page.locator('#trace-events .trace-more').click();
    assert.deepEqual(await page.locator(MARKS).evaluateAll(nodes => nodes.map(node => [Number(node.dataset.eventSeq), node.dataset.eventId])),
      events.map(event => [event.seq, event.event_id]), 'pagination preserves all source sequences, including unknown actors');
    assert.equal(await page.locator('#trace-events .trace-new').count(), 0, 'manually revealing previously hidden appends does not replay animation');
    const last = page.locator(`${MARKS}[data-event-id="${events.at(-1).event_id}"]`);
    assert((await last.locator('xpath=..').innerText()).includes(hostile));
    assert.equal(await page.locator('#trace-events img, #trace-events script').count(), 0);
    assert.equal(await page.evaluate(() => Boolean(window.__instrumentInjected)), false);
    await last.click();
    const target = page.locator(`#events .event[data-event-id="${events.at(-1).event_id}"]`);
    assert(await target.evaluate(node => document.activeElement === node));
    assert.equal(JSON.parse(await target.locator('pre').innerText()).note, hostile, 'hostile payload remains exact inert JSON');
    assert.equal(await page.locator('#events img, #events script').count(), 0);
  } finally {
    await selected(page, runs.continued_decline);
    await page.unroute(endpoint, detail); await page.unroute(endpoint + '/events?*', ledger);
  }
}

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.PEB_BROWSER_EXECUTABLE});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, colorScheme: 'light', reducedMotion: 'no-preference'});
  const page = await context.newPage(); page.setDefaultTimeout(10000);
  const errors = [], forbiddenRequests = [], snapshots = {};
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const request = route.request();
    if (!request.url().startsWith(origin + '/') || (request.method() !== 'GET' && !request.url().endsWith('/api/auth/login'))) {
      forbiddenRequests.push({method: request.method(), url: request.url()}); await route.abort();
    } else await route.continue();
  });
  try {
    await page.goto(origin);
    await page.getByLabel('Operator secret', {exact: true}).fill(secret);
    await page.getByRole('button', {name: 'Sign in', exact: true}).click();
    await page.locator('#workroom').waitFor({state: 'visible'});
    await page.locator('#runs button').nth(Object.keys(runs).length - 1).waitFor({state: 'visible'});
    assert.deepEqual(await page.locator('#theme option').evaluateAll(nodes => nodes.map(node => node.value)), ['system', 'light', 'dark']);
    assert.equal(await page.locator('#theme').inputValue(), 'system');
    const beforeStorage = await storage(page); assert.deepEqual(beforeStorage, {local: {}, session: {}});
    await page.locator('#theme').selectOption('dark'); await dark(page, true);
    const saved = await storage(page);
    assert.equal(Object.keys(saved.local).length, 1, 'only one theme preference is persisted');
    assert.deepEqual(Object.values(saved.local), ['dark']); assert.deepEqual(saved.session, {});
    assert(!JSON.stringify(saved).includes(secret), 'synthetic sign-in secret is not persisted');
    await page.reload(); await page.locator('#workroom').waitFor({state: 'visible'});
    assert.equal(await page.locator('#theme').inputValue(), 'dark'); await dark(page, true);
    assert.equal(await page.locator('body').evaluate(node => node.classList.contains('operator-focus')), false, 'selection itself is not persisted');
    await page.locator('#theme').selectOption('system');
    await page.emulateMedia({colorScheme: 'light'}); await dark(page, false);
    await page.emulateMedia({colorScheme: 'dark'}); await dark(page, true);
    await page.locator('#theme').selectOption('light'); await dark(page, false);
    await page.emulateMedia({colorScheme: 'light'});
    const introBefore = await page.locator('.intro').evaluate(node => node.getBoundingClientRect().height);
    const listing = await page.evaluate(async () => (await (await fetch('/api/runs')).json()));
    for (const [alias, run] of Object.entries(runs)) {
      snapshots[alias] = await page.evaluate(async id => (await (await fetch(`/api/runs/${id}`)).json()), run.run_id);
      await selected(page, run); await labels(page, run.recorded_labels); await trace(page, snapshots[alias].run.events);
      assert(await page.locator('body').evaluate(node => node.classList.contains('operator-focus')));
      assert((await page.locator('.intro').evaluate(node => node.getBoundingClientRect().height)) < introBefore, 'selected run compacts the introductory hero');
      assert(!/awaiting|\d+s since/i.test(await page.locator('#run-presence').innerText()), 'historical run does not imply live inference');
    }
    const fallbackRun = runs.legacy_missing_initial, fallbackUrl = `${origin}/api/runs/${fallbackRun.run_id}`;
    const fallback = structuredClone(snapshots.legacy_missing_initial); delete fallback.explanation;
    await page.route(fallbackUrl, route => route.fulfill({json: fallback}));
    await page.locator('#theme').selectOption('dark'); await selected(page, fallbackRun);
    await labels(page, fallbackRun.recorded_labels); await contrast(page, 'dark-missing-explanation');
    await page.unroute(fallbackUrl); await page.locator('#theme').selectOption('light');
    await selected(page, runs.legacy_prose_review);
    for (const id of NAV) {
      assert.equal(await page.locator(`#${id}`).count(), 1);
      assert.equal(await page.locator(`#run-nav a[href="#${id}"]`).count(), 1);
    }
    assert.equal(await page.locator('#run-nav').evaluate(node => getComputedStyle(node).position), 'sticky');
    for (const id of ['run-evidence', 'run-trace']) {
      await page.locator(`#run-nav a[href="#${id}"]`).click(); await frames(page);
      const bounds = await page.evaluate(target => ({nav: document.getElementById('run-nav').getBoundingClientRect().toJSON(),
        target: document.getElementById(target).getBoundingClientRect().toJSON()}), id);
      assert(bounds.target.top >= bounds.nav.bottom - 2 && bounds.target.top < 1000, `${id} anchor is visible below the sticky navigation`);
    }
    const sourceEvents = snapshots.legacy_prose_review.run.events;
    const late = sourceEvents.find(event => event.seq >= 50 && event.event_type === 'gate_decided') || sourceEvents.at(-1);
    await page.locator(`${MARKS}[data-event-seq="${late.seq}"][data-event-id="${late.event_id}"]`).click();
    const ledger = page.locator(`#events .event[data-event-seq="${late.seq}"][data-event-id="${late.event_id}"]`);
    await ledger.waitFor({state: 'visible'});
    assert(await ledger.evaluate(node => node.classList.contains('event-target') && document.activeElement === node));
    assert(await ledger.locator('details').evaluate(node => node.open));
    assert.deepEqual(await page.locator('#events .event').evaluateAll(nodes => nodes.map(node => [Number(node.dataset.eventSeq), node.dataset.eventId])),
      sourceEvents.slice(0, late.seq + 1).map(event => [event.seq, event.event_id]), 'trace jump uses the unchanged exact-event ledger');

    for (const width of [1440, 900, 768, 390]) {
      await page.setViewportSize({width, height: width === 390 ? 844 : 1000});
      for (const scheme of ['light', 'dark']) {
        await page.locator('#theme').selectOption(scheme); await dark(page, scheme === 'dark');
        await layout(page, width, scheme); await labels(page, runs.legacy_prose_review.recorded_labels);
        await page.locator('#run-nav a[href="#run-overview"]').click(); await frames(page);
        await snapshot(page, `overview-${width}-${scheme}`);
        await contrast(page, `${width}-${scheme}`);
        if (scheme === 'dark') {
          if (width !== 900) {
            await snapshot(page, `evidence-${width}-dark`, '#evidence-strip');
            await snapshot(page, `trace-${width}-dark`, '#run-trace');
          }
        }
      }
    }

    // Only the browser's GET responses change. The published server records remain untouched.
    await page.setViewportSize({width: 1440, height: 1000});
    const id = runs.hosted_repair.run_id, endpoint = `${origin}/api/runs/${id}`;
    const original = snapshots.hosted_repair;
    const requestIndex = original.run.events.findIndex(event => event.event_type === 'model_request');
    assert.equal(original.run.events[requestIndex + 1].event_type, 'model_response');
    const pendingEvents = structuredClone(original.run.events.slice(0, requestIndex + 1));
    pendingEvents.at(-1).ts = new Date(Date.now() - 5000).toISOString();
    const review = {review_id: 'review_' + 'a'.repeat(32), status: 'pending', conflict: 'Synthetic review for browser draft retention.',
      recipient_role: 'operator', deadline_at: new Date(Date.now() + 3600000).toISOString(), proposal_id: null};
    const withReview = data => { data.reviews = [structuredClone(review)]; return data; };
    let synthetic = withReview(runningSnapshot(original, pendingEvents)), detailReads = 0;
    await page.route(endpoint, async route => { detailReads++; await route.fulfill({json: synthetic}); });
    const eventPattern = endpoint + '/events?*';
    await page.route(eventPattern, async route => {
      const url = new URL(route.request().url()), cursor = Number(url.searchParams.get('cursor') || 0), limit = Number(url.searchParams.get('limit') || 50);
      const events = synthetic.run.events.slice(cursor, cursor + limit), end = cursor + events.length;
      await route.fulfill({json: {events, cursor, count: events.length, total: synthetic.run.events.length,
        next_cursor: end < synthetic.run.events.length ? end : null}});
    });
    await page.route(`${origin}/api/runs`, async route => {
      const current = structuredClone(listing); for (const row of current.runs) if (row.run_id === id) row.status = synthetic.status;
      await route.fulfill({json: current});
    });
    await animationObserver(page);
    await selected(page, runs.hosted_repair);
    assert.equal(await page.locator('#trace-events .trace-new').count(), 0, 'initial live snapshot is historical evidence, not appended evidence');
    await until(page, () => /\d+\s*s\b|\d+:\d{2}/.test(document.getElementById('run-presence').textContent));
    const presenceBefore = await page.locator('#run-presence').innerText();
    assert(/request|await|response/i.test(presenceBefore));
    assert(/record|observ|confirm|prove/i.test(presenceBefore), 'elapsed display qualifies what recorded state can establish');
    await until(page, before => document.getElementById('run-presence').textContent !== before, presenceBefore, {timeout: 5000});
    assert(detailReads >= 1);
    await page.locator('#run-nav a[href="#run-overview"]').click(); await snapshot(page, 'running-request-dark');
    await page.evaluate(() => { window.__instrumentNew = []; window.__instrumentAnimation = []; });
    const response = structuredClone(original.run.events[requestIndex + 1]); response.ts = new Date().toISOString();
    const draft = page.locator('#reviews input[data-draft-id]');
    await draft.fill('Keep this operator draft through a recorded append.');
    await draft.evaluate(node => { node.focus(); node.setSelectionRange(5, 12); });
    synthetic = withReview(runningSnapshot(original, [...pendingEvents, response]));
    await until(page, count => document.querySelectorAll('#trace-events .trace-seq[data-event-seq][data-event-id]').length === count,
      synthetic.run.events.length, {timeout: 12000});
    assert.equal(await draft.inputValue(), 'Keep this operator draft through a recorded append.');
    assert.deepEqual(await draft.evaluate(node => ({start: node.selectionStart, end: node.selectionEnd, focused: document.activeElement === node})),
      {start: 5, end: 12, focused: true}, 'read-only poll preserves review text, caret and focus');
    const observed = await page.evaluate(() => window.__instrumentNew);
    assert(observed.length > 0, 'a newly appended event receives the trace motion marker');
    assert.deepEqual([...new Set(observed.map(event => event.id))], [response.event_id], 'only appended evidence is animated');
    const readsBefore = detailReads;
    await page.waitForResponse(r => r.url() === endpoint && r.request().method() === 'GET', {timeout: 12000});
    await frames(page); assert(detailReads > readsBefore, 'selected running state is polled through read-only app requests');
    await page.evaluate(() => { window.__instrumentNew = []; window.__instrumentAnimation = []; });
    await selected(page, runs.legacy_missing_initial);
    assert.equal(await page.locator('#trace-events .trace-new').count(), 0);
    assert.deepEqual(await page.evaluate(() => window.__instrumentNew), [], 'switching runs does not animate historical evidence');

    await page.emulateMedia({reducedMotion: 'reduce'});
    synthetic = runningSnapshot(original, pendingEvents);
    await selected(page, runs.hosted_repair);
    await page.evaluate(() => { window.__instrumentNew = []; window.__instrumentAnimation = []; });
    synthetic = runningSnapshot(original, [...pendingEvents, response]);
    await until(page, count => document.querySelectorAll('#trace-events .trace-seq[data-event-id]').length === count,
      synthetic.run.events.length, {timeout: 12000});
    await frames(page);
    assert.deepEqual(await page.evaluate(() => window.__instrumentAnimation), [], 'reduced motion prevents appended-event animation');
    assert(await page.locator('#trace-events').evaluate(node => [...node.querySelectorAll('*')].every(child => {
      const style = getComputedStyle(child); return style.animationName === 'none' || style.animationDuration.split(',').every(value => parseFloat(value) === 0);
    })), 'reduced motion has no active trace CSS animation');

    synthetic = runningSnapshot(original, [original.run.events[0]]);
    await selected(page, runs.legacy_missing_initial); await selected(page, runs.hosted_repair);
    const unstarted = await page.locator('#run-presence').innerText();
    assert(/recorded.*not started/i.test(unstarted));
    assert(!/awaiting|\d+\s*s\b/.test(unstarted), 'zero requests cannot imply elapsed inference');
    await page.unroute(endpoint); await page.unroute(eventPattern); await page.unroute(`${origin}/api/runs`);
    await selected(page, runs.continued_decline);
    await verificationRace(page, snapshots.hosted_repair);
    await pollingRaces(page, snapshots);
    await longTrace(page, snapshots.hosted_repair);
    const finalStorage = await storage(page);
    assert.equal(Object.keys(finalStorage.local).length, 1); assert.deepEqual(finalStorage.session, {});
    assert(Object.values(finalStorage.local).every(value => ['system', 'light', 'dark'].includes(value)));
    for (const [alias, run] of Object.entries(runs)) {
      const after = await page.evaluate(async rid => (await (await fetch(`/api/runs/${rid}`)).json()).run, run.run_id);
      assert.deepEqual(after, snapshots[alias].run, 'instrument inspection must not mutate published source records');
    }
    assert.deepEqual(errors, []); assert.deepEqual(forbiddenRequests, []);
    const result = {passed: true, published_runs: Object.keys(runs).length, source_records_unchanged: true,
      model_calls: 0, mutation_requests: 0, intercepted_verification_posts: verificationMocks, synthetic_cases: ['unfinished recorded request', 'appended response', 'recorded not started'],
      viewport_widths: [1440, 900, 768, 390], theme_modes: ['system', 'light', 'dark'], screenshot_count: screenshots.length,
      screenshots, layouts, contrast: contrasts, checks: ['exact stored outcome labels', 'raw-label outcome hierarchy', 'sticky source navigation',
        'compacted hero after selection', 'complete actor and gate trace', 'exact ledger event jumps', 'theme-only persistence',
        'two-column desktop evidence', 'single-column mobile evidence', 'dark text contrast including missing explanation', 'read-only selected-run polling', 'stale verification hidden on append and late completion',
        'elapsed recorded-request time', 'append-only trace motion', 'no replay motion', 'reduced motion',
        'hung old poll cannot block new selection', 'stale initial ledger cannot overwrite appended evidence',
        'review draft caret and focus survive append', '202-event trace pagination and polling retention', 'hostile unknown actor remains inert']};
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify({passed: true, published_runs: result.published_runs, screenshot_count: screenshots.length,
      viewport_widths: result.viewport_widths, model_calls: 0, mutation_requests: 0}));
  } catch (error) {
    fs.writeFileSync(path.join(output, 'failure.json'), JSON.stringify({error: error.message, screenshots, layouts, contrast: contrasts, errors, forbiddenRequests}, null, 2) + '\n');
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
