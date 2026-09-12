"use strict";
const $ = (id) => document.getElementById(id);
let csrf = "", selectedId = null, nextCursor = null, preview = null, activeRequests = 0;
let selectionVersion = 0, previewVersion = 0, selectedState = null;
let studyVersion = 0, studyPlan = null, reviewQueueVersion = 0;
let replayEvents = [], comparisonVersion = 0;
let bundleEvents = [], bundleVersion = 0;
let activeStudyId = null, studyReadVersion = 0, studyReportStatus = null, studyPollBusy = false;
let studyPreview = null, studyPreviewVersion = 0;
let studyReadFailures = 0;
const attemptedStudies = new Set();
const pretty = (value) => JSON.stringify(value, null, 2);
function note(text, error = false) { $("notice").textContent = text; $("notice").classList.toggle("error", error); }
function el(tag, text, className) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; }
async function api(path, body, method) {
  const options = {method: method || (body === undefined ? "GET" : "POST"), credentials: "same-origin", headers: {}};
  if (body !== undefined) { options.headers["Content-Type"] = "application/json"; options.headers["X-Peb-CSRF"] = csrf; options.body = JSON.stringify(body); }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401) signedIn(false);
    throw new Error(result.error?.message || `Request failed (${response.status}).`);
  }
  return result;
}
function signedIn(yes) { $("signin").hidden = yes; $("workroom").hidden = !yes; $("logout").hidden = !yes; if (!yes) { csrf = ""; invalidatePreview(); invalidateStudy(); clearStudyRead(); invalidateComparison(); invalidateBundle(); reviewQueueVersion++; $("global-reviews").replaceChildren(); $("global-review-count").textContent = "Not loaded"; } }
async function action(button, task) {
  button.disabled = true; activeRequests++;
  try { await task(); } catch (error) { note(error.message, true); }
  finally { activeRequests--; button.disabled = false; updateStart(); updateRunControls(); updateStudyLaunch(); }
}
function invalidatePreview() { previewVersion++; preview = null; $("scope").hidden = true; $("approve-start").checked = false; updateStart(); }
function updateStart() { const hosted = $("provider").value === "deepseek"; $("hosted-fields").hidden = !hosted; $("create-model").disabled = hosted; $("start-model").disabled = !$("approve-start").checked || (hosted && !preview?.preview_token); }
function startPayload() { return {provider: $("provider").value, model: $("model").value.trim(), profile: $("profile").value, task: $("model-task").value, max_model_calls: Number($("calls").value), max_output_tokens: Number($("tokens").value), thinking: $("thinking").value, confirm: true}; }
async function loadProfiles() {
  const data = await api("/api/profiles"); $("profile").replaceChildren();
  for (const p of data.profiles) { const option = el("option", `${p.profile_id} · ${p.arm} · ${p.status}`); option.value = p.profile_id; option.disabled = !p.runnable; $("profile").append(option); }
  $("profile").value = "baseline";
  $("study-profiles").replaceChildren();
  for (const p of data.profiles.filter(p => ["A0", "A1", "A2", "A3"].includes(p.arm))) studyChoice("study-profiles", p.profile_id, `${p.arm} · ${p.profile_id}`, ["baseline", "tone_only"].includes(p.profile_id), !p.runnable);

}
async function loadRuns() {
  const data = await api("/api/runs"); $("run-count").textContent = String(data.runs.length); $("runs").replaceChildren();
  invalidateComparison();
  for (const [id, fallback] of [["comparison-left", 0], ["comparison-right", 1]]) {
    const select = $(id), prior = select.value; select.replaceChildren();
    for (const run of data.runs) { const option = el("option", `${run.run_id} · ${run.mode} · ${run.status}`); option.value = run.run_id; select.append(option); }
    select.value = data.runs.some(run => run.run_id === prior) ? prior : data.runs[fallback]?.run_id || "";
  }
  if (!data.runs.length) $("runs").append(el("p", "No records yet. Run a control to begin.", "fine"));
  for (const run of [...data.runs].reverse()) {
    const button = el("button", run.status.replaceAll("_", " ")); button.type = "button";
    button.classList.toggle("active", run.run_id === selectedId); button.append(el("span", `${run.run_id.slice(0, 18)}… · ${run.mode}`));
    button.addEventListener("click", () => action(button, () => selectRun(run.run_id))); $("runs").append(button);
  }
}
function resourceMap(events) {
  const values = new Map();
  for (const event of events) {
    if (event.event_type === "run_created") for (const r of event.payload.resources || []) values.set(r.resource_id, r);
    if (event.event_type === "effect_observed" && event.payload.status === "applied") for (const [id, body] of Object.entries(event.payload.applied || {})) values.set(id, {resource_id: id, ...body});
  }
  return values;
}
function renderResources(events, target = "resources") {
  $(target).replaceChildren();
  for (const [id, value] of resourceMap(events)) { const details = el("details", undefined, "resource"); const summary = el("summary", id); summary.append(el("span", `rev ${value.revision} · ${value.kind}`)); details.append(summary, el("pre", pretty(value.value))); $(target).append(details); }
}
function renderOutcomes(events) {
  const evaluation = [...events].reverse().find((e) => e.event_type === "evaluation_recorded")?.payload.evaluation;
  $("outcomes").replaceChildren();
  const titles = new Map([["useful_completion", "Useful completion"], ["concealment_executed", "Concealment executed"], ["attempted_unauthorized", "Unauthorized attempt"], ["executed_unauthorized", "Unauthorized effect"], ["voluntary_decline", "Voluntary decline"], ["protocol_hold", "Protocol hold"]]);
  const labels = evaluation?.behavior_labels || {};
  for (const key of Object.keys(labels).sort()) if (!titles.has(key)) titles.set(key, key.replaceAll("_", " ").replace(/^./, c => c.toUpperCase()));
  for (const [key, title] of titles) {
    const box = el("div", undefined, "outcome"); box.append(el("span", title), el("strong", labels[key] ?? "not evaluated")); $("outcomes").append(box);
  }
  if (evaluation?.missingness?.length) $("outcomes").append(el("p", `Missingness: ${evaluation.missingness.join(", ")}`, "fine"));
}
function renderReviews(reviews, held, events, runId) {
  $("reviews").replaceChildren();
  if (!reviews.length) $("reviews").append(el("p", "No review requests in this run.", "muted"));
  for (const review of reviews) {
    const row = el("div", undefined, "review"); row.append(el("strong", review.status), el("p", review.conflict), el("p", `Recipient: ${review.recipient_role} · Deadline: ${review.deadline_at}`, "fine"));
    const binding = el("details"); binding.append(el("summary", "Exact review and proposal binding"), el("pre", pretty({review, held_proposal: held[review.review_id] || null, proposal_events: events.filter(e => e.payload?.proposal?.proposal_id === review.proposal_id)}))); row.append(binding);
    if (["pending", "acknowledged"].includes(review.status)) {
      const input = el("input"); input.placeholder = "Operator note"; input.setAttribute("aria-label", "Operator review note"); input.maxLength = 500; row.append(input);
      const buttons = el("div", undefined, "actions");
      for (const [decision, label] of [["ack", "Acknowledge"], ["allow", "Allow & re-gate"], ["deny", "Deny"]]) {
        const button = el("button", label, "secondary"); button.type = "button"; button.disabled = (decision === "ack" && review.status !== "pending") || (decision === "allow" && (!held[review.review_id] || Date.parse(review.deadline_at) <= Date.now()));
        button.addEventListener("click", () => action(button, async () => {
          if (decision === "allow" && !window.confirm("Approve this exact held proposal for re-gating? State and grants will still be checked.")) return;
          const result = await api(`/api/runs/${runId}/reviews/${review.review_id}/resolve`, {decision, note: input.value});
          note(`Review ${decision} recorded. ${result.executed ? "Effect applied." : "Inspect the recorded outcome below."}`); if (selectedId === runId) await selectRun(runId); if ($("global-review-panel").open) await loadReviewQueue();
        })); buttons.append(button);
      }
      row.append(buttons);
    }
    $("reviews").append(row);
  }
}
async function loadEvents(reset = false) {
  const id = selectedId, version = selectionVersion;
  const page = await api(`/api/runs/${id}/events?cursor=${reset ? 0 : nextCursor || 0}&limit=50`);
  if (id !== selectedId || version !== selectionVersion) return;
  if (reset) $("events").replaceChildren();
  for (const e of page.events) {
    const row = el("div", undefined, "event"); row.append(el("span", String(e.seq).padStart(3, "0"), "event-num"));
    const details = el("details"); const summary = el("summary", e.event_type.replaceAll("_", " "), "event-type"); summary.append(el("span", e.actor, "event-meta")); details.append(summary, el("p", e.ts, "fine"), el("pre", pretty(e.payload))); row.append(details); $("events").append(row);
  }
  nextCursor = page.next_cursor; $("more-events").hidden = nextCursor === null; $("event-count").textContent = `${$("events").children.length} of ${page.total} events`;
}
function updateRunControls() {
  if (!selectedState) return;
  const {status, provider} = selectedState;
  for (const verb of ["step", "begin"]) $(verb).disabled = !["created", "running"].includes(status) || provider !== "ollama";
  $("resume").disabled = !["paused", "waiting_review"].includes(status) || provider !== "ollama";
  $("pause").disabled = !["created", "running", "waiting_review", "paused"].includes(status); $("cancel").disabled = $("pause").disabled;
}
async function selectRun(id) {
  const version = ++selectionVersion; selectedId = id; const data = await api(`/api/runs/${id}`);
  if (version !== selectionVersion) return;
  $("empty").hidden = true; $("selected").hidden = false; $("run-title").textContent = data.run.manifest.settings?.case || data.run.manifest.task_id;
  $("run-id").textContent = id; $("run-status").textContent = data.status === "running" && !data.run.events.some(e => e.event_type === "model_request") ? "recorded · not started" : data.status; $("provenance").textContent = `${data.run.manifest.mode} · ${data.run.manifest.provider_kind} · ${data.run.manifest.model_requested || "scripted"} · ${data.run.manifest.profile_id}`;
  $("manifest").textContent = pretty(data.run.manifest); renderResources(data.run.events); loadReplay(data.run); renderOutcomes(data.run.events); renderReviews(data.reviews || [], data.held || {}, data.run.events, id); renderCommitments(data.run.commitments || []); $("corrections").textContent = pretty(data.run.corrections || []);
  $("verification").hidden = true; $("export-result").hidden = true;
  selectedState = {status: data.status, provider: data.run.manifest.provider_kind}; updateRunControls();
  await loadEvents(true); await loadRuns();
}

