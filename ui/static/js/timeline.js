// Agent timeline — the live "watch it think" rail. One row per tool call,
// sliding in as it streams, colored by the medallion layer it traverses,
// expandable to reveal touched entities + the raw tool result.

import { makeChip } from "./store.js";

const TOOL_HUE = {
  search_entities: "var(--project)",
  get_entity: "var(--project)",
  search_golds: "var(--gold)",
  get_gold: "var(--gold)",
  get_silvers: "var(--silver)",
  get_bronze: "var(--bronze)",
};

export function createTimeline(els) {
  const { list, meta, idle } = els;
  const rows = new Map(); // seq -> { li }

  function reset() {
    list.innerHTML = "";
    rows.clear();
    idle.hidden = true;
    meta.textContent = "executando…";
  }

  function idleState() {
    list.innerHTML = "";
    rows.clear();
    idle.hidden = false;
    meta.textContent = "ocioso";
  }

  function addCall({ seq, name, args, dt = 0 }) {
    idle.hidden = true;
    const delta = dt;

    const li = document.createElement("li");
    li.className = "tl-item is-running";
    li.style.setProperty("--tool-hue", TOOL_HUE[name] || "var(--silver)");

    const node = document.createElement("span");
    node.className = "tl-item__node";

    const row = document.createElement("button");
    row.type = "button";
    row.className = "tl-row";
    row.innerHTML = `
      <span class="tl-row__seq">${String(seq).padStart(2, "0")}</span>
      <div class="tl-row__main">
        <div class="tl-row__name"><span class="caret">›</span> ${name}</div>
        <div class="tl-row__args"></div>
        <div class="tl-row__summary">executando…</div>
      </div>
      <span class="tl-row__time">+${delta.toFixed(1)}s</span>`;
    row.querySelector(".tl-row__args").textContent = compactArgs(args);
    row.addEventListener("click", () => li.classList.toggle("is-open"));

    li.append(node, row);
    const detail = document.createElement("div");
    detail.className = "tl-detail";
    detail.innerHTML = `<div class="tl-detail__inner"></div>`;
    li.append(detail);

    list.appendChild(li);
    list.scrollTop = list.scrollHeight;
    rows.set(seq, { li });
  }

  function completeCall({ seq, name, summary, full, touched }, onOpenEvidence) {
    const entry = rows.get(seq);
    if (!entry) return;
    const { li } = entry;
    li.classList.remove("is-running");
    li.classList.add("is-done");
    li.querySelector(".tl-row__summary").textContent = summary || "";

    const inner = li.querySelector(".tl-detail__inner");
    inner.innerHTML = "";

    // touched chips (entities + corpus ids the result references)
    const touchedIds = [
      ...(touched?.golds || []).map((id) => ({ kind: "gold", id })),
      ...(touched?.silvers || []).map((id) => ({ kind: "silver", id })),
      ...(touched?.bronzes || []).map((id) => ({ kind: "bronze", id })),
      ...(touched?.entities || []).map((id) => ({ kind: "entity", id })),
    ];
    if (touchedIds.length) {
      const wrap = document.createElement("div");
      wrap.className = "tl-touch";
      touchedIds.slice(0, 24).forEach((t) => wrap.appendChild(makeChip(t, onOpenEvidence)));
      inner.appendChild(wrap);
    }

    const pre = document.createElement("pre");
    pre.className = "tl-json";
    pre.textContent = safeJson(full);
    inner.appendChild(pre);
  }

  function finish(stats) {
    const n = rows.size;
    meta.textContent = stats
      ? `concluído · ${n} tool${n === 1 ? "" : "s"} · ${stats.latency_s}s`
      : `concluído · ${n} tools`;
  }

  function errorState() {
    for (const { li } of rows.values()) {
      if (li.classList.contains("is-running")) {
        li.classList.remove("is-running");
        li.classList.add("is-error");
      }
    }
    meta.textContent = "erro";
  }

  // Rebuild a finished run from stored calls (history restore).
  function restore(calls, onOpen, stats) {
    list.innerHTML = "";
    rows.clear();
    idle.hidden = true;
    (calls || []).forEach((c) => {
      addCall(c);
      completeCall(c, onOpen);
    });
    finish(stats);
  }

  return { reset, idleState, addCall, completeCall, finish, errorState, restore };
}

function compactArgs(args) {
  if (!args || Object.keys(args).length === 0) return "";
  return JSON.stringify(args);
}

function safeJson(v) {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
