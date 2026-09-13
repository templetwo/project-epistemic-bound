"use strict";

// Display committed records only. The caller owns selection, ledger navigation,
// and the set of newly committed IDs; this module never reads or writes a run.
(() => {
  const actors = Object.freeze([
    {id: "supervisor", label: "Supervisor", glyph: "◉", className: "actor-supervisor"},
    {id: "subject", label: "Subject", glyph: "●", className: "actor-subject"},
    {id: "reference_monitor", label: "Reference monitor", glyph: "◇", className: "actor-monitor"},
    {id: "executor", label: "Executor", glyph: "▣", className: "actor-executor"},
    {id: "evaluator", label: "Evaluator", glyph: "≡", className: "actor-evaluator"},
  ].map(Object.freeze));
  const actorIndex = new Map(actors.map(actor => [actor.id, actor]));
  const views = new WeakMap();
  const PAGE_SIZE = 100;

  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  }

  function actorInfo(value) {
    const original = typeof value === "string" && value.length ? value : "Unknown actor";
    return actorIndex.get(original) || {id: original, label: original, glyph: "○", className: "actor-other"};
  }

  function actorBadge(actor) {
    const info = actorInfo(actor);
    const badge = node("span", undefined, `actor-badge ${info.className}`);
    badge.dataset.actor = info.id;
    const glyph = node("span", info.glyph, "actor-glyph");
    glyph.setAttribute("aria-hidden", "true");
    badge.append(glyph, node("span", info.label, "actor-label"));
    return badge;
  }

  function scalar(value) {
    return ["string", "number", "boolean"].includes(typeof value) ? String(value) : "";
  }

  function compact(value) {
    const text = scalar(value);
    return text.length > 120 ? `${text.slice(0, 119)}…` : text;
  }

  function summary(event) {
    const p = event.payload && typeof event.payload === "object" ? event.payload : {};
    switch (event.event_type) {
      case "run_created": return "Run and initial workspace recorded.";
      case "model_request": return p.correction_number !== undefined
        ? `Format correction request ${scalar(p.correction_number)} · step ${scalar(p.step)}`
        : `Model request recorded${p.step !== undefined ? ` · step ${scalar(p.step)}` : ""}`;
      case "model_response": return p.error ? `Response error: ${scalar(p.error)}`
        : `Response recorded${p.finish_reason ? ` · ${scalar(p.finish_reason)}` : ""}`;
      case "decision_recorded": return `Structured decision: ${scalar(p.kind) || "kind not recorded"}`;
      case "decision_invalid": return `Invalid structured output${p.reason ? ` · ${scalar(p.reason)}` : ""}`;
      case "action_proposed": return `Proposal: ${scalar(p.tool) || "tool not recorded"}`;
      case "preaction_declared": return "Pre-action declaration recorded.";
      case "gate_decided": return `${scalar(p.outcome) || "outcome not recorded"}${p.reason ? ` · ${scalar(p.reason)}` : ""}`;
      case "effect_observed": {
        const resources = p.status === "applied" && p.applied && typeof p.applied === "object"
          ? Object.keys(p.applied).join(", ") : "";
        return `${scalar(p.status) || "status not recorded"}${resources ? ` · ${resources}` : ""}`;
      }
      case "run_finished": return `${scalar(p.status) || "status not recorded"}${p.terminal_reason ? ` · ${scalar(p.terminal_reason)}` : ""}`;
      case "evaluation_recorded": return `Recorded evaluation${p.evaluation?.predicate_version ? ` · ${scalar(p.evaluation.predicate_version)}` : ""}`;
      case "review_opened": return "Review request recorded.";
      case "review_resolved": return `Review resolution: ${scalar(p.status) || scalar(p.decision) || "inspect record"}`;
      case "run_paused": return "Pause recorded.";
      case "run_resumed": return "Resume recorded.";
      case "run_interrupted": return "Interruption recorded.";
      case "commitment_proposed": return "Commitment proposal recorded.";
      case "commitment_accepted": return "Commitment acceptance recorded.";
      case "claim_corrected": return "Correction recorded; prior record retained.";
      case "checkpoint_exported": return "Checkpoint export recorded.";
      default: return "Recorded event; inspect the exact ledger payload.";
    }
  }

  function eventMark(event) {
    const p = event.payload || {};
    let glyph = "•", className = "trace-mark trace-event-mark";
    if (event.event_type === "gate_decided") {
      const state = p.outcome === "needs_approval" || p.reason === "protocol_hold" ? "hold"
        : p.outcome === "allow" ? "allow" : p.outcome === "deny" ? "deny" : "unknown";
      glyph = "◆"; className = `trace-mark trace-gate trace-gate-${state}`;
    } else if (event.event_type === "effect_observed" && p.status === "applied") {
      glyph = "■"; className = "trace-mark trace-effect-applied";
    }
    const mark = node("span", glyph, className);
    mark.setAttribute("aria-hidden", "true");
    return mark;
  }

  function eventContent(event, info) {
    const content = node("div", undefined, "trace-event-content");
    const badge = actorBadge(info.id); badge.classList.add("trace-row-actor");
    const eventType = scalar(event.event_type) || "unknown event";
    const title = node("p", eventType.replaceAll("_", " "), "trace-event-title");
    title.title = eventType;
    const fullSummary = summary(event);
    const detail = node("p", compact(fullSummary), "trace-event-summary");
    detail.title = fullSummary;
    content.append(eventMark(event), badge, title, detail);
    return content;
  }

  function eventRow(source, onJump, animateIds) {
    const event = source && typeof source === "object" ? source : {};
    const info = actorInfo(event.actor);
    const sequence = Number.isInteger(event.seq) && event.seq >= 0 ? String(event.seq) : "?";
    const eventId = scalar(event.event_id), eventType = scalar(event.event_type) || "unknown event";
    const row = node("article", undefined, `trace-row ${info.className}`);
    row.setAttribute("role", "listitem");
    row.setAttribute("aria-label", `Event ${sequence}: ${eventType.replaceAll("_", " ")}, ${info.label}`);
    if (eventId && animateIds.has(eventId)) {
      row.classList.add("trace-new");
      row.addEventListener("animationend", () => row.classList.remove("trace-new"), {once: true});
    }
    const jump = node("button", sequence === "?" ? "Event ?" : `#${sequence.padStart(3, "0")}`, "trace-seq");
    jump.type = "button";
    jump.dataset.eventId = eventId; jump.dataset.eventSeq = sequence;
    jump.dataset.actor = scalar(event.actor);
    jump.dataset.eventType = eventType;
    if (event.event_type === "gate_decided") jump.dataset.gateOutcome = scalar(event.payload?.outcome);
    jump.setAttribute("aria-label", `Inspect event ${sequence}: ${eventType.replaceAll("_", " ")}, ${info.label}`);
    jump.disabled = typeof onJump !== "function" || !eventId || sequence === "?" || !event.event_type;
    if (!jump.disabled) {
      const reference = Object.freeze({event_id: eventId, seq: event.seq, event_type: eventType});
      jump.addEventListener("click", () => onJump(reference));
    }
    const lanes = node("div", undefined, "trace-lanes");
    for (const actor of actors) {
      const lane = node("div", undefined, `trace-lane ${actor.className}`);
      if (actor.id === info.id) {
        lane.classList.add("trace-active");
        lane.setAttribute("aria-label", `${actor.label} actor lane`);
        lane.append(eventContent(event, info));
      } else lane.setAttribute("aria-hidden", "true");
      lanes.append(lane);
    }
    if (!actorIndex.has(info.id)) {
      const lane = node("div", undefined, "trace-other-lane trace-active actor-other");
      lane.setAttribute("aria-label", `Other recorded actor lane: ${info.label}`);
      lane.append(eventContent(event, info)); lanes.append(lane);
    }
    row.append(jump, lanes);
    return row;
  }

  function render(container, events, {onJump, animateIds} = {}) {
    const records = Array.isArray(events) ? events : [];
    const ordered = records.map((event, index) => ({event, index})).sort((left, right) => {
      const a = Number.isInteger(left.event?.seq) ? left.event.seq : Infinity;
      const b = Number.isInteger(right.event?.seq) ? right.event.seq : Infinity;
      return a === b ? left.index - right.index : a - b;
    }).map(item => item.event);
    const firstId = scalar(ordered[0]?.event_id);
    const prior = views.get(container);
    const shown = prior?.firstId === firstId ? Math.max(PAGE_SIZE, prior.shown) : PAGE_SIZE;
    const fresh = animateIds instanceof Set || Array.isArray(animateIds) ? new Set(animateIds) : new Set();
    const state = {firstId, shown}; views.set(container, state);
    const jumpCurrent = typeof onJump === "function" ? reference => {
      if (views.get(container) === state) onJump(reference);
    } : undefined;
    const focused = container.contains(document.activeElement) ? document.activeElement : null;
    const focusId = focused?.classList.contains("trace-seq") ? focused.dataset.eventId : null;
    const focusMore = focused?.classList.contains("trace-more"), focusScroll = focused?.classList.contains("trace-scroll");
    const previousScroll = container.querySelector(".trace-scroll");
    const scrollPosition = {left: previousScroll?.scrollLeft || 0, top: previousScroll?.scrollTop || 0};
    const view = node("div", undefined, "trace-view");
    const caption = node("p", undefined, "trace-caption");
    caption.setAttribute("role", "status");
    const guide = node("p", "Committed events in sequence order. Diamonds show recorded gate decisions; solid squares mark applied effects. Position does not imply causation. Event buttons open exact records.", "trace-guide");
    const scroll = node("div", undefined, "trace-scroll");
    scroll.tabIndex = 0;
    scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", "Committed event trace with five actor lanes and a supplementary lane for other actors");
    const grid = node("div", undefined, "trace-grid");
    const header = node("div", undefined, "trace-header");
    header.append(node("span", "Event", "trace-step-heading"));
    const headings = node("div", undefined, "trace-lanes");
    for (const actor of actors) {
      const heading = node("div", undefined, `trace-lane-heading ${actor.className}`);
      heading.append(actorBadge(actor.id)); headings.append(heading);
    }
    header.append(headings);
    const body = node("div", undefined, "trace-body"); body.setAttribute("role", "list");
    body.setAttribute("aria-label", "Recorded events in sequence order");
    grid.append(header, body); scroll.append(grid);
    const more = node("button", "Show next 100 recorded events", "trace-more"); more.type = "button";
    function appendPage() {
      const before = body.children.length;
      const end = Math.min(state.shown, ordered.length);
      for (let index = before; index < end; index++) body.append(eventRow(ordered[index], jumpCurrent, fresh));
      caption.textContent = `Showing ${end} of ${ordered.length} committed events · five actor lanes; other recorded actors remain labeled.`;
      more.hidden = end >= ordered.length;
      more.textContent = `Show next ${Math.min(PAGE_SIZE, ordered.length - end)} recorded events`;
      if (!ordered.length) caption.textContent = Array.isArray(events) ? "No committed events recorded." : "Committed event data is unavailable.";
    }
    more.addEventListener("click", () => {
      const next = body.children.length; state.shown += PAGE_SIZE; appendPage();
      body.children[next]?.querySelector(".trace-seq")?.focus({preventScroll: true});
    });
    appendPage();
    fresh.clear(); // Manual pagination reveals existing records, never newly arriving evidence.
    view.append(caption, guide, scroll, more);
    if (!ordered.length) view.append(node("p", "The trace will appear when committed events are available.", "trace-empty"));
    container.replaceChildren(view);
    scroll.scrollLeft = scrollPosition.left; scroll.scrollTop = scrollPosition.top;
    if (focusId) [...body.querySelectorAll(".trace-seq")].find(button => button.dataset.eventId === focusId)?.focus({preventScroll: true});
    else if (focusMore) (more.hidden ? body.lastElementChild?.querySelector(".trace-seq") : more)?.focus({preventScroll: true});
    else if (focusScroll) scroll.focus({preventScroll: true});
    return {eventCount: ordered.length, shownCount: Math.min(state.shown, ordered.length)};
  }

  window.PebTrace = Object.freeze({render, actorBadge, actors});
})();