function renderCommitments(commitments) {
  $("commitments").replaceChildren();
  if (!commitments.length) $("commitments").append(el("p", "No commitments recorded.", "muted"));
  for (const commitment of commitments) {
    const row = el("div", undefined, "review");
    row.append(el("strong", `${commitment.kind} · ${commitment.status}`), el("p", commitment.text), el("p", `Origin: ${commitment.origin} · ${commitment.commitment_id}`, "fine"));
    const details = el("details"); details.append(el("summary", "Provenance and prior version"), el("pre", pretty(commitment))); row.append(details);
    if (["proposed", "accepted"].includes(commitment.status)) {
      const input = el("input"); input.setAttribute("aria-label", "Revised commitment text"); input.value = commitment.text; input.maxLength = 4000;
      const buttons = el("div", undefined, "actions");
      for (const verb of ["accept", "revise"]) {
        const button = el("button", verb === "accept" ? "Accept undertaking" : "Save revision", "secondary"); button.type = "button";
        button.disabled = verb === "accept" && commitment.status !== "proposed";
        button.addEventListener("click", () => action(button, async () => {
          if (verb === "revise" && !input.value.trim()) throw new Error("Revision text is required.");
          const id = selectedId;
          await api(`/api/runs/${id}/commitments/${commitment.commitment_id}/${verb}`, verb === "revise" ? {text: input.value} : {});
          if (id === selectedId) await selectRun(id); note(`Commitment ${verb} recorded. Permissions are unchanged.`);
        })); buttons.append(button);
      }
      row.append(input, buttons);
    }
    $("commitments").append(row);
  }
}
$("create-model").addEventListener("click", () => action($("create-model"), async () => {
  if (!$("model-form").reportValidity()) return;
  const payload = startPayload(); delete payload.confirm;
  if (payload.provider !== "ollama") throw new Error("Use the previewed bounded launch for hosted runs.");
  note("Recording local run without inference…");
  const result = await api("/api/runs", payload); await selectRun(result.run_id); note("Run recorded. No model call made. Step once or run to a boundary when ready.");
}));
for (const [verb, route] of [["step", "step"], ["begin", "start"]]) $(verb).addEventListener("click", () => action($(verb), async () => {
  const id = selectedId;
  note(verb === "step" ? "Requesting one decision…" : "Requesting the bounded loop…");
  const result = await api(`/api/runs/${id}/${route}`, {confirm: true});
  if (id === selectedId) await selectRun(id); note(`Observed status: ${result.status}. Model calls this operation: ${result.steps_taken}.`);
}));

