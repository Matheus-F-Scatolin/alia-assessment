"""Agent tools over the Medallion data layer.

Each tool is a plain function returning JSON-serializable data, plus an
Anthropic tool schema in TOOLS. `run_tool` dispatches by name and is the
single entry point the agent loop uses.

The intended traversal mirrors the medallion itself:
  question -> search_entities / search_golds -> get_gold (silver_refs)
           -> get_silvers (bronze_refs) -> get_bronze
with get_entity exposing graph edges so adjacent context (e.g. an owner
who is leaving) can be discovered even when not asked about.
"""

from __future__ import annotations

import unicodedata

from data import Medallion


def _fold(s: str) -> str:
    """Lowercase and strip accents for fuzzy matching (Itaú ~ itau)."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower())
        if not unicodedata.combining(c)
    )


def _score(query: str, text: str) -> int:
    """Token-overlap score; full-phrase match scores extra."""
    q, t = _fold(query), _fold(text)
    score = sum(1 for tok in q.split() if len(tok) > 2 and tok in t)
    if q in t:
        score += 3
    return score


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def search_entities(m: Medallion, query: str) -> list[dict]:
    results = []
    for node in m.nodes.values():
        haystack = f"{node.ref} {node.props.get('role', '')} {node.props.get('description', '')}"
        s = _score(query, haystack)
        if s > 0:
            results.append((s, {
                "ref": node.ref,
                "role": node.props.get("role", ""),
                "description": node.props.get("description", ""),
                "active": node.active,
                "valid_to": node.props.get("valid_to", ""),
            }))
    results.sort(key=lambda r: -r[0])
    return [r for _, r in results[:8]] or [{"error": f"no entity matched '{query}'"}]


def get_entity(m: Medallion, ref: str) -> dict:
    node = m.nodes.get(ref)
    if node is None:
        # forgive near-misses: retry as a search
        hits = search_entities(m, ref)
        exact = m.nodes.get(hits[0].get("ref", "")) if "error" not in hits[0] else None
        if exact is None:
            return {"error": f"unknown entity '{ref}'", "suggestions": hits}
        node = exact
    return {
        "ref": node.ref,
        "label": node.label,
        "active": node.active,
        **node.props,
        "edges": m.neighbors(node.ref),
        "gold_ids": m.golds_by_entity.get(node.ref, []),
        "silver_ids": m.silvers_by_entity.get(node.ref, []),
    }


def search_golds(m: Medallion, query: str) -> list[dict]:
    results = []
    for g in m.golds.values():
        haystack = " ".join([g["topic_key"], g["title"], g["narrative"],
                             " ".join(g["entity_refs"])])
        s = _score(query, haystack)
        if s > 0:
            results.append((s, {
                "id": g["id"],
                "topic_key": g["topic_key"],
                "title": g["title"],
                "entity_refs": g["entity_refs"],
            }))
    results.sort(key=lambda r: -r[0])
    return [r for _, r in results] or [{"error": f"no gold matched '{query}'"}]


def get_gold(m: Medallion, gold_id: str) -> dict:
    g = m.golds.get(gold_id)
    if g is None:
        return {"error": f"unknown gold '{gold_id}'", "known": sorted(m.golds)}
    return {**g, "lineage": m.lineage_of_gold(gold_id)}


def get_silvers(m: Medallion, silver_ids: list[str]) -> list[dict]:
    out = []
    for sid in silver_ids:
        s = m.silvers.get(sid)
        out.append(s if s else {"error": f"unknown silver '{sid}'"})
    return out


def _render_bronze(b: dict) -> str:
    src = b["source"]
    if src == "slack":
        lines = [f"Slack {b['channel']} — thread capturado {b['captured_at']}"]
        lines += [f"[{msg['ts']}] {msg['author']}: {msg['text']}" for msg in b["messages"]]
        return "\n".join(lines)
    if src == "google_meet":
        lines = [f"Google Meet: {b['meeting_title']} ({b['captured_at']})",
                 f"Participantes: {', '.join(b['participants'])}"]
        lines += [f"[{t['ts']}] {t['speaker']}: {t['text']}" for t in b["transcript"]]
        return "\n".join(lines)
    if src == "email":
        lines = [f"Email thread: {b['subject']}"]
        for msg in b["messages"]:
            lines.append(f"[{msg['ts']}] de {msg['from']} para {', '.join(msg['to'])}:\n{msg['body']}")
        return "\n".join(lines)
    if src == "github":
        return (f"GitHub PR #{b['pr_number']} em {b['repo']}: {b['pr_title']}\n"
                f"autor: {b['author']}, merged por {b['merged_by']} em {b['merged_at']}\n"
                f"branch: {b['head']} -> {b['base']}\n\n{b['body']}")
    if src == "notion":
        return (f"Notion: {b['page_title']} ({b['captured_at']})\n"
                f"Participantes: {', '.join(b.get('participants', []))}\n"
                f"Autor: {b.get('author', '?')}\n\n{b['body']}")
    return str(b)  # unknown source: raw fallback


def get_bronze(m: Medallion, bronze_id: str) -> dict:
    b = m.bronzes.get(bronze_id)
    if b is None:
        return {"error": f"unknown bronze '{bronze_id}'", "known": sorted(m.bronzes)}
    return {
        "id": b["id"],
        "source": b["source"],
        "captured_at": b.get("captured_at", ""),
        "content": _render_bronze(b),
        "cited_by_silvers": [s["id"] for s in m.silvers.values()
                             if bronze_id in s.get("bronze_refs", [])],
    }


# ---------------------------------------------------------------------------
# Anthropic tool schemas + dispatch
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_entities",
        "description": "Busca pessoas, projetos, goals e objectives no knowledge graph por nome, papel ou descrição. Use primeiro para resolver quem/o quê a pergunta menciona.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Nome ou termo, ex: 'Bernardo', 'entity layer', 'NGCash'"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_entity",
        "description": "Retorna um nó completo do knowledge graph: papel, status (ativo ou saindo/encerrado), arestas com outros nós, e os IDs de golds/silvers que o citam. Use para descobrir contexto adjacente (donos, colaboradores, riscos).",
        "input_schema": {
            "type": "object",
            "properties": {"ref": {"type": "string", "description": "Ref exata, ex: 'Person:Bernardo Aires'"}},
            "required": ["ref"],
        },
    },
    {
        "name": "search_golds",
        "description": "Busca narrativas gold por tema, título ou entidade. Golds são o ponto de partida do lineage (gold -> silver -> bronze).",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Tema ou entidade, ex: 'handoff', 'design partners'"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_gold",
        "description": "Retorna uma narrativa gold completa com seus silver_refs e o lineage completo até os bronzes.",
        "input_schema": {
            "type": "object",
            "properties": {"gold_id": {"type": "string", "description": "ex: 'gold-002'"}},
            "required": ["gold_id"],
        },
    },
    {
        "name": "get_silvers",
        "description": "Retorna interpretações silver completas (texto, entidades, bronze_refs, timestamp) para uma lista de IDs.",
        "input_schema": {
            "type": "object",
            "properties": {"silver_ids": {"type": "array", "items": {"type": "string"}, "description": "ex: ['silver-004', 'silver-002']"}},
            "required": ["silver_ids"],
        },
    },
    {
        "name": "get_bronze",
        "description": "Retorna o datapoint bronze bruto (thread de Slack, transcrição de Meet, PR, email, Notion) renderizado como texto. Use para citar a evidência primária.",
        "input_schema": {
            "type": "object",
            "properties": {"bronze_id": {"type": "string", "description": "ex: 'bronze-slack-001'"}},
            "required": ["bronze_id"],
        },
    },
]

_IMPL = {
    "search_entities": lambda m, a: search_entities(m, a["query"]),
    "get_entity": lambda m, a: get_entity(m, a["ref"]),
    "search_golds": lambda m, a: search_golds(m, a["query"]),
    "get_gold": lambda m, a: get_gold(m, a["gold_id"]),
    "get_silvers": lambda m, a: get_silvers(m, a["silver_ids"]),
    "get_bronze": lambda m, a: get_bronze(m, a["bronze_id"]),
}


def run_tool(m: Medallion, name: str, args: dict):
    fn = _IMPL.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(m, args)
    except KeyError as e:
        return {"error": f"missing argument {e} for tool '{name}'"}


def _smoke():
    m = Medallion()
    hits = search_entities(m, "bernardo")
    assert hits[0]["ref"] == "Person:Bernardo Aires", hits[0]
    ent = get_entity(m, "Project:Entity Layer")
    assert any(e["node"] == "Person:Henrique Silva" for e in ent["edges"])
    golds = search_golds(m, "alinhados medallion camadas")
    assert golds[0]["id"] == "gold-002", golds[0]
    g = get_gold(m, "gold-002")
    assert g["lineage"]["bronzes"] == ["bronze-meet-002", "bronze-slack-001"]
    silvers = get_silvers(m, g["silver_refs"])
    assert all("error" not in s for s in silvers)
    for bid in m.bronzes:  # every bronze source renders
        assert len(get_bronze(m, bid)["content"]) > 100, bid
    # accent-insensitive: 'itau' finds Itaú
    assert any("Ita" in h["ref"] for h in search_entities(m, "itau"))
    print("OK — all tools pass smoke checks")


if __name__ == "__main__":
    _smoke()
