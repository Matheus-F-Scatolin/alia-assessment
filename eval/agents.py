"""Provider-agnostic agent runners for the eval.

Both runners drive the SAME tools (tools.py) with the SAME system prompt
(answer.py) so the eval compares models, not scaffolds. Each returns:

    {
      "text": final answer (str),
      "fetched": {"gold": [...], "silver": [...], "bronze": [...]},  # verified
      "tool_calls": [{"name": ..., "args": {...}}, ...],
      "turns": int, "latency_s": float,
      "input_tokens": int, "output_tokens": int,
      "error": str | None,
    }

`fetched` is tracked from the actual tool executions (like answer.py's
verified footer) — lineage metrics are computed from it, never from prose.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data import Medallion  # noqa: E402
from tools import TOOLS, run_tool  # noqa: E402
from answer import SYSTEM_PROMPT, load_env  # noqa: E402

MAX_TURNS = 15

_MEDALLION = None


def medallion() -> Medallion:
    global _MEDALLION
    if _MEDALLION is None:
        _MEDALLION = Medallion()
    return _MEDALLION


def _new_result() -> dict:
    return {
        "text": "", "fetched": {"gold": set(), "silver": set(), "bronze": set()},
        "tool_calls": [], "turns": 0, "latency_s": 0.0,
        "input_tokens": 0, "output_tokens": 0, "error": None,
    }


def _track(fetched: dict, name: str, args: dict, result) -> None:
    if name == "get_gold" and isinstance(result, dict) and "error" not in result:
        fetched["gold"].add(args["gold_id"])
    elif name == "get_silvers" and isinstance(result, list):
        for s in result:
            if isinstance(s, dict) and "error" not in s:
                fetched["silver"].add(s["id"])
    elif name == "get_bronze" and isinstance(result, dict) and "error" not in result:
        fetched["bronze"].add(args["bronze_id"])


def _finalize(res: dict, t0: float) -> dict:
    res["latency_s"] = round(time.time() - t0, 1)
    res["fetched"] = {k: sorted(v) for k, v in res["fetched"].items()}
    return res


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def run_anthropic(question: str, model: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    res, t0 = _new_result(), time.time()
    messages = [{"role": "user", "content": question}]

    for turn in range(MAX_TURNS):
        res["turns"] = turn + 1
        response = client.messages.create(
            model=model, max_tokens=4000, system=SYSTEM_PROMPT,
            tools=TOOLS, messages=messages,
        )
        res["input_tokens"] += response.usage.input_tokens
        res["output_tokens"] += response.usage.output_tokens

        tool_results = []
        for block in response.content:
            if block.type == "text":
                res["text"] = block.text
            elif block.type == "tool_use":
                result = run_tool(medallion(), block.name, block.input)
                _track(res["fetched"], block.name, block.input, result)
                res["tool_calls"].append({"name": block.name, "args": block.input})
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
    else:
        res["error"] = "max_turns"

    return _finalize(res, t0)


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def run_gemini(question: str, model: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client()  # GEMINI_API_KEY from env
    declarations = [
        types.FunctionDeclaration(
            name=t["name"], description=t["description"],
            parameters=t["input_schema"],
        )
        for t in TOOLS
    ]
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=declarations)],
        max_output_tokens=4000,
    )

    res, t0 = _new_result(), time.time()
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]

    for turn in range(MAX_TURNS):
        res["turns"] = turn + 1
        response = client.models.generate_content(
            model=model, contents=contents, config=config,
        )
        usage = response.usage_metadata
        if usage:
            res["input_tokens"] += usage.prompt_token_count or 0
            res["output_tokens"] += usage.candidates_token_count or 0

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            res["error"] = "empty_response"
            break

        calls = [p.function_call for p in (candidate.content.parts or [])
                 if p.function_call]
        texts = [p.text for p in (candidate.content.parts or []) if p.text]
        if texts:
            res["text"] = "\n".join(texts)

        if not calls:
            break

        contents.append(candidate.content)
        response_parts = []
        for fc in calls:
            args = dict(fc.args or {})
            result = run_tool(medallion(), fc.name, args)
            _track(res["fetched"], fc.name, args, result)
            res["tool_calls"].append({"name": fc.name, "args": args})
            response_parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": result},
            ))
        contents.append(types.Content(role="user", parts=response_parts))
    else:
        res["error"] = "max_turns"

    return _finalize(res, t0)


# ---------------------------------------------------------------------------

RUNNERS = {"anthropic": run_anthropic, "gemini": run_gemini}


def provider_of(model: str) -> str:
    return "gemini" if model.startswith("gemini") else "anthropic"


def run_model(question: str, model: str) -> dict:
    try:
        return RUNNERS[provider_of(model)](question, model)
    except Exception as e:  # surface provider errors as data, not crashes
        res = _new_result()
        res["error"] = f"{type(e).__name__}: {e}"
        return _finalize(res, time.time())


if __name__ == "__main__":
    load_env()
    q = sys.argv[2] if len(sys.argv) > 2 else "Onde está a negociação com o NGCash?"
    model = sys.argv[1] if len(sys.argv) > 1 else "claude-haiku-4-5-20251001"
    out = run_model(q, model)
    print(json.dumps({k: v for k, v in out.items() if k != "text"},
                     ensure_ascii=False, indent=2))
    print("\n" + out["text"][:1500])
