"""answer.py — responde perguntas sobre a Alia com lineage gold -> silver -> bronze.

Uso:
    python answer.py "Bernardo e Lucas estão alinhados sobre as camadas do medallion?"

Um agente LLM com tool-use navega o medallion: resolve entidades no
knowledge graph, encontra as narrativas gold relevantes, desce o lineage
até os silvers e bronzes, e responde em português citando os IDs usados.
Os IDs citados no rodapé "Lineage" vêm do rastreio das tool calls reais —
não do texto do modelo — então não podem ser alucinados.

Modelo default: gemini-3.5-flash (melhor score e ~2.3x mais barato que Opus
no eval em eval/ — ver eval/report.html). Override com ALIA_MODEL; modelos
"claude-*" usam a API Anthropic, "gemini-*" usam a API Gemini.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from data import Medallion
from tools import TOOLS, run_tool

MODEL = os.environ.get("ALIA_MODEL", "gemini-3.5-flash")
MAX_TURNS = 15

SYSTEM_PROMPT = """\
Você é o modo "Gold verbose" da Alia: responde perguntas sobre a empresa \
com base em um medallion de dados reais.

Estrutura dos dados:
- Knowledge graph: pessoas, projetos, goals e objectives, com arestas entre \
eles. `valid_to` preenchido significa que o nó/aresta terminou ou está \
terminando (ex: uma pessoa saindo da empresa).
- Gold: narrativas por tema, apontando para silvers (silver_refs).
- Silver: interpretações estruturadas, apontando para bronzes (bronze_refs).
- Bronze: dados brutos — threads de Slack, transcrições de Meet, PRs, \
emails, páginas de Notion.

Método (siga o lineage, sempre):
1. Resolva as entidades da pergunta com search_entities / get_entity.
2. Encontre as narrativas gold relevantes com search_golds / get_gold.
3. Desça aos silvers (get_silvers) e, para os fatos centrais da resposta, \
até o bronze (get_bronze) para citar a evidência primária.
4. Olhe as arestas do knowledge graph das entidades envolvidas: se houver \
contexto adjacente relevante que o usuário NÃO perguntou — um dono saindo, \
um risco, um bloqueio, uma dependência — traga na resposta, em uma seção \
própria. É a proposta central do produto.

Contrato da resposta:
- Responda em português, em prosa clara — uma resposta de verdade, não um \
resumo do JSON.
- Cite os IDs entre colchetes junto de cada afirmação: [gold-002], \
[silver-004], [bronze-meet-002]. Nomeie as pessoas com seus papéis.
- Se os dados forem finos ou não cobrirem a pergunta, diga exatamente o que \
está faltando em vez de inventar.
- Nunca invente IDs, pessoas ou fatos que não vieram das tools. Só cite um \
ID (gold/silver/bronze) se você o consultou de fato via tool nesta conversa \
— se um ID apareceu apenas como referência dentro de outro resultado, \
busque-o antes de citá-lo.
"""


def load_env(path: Path = Path(__file__).parent / ".env") -> None:
    """Carrega .env sem dependência externa."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def provider_of(model: str) -> str:
    return "gemini" if model.startswith("gemini") else "anthropic"


def _exec_tool(medallion: Medallion, fetched: dict, name: str, args: dict):
    """Executa uma tool com trace no stderr e rastreio de lineage."""
    print(f"  → {name}({json.dumps(args, ensure_ascii=False)})", file=sys.stderr)
    result = run_tool(medallion, name, args)
    if name == "get_gold" and isinstance(result, dict) and "error" not in result:
        fetched["gold"].add(args["gold_id"])
    elif name == "get_silvers" and isinstance(result, list):
        for s in result:
            if isinstance(s, dict) and "error" not in s:
                fetched["silver"].add(s["id"])
    elif name == "get_bronze" and isinstance(result, dict) and "error" not in result:
        fetched["bronze"].add(args["bronze_id"])
    return result


def _loop_anthropic(medallion: Medallion, question: str, model: str,
                    fetched: dict) -> str:
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": question}]
    final_text = ""

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=model, max_tokens=4000, system=SYSTEM_PROMPT,
            tools=TOOLS, messages=messages,
        )
        tool_results = []
        for block in response.content:
            if block.type == "text":
                final_text = block.text
            elif block.type == "tool_use":
                result = _exec_tool(medallion, fetched, block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        if response.stop_reason != "tool_use":
            return final_text
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return final_text + "\n\n[aviso: limite de iterações do agente atingido]"


def _loop_gemini(medallion: Medallion, question: str, model: str,
                 fetched: dict) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client()  # GEMINI_API_KEY do ambiente
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=t["name"], description=t["description"],
                parameters=t["input_schema"],
            )
            for t in TOOLS
        ])],
        max_output_tokens=4000,
    )
    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    final_text = ""

    for _ in range(MAX_TURNS):
        response = client.models.generate_content(
            model=model, contents=contents, config=config,
        )
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            return final_text + "\n\n[aviso: resposta vazia do modelo]"

        parts = candidate.content.parts or []
        texts = [p.text for p in parts if p.text]
        if texts:
            final_text = "\n".join(texts)
        calls = [p.function_call for p in parts if p.function_call]
        if not calls:
            return final_text

        contents.append(candidate.content)
        response_parts = []
        for fc in calls:
            args = dict(fc.args or {})
            result = _exec_tool(medallion, fetched, fc.name, args)
            response_parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": result},
            ))
        contents.append(types.Content(role="user", parts=response_parts))

    return final_text + "\n\n[aviso: limite de iterações do agente atingido]"


def answer(question: str, model: str = MODEL) -> str:
    medallion = Medallion()
    fetched = {"gold": set(), "silver": set(), "bronze": set()}
    loop = _loop_gemini if provider_of(model) == "gemini" else _loop_anthropic
    text = loop(medallion, question, model, fetched)
    return text + _lineage_footer(fetched)


def _lineage_footer(fetched: dict) -> str:
    lines = ["", "---", "Lineage consultado:"]
    for layer in ("gold", "silver", "bronze"):
        if fetched[layer]:
            lines.append(f"  {layer}: {', '.join(sorted(fetched[layer]))}")
    if len(lines) == 3:
        lines.append("  (nenhum dado do medallion foi consultado)")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('uso: python answer.py "sua pergunta sobre a Alia"', file=sys.stderr)
        sys.exit(1)
    load_env()
    key = "GEMINI_API_KEY" if provider_of(MODEL) == "gemini" else "ANTHROPIC_API_KEY"
    if not os.environ.get(key):
        print(f"erro: defina {key} (ou coloque no .env) para o modelo {MODEL}",
              file=sys.stderr)
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    print(f"Pergunta: {question}\nModelo: {MODEL}\n", file=sys.stderr)
    print(answer(question))


if __name__ == "__main__":
    main()