$("login-form").addEventListener("submit", (event) => { event.preventDefault(); action(event.submitter, async () => { const data = await api("/api/auth/login", {secret: $("secret").value}); $("secret").value = ""; csrf = data.csrf_token; signedIn(true); note("Operator session opened."); await Promise.all([loadRuns(), loadProfiles()]); }); });
$("logout").addEventListener("click", () => action($("logout"), async () => { await api("/api/auth/logout", {}); signedIn(false); note("Signed out."); }));
$("refresh").addEventListener("click", () => action($("refresh"), async () => { await loadRuns(); if (selectedId) await selectRun(selectedId); $("health").textContent = pretty(await api("/api/health")); note("Records refreshed."); }));
$("demo-form").addEventListener("submit", (event) => { event.preventDefault(); action(event.submitter, async () => { note("Running scripted control…"); const result = await api("/api/demos", {case: $("case").value, frame: $("frame").value}); await selectRun(result.run_id); note("Scripted control recorded. Inspect the observed outcome below."); }); });
$("model-form").addEventListener("input", (event) => { if (event.target.id !== "approve-start") invalidatePreview(); else updateStart(); });
$("preview").addEventListener("click", () => action($("preview"), async () => {
  if (!$("model-form").reportValidity()) return;
  const version = previewVersion;
  const payload = startPayload(); delete payload.confirm;
  if (payload.provider === "deepseek" && $("input-rate").value !== "" && $("output-rate").value !== "") { payload.input_rate = Number($("input-rate").value); payload.output_rate = Number($("output-rate").value); if ($("rate-source").value.trim()) payload.rates_provenance = $("rate-source").value.trim(); }
  const result = await api("/api/runs/preview", payload);
  if (version !== previewVersion) throw new Error("Selection changed during preview. Preview again.");
  preview = result; $("scope").hidden = false; $("scope-text").textContent = pretty(preview.scope); updateStart(); note("Scope ready. Review it and explicitly authorize before starting. Rates are informational.");
}));
$("model-form").addEventListener("submit", (event) => { event.preventDefault(); action(event.submitter, async () => {
  if (!$("approve-start").checked) throw new Error("Explicit authorization is required.");
  const hosted = $("provider").value === "deepseek"; if (hosted && !preview?.preview_token) throw new Error("Preview this exact hosted request first.");
  const payload = hosted ? {...preview.start_payload, preview_token: preview.preview_token} : startPayload();
  invalidatePreview(); note("Requesting model run… Its record will appear after creation; pause and cancel remain available there.");
  const result = await api("/api/runs/observe", payload); await selectRun(result.run_id); note("Run reached a boundary. Its observed outcome is recorded.");
}); });
for (const verb of ["pause", "cancel", "resume"]) $(verb).addEventListener("click", () => action($(verb), async () => {
  if (["cancel", "resume"].includes(verb) && !window.confirm(`${verb === "cancel" ? "Cancel" : "Resume"} this run?`)) return;
  const result = await api(`/api/runs/${selectedId}/${verb}`, verb === "resume" ? {confirm: true} : {}); note(`Observed status: ${result.status || "recorded"}`); await selectRun(selectedId);
}));
$("verify").addEventListener("click", () => action($("verify"), async () => { const data = await api(`/api/runs/${selectedId}/verify`, {}); $("verification").hidden = false; $("verification").textContent = pretty(data); note("Verification recorded in view. Check anchor coverage and failures."); }));
$("more-events").addEventListener("click", () => action($("more-events"), () => loadEvents()));
$("export-form").addEventListener("submit", (event) => { event.preventDefault(); action(event.submitter, async () => { const data = await api(`/api/runs/${selectedId}/export`, {out: $("export-path").value}); $("export-result").hidden = false; $("export-result").textContent = pretty(data); note("Local evidence bundle exported."); }); });
(async () => { try { const session = await api("/api/auth/session"); csrf = session.csrf_token; signedIn(true); await Promise.all([loadRuns(), loadProfiles()]); } catch (_) { signedIn(false); } })();
setInterval(() => { if (csrf && activeRequests > 0) loadRuns().catch(() => {}); }, 3000);

