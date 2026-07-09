// Thin API client: two JSON reads + one SSE stream (POST, so we parse the
// event stream by hand rather than using EventSource, which is GET-only).

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status} em ${url}`);
  return r.json();
}

export const getGraph = () => getJSON("/api/graph");
export const getCorpus = () => getJSON("/api/corpus");

/**
 * Stream an answer. Calls onEvent(obj) for each SSE `data:` line.
 * Returns a promise that resolves when the stream ends.
 */
export async function askStream({ question, model }, onEvent, signal) {
  let res;
  try {
    res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, model }),
      signal,
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    onEvent({ type: "error", message: `Não foi possível conectar ao servidor: ${e.message}` });
    return;
  }

  if (!res.ok || !res.body) {
    onEvent({ type: "error", message: `Servidor respondeu HTTP ${res.status}.` });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        const payload = dataLine.replace(/^data:\s*/, "");
        try {
          onEvent(JSON.parse(payload));
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      onEvent({ type: "error", message: `Conexão interrompida: ${e.message}` });
    }
  }
}
