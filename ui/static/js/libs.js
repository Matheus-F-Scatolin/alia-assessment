// Third-party libs, loaded from CDN as ES modules with graceful fallback.
// If any fail (e.g. offline), the app still runs: markdown degrades to
// escaped text, and the graph panel shows a designed "unavailable" note.

export const libs = { marked: null, DOMPurify: null, ForceGraph: null };

export async function loadRenderLibs() {
  try {
    const m = await import("https://esm.sh/marked@12.0.2");
    libs.marked = m.marked || m.default;
    if (libs.marked?.setOptions) {
      libs.marked.setOptions({ breaks: false, gfm: true });
    }
  } catch (e) {
    console.warn("[alia] marked indisponível — usando texto simples", e);
  }
  try {
    const d = await import("https://esm.sh/dompurify@3.1.6");
    libs.DOMPurify = d.default || d;
  } catch (e) {
    console.warn("[alia] DOMPurify indisponível — usando texto simples", e);
  }
}

export async function loadForceGraph() {
  if (libs.ForceGraph) return libs.ForceGraph;
  try {
    const f = await import("https://esm.sh/force-graph@1.49.4");
    libs.ForceGraph = f.default || f;
  } catch (e) {
    console.warn("[alia] force-graph indisponível", e);
    libs.ForceGraph = null;
  }
  return libs.ForceGraph;
}