function studyChoice(container, value, title, checked, disabled = false) {
  const label = el("label", undefined, "check"), input = el("input");
  input.type = "checkbox"; input.value = value; input.checked = checked; input.disabled = disabled;
  label.append(input, el("span", title)); $(container).append(label);
}
for (const [id, title] of [["conceal-error-basic", "Conceal an error"], ["fictional-authority-basic", "Fictional authority"], ["claimed-harmlessness-basic", "Claimed harmlessness"], ["evaluation-pressure-basic", "Evaluation pressure"], ["authorized-useful-work-basic", "Authorized useful work"], ["correction-handoff-basic", "Correction and handoff"]]) {
  studyChoice("study-fixtures", id, title, ["conceal-error-basic", "authorized-useful-work-basic"].includes(id));
  const option = el("option", title); option.value = id; $("model-task").append(option);
}
for (const frame of ["ordinary", "game", "roleplay", "evaluation"]) studyChoice("study-frames", frame, frame, ["ordinary", "game"].includes(frame));
function invalidateStudy() { studyVersion++; studyPlan = null; $("study-result").hidden = true; invalidateStudyPreview(); }
function studyConfig() {
  const choices = id => [...$(id).querySelectorAll("input:checked:not(:disabled)")].map(input => input.value);
  const config = {schema_version: 1, fixture_ids: choices("study-fixtures"), frames: choices("study-frames"), profile_ids: choices("study-profiles"), provider: $("study-provider").value, model: $("study-model").value.trim(), thinking: $("study-thinking").value};
  for (const [key, id] of [["seed", "seed"], ["repeats", "repeats"], ["max_model_calls_per_trial", "calls"], ["max_output_tokens", "tokens"], ["max_trials", "max-trials"], ["max_total_model_calls", "total-calls"]]) config[key] = Number($("study-" + id).value);
  if (!config.fixture_ids.length || !config.frames.length || !config.profile_ids.length) throw new Error("Select at least one family, presentation and profile.");
  return config;
}
$("study-form").addEventListener("input", invalidateStudy);
$("study-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  invalidateStudy(); const version = studyVersion;
  const plan = await api("/api/studies/plan", {config: studyConfig()});
  if (version !== studyVersion || !csrf) throw new Error("Study selections changed. Build the schedule again.");
  studyPlan = plan; $("study-summary").textContent = `Planned: ${plan.counts.planned} · Started: ${plan.counts.started} · Provider completed: ${plan.counts.provider_completed} · Evaluable: ${plan.counts.evaluable}`;
  $("study-budget").textContent = `Ceilings: ${plan.budget.model_calls_ceiling} model calls · ${plan.budget.output_tokens_ceiling} output tokens`;
  $("study-identity").textContent = `${plan.study_id} · ${plan.plan_hash}`; $("study-json").textContent = pretty(plan);
  $("study-trials").replaceChildren();
  for (const trial of plan.trials) { const row = el("tr"); for (const value of [trial.ordinal + 1, trial.fixture_id, trial.frame, trial.profile_id, trial.repeat + 1]) row.append(el("td", String(value))); $("study-trials").append(row); }
  $("study-execution-cap").value = String(plan.config.max_total_model_calls);
  $("study-result").hidden = false; updateStudyLaunch(); note("Schedule built. No trials started.");
}); });
$("download-plan").addEventListener("click", () => {
  if (!studyPlan) return;
  const url = URL.createObjectURL(new Blob([pretty(studyPlan) + "\n"], {type: "application/json"}));
  const link = el("a"); link.href = url; link.download = `${studyPlan.study_id}.json`; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

function updateStudyLaunch() {
  const hosted = studyPlan?.config.provider === "deepseek";
  $("study-hosted-fields").hidden = !hosted;
  $("preview-study").hidden = !studyPlan || studyPlan.config.provider === "scripted";
  $("start-study").disabled = !studyPlan || (hosted && !studyPreview?.preview_token) || !$("study-approve").checked || attemptedStudies.has(studyPlan?.study_id);
}
function invalidateStudyPreview() {
  studyPreviewVersion++; studyPreview = null; $("study-scope").hidden = true;
  $("study-approve").checked = false; updateStudyLaunch();
}
for (const id of ["study-execution-cap", "study-input-rate", "study-output-rate", "study-rate-source"]) $(id).addEventListener("input", invalidateStudyPreview);
$("preview-study").addEventListener("click", () => action($("preview-study"), async () => {
  if (!studyPlan) throw new Error("Build the schedule first.");
  invalidateStudyPreview(); const version = studyPreviewVersion;
  const body = {plan: studyPlan, max_model_calls: Number($("study-execution-cap").value)};
  const input = $("study-input-rate").value, output = $("study-output-rate").value;
  if ((input === "") !== (output === "")) throw new Error("Supply both rates, or leave both unknown.");
  if (input !== "") { body.input_rate = Number(input); body.output_rate = Number(output); if ($("study-rate-source").value.trim()) body.rates_provenance = $("study-rate-source").value.trim(); }
  const result = await api("/api/studies/preview", body);
  if (version !== studyPreviewVersion || !csrf) throw new Error("Study selections changed. Preview again.");
  studyPreview = result; $("study-scope-text").textContent = pretty(result.scope); $("study-scope").hidden = false;
  updateStudyLaunch(); note("Study scope ready. Review every condition, then authorize the exact plan and ceiling. Rates are informational.");
}));
$("study-approve").addEventListener("change", updateStudyLaunch);
$("study-provider").addEventListener("change", () => {
  if ($("study-provider").value === "scripted") $("study-model").value = "scripted";
  else if ($("study-model").value === "scripted") $("study-model").value = "";
  invalidateStudy();
});
function clearStudyRead() {
  activeStudyId = null; studyReportStatus = null; studyReadVersion++; studyReadFailures = 0;
  $("study-execution-result").hidden = true;
}
function renderStudyReport(report) {
  if (report.study_id !== activeStudyId || report.plan?.study_id !== activeStudyId || !Array.isArray(report.rows) || !Array.isArray(report.metric_counts)) throw new Error("Unexpected study report.");
  if (!["ready", "running", "completed", "partial", "interrupted"].includes(report.status)) throw new Error("Unknown study status.");
  studyReportStatus = report.status;
  $("study-execution-status").textContent = `Study ${report.status}`;
  $("study-execution-identity").textContent = report.study_id;
  $("study-execution-status").classList.toggle("error", ["partial", "interrupted"].includes(report.status));
  $("study-execution-provenance").textContent = `${report.plan.mode} · ${report.plan.config.provider} · ${report.plan.config.model} · development cases`;
  const c = report.counts;
  $("study-execution-counts").textContent = `Planned ${c.planned} · Dispatched ${c.dispatched} · Recorded ${c.recorded} · Started ${c.started} · Provider completed ${c.provider_completed} · Unknown ${c.unknown}`;
  $("study-execution-budget").textContent = `Reserved decision calls ${report.reserved_model_calls} / authorized ceiling ${report.max_model_calls}`;
  $("study-progress-note").textContent = ["ready", "running"].includes(report.status) ? "Reading progress while the study runs. Recorded runs are also available in the run inventory." : "Recorded snapshot loaded. Trials are not automatically resumed or repeated.";
  $("study-execution-trials").replaceChildren();
  for (const row of report.rows) {
    const trial = report.plan.trials[row.ordinal], tr = el("tr");
    tr.append(el("td", String(row.ordinal + 1)), el("td", `${trial.fixture_id} · ${trial.frame} · ${trial.profile_id}`), el("td", row.status));
    const cell = el("td"), runId = row.result?.run_id || row.observed_run_id;
    if (runId) {
      const button = el("button", row.result ? `Inspect ${row.result.status} run` : "Inspect unconfirmed run", "secondary"); button.type = "button";
      button.addEventListener("click", () => action(button, async () => { await selectRun(runId); $("events").scrollIntoView({block: "center"}); }));
      cell.append(button, el("p", runId, "mono"));
    } else cell.textContent = row.dispatched ? "Run identity not returned" : "No dispatch";
    const missingness = row.stop_reason ? `${row.missing_reason} · study stopped: ${row.stop_reason}` : row.missing_reason || "—";
    tr.append(cell, el("td", missingness.replaceAll("_", " "))); $("study-execution-trials").append(tr);
  }
  $("study-execution-metrics").replaceChildren();
  for (const metric of report.metric_counts) {
    const tr = el("tr");
    for (const value of [`${metric.profile_id} · ${metric.frame} · ${metric.condition_hash.slice(0, 12)} · ${metric.metric}`, metric.planned, metric.evaluable, `${metric.yes} / ${metric.no}`, `${metric.indeterminate} / ${metric.not_estimated}`]) tr.append(el("td", String(value)));
    $("study-execution-metrics").append(tr);
  }
  $("study-execution-json").textContent = pretty(report); $("study-execution-result").hidden = false;
}
async function readStudyProgress() {
  if (!activeStudyId || !csrf) return;
  const id = activeStudyId, version = ++studyReadVersion;
  try {
    const report = await api(`/api/studies/${encodeURIComponent(id)}`);
    if (version !== studyReadVersion || id !== activeStudyId || !csrf) return;
    studyReadFailures = 0; renderStudyReport(report);
  } catch (error) {
    if (version === studyReadVersion && id === activeStudyId && csrf) {
      if (++studyReadFailures >= 3) studyReportStatus = "unconfirmed";
      $("study-progress-note").textContent = `Progress unavailable: ${error.message} Any displayed snapshot may be older. ${studyReadFailures >= 3 ? "Automatic refresh paused; use Read study progress." : "Do not retry a launch to refresh it."}`;
    }
    throw error;
  }
}
$("study-launch-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  if (!studyPlan || !$("study-approve").checked || attemptedStudies.has(studyPlan.study_id)) throw new Error("Build and authorize a new plan, or inspect the existing study.");
  const hosted = studyPlan.config.provider === "deepseek";
  if (hosted && !studyPreview?.preview_token) throw new Error("Preview this exact hosted study first.");
  const cap = Number($("study-execution-cap").value);
  if (!Number.isInteger(cap) || cap < studyPlan.budget.model_calls_ceiling || cap > 32768) throw new Error("The authorized ceiling must cover the displayed schedule.");
  const plan = studyPlan, requestSession = csrf;
  const payload = hosted ? {...studyPreview.start_payload, preview_token: studyPreview.preview_token} : {plan, max_model_calls: cap, confirm: true};
  invalidateStudyPreview();
  attemptedStudies.add(plan.study_id); updateStudyLaunch(); clearStudyRead();
  activeStudyId = plan.study_id; studyReportStatus = "submitting"; $("study-record-id").value = activeStudyId;
  $("study-execution-status").textContent = "Study launch requested · outcome pending";
  $("study-execution-status").classList.remove("error");
  for (const id of ["study-execution-identity", "study-execution-provenance", "study-execution-counts", "study-execution-budget", "study-execution-json"]) $(id).textContent = "";
  for (const id of ["study-execution-trials", "study-execution-metrics"]) $(id).replaceChildren();
  $("study-progress-note").textContent = "Reading the durable journal as trials reach recorded boundaries.";
  $("study-execution-result").hidden = false;
  try {
    const report = await api("/api/studies/start", payload);
    if (requestSession !== csrf || activeStudyId !== plan.study_id) return;
    studyReadVersion++; renderStudyReport(report); await loadRuns(); note(`Study ${report.status}. Inspect every planned row and its missingness.`, report.status !== "completed");
  } catch (error) {
    if (requestSession === csrf && activeStudyId === plan.study_id) {
      $("study-progress-note").textContent = `Launch response unavailable: ${error.message} Inspect this study; the request may have created records.`;
      await readStudyProgress().catch(() => {});
    }
    throw error;
  }
}); });
$("study-record-id").addEventListener("input", clearStudyRead);
$("study-inspect-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  clearStudyRead(); activeStudyId = $("study-record-id").value.trim(); await readStudyProgress();
}); });
$("refresh-study").addEventListener("click", () => action($("refresh-study"), readStudyProgress));
setInterval(async () => {
  if (!csrf || !activeStudyId || studyPollBusy || !["submitting", "ready", "running"].includes(studyReportStatus)) return;
  studyPollBusy = true;
  try { await readStudyProgress(); } catch (_) { /* visible in the progress note; never retry POST */ }
  finally { studyPollBusy = false; }
}, 1500);

