// Central data store + rendering helpers.
// Holds the graph + corpus once loaded, and owns the two rendering concerns
// that several modules share: markdown → HTML, and inline citation chips.

import { libs } from "./libs.js";

export const store = {
  nodes: new Map(),   // ref -> node
  edges: [],
  golds: new Map(),   // id -> gold
  silvers: new Map(),
  bronzes: new Map(),
  examples: [],
  models: [],
  defaultModel: "claude-sonnet-5",
};

export const ENTITY_LABELS = ["Person", "Project", "Goal", "Objective"];

export function ingestGraph(g) {
  store.nodes = new Map(g.nodes.map((n) => [n.ref, n]));
  store.edges = g.edges;
}

export function ingestCorpus(c) {
  store.golds = new Map(c.golds.map((x) => [x.id, x]));
  store.silvers = new Map(c.silvers.map((x) => [x.id, x]));
  store.bronzes = new Map(c.bronzes.map((x) => [x.id, x]));
  store.examples = c.examples || [];
  store.models = c.models || [];
  store.defaultModel = c.default_model || store.defaultModel;
}

// ---- classification helpers ----------------------------------------------

export function layerOf(id) {
  if (typeof id !== "string") return null;
  if (id.startsWith("gold-")) return "gold";
  if (id.startsWith("silver-")) return "silver";
  if (id.startsWith("bronze-")) return "bronze";
  return null;
}

export function isEntityRef(s) {
  return typeof s === "string" && /^(Person|Project|Goal|Objective):/.test(s);
}

export function entityLabel(ref) {
  return isEntityRef(ref) ? ref.split(":", 1)[0] : null;
}

export function entityName(ref) {
  const i = ref.indexOf(":");
  return i >= 0 ? ref.slice(i + 1) : ref;
}

export function knownId(token) {
  // a recognized citation target that actually exists in the loaded data
  const layer = layerOf(token);
  if (layer === "gold") return store.golds.has(token) ? { kind: "gold", id: token } : null;
  if (layer === "silver") return store.silvers.has(token) ? { kind: "silver", id: token } : null;
  if (layer === "bronze") return store.bronzes.has(token) ? { kind: "bronze", id: token } : null;
  if (isEntityRef(token) && store.nodes.has(token)) return { kind: "entity", id: token };
  return null;
}

export function goldsCiting(silverId) {
  return [...store.golds.values()].filter((g) => (g.silver_refs || []).includes(silverId));
}
export function silversCiting(bronzeId) {
  const b = store.bronzes.get(bronzeId);
  if (b?.cited_by_silvers) return b.cited_by_silvers;
  return [...store.silvers.values()].filter((s) => (s.bronze_refs || []).includes(bronzeId)).map((s) => s.id);
}

// ---- chips ---------------------------------------------------------------

const LAYER_TITLE = {
  gold: (id) => store.golds.get(id)?.title || id,
  silver: (id) => store.silvers.get(id)?.text || id,
  bronze: (id) => `${store.bronzes.get(id)?.source || ""} · ${id}`,
};

/**
 * Build a citation chip element. Layer citations (gold/silver/bronze) are
 * pills — "evento". Entity citations (Person/Project/...) are square tags with
 * a colored left bar — "estado". Two shapes, kept inline: exactly the spec the
 * advisors set in silver-015 / silver-016.
 */
export function makeChip({ kind, id }, onOpen) {
  const el = document.createElement("button");
  el.type = "button";
  el.dataset.kind = kind;
  el.dataset.id = id;
  el.tabIndex = 0;

  if (kind === "entity") {
    const label = entityLabel(id);
    el.className = `chip chip--entity chip--${label}`;
    el.title = `${label} · ${id}`;
    const glyph = document.createElement("span");
    glyph.className = "chip__glyph";
    glyph.textContent = "◆";
    const text = document.createElement("span");
    text.textContent = entityName(id);
    el.append(glyph, text);
  } else {
    el.className = `chip chip--layer chip--${kind}`;
    el.title = LAYER_TITLE[kind](id);
    el.append(document.createTextNode(id));
  }

  el.addEventListener("click", (e) => {
    e.preventDefault();
    onOpen?.(kind, id);
  });
  return el;
}

// ---- markdown ------------------------------------------------------------

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

export function renderMarkdown(md) {
  if (libs.marked && libs.DOMPurify) {
    const raw = libs.marked.parse(md);
    return libs.DOMPurify.sanitize(raw, {
      ADD_ATTR: ["target"],
      FORBID_TAGS: ["style", "img"],
    });
  }
  // fallback: escape + naive paragraphs
  return md.split(/\n{2,}/).map((p) => `<p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`).join("");
}

const BRACKET_RE = /\[([^\[\]\n]{1,100})\]/g;

/**
 * Walk rendered HTML and turn bracketed citation tokens into chips, in place.
 * Only tokens that resolve to real corpus/graph items become chips; anything
 * else is left as literal text (so "[TODO]" or "[1]" survive untouched).
 */
export function decorateCitations(root, onOpen) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue || node.nodeValue.indexOf("[") < 0) return NodeFilter.FILTER_REJECT;
      const p = node.parentElement;
      if (p && p.closest("code, pre, a, .chip")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const targets = [];
  let n;
  while ((n = walker.nextNode())) targets.push(n);

  for (const textNode of targets) {
    const text = textNode.nodeValue;
    BRACKET_RE.lastIndex = 0;
    if (!BRACKET_RE.test(text)) continue;
    BRACKET_RE.lastIndex = 0;

    const frag = document.createDocumentFragment();
    let last = 0;
    let m;
    while ((m = BRACKET_RE.exec(text))) {
      const [full, inner] = m;
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      last = m.index + full.length;

      const parts = inner.split(/\s*[,;]\s*/).map((s) => s.trim()).filter(Boolean);
      const resolved = parts.map((p) => ({ raw: p, hit: knownId(p) }));
      const anyHit = resolved.some((r) => r.hit);

      if (!anyHit) {
        // nothing recognized → keep the literal bracketed text
        frag.appendChild(document.createTextNode(full));
        continue;
      }
      if (parts.length === 1) {
        frag.appendChild(makeChip(resolved[0].hit, onOpen));
        continue;
      }
      // mixed / multi: chips for hits, literal text for the rest
      resolved.forEach((r, i) => {
        if (i > 0) frag.appendChild(document.createTextNode(" "));
        if (r.hit) frag.appendChild(makeChip(r.hit, onOpen));
        else frag.appendChild(document.createTextNode(r.raw));
      });
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    textNode.parentNode.replaceChild(frag, textNode);
  }
}
