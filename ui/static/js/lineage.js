// Lineage DAG: the verified trail drawn left→right as gold → silver → bronze,
// with SVG connectors following the real refs (gold.silver_refs, silver.
// bronze_refs). Every node is clickable into the evidence drawer.

import { store } from "./store.js";

export function createLineageView(container, { onOpen } = {}) {
  let current = { gold: [], silver: [], bronze: [] };
  let dag = null;
  let svg = null;

  function render(sets) {
    current = {
      gold: sets.gold || [],
      silver: sets.silver || [],
      bronze: sets.bronze || [],
    };
    container.innerHTML = "";

    const total = current.gold.length + current.silver.length + current.bronze.length;
    if (!total) {
      container.innerHTML = `<div class="lineage-empty">Sem lineage ainda.<br>Faça uma pergunta — o caminho gold → silver → bronze aparece aqui.</div>`;
      dag = null;
      return;
    }

    dag = document.createElement("div");
    dag.className = "lineage-dag";
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "lineage-dag__svg");
    dag.appendChild(svg);

    dag.appendChild(column("gold", "Gold", current.gold));
    dag.appendChild(column("silver", "Silver", current.silver));
    dag.appendChild(column("bronze", "Bronze", current.bronze));
    container.appendChild(dag);

    relayout();
  }

  function column(kind, title, ids) {
    const col = document.createElement("div");
    col.className = `lineage-col lcol-${kind}`;
    const head = document.createElement("div");
    head.className = "lineage-col__head";
    head.textContent = `${title} · ${ids.length}`;
    col.appendChild(head);
    ids.forEach((id) => col.appendChild(node(kind, id)));
    return col;
  }

  function node(kind, id) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = `dag-node dag-${kind}`;
    el.dataset.id = id;
    el.dataset.kind = kind;
    const idEl = document.createElement("div");
    idEl.className = "dag-node__id";
    idEl.textContent = id;
    const t = document.createElement("div");
    t.className = "dag-node__t";
    t.textContent = preview(kind, id);
    el.append(idEl, t);
    el.addEventListener("click", () => onOpen?.(kind, id));
    el.addEventListener("mouseenter", () => highlight(kind, id, true));
    el.addEventListener("mouseleave", () => highlight(kind, id, false));
    return el;
  }

  // draw connector paths after layout is known
  function relayout() {
    if (!dag || !svg) return;
    // only meaningful when visible (has layout)
    if (!dag.offsetParent && dag.clientHeight === 0) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const base = dag.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${base.width} ${base.height}`);

    const center = (id) => {
      const el = dag.querySelector(`.dag-node[data-id="${cssEsc(id)}"]`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { top: r.top - base.top + r.height / 2, left: r.left - base.left, right: r.right - base.left };
    };

    const pairs = [];
    current.gold.forEach((gid) => {
      const g = store.golds.get(gid);
      (g?.silver_refs || []).forEach((sid) => {
        if (current.silver.includes(sid)) pairs.push([gid, sid, "var(--gold)"]);
      });
    });
    current.silver.forEach((sid) => {
      const s = store.silvers.get(sid);
      (s?.bronze_refs || []).forEach((bid) => {
        if (current.bronze.includes(bid)) pairs.push([sid, bid, "var(--silver)"]);
      });
    });

    for (const [a, b, color] of pairs) {
      const ca = center(a), cb = center(b);
      if (!ca || !cb) continue;
      const x1 = ca.right, y1 = ca.top, x2 = cb.left, y2 = cb.top;
      const mx = (x1 + x2) / 2;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", color);
      path.setAttribute("stroke-width", "1.2");
      path.setAttribute("stroke-opacity", "0.4");
      path.dataset.from = a;
      path.dataset.to = b;
      svg.appendChild(path);
    }
  }

  function highlight(kind, id, on) {
    if (!dag) return;
    const connected = new Set([id]);
    // find direct neighbors across the pairs currently drawn
    svg.querySelectorAll("path").forEach((p) => {
      if (p.dataset.from === id) connected.add(p.dataset.to);
      if (p.dataset.to === id) connected.add(p.dataset.from);
      const active = p.dataset.from === id || p.dataset.to === id;
      p.setAttribute("stroke-opacity", on ? (active ? "0.95" : "0.12") : "0.4");
      p.setAttribute("stroke-width", on && active ? "1.8" : "1.2");
    });
    dag.querySelectorAll(".dag-node").forEach((el) => {
      el.classList.toggle("is-dim", on && !connected.has(el.dataset.id));
    });
  }

  return { render, relayout };
}

function preview(kind, id) {
  if (kind === "gold") return store.golds.get(id)?.title || "";
  if (kind === "silver") return store.silvers.get(id)?.text || "";
  if (kind === "bronze") {
    const b = store.bronzes.get(id);
    return b ? `${b.source} · capturado ${(b.captured_at || "").slice(0, 10)}` : "";
  }
  return "";
}
function cssEsc(s) {
  return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/"/g, '\\"');
}