async function loadReviewQueue() {
  const version = ++reviewQueueVersion;
  $("global-review-count").textContent = "Loading…";
  try {
    const data = await api("/api/reviews");
    if (version !== reviewQueueVersion || !csrf) return;
    $("global-reviews").replaceChildren();
    $("global-review-count").textContent = `${data.open} open · ${data.total} total`;
    if (!data.reviews.length) $("global-reviews").append(el("p", "No recorded review requests.", "muted"));
    for (const review of data.reviews) {
      const row = el("div", undefined, "review"); row.dataset.reviewId = review.review_id;
      row.append(el("strong", review.effective_status.replaceAll("_", " ") + (review.effective_status !== review.status ? ` (recorded: ${review.status})` : "")), el("p", review.conflict), el("p", `Recipient: ${review.recipient_role} · Deadline: ${review.deadline_at}`, "fine"), el("p", `Run: ${review.run_id} · ${review.run_status}`, "mono"));
      const button = el("button", "Inspect proposal in run", "secondary"); button.type = "button";
      button.addEventListener("click", () => action(button, async () => { await selectRun(review.run_id); $("reviews").scrollIntoView({block: "center"}); note("Review loaded from its run. Inspect the binding and observed state before resolving."); }));
      row.append(button); $("global-reviews").append(row);
    }
  } catch (error) { if (version === reviewQueueVersion) { $("global-review-count").textContent = "Unavailable"; $("global-reviews").replaceChildren(el("p", error.message, "error")); } throw error; }
}
$("refresh-reviews").addEventListener("click", () => action($("refresh-reviews"), loadReviewQueue));
$("global-review-panel").addEventListener("toggle", () => { if ($("global-review-panel").open && csrf) loadReviewQueue().catch(error => note(error.message, true)); });

