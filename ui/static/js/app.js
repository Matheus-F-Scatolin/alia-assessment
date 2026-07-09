// Orchestrator: loads data, wires the panels, and drives one question's
// live run — routing SSE events to the answer, the timeline, the graph, and
// the lineage view; then persisting the result to history.

import { getGraph, getCorpus, askStream } from "./api.js";
import { loadRenderLibs } from "./libs.js";
import {
  store, ingestGraph, ingestCorpus,
  renderMarkdown, decorateCitations, makeChip,
} from "./store.js";
import { createTimeline } from "./timeline.js";
import { createGraph } from "./graph.js";
import { createDrawer } from "./drawer.js";
import { createLineageView } from "./lineage.js";

const $ = (id) => document.getElementById(id);
const HISTORY_KEY = "alia:history:v2";
const MODEL_KEY = "alia:model";
const HISTORY_MAX = 20;

const els = {
  app: $("app"),
  messages: $("messages"),
  examples: $("examples"),
  form: $("ask-form"),
  question: $("question"),
  askBtn: $("ask-btn"),
  hint: $("composer-hint"),
  modelSelect: $("model-select"),
  history: $("history-list"),
  newBtn: $("new-btn"),
  railToggle: $("rail-toggle"),
  legend: $("legend"),
  graphLegend: $("graph-legend"),
  graphCanvas: $("graph-canvas"),
  graphSeg: $("graph-seg"),
  graphMeta: $("graph-meta"),
  graphHint: $("graph-hint"),
  lineageView: $("lineage-view"),
  timeline: { list: $("timeline"), meta: $("timeline-meta"), idle: $("timeline-idle") },
  drawer: {
    root: $("drawer"), scrim: $("drawer-scrim"),
    kicker: $("drawer-kicker"), body: $("drawer-body"), closeBtn: $("drawer-close"),
  },
};

const app = window.__alia = {
  graph: null,
  timeline: null,
  drawer: null,
  lineage: null,
  run: null,
  busy: false,
  graphMode: "completo",
  history: [],
  activeHistory: null,
};

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------
(async function boot() {
  app.timeline = createTimeline(els.timeline);
  app.drawer = createDrawer(els.drawer);
  app.lineage = createLineageView(els.lineageView, { onOpen: openEvidence });

  try {
    await loadRenderLibs();
    const [graph, corpus] = await Promise.all([getGraph(), getCorpus()]);
    ingestGraph(graph);
    ingestCorpus(corpus);
  } catch (e) {
    els.messages.innerHTML =
      `<div class="msg"><div class="error-card"><div class="error-card__msg">Não foi possível carregar os dados do servidor: ${e.message}. Confirme que o servidor está rodando (uvicorn ui.server:app --port 8410).</div></div></div>`;
    return;
  }

  renderExamples();
  renderModelSelect();
  renderLegends();
  loadHistory();
  renderHistory();
  wireEvents();

  app.graph = await createGraph(els.graphCanvas, {
    onNodeClick: (ref) => openEvidence("entity", ref),
    onReady: () => { app.graph?.zoomToFit(0, 46); updateGraphMeta(); },
  });
  updateGraphMeta();
  updateGraphHint();
})();

// ---------------------------------------------------------------------------
// static UI
// ---------------------------------------------------------------------------
function renderExamples() {
  els.examples.innerHTML = "";
  store.examples.forEach((q, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "example";
    b.innerHTML = `<span class="example__k">exemplo ${String(i + 1).padStart(2, "0")}</span>`;
    b.appendChild(document.createTextNode(q));
    b.addEventListener("click", () => submit(q));
    els.examples.appendChild(b);
  });
}

function renderModelSelect() {
  const saved = localStorage.getItem(MODEL_KEY);
  const chosen = store.models.some((m) => m.id === saved) ? saved : store.defaultModel;
  els.modelSelect.innerHTML = "";
  store.models.forEach((m) => {
    const o = document.createElement("option");
    o.value = m.id;
    o.textContent = m.label;
    if (m.id === chosen) o.selected = true;
    els.modelSelect.appendChild(o);
  });
  els.modelSelect.addEventListener("change", () => localStorage.setItem(MODEL_KEY, els.modelSelect.value));
}

