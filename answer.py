"""answer.py — responde perguntas sobre a Alia com lineage gold -> silver -> bronze.

Uso:
    python answer.py "Bernardo e Lucas estão alinhados sobre as camadas do medallion?"

Um agente Claude com tool-use navega o medallion: resolve entidades no
knowledge graph, encontra as narrativas gold relevantes, desce o lineage
até os silvers e bronzes, e responde em português citando os IDs usados.
Os IDs citados no rodapé "Lineage" vêm do rastreio das tool calls reais —
não do texto do modelo — então não podem ser alucinados.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

from data import Medallion
from tools import TOOLS, run_tool

MODEL = os.environ.get("ALIA_MODEL", "claude-sonnet-5")
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


def answer(question: str) -> str:
    medallion = Medallion()
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": question}]
    fetched = {"gold": set(), "silver": set(), "bronze": set()}
    final_text = ""

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        tool_results = []
        for block in response.content:
            if block.type == "text":
                final_text = block.text
            elif block.type == "tool_use":
                print(f"  → {block.name}({json.dumps(block.input, ensure_ascii=False)})",
                      file=sys.stderr)
                result = run_tool(medallion, block.name, block.input)
                _track(fetched, block.name, block.input, result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
    else:
        final_text += "\n\n[aviso: limite de iterações do agente atingido]"

    return final_text + _lineage_footer(fetched)


def _track(fetched: dict, name: str, args: dict, result) -> None:
    """Registra os IDs realmente consultados, para o rodapé de lineage."""
    if name == "get_gold" and isinstance(result, dict) and "error" not in result:
        fetched["gold"].add(args["gold_id"])
    elif name == "get_silvers":
        for s in result:
            if "error" not in s:
                fetched["silver"].add(s["id"])
    elif name == "get_bronze" and isinstance(result, dict) and "error" not in result:
        fetched["bronze"].add(args["bronze_id"])


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
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("erro: defina ANTHROPIC_API_KEY (ou coloque no .env)", file=sys.stderr)
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    print(f"Pergunta: {question}\n", file=sys.stderr)
    print(answer(question))


if __name__ == "__main__":
    main()