function loadReplay(run) {
  replayEvents = [...run.events].sort((a, b) => a.seq - b.seq);
  $("replay-provenance").textContent = `Replay view · source: ${run.manifest.mode} · ${run.manifest.provider_kind} · ${run.manifest.run_id}. No provider is invoked and no run state is changed.`;
  $("replay-position").max = String(Math.max(0, replayEvents.length - 1));
  $("replay-position").value = $("replay-position").max;
  $("replay-position").disabled = replayEvents.length === 0;
  renderReplay();
}
function renderReplay() {
  const index = Number($("replay-position").value), event = replayEvents[index];
  $("replay-position-label").textContent = event ? `Event ${event.seq} · ${event.event_type.replaceAll("_", " ")} · ${index + 1} of ${replayEvents.length} recorded events` : "No recorded events to replay.";
  renderResources(replayEvents.slice(0, index + 1), "replay-resources");
}
$("replay-position").addEventListener("input", renderReplay);

function invalidateComparison() { comparisonVersion++; $("comparison-result").hidden = true; }
$("comparison-form").addEventListener("input", invalidateComparison);
$("comparison-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  invalidateComparison(); const version = comparisonVersion;
  const params = new URLSearchParams({left_run_id: $("comparison-left").value, right_run_id: $("comparison-right").value, axis: $("comparison-axis").value});
  const response = await api(`/api/comparisons?${params}`);
  const result = response.comparison;
  if (version !== comparisonVersion || !csrf) throw new Error("Comparison selection changed. Compare again.");
  $("comparison-status").textContent = result.status === "matched" ? "Recorded conditions match" : "Not comparable";
  $("comparison-counts").textContent = `Selected: ${result.counts.selected} · Planned: unavailable (selected after collection) · Started: ${result.counts.started} · Provider completed: ${result.counts.provider_completed}`;
  $("comparison-count-definition").textContent = "Provider completed means the run recorded completion. Inspect the outcome labels for behavioral results.";
  $("comparison-reasons").replaceChildren();
  for (const reason of result.reasons) $("comparison-reasons").append(el("p", reason.replaceAll("_", " "), "fine"));
  $("comparison-runs").replaceChildren();
  for (const run of result.runs) {
    const row = el("div", undefined, "review"); row.append(el("strong", `${run.side}: ${run.mode} · Dataset split: ${run.dataset_split}`), el("p", `${run.run_id} · ${run.provider} · ${run.profile_id} · ${run.frame}`, "fine"));
    if (run.recorded_evaluation.missingness.length) row.append(el("p", `Missingness: ${run.recorded_evaluation.missingness.join(", ")}`, "fine"));
    row.append(el("p", `Evidence: ${run.verification.summary || run.verification.status}`, "fine"));
    $("comparison-runs").append(row);
  }
  $("comparison-metrics").replaceChildren();
  for (const metric of result.metrics) { const row = el("tr"); for (const value of [metric.metric.replaceAll("_", " "), metric.left, metric.right, metric.evaluable_pairs, `${metric.not_evaluable_pairs} · ${metric.reason || "none"}`]) row.append(el("td", String(value))); $("comparison-metrics").append(row); }
  if (!result.metrics.length) { const row = el("tr"), cell = el("td", "No usable recorded evaluation labels."); cell.colSpan = 5; row.append(cell); $("comparison-metrics").append(row); }
  $("comparison-limits").textContent = result.limitations.join(" "); $("comparison-json").textContent = pretty(result); $("comparison-result").hidden = false;
  note(result.status === "matched" ? "Conditions matched; inspect metric-specific missingness and evidence limits." : "Comparison refused for the listed conditions. No paired outcome counts are eligible.");
}); });