function renderLegends() {
  // node hues over the canvas
  const hues = [
    ["Person", "var(--person)"], ["Project", "var(--project)"],
    ["Goal", "var(--goal)"], ["Objective", "var(--objective)"],
  ];
  els.graphLegend.innerHTML = hues
    .map(([n, c]) => `<span class="legend__row"><span class="legend__dot" style="background:${c}"></span>${n}</span>`)
    .join("") +
    `<span class="legend__row"><span class="legend__dot" style="background:transparent;border:1.3px dashed var(--leaving)"></span>saindo</span>`;

  // chip-type key in the rail (reinforces the estado/evento distinction)
  els.legend.innerHTML = `
    <span class="eyebrow legend__title">evidência</span>
    <span class="legend__row"><span class="legend__dot" style="background:var(--gold)"></span><span class="legend__dot" style="background:var(--silver)"></span><span class="legend__dot" style="background:var(--bronze)"></span>&nbsp;pílula = evento (gold/silver/bronze)</span>
    <span class="legend__row"><span class="legend__sq" style="background:var(--surface-3);border-left:3px solid var(--person)"></span>tag = estado (entidade)</span>`;
}

// ---------------------------------------------------------------------------
// history
// ---------------------------------------------------------------------------
function loadHistory() {
  try { app.history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch { app.history = []; }
}
function saveHistory() {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(app.history.slice(0, HISTORY_MAX))); }
  catch { /* quota — ignore */ }
}
function renderHistory() {
  if (!app.history.length) {
    els.history.innerHTML = `<div class="history-empty">Suas perguntas aparecem aqui.</div>`;
    return;
  }
  els.history.innerHTML = "";
  app.history.forEach((h) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "history-item" + (h.id === app.activeHistory ? " is-active" : "");
    const when = new Date(h.ts);
    const meta = `${h.stats ? h.stats.tool_calls + " tools · " : ""}${isNaN(when) ? "" : when.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`;
    b.innerHTML = `<span class="history-item__q"></span><span class="history-item__meta mono">${meta}</span>`;
    b.querySelector(".history-item__q").textContent = h.question;
    b.addEventListener("click", () => restoreHistory(h.id));
    els.history.appendChild(b);
  });
}

function persistRun(run) {
  if (run.status !== "done") return;
  const rec = {
    id: run.id, question: run.question, model: run.model, ts: run.ts,
    answer: run.answer, lineage: run.lineage, stats: run.stats,
    trail: {
      entities: [...run.trail.entities], golds: [...run.trail.golds],
      silvers: [...run.trail.silvers], bronzes: [...run.trail.bronzes],
    },
    calls: run.calls,
  };
  app.history = [rec, ...app.history.filter((h) => h.id !== rec.id)].slice(0, HISTORY_MAX);
  app.activeHistory = rec.id;
  saveHistory();
  renderHistory();
}

function restoreHistory(id) {
  if (app.busy) return;
  const h = app.history.find((x) => x.id === id);
  if (!h) return;
  app.activeHistory = id;
  app.run = null;

  els.app.dataset.empty = "false";
  const { answerEl } = buildMessage(h.question);
  answerEl.innerHTML = renderMarkdown(h.answer || "");
  decorateCitations(answerEl, openEvidence);
  markVerified(answerEl, h.lineage);
  renderLineageFooter(answerEl.parentElement, h.lineage);
  renderStats(answerEl.parentElement, h.stats);

  app.timeline.restore(h.calls, openEvidence, h.stats);
  app.lineage.render(h.lineage);
  if (app.graph) {
    app.graph.setActive(false);
    app.graph.setTrail(h.trail?.entities || []);
    if (app.graphMode === "trilha") app.graph.zoomToTrail();
  }
  updateGraphMeta();
  renderHistory();
}

