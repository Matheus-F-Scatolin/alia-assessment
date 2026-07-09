// Evidence drawer. Opens for a gold / silver / bronze / entity and shows its
// real content plus its lineage links (gold → its silvers → their bronzes, and
// the reverse), each clickable to navigate deeper. The entity card is the
// advisors' "side card" for entity-sourced evidence ("estado").

import {
  store, entityLabel, entityName, goldsCiting, silversCiting,
} from "./store.js";

const LAYER_LABEL = { gold: "Gold · narrativa", silver: "Silver · interpretação", bronze: "Bronze · dado bruto" };
const SOURCE_LABEL = {
  slack: "Slack", google_meet: "Google Meet", email: "E-mail",
  github: "GitHub", notion: "Notion",
};

export function createDrawer(els, { onNavigate } = {}) {
  const { root, scrim, kicker, body, closeBtn } = els;
  let lastFocus = null;

  function open(kind, id) {
    lastFocus = document.activeElement;
    kicker.innerHTML = "";
    body.innerHTML = "";
    let ok = false;
    if (kind === "gold") ok = renderGold(id);
    else if (kind === "silver") ok = renderSilver(id);
    else if (kind === "bronze") ok = renderBronze(id);
    else if (kind === "entity") ok = renderEntity(id);
    if (!ok) return;

    scrim.hidden = false;
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
    body.scrollTop = 0;
    closeBtn.focus();
    onNavigate?.(kind, id);
  }

  function close() {
    root.hidden = true;
    scrim.hidden = true;
    root.setAttribute("aria-hidden", "true");
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }

  // -- kicker (top-left label with a colored token) --
  function setKicker(cls, text, sub) {
    kicker.innerHTML = "";
    const dot = document.createElement("span");
    dot.className = `legend__${cls === "entity" ? "sq" : "dot"}`;
    dot.style.background = kickerColor(cls, sub);
    const label = document.createElement("span");
    label.textContent = text;
    kicker.append(dot, label);
  }

  // -- gold --
  function renderGold(id) {
    const g = store.golds.get(id);
    if (!g) return false;
    setKicker("gold", LAYER_LABEL.gold);
    addTitle(g.title, id);
    addProse(g.narrative);
    addEntityRefs(g.entity_refs);
    addLinkSection("silver", "Silvers de origem", g.silver_refs, "silver");
    addMeta({ atualizado_em: fmtTs(g.updated_at), tema: g.topic_key });
    return true;
  }

  // -- silver --
  function renderSilver(id) {
    const s = store.silvers.get(id);
    if (!s) return false;
    setKicker("silver", LAYER_LABEL.silver);
    addTitle(s.text, id);
    addEntityRefs(s.entity_refs);
    addLinkSection("bronze", "Evidência bruta (bronze)", s.bronze_refs, "bronze");
    const golds = goldsCiting(id).map((g) => g.id);
    addLinkSection("gold", "Citado por (gold)", golds, "gold");
    addMeta({ projeto: s.project_ref, ocorreu_em: fmtTs(s.occurred_at) });
    return true;
  }

  // -- bronze --
  function renderBronze(id) {
    const b = store.bronzes.get(id);
    if (!b) return false;
    setKicker("bronze", LAYER_LABEL.bronze);
    const h = document.createElement("div");
    h.innerHTML = `<div class="dw-sub">${id}</div>`;
    const tag = document.createElement("span");
    tag.className = "dw-source-tag";
    tag.textContent = SOURCE_LABEL[b.source] || b.source;
    const titleRow = document.createElement("div");
    titleRow.style.cssText = "display:flex;align-items:center;gap:10px;margin-bottom:16px";
    titleRow.append(tag, spanMuted(fmtTs(b.captured_at)));
    body.append(h, titleRow);

    const pre = document.createElement("pre");
    pre.className = "dw-raw";
    pre.textContent = b.content;
    body.appendChild(pre);

    addLinkSection("silver", "Interpretado em (silver)", silversCiting(id), "silver");
    return true;
  }

  // -- entity (the advisors' side card) --
  function renderEntity(ref) {
    const node = store.nodes.get(ref);
    if (!node) return false;
    const label = entityLabel(ref);
    setKicker("entity", `${label} · entidade`, label);

    const h1 = document.createElement("h2");
    h1.className = "dw-title";
    h1.textContent = entityName(ref);
    const sub = document.createElement("div");
    sub.className = "dw-sub";
    sub.textContent = ref;
    body.append(h1, sub);

    // status badge
    const badgeWrap = document.createElement("div");
    badgeWrap.style.marginBottom = "16px";
    if (node.active) {
      badgeWrap.innerHTML = `<span class="dw-badge-active">● ativo${node.valid_from ? " · desde " + node.valid_from : ""}</span>`;
    } else {
      badgeWrap.innerHTML = `<span class="dw-badge-leaving">▲ saindo · ${node.valid_to}</span>`;
    }
    body.appendChild(badgeWrap);

    if (node.role) addField("Papel", node.role);
    if (node.description) addProse(node.description);

    // graph neighborhood
    const neighbors = edgesFor(ref);
    if (neighbors.length) {
      const sec = section("Conexões no grafo");
      const wrap = document.createElement("div");
      neighbors.forEach((e) => {
        const other = e.source === ref ? e.target : e.source;
        const dir = e.source === ref ? "→" : "←";
        const row = document.createElement("div");
        row.style.cssText = "margin:9px 0";
        row.appendChild(makeEntityTag(other));
        const details = document.createElement("div");
        details.style.cssText = "font-size:12px;color:var(--ink-3);margin:3px 0 0 3px";
        details.innerHTML = `<span class="mono" style="color:var(--ink-4)">${dir} ${e.rel}</span>` +
          `${e.details ? " · " + escapeText(e.details) : ""}` +
          `${e.valid_to ? ` <span style="color:var(--leaving)">(até ${e.valid_to})</span>` : ""}`;
        row.appendChild(details);
        wrap.append(row);
      });
      sec.appendChild(wrap);
    }

    // corpus that cites this entity
    const golds = [...store.golds.values()].filter((g) => (g.entity_refs || []).includes(ref)).map((g) => g.id);
    const silvers = [...store.silvers.values()].filter((s) => (s.entity_refs || []).includes(ref) || s.project_ref === ref).map((s) => s.id);
    addLinkSection("gold", "Aparece em (gold)", golds, "gold");
    addLinkSection("silver", "Aparece em (silver)", silvers, "silver");

    // the advisors' rationale, surfaced in the very UI they specified
    const note = document.createElement("div");
    note.className = "dw-estado-note";
    note.innerHTML = `<b>Evidência de entidade = “estado”.</b> Diferente de um silver, que registra um “evento”, este card descreve o que a entidade <em>é</em> no grafo (papel, vínculos, validade). Por isso o chip tem forma e cor distintas — decisão dos advisors em silver-015 / silver-016.`;
    body.appendChild(note);
    return true;
  }

  // -- shared builders --
  function addTitle(title, id) {
    const h = document.createElement("h2");
    h.className = "dw-title";
    h.textContent = title;
    const sub = document.createElement("div");
    sub.className = "dw-sub";
    sub.textContent = id;
    body.append(h, sub);
  }
  function addProse(txt) {
    const d = document.createElement("div");
    d.className = "dw-body-text";
    txt.split(/\n{2,}/).forEach((p) => {
      const el = document.createElement("p");
      el.textContent = p;
      d.appendChild(el);
    });
    body.appendChild(d);
  }
  function addField(k, v) {
    const dl = document.createElement("dl");
    dl.className = "dw-meta-grid";
    dl.style.margin = "0 0 14px";
    dl.innerHTML = `<dt>${k}</dt><dd>${escapeText(v)}</dd>`;
    body.appendChild(dl);
  }
  function addMeta(obj) {
    const entries = Object.entries(obj).filter(([, v]) => v);
    if (!entries.length) return;
    const sec = section("Metadados");
    const dl = document.createElement("dl");
    dl.className = "dw-meta-grid";
    entries.forEach(([k, v]) => {
      dl.innerHTML += `<dt>${k.replace(/_/g, " ")}</dt><dd>${escapeText(v)}</dd>`;
    });
    sec.appendChild(dl);
  }
  function addEntityRefs(refs) {
    if (!refs || !refs.length) return;
    const sec = section("Entidades");
    const wrap = document.createElement("div");
    refs.forEach((r) => wrap.appendChild(makeEntityTag(r)));
    sec.appendChild(wrap);
  }
  function addLinkSection(cls, title, ids, kind) {
    const list = (ids || []).filter(Boolean);
    if (!list.length) return;
    const sec = section(title);
    const wrap = document.createElement("div");
    wrap.className = "dw-links";
    list.forEach((id) => wrap.appendChild(makeLink(kind, id)));
    sec.appendChild(wrap);
  }
  function section(title) {
    const sec = document.createElement("div");
    sec.className = "dw-section";
    const h = document.createElement("div");
    h.className = "dw-section__h";
    h.innerHTML = `<span class="eyebrow">${title}</span>`;
    sec.appendChild(h);
    body.appendChild(sec);
    return sec;
  }
  function makeLink(kind, id) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `dw-link dw-link--${kind}`;
    const idEl = document.createElement("span");
    idEl.className = "dw-link__id";
    idEl.textContent = id;
    const t = document.createElement("span");
    t.className = "dw-link__t";
    t.textContent = linkPreview(kind, id);
    b.append(idEl, t);
    b.addEventListener("click", () => open(kind, id));
    return b;
  }
  function makeEntityTag(ref) {
    const label = entityLabel(ref) || "Person";
    const node = store.nodes.get(ref);
    const b = document.createElement("button");
    b.type = "button";
    b.className = "dw-node-tag";
    b.style.borderLeftColor = entityHue(label);
    b.title = ref + (node && !node.active ? ` · saindo ${node.valid_to}` : "");
    const g = document.createElement("span");
    g.className = "mono";
    g.style.cssText = `color:${entityHue(label)};font-size:11px`;
    g.textContent = "◆";
    b.append(g, document.createTextNode(entityName(ref)));
    if (node && !node.active) {
      const x = document.createElement("span");
      x.style.cssText = "color:var(--leaving);font-size:10px;font-family:var(--mono);margin-left:4px";
      x.textContent = "↗";
      b.appendChild(x);
    }
    b.addEventListener("click", () => open("entity", ref));
    return b;
  }

  closeBtn.addEventListener("click", close);
  scrim.addEventListener("click", close);

  return { open, close, isOpen: () => !root.hidden };
}

