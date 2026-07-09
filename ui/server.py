"""ui/server.py — FastAPI backend for the Alia instrument panel.

Serves the static frontend and three endpoints:
  GET  /api/graph   -> the full knowledge graph (nodes + edges)
  GET  /api/corpus  -> golds / silvers / bronzes + the README example questions
  POST /api/ask     -> Server-Sent Events stream of the live agent traversal

The agent loop is the one from `answer.py`, copied here (per the handoff) and
instrumented with event hooks so the UI can render each tool call, each result,
the streamed answer, and — crucially — the *verified* lineage, built from the
tool calls actually run, never parsed out of model text.

Root modules (data.py / tools.py / answer.py) are imported by putting the repo
root on sys.path; this file lives under ui/ and never edits them.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import os

import anthropic
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from answer import MAX_TURNS, SYSTEM_PROMPT, load_env
from data import Medallion
from tools import TOOLS, get_bronze, run_tool

# --- one-time setup --------------------------------------------------------

load_env()  # populate ANTHROPIC_API_KEY / ALIA_MODEL from .env if present

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_MODEL = os.environ.get("ALIA_MODEL", "claude-sonnet-5")

# Offered in the picker. The default (env or sonnet) is always included.
MODEL_CHOICES = [
    {"id": "claude-sonnet-5", "label": "Claude Sonnet 5"},
    {"id": "claude-opus-4-8", "label": "Claude Opus 4.8"},
    {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
]
if DEFAULT_MODEL not in {m["id"] for m in MODEL_CHOICES}:
    MODEL_CHOICES.insert(0, {"id": DEFAULT_MODEL, "label": DEFAULT_MODEL})

# The four illustrative questions from README.md (stable; not read at runtime
# so this file has zero dependency on README's formatting).
EXAMPLE_QUESTIONS = [
    "Bernardo e Lucas estão alinhados sobre as camadas do medallion?",
    "Por que os agentes do Bernardo quebraram?",
    "O que muda com a saída do Henrique?",
    "Onde está a negociação com o NGCash?",
]

# Load the medallion once — it is read-only and deterministic.
MEDALLION = Medallion()

app = FastAPI(title="Alia — Gold verbose")


# ---------------------------------------------------------------------------
# Read endpoints: graph + corpus
# ---------------------------------------------------------------------------

@app.get("/api/graph")
def api_graph() -> dict:
    m = MEDALLION
    nodes = [
        {
            "ref": n.ref,
            "label": n.label,
            "name": n.name,
            "role": n.props.get("role", ""),
            "description": n.props.get("description", ""),
            "active": n.active,
            "valid_from": n.props.get("valid_from", ""),
            "valid_to": n.props.get("valid_to", ""),
        }
        for n in m.nodes.values()
    ]
    edges = [
        {
            "source": e.source,
            "rel": e.rel,
            "target": e.target,
            "details": e.props.get("details", ""),
            "valid_from": e.props.get("valid_from", ""),
            "valid_to": e.props.get("valid_to", ""),
        }
        for e in m.edges
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/corpus")
def api_corpus() -> dict:
    m = MEDALLION
    golds = [
        {
            "id": g["id"],
            "topic_key": g["topic_key"],
            "title": g["title"],
            "narrative": g["narrative"],
            "entity_refs": g["entity_refs"],
            "silver_refs": g["silver_refs"],
            "updated_at": g.get("updated_at", ""),
        }
        for g in m.golds.values()
    ]
    silvers = [
        {
            "id": s["id"],
            "text": s["text"],
            "project_ref": s.get("project_ref", ""),
            "entity_refs": s.get("entity_refs", []),
            "bronze_refs": s.get("bronze_refs", []),
            "occurred_at": s.get("occurred_at", ""),
        }
        for s in m.silvers.values()
    ]
    bronzes = []
    for bid in m.bronzes:
        b = get_bronze(m, bid)
        bronzes.append({
            "id": b["id"],
            "source": b["source"],
            "captured_at": b.get("captured_at", ""),
            "content": b["content"],
            "cited_by_silvers": b.get("cited_by_silvers", []),
        })
    return {
        "golds": golds,
        "silvers": silvers,
        "bronzes": bronzes,
        "examples": EXAMPLE_QUESTIONS,
        "models": MODEL_CHOICES,
        "default_model": DEFAULT_MODEL,
    }


# ---------------------------------------------------------------------------
# Ask endpoint: SSE stream of the live agent traversal
# ---------------------------------------------------------------------------

class AskBody(BaseModel):
    question: str
    model: str | None = None


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _dedup(seq) -> list:
    """Order-preserving de-dup for building touched sets."""
    out, seen = [], set()
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _touched(name: str, args: dict, result) -> dict:
    """Derive the graph nodes / corpus items a tool result references.

    This is broader than the verified lineage: it includes ids merely *seen*
    in a result (e.g. a gold's silver_refs before they are fetched). The UI
    uses it to light up the graph and assemble the evidence trail as the agent
    traverses; the strict verified set is tracked separately in `_track`.
    """
    ents, golds, silvers, bronzes = [], [], [], []

    def ok(x):
        return isinstance(x, dict) and "error" not in x

    if name == "search_entities" and isinstance(result, list):
        ents = [r["ref"] for r in result if ok(r) and "ref" in r]
    elif name == "get_entity" and ok(result):
        ents = [result["ref"]] + [e.get("node", "") for e in result.get("edges", [])]
        golds = list(result.get("gold_ids", []))
        silvers = list(result.get("silver_ids", []))
    elif name == "search_golds" and isinstance(result, list):
        for r in result:
            if ok(r) and "id" in r:
                golds.append(r["id"])
                ents += r.get("entity_refs", [])
    elif name == "get_gold" and ok(result):
        golds = [result["id"]]
        silvers = list(result.get("silver_refs", []))
        bronzes = list(result.get("lineage", {}).get("bronzes", []))
        ents = list(result.get("entity_refs", []))
    elif name == "get_silvers" and isinstance(result, list):
        for s in result:
            if ok(s) and "id" in s:
                silvers.append(s["id"])
                bronzes += s.get("bronze_refs", [])
                ents += s.get("entity_refs", [])
                if s.get("project_ref"):
                    ents.append(s["project_ref"])
    elif name == "get_bronze" and ok(result):
        bronzes = [result["id"]]
        silvers = list(result.get("cited_by_silvers", []))

    return {
        "entities": _dedup(ents),
        "golds": _dedup(golds),
        "silvers": _dedup(silvers),
        "bronzes": _dedup(bronzes),
    }


def _summary(name: str, args: dict, result) -> str:
    """One-line human summary for the timeline row header."""
    if name == "search_entities":
        n = len([r for r in result if isinstance(r, dict) and "error" not in r]) \
            if isinstance(result, list) else 0
        return f'{n} entidade(s) · "{args.get("query", "")}"'
    if name == "get_entity":
        if isinstance(result, dict) and "error" not in result:
            role = result.get("role", "")
            return f'{result.get("ref", "")}' + (f" · {role}" if role else "")
        return args.get("ref", "?") + " · não encontrado"
    if name == "search_golds":
        n = len([r for r in result if isinstance(r, dict) and "error" not in r]) \
            if isinstance(result, list) else 0
        return f'{n} gold(s) · "{args.get("query", "")}"'
    if name == "get_gold":
        if isinstance(result, dict) and "error" not in result:
            return f'{result.get("id", "")} · {result.get("title", "")}'
        return args.get("gold_id", "?") + " · não encontrado"
    if name == "get_silvers":
        ids = [s["id"] for s in result if isinstance(s, dict) and "id" in s] \
            if isinstance(result, list) else []
        head = ", ".join(ids[:3]) + ("…" if len(ids) > 3 else "")
        return f"{len(ids)} silver(s) · {head}"
    if name == "get_bronze":
        if isinstance(result, dict) and "error" not in result:
            return f'{result.get("id", "")} · {result.get("source", "")}'
        return args.get("bronze_id", "?") + " · não encontrado"
    return name


def _track(fetched: dict, name: str, args: dict, result) -> None:
    """Verified lineage: only ids actually fetched via a successful tool call.

    Identical policy to answer.py — these ids cannot be hallucinated because
    they come from the tool trace, not the model's prose.
    """
    if name == "get_gold" and isinstance(result, dict) and "error" not in result:
        fetched["gold"].add(args["gold_id"])
    elif name == "get_silvers" and isinstance(result, list):
        for s in result:
            if isinstance(s, dict) and "error" not in s and "id" in s:
                fetched["silver"].add(s["id"])
    elif name == "get_bronze" and isinstance(result, dict) and "error" not in result:
        fetched["bronze"].add(args["bronze_id"])


def _run_stream(question: str, model: str):
    """Generator yielding SSE lines for one question."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        yield _sse({"type": "error",
                    "message": "ANTHROPIC_API_KEY não encontrada. "
                               "Adicione-a ao arquivo .env na raiz do projeto."})
        return

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": question}]
    fetched = {"gold": set(), "silver": set(), "bronze": set()}
    seq = 0
    in_tok = out_tok = 0
    t0 = time.perf_counter()

    try:
        for turn in range(1, MAX_TURNS + 1):
            with client.messages.stream(
                model=model,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                for event in stream:
                    if (event.type == "content_block_delta"
                            and getattr(event.delta, "type", "") == "text_delta"):
                        yield _sse({"type": "text_delta",
                                    "turn": turn, "text": event.delta.text})
                final = stream.get_final_message()

            in_tok += final.usage.input_tokens
            out_tok += final.usage.output_tokens

            tool_results = []
            for block in final.content:
                if block.type == "tool_use":
                    seq += 1
                    yield _sse({"type": "tool_call", "seq": seq,
                                "name": block.name, "args": block.input})
                    result = run_tool(MEDALLION, block.name, block.input)
                    _track(fetched, block.name, block.input, result)
                    yield _sse({
                        "type": "tool_result",
                        "seq": seq,
                        "name": block.name,
                        "summary": _summary(block.name, block.input, result),
                        "full": result,
                        "touched": _touched(block.name, block.input, result),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

            if final.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": final.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            yield _sse({"type": "text_delta", "turn": MAX_TURNS,
                        "text": "\n\n_[limite de iterações do agente atingido]_"})

        yield _sse({
            "type": "lineage",
            "gold": sorted(fetched["gold"]),
            "silver": sorted(fetched["silver"]),
            "bronze": sorted(fetched["bronze"]),
        })
        yield _sse({
            "type": "done",
            "stats": {
                "latency_s": round(time.perf_counter() - t0, 1),
                "tool_calls": seq,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
            },
        })
    except anthropic.APIStatusError as e:
        msg = getattr(e, "message", None) or str(e)
        yield _sse({"type": "error",
                    "message": f"Erro da API Anthropic ({e.status_code}): {msg}"})
    except anthropic.APIError as e:
        yield _sse({"type": "error", "message": f"Erro da API: {e}"})
    except Exception as e:  # noqa: BLE001 — surface anything to a designed UI state
        yield _sse({"type": "error", "message": f"Erro inesperado: {e}"})


@app.post("/api/ask")
def api_ask(body: AskBody) -> StreamingResponse:
    question = (body.question or "").strip()
    model = (body.model or DEFAULT_MODEL).strip()

    def gen():
        if not question:
            yield _sse({"type": "error", "message": "Pergunta vazia."})
            return
        yield from _run_stream(question, model)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering if any
        },
    )


# Static frontend last, so /api routes take precedence.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