// ---------------------------------------------------------------------------
// asking
// ---------------------------------------------------------------------------
function buildMessage(question) {
  // keep the persistent hero in the DOM; just hide it and swap the answer
  els.messages.querySelectorAll(".msg").forEach((m) => m.remove());
  els.app.dataset.empty = "false";
  const msg = document.createElement("div");
  msg.className = "msg";
  msg.innerHTML =
    `<div class="msg__q"><span class="msg__q-tag">pergunta</span><div class="msg__q-text"></div></div>` +
    `<div class="answer is-streaming" tabindex="-1"></div>`;
  msg.querySelector(".msg__q-text").textContent = question;
  els.messages.appendChild(msg);
  return { msgEl: msg, answerEl: msg.querySelector(".answer") };
}

function submit(question) {
  question = (question || "").trim();
  if (!question || app.busy) return;

  els.app.dataset.empty = "false";
  app.activeHistory = null;
  const { msgEl, answerEl } = buildMessage(question);

  const run = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    question, model: els.modelSelect.value, ts: Date.now(),
    answer: "", turn: 0, msgEl, answerEl,
    trail: { entities: new Set(), golds: new Set(), silvers: new Set(), bronzes: new Set() },
    lineage: { gold: [], silver: [], bronze: [] },
    calls: [], stats: null, error: null, status: "streaming",
    abort: new AbortController(),
    t0: performance.now(), lastAt: performance.now(),
    renderScheduled: false,
  };
  app.run = run;
  setBusy(true);

  app.timeline.reset();
  app.lineage.render(run.lineage);
  if (app.graph) {
    app.graph.reset();
    app.graph.setActive(true);
    setGraphMode("completo");
  }
  updateGraphMeta();

  askStream({ question, model: run.model }, (ev) => onEvent(run, ev), run.abort.signal)
    .catch((e) => onEvent(run, { type: "error", message: e.message }))
    .finally(() => { if (run.status === "streaming") { run.status = "done"; finalize(run); } });
}

function onEvent(run, ev) {
  if (app.run !== run) return; // stale (superseded run)
  switch (ev.type) {
    case "text_delta": {
      if (ev.turn && ev.turn !== run.turn) { run.turn = ev.turn; run.answer = ""; }
      run.answer += ev.text || "";
      scheduleRender(run);
      break;
    }
    case "tool_call": {
      const now = performance.now();
      const dt = (now - run.lastAt) / 1000;
      run.lastAt = now;
      const call = { seq: ev.seq, name: ev.name, args: ev.args, dt };
      run.calls.push(call);
      app.timeline.addCall(call);
      break;
    }
    case "tool_result": {
      const call = run.calls.find((c) => c.seq === ev.seq);
      if (call) { call.summary = ev.summary; call.full = ev.full; call.touched = ev.touched; }
      app.timeline.completeCall(ev, openEvidence);
      const t = ev.touched || {};
      addAll(run.trail.entities, t.entities);
      addAll(run.trail.golds, t.golds);
      addAll(run.trail.silvers, t.silvers);
      addAll(run.trail.bronzes, t.bronzes);
      if (app.graph && app.graph.touch(t.entities)) {
        if (app.graphMode === "trilha") app.graph.zoomToTrail(500);
      }
      updateGraphMeta();
      break;
    }
    case "lineage": {
      run.lineage = { gold: ev.gold || [], silver: ev.silver || [], bronze: ev.bronze || [] };
      renderLineageFooter(run.msgEl, run.lineage);
      markVerified(run.answerEl, run.lineage);
      app.lineage.render(run.lineage);
      if (app.graphMode === "lineage") app.lineage.relayout();
      break;
    }
    case "done": {
      run.stats = ev.stats;
      run.status = "done";
      finalize(run);
      break;
    }
    case "error": {
      run.error = ev.message;
      run.status = "error";
      renderError(run.msgEl, ev.message);
      finalize(run);
      break;
    }
  }
}