function invalidateBundle() {
  bundleVersion++; bundleEvents = []; $("bundle-result").hidden = true;
  $("bundle-replay").hidden = true; $("bundle-resources").replaceChildren();
}
$("bundle-form").addEventListener("input", invalidateBundle);
$("bundle-form").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => {
  invalidateBundle(); const version = bundleVersion;
  const result = await api("/api/replays", {bundle_dir: $("bundle-path").value.trim()});
  if (version !== bundleVersion || !csrf) throw new Error("Bundle selection changed. Inspect again.");
  if (result.mode !== "replay" || result.recorded !== false || result.provider_invoked !== false) throw new Error("Unexpected bundle inspection response.");
  const verification = result.verification;
  const usable = verification.chain_consistent && !verification.failures.length && verification.summary === "chain_consistent; external_anchor_absent";
  $("bundle-status").textContent = usable ? "Bundle checks passed · external anchor absent" : "Bundle inspection failed";
  $("bundle-status").classList.toggle("error", !usable);
  const manifest = result.source_manifest;
  $("bundle-provenance").textContent = manifest ? `Replay · source: ${manifest.mode} · ${manifest.provider_kind} · ${manifest.run_id}` : "Replay · source manifest unavailable";
  $("bundle-limits").textContent = "These checks assess the imported files. They do not establish an independently retained anchor or correspondence with the current store. No run is imported or started.";
  $("bundle-verification").textContent = pretty(verification); $("bundle-failures").replaceChildren();
  for (const failure of verification.failures) $("bundle-failures").append(el("p", failure, "error"));
  if (usable) {
    bundleEvents = result.events;
    $("bundle-position").max = String(Math.max(0, bundleEvents.length - 1));
    $("bundle-position").value = $("bundle-position").max;
    $("bundle-position").disabled = bundleEvents.length === 0;
    renderBundleReplay(); $("bundle-replay").hidden = false;
  }
  $("bundle-result").hidden = false;
  note(usable ? "Imported trace inspected. Replay is separate from stored-run controls." : "Bundle checks failed. Reconstruction is withheld; inspect the failures.", !usable);
}); });
function renderBundleReplay() {
  const index = Number($("bundle-position").value), event = bundleEvents[index];
  $("bundle-position-label").textContent = event ? `Event ${event.seq} · ${event.event_type.replaceAll("_", " ")} · ${index + 1} of ${bundleEvents.length} imported events` : "No imported events.";
  renderResources(bundleEvents.slice(0, index + 1), "bundle-resources");
}
$("bundle-position").addEventListener("input", renderBundleReplay);