// ---- pure helpers --------------------------------------------------------

function edgesFor(ref) {
  return store.edges.filter((e) => e.source === ref || e.target === ref);
}
function linkPreview(kind, id) {
  if (kind === "gold") return store.golds.get(id)?.title || "";
  if (kind === "silver") return store.silvers.get(id)?.text || "";
  if (kind === "bronze") {
    const b = store.bronzes.get(id);
    return b ? (SOURCE_LABEL[b.source] || b.source) : "";
  }
  return "";
}
function entityHue(label) {
  return { Person: "var(--person)", Project: "var(--project)", Goal: "var(--goal)", Objective: "var(--objective)" }[label] || "var(--silver)";
}
function kickerColor(cls, sub) {
  if (cls === "gold") return "var(--gold)";
  if (cls === "silver") return "var(--silver)";
  if (cls === "bronze") return "var(--bronze)";
  if (cls === "entity") return entityHue(sub);
  return "var(--silver)";
}
function spanMuted(txt) {
  const s = document.createElement("span");
  s.style.cssText = "color:var(--ink-3);font-size:var(--fs-sm);font-family:var(--mono)";
  s.textContent = txt;
  return s;
}
function escapeText(s) {
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}
function fmtTs(ts) {
  if (!ts) return "";
  return ts.replace("T", " ").replace(/([+-]\d\d:\d\d)$/, "").slice(0, 16);
}