function scheduleRender(run) {
  if (run.renderScheduled) return;
  run.renderScheduled = true;
  requestAnimationFrame(() => {
    run.renderScheduled = false;
    if (app.run !== run) return;
    const nearBottom = isNearBottom();
    run.answerEl.innerHTML = renderMarkdown(run.answer);
    decorateCitations(run.answerEl, openEvidence);
    markVerified(run.answerEl, run.lineage);
    if (nearBottom) scrollToBottom();
  });
}

function finalize(run) {
  if (run !== app.run && run.status !== "done") return;
  run.answerEl.classList.remove("is-streaming");
  setBusy(false);
  if (app.graph) { app.graph.setActive(false); app.graph.fit(600); }
  if (run.status === "error") {
    app.timeline.errorState();
  } else {
    app.timeline.finish(run.stats);
    renderStats(run.msgEl, run.stats);
    persistRun(run);
  }
  updateGraphMeta();
}

// ---------------------------------------------------------------------------
// answer add-ons
// ---------------------------------------------------------------------------
function renderLineageFooter(msgEl, lineage) {
  msgEl.querySelector(".lineage-footer")?.remove();
  const total = lineage.gold.length + lineage.silver.length + lineage.bronze.length;
  const foot = document.createElement("div");
  foot.className = "lineage-footer";
  const head = document.createElement("div");
  head.className = "lineage-footer__head";
  head.innerHTML = `<span class="eyebrow">lineage consultado</span><span class="lineage-footer__badge">verificado</span>`;
  foot.appendChild(head);

  if (!total) {
    const p = document.createElement("div");
    p.style.cssText = "color:var(--ink-4);font-size:var(--fs-sm);font-style:italic";
    p.textContent = "nenhum dado do medallion foi consultado";
    foot.appendChild(p);
  } else {
    [["gold", lineage.gold], ["silver", lineage.silver], ["bronze", lineage.bronze]].forEach(([kind, ids]) => {
      if (!ids.length) return;
      const row = document.createElement("div");
      row.className = `lineage-row lineage-row--${kind}`;
      const label = document.createElement("span");
      label.className = "lineage-row__label";
      label.textContent = kind;
      const chips = document.createElement("span");
      chips.className = "lineage-row__chips";
      ids.forEach((id) => {
        const c = makeChip({ kind, id }, openEvidence);
        c.classList.add("chip--verified");
        chips.appendChild(c);
      });
      row.append(label, chips);
      foot.appendChild(row);
    });
  }
  // insert before stats if present
  const stats = msgEl.querySelector(".stats");
  if (stats) msgEl.insertBefore(foot, stats);
  else msgEl.appendChild(foot);
}

function renderStats(msgEl, stats) {
  msgEl.querySelector(".stats")?.remove();
  if (!stats) return;
  const wrap = document.createElement("div");
  wrap.className = "stats";
  const items = [
    ["latência", `${stats.latency_s}s`],
    ["tool calls", stats.tool_calls],
    ["tokens in", fmtNum(stats.input_tokens)],
    ["tokens out", fmtNum(stats.output_tokens)],
  ];
  wrap.innerHTML = items
    .map(([k, v]) => `<div class="stat"><span class="stat__v">${v}</span><span class="stat__k">${k}</span></div>`)
    .join("");
  msgEl.appendChild(wrap);
}

function renderError(msgEl, message) {
  msgEl.querySelector(".answer").classList.remove("is-streaming");
  msgEl.querySelector(".error-card")?.remove();
  const card = document.createElement("div");
  card.className = "error-card";
  card.innerHTML = `
    <span class="error-card__icon"><svg viewBox="0 0 20 20" width="20" height="20"><path d="M10 2l8 15H2z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M10 8v4M10 14.5v.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></span>
    <div><div class="error-card__title">Não foi possível responder</div><div class="error-card__msg"></div></div>`;
  card.querySelector(".error-card__msg").textContent = message;
  const answer = msgEl.querySelector(".answer");
  answer.after(card);
}

function markVerified(answerEl, lineage) {
  if (!lineage) return;
  const verified = new Set([...(lineage.gold || []), ...(lineage.silver || []), ...(lineage.bronze || [])]);
  answerEl.querySelectorAll(".chip--layer[data-id]").forEach((c) => {
    c.classList.toggle("chip--verified", verified.has(c.dataset.id));
  });
}

