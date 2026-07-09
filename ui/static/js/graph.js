// Knowledge-graph view (force layout). Nodes colored by label, sized by degree;
// inactive nodes (valid_to set) render dashed + faded with a "saindo" tag.
// During a run, tool results "touch" nodes: they pulse once and stay lit,
// leaving a highlighted evidence trail. Modes: full graph ⇄ trail-only.

import { loadForceGraph } from "./libs.js";
import { store, entityLabel, entityName } from "./store.js";

const HUE = {
  Person: "#57B4A8", Project: "#6E93D6", Goal: "#B98CD9", Objective: "#D98AA2",
};
const HUE_RGB = {
  Person: [87, 180, 168], Project: [110, 147, 214], Goal: [185, 140, 217], Objective: [217, 138, 162],
};

export async function createGraph(container, { onNodeClick, onReady } = {}) {
  const ForceGraph = await loadForceGraph();
  if (!ForceGraph) {
    container.innerHTML = `<div class="graph-empty-note">Biblioteca de grafo indisponível (offline?).<br>O chat e o traço do agente seguem funcionando.</div>`;
    return null;
  }

  // build data
  const degree = new Map();
  for (const e of store.edges) {
    degree.set(e.source, (degree.get(e.source) || 0) + 1);
    degree.set(e.target, (degree.get(e.target) || 0) + 1);
  }
  const nodes = [...store.nodes.values()].map((n) => ({
    id: n.ref, label: n.label, name: n.name, role: n.role,
    active: n.active, valid_to: n.valid_to, deg: degree.get(n.ref) || 0,
  }));
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const links = store.edges
    .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, rel: e.rel, details: e.details, valid_to: e.valid_to }));

  let mode = "completo";        // completo | trilha
  let active = false;           // a run is in progress
  const touched = new Set();    // accumulated evidence trail (node refs)
  const pulses = new Map();     // ref -> start time
  let hoverId = null;

  const radius = (n) => 2.8 + Math.min(n.deg, 9) * 0.72;

  function nodeAlpha(n) {
    if (mode === "trilha") return touched.has(n.id) ? 1 : 0;
    if (active && touched.size) return touched.has(n.id) ? 1 : 0.12;
    return 1;
  }

  const Graph = ForceGraph()(container)
    .graphData({ nodes, links })
    .nodeId("id")
    .backgroundColor("rgba(0,0,0,0)")
    .autoPauseRedraw(false) // keep painting so pulses animate after cooldown
    .cooldownTime(4000)
    .d3AlphaDecay(0.035)
    .nodeLabel(nodeTooltip)
    .linkLabel((l) => (l.details ? `<div class="gtip"><span class="gtip__k">${l.rel}</span><br>${escapeHtml(l.details)}${l.valid_to ? `<br><span class="gtip__leaving">até ${l.valid_to}</span>` : ""}</div>` : `<div class="gtip"><span class="gtip__k">${l.rel}</span></div>`))
    .linkColor(linkColor)
    .linkWidth(linkWidth)
    .linkLineDash((l) => (l.valid_to ? [2, 2] : null))
    .onNodeHover((n) => { hoverId = n ? n.id : null; container.style.cursor = n ? "pointer" : "default"; })
    .onNodeClick((n) => onNodeClick?.(n.id))
    .onEngineStop(() => fitToMode(500))
    .nodeCanvasObject(drawNode)
    .nodePointerAreaPaint((n, color, ctx) => {
      if (nodeAlpha(n) <= 0.01) return;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius(n) + 3, 0, 2 * Math.PI);
      ctx.fill();
    });

  // gently spread the graph
  Graph.d3Force("charge").strength(-160);
  if (Graph.d3Force("link")) Graph.d3Force("link").distance(46);

  // keep the view framed: fit all nodes (or the trail, in trilha mode). Called
  // whenever the layout settles, so nodes never drift out of frame.
  function fitToMode(ms = 500) {
    try {
      if (mode === "trilha" && touched.size) Graph.zoomToFit(ms, 60, (n) => touched.has(n.id));
      else Graph.zoomToFit(ms, 46);
    } catch { /* zoomToFit can throw before first paint */ }
  }

  function drawNode(n, ctx, scale) {
    const a = nodeAlpha(n);
    if (a <= 0.01) return;
    const hue = HUE[n.label] || "#9BA8B5";
    const rgb = HUE_RGB[n.label] || [155, 168, 181];
    const r = radius(n);
    const lit = touched.has(n.id);

    // pulse ring (once)
    const ps = pulses.get(n.id);
    if (ps != null) {
      const t = (performance.now() - ps) / 850;
      if (t < 1) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + t * 11, 0, 2 * Math.PI);
        ctx.strokeStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${(1 - t) * 0.75 * a})`;
        ctx.lineWidth = 1.6 / scale;
        ctx.stroke();
      } else {
        pulses.delete(n.id);
      }
    }

    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
    if (n.active) {
      ctx.fillStyle = withAlpha(rgb, a);
      ctx.fill();
    } else {
      // inactive: faded fill + dashed ring
      ctx.fillStyle = withAlpha(rgb, a * 0.16);
      ctx.fill();
      ctx.setLineDash([2 / scale, 1.8 / scale]);
      ctx.lineWidth = 1.3 / scale;
      ctx.strokeStyle = withAlpha(rgb, a * 0.9);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    if (lit) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 2.6 / scale, 0, 2 * Math.PI);
      ctx.strokeStyle = withAlpha(rgb, a);
      ctx.lineWidth = 1.4 / scale;
      ctx.stroke();
    }

    const showLabel = lit || n.id === hoverId || scale > 1.55 || n.deg >= 6;
    if (showLabel) {
      const fs = 10.5 / scale;
      ctx.font = `${lit ? 600 : 400} ${fs}px "IBM Plex Sans", sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      const label = n.name.length > 22 ? n.name.slice(0, 21) + "…" : n.name;
      ctx.fillStyle = lit ? `rgba(230,237,243,${a})` : `rgba(168,178,190,${a * 0.9})`;
      ctx.fillText(label, n.x, n.y + r + 1.5 / scale);
      if (!n.active && (lit || n.id === hoverId)) {
        ctx.font = `${9 / scale}px "JetBrains Mono", monospace`;
        ctx.fillStyle = `rgba(208,112,95,${a})`;
        ctx.fillText(`saindo ${n.valid_to}`, n.x, n.y + r + fs + 2.5 / scale);
      }
    }
  }

  function linkColor(l) {
    const s = idOf(l.source), t = idOf(l.target);
    const on = touched.has(s) && touched.has(t);
    if (mode === "trilha") return on ? "rgba(217,164,65,0.55)" : "rgba(0,0,0,0)";
    if (active && touched.size) return on ? "rgba(217,164,65,0.55)" : "rgba(120,132,146,0.045)";
    return "rgba(120,132,146,0.15)";
  }
  function linkWidth(l) {
    const on = touched.has(idOf(l.source)) && touched.has(idOf(l.target));
    return on ? 1.4 : 0.6;
  }

  // ResizeObserver keeps the canvas matched to its container
  const ro = new ResizeObserver(() => {
    const w = container.clientWidth, h = container.clientHeight;
    if (w && h) Graph.width(w).height(h);
  });
  ro.observe(container);
  requestAnimationFrame(() => {
    const w = container.clientWidth, h = container.clientHeight;
    if (w && h) Graph.width(w).height(h);
    onReady?.();
  });

  if (typeof window !== "undefined") window.__fg = Graph; // debug handle

  return {
    setMode(m) { mode = m; },
    setActive(v) { active = v; },
    touch(refs) {
      let added = false;
      for (const ref of refs || []) {
        if (nodeById.has(ref) && !touched.has(ref)) {
          touched.add(ref);
          pulses.set(ref, performance.now());
          added = true;
        }
      }
      return added;
    },
    setTrail(refs) {
      touched.clear();
      pulses.clear();
      for (const ref of refs || []) if (nodeById.has(ref)) touched.add(ref);
    },
    reset() { touched.clear(); pulses.clear(); },
    trailSize: () => touched.size,
    fit: fitToMode,
    zoomToFit(ms = 600, pad = 40) { try { Graph.zoomToFit(ms, pad); } catch {} },
    zoomToTrail(ms = 700) {
      if (!touched.size) return;
      try { Graph.zoomToFit(ms, 60, (n) => touched.has(n.id)); } catch {}
    },
    destroy() { ro.disconnect(); },
  };
}

// ---- helpers -------------------------------------------------------------
function idOf(x) { return typeof x === "object" ? x.id : x; }
function withAlpha(rgb, a) { return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`; }
function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
function nodeTooltip(n) {
  const label = entityLabel(n.id);
  const status = n.active
    ? ""
    : `<div class="gtip__leaving">saindo · ${n.valid_to}</div>`;
  return `<div class="gtip"><span class="gtip__k" style="color:${HUE[label] || "#9BA8B5"}">${label}</span><br><b>${escapeHtml(entityName(n.id))}</b>${n.role ? `<div class="gtip__role">${escapeHtml(n.role)}</div>` : ""}${status}</div>`;
}
