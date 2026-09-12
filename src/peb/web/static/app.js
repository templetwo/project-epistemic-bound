"use strict";
const $ = (id) => document.getElementById(id);
let csrf = "", selectedId = null, nextCursor = null, preview = null, activeRequests = 0;
let selectionVersion = 0, previewVersion = 0, selectedState = null;
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
function signedIn(yes) { $("signin").hidden = yes; $("workroom").hidden = !yes; $("logout").hidden = !yes; if (!yes) { csrf = ""; invalidatePreview(); } }
async function action(button, task) {
  button.disabled = true; activeRequests++;
  try { await task(); } catch (error) { note(error.message, true); }
  finally { activeRequests--; button.disabled = false; updateStart(); updateRunControls(); }
}
function invalidatePreview() { previewVersion++; preview = null; $("scope").hidden = true; $("approve-start").checked = false; updateStart(); }
function updateStart() { const hosted = $("provider").value === "deepseek"; $("hosted-fields").hidden = !hosted; $("create-model").disabled = hosted; $("start-model").disabled = !$("approve-start").checked || (hosted && !preview?.preview_token); }
function startPayload() { return {provider: $("provider").value, model: $("model").value.trim(), profile: $("profile").value, task: "conceal-error-basic", max_model_calls: Number($("calls").value), max_output_tokens: Number($("tokens").value), thinking: $("thinking").value, confirm: true}; }
async function loadProfiles() {
  const data = await api("/api/profiles"); $("profile").replaceChildren();
  for (const p of data.profiles) { const option = el("option", `${p.profile_id} · ${p.arm} · ${p.status}`); option.value = p.profile_id; option.disabled = !p.runnable; $("profile").append(option); }
  $("profile").value = "baseline";
}
async function loadRuns() {
  const data = await api("/api/runs"); $("run-count").textContent = String(data.runs.length); $("runs").replaceChildren();
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
function renderResources(events) {
  $("resources").replaceChildren();
  for (const [id, value] of resourceMap(events)) { const details = el("details", undefined, "resource"); const summary = el("summary", id); summary.append(el("span", `rev ${value.revision} · ${value.kind}`)); details.append(summary, el("pre", pretty(value.value))); $("resources").append(details); }
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
function renderReviews(reviews, held, events) {
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
          const result = await api(`/api/runs/${selectedId}/reviews/${review.review_id}/resolve`, {decision, note: input.value});
          note(`Review ${decision} recorded. ${result.executed ? "Effect applied." : "Inspect the recorded outcome below."}`); await selectRun(selectedId);
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
  $("manifest").textContent = pretty(data.run.manifest); renderResources(data.run.events); renderOutcomes(data.run.events); renderReviews(data.reviews || [], data.held || {}, data.run.events); renderCommitments(data.run.commitments || []); $("corrections").textContent = pretty(data.run.corrections || []);
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