// ---------------------------------------------------------------------------
// graph mode + meta
// ---------------------------------------------------------------------------
function setGraphMode(mode) {
  app.graphMode = mode;
  els.graphSeg.querySelectorAll("button").forEach((b) => b.classList.toggle("is-active", b.dataset.mode === mode));
  const showLineage = mode === "lineage";
  els.lineageView.hidden = !showLineage;
  els.graphCanvas.style.visibility = showLineage ? "hidden" : "visible";
  els.graphLegend.style.display = showLineage ? "none" : "";
  if (app.graph && mode !== "lineage") {
    app.graph.setMode(mode);
    if (mode === "trilha") app.graph.zoomToTrail(600);
    else app.graph.zoomToFit(600, 46);
  }
  if (showLineage) {
    const lin = app.run?.lineage || app.history.find((h) => h.id === app.activeHistory)?.lineage || { gold: [], silver: [], bronze: [] };
    app.lineage.render(lin);
    requestAnimationFrame(() => app.lineage.relayout());
  }
  updateGraphHint();
}

function updateGraphMeta() {
  if (app.graphMode === "lineage") { els.graphMeta.textContent = "gold → silver → bronze"; return; }
  const trail = app.graph ? app.graph.trailSize() : 0;
  if (trail) els.graphMeta.textContent = `trilha: ${trail} nó${trail === 1 ? "" : "s"}`;
  else els.graphMeta.textContent = `${store.nodes.size} nós · ${store.edges.length} arestas`;
}
function updateGraphHint() {
  const hint = {
    completo: "arraste · scroll para zoom · clique num nó",
    trilha: "só o caminho da evidência desta resposta",
    lineage: "clique num card para abrir a evidência",
  }[app.graphMode];
  els.graphHint.textContent = hint || "";
}

// ---------------------------------------------------------------------------
// events + keyboard
// ---------------------------------------------------------------------------
function wireEvents() {
  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    submit(els.question.value);
    els.question.value = "";
    autoGrow();
  });
  els.question.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      els.form.requestSubmit();
    }
  });
  els.question.addEventListener("input", autoGrow);

  els.newBtn.addEventListener("click", newQuestion);

  els.graphSeg.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => setGraphMode(b.dataset.mode));
  });

  els.railToggle.addEventListener("click", () => {
    if (window.innerWidth <= 900) els.app.classList.toggle("rail-open");
    else els.app.classList.toggle("rail-collapsed");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && app.drawer.isOpen()) { app.drawer.close(); return; }
    if (e.key === "/" && !isTyping(e.target)) { e.preventDefault(); els.question.focus(); }
  });
}

function newQuestion() {
  if (app.busy && app.run) app.run.abort.abort();
  app.run = null;
  app.activeHistory = null;
  setBusy(false);
  els.messages.querySelectorAll(".msg").forEach((m) => m.remove());
  els.app.dataset.empty = "true";
  els.messages.scrollTop = 0;
  app.timeline.idleState();
  app.lineage.render({ gold: [], silver: [], bronze: [] });
  if (app.graph) { app.graph.reset(); app.graph.setActive(false); setGraphMode("completo"); }
  updateGraphMeta();
  renderHistory();
  els.question.focus();
}

function setBusy(v) {
  app.busy = v;
  els.askBtn.disabled = v;
  els.question.setAttribute("aria-busy", v ? "true" : "false");
}

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------
function openEvidence(kind, id) { app.drawer.open(kind, id); }
function addAll(set, arr) { (arr || []).forEach((x) => set.add(x)); }
function fmtNum(n) { return (n ?? 0).toLocaleString("pt-BR"); }
function isTyping(t) { return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable); }
function autoGrow() {
  const ta = els.question;
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
}
function isNearBottom() {
  const m = els.messages;
  return m.scrollHeight - m.scrollTop - m.clientHeight < 120;
}
function scrollToBottom() { els.messages.scrollTop = els.messages.scrollHeight; }
