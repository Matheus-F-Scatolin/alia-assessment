# NOTES

## O que eu construí

`answer.py` é um agente Claude com tool-use que navega o medallion do mesmo
jeito que o README descreve o produto: resolve as entidades da pergunta no
knowledge graph, encontra as narrativas gold relevantes, desce o lineage até
silvers e bronzes, e responde em português citando os IDs que usou.

Três camadas, uma por commit:

1. **`data.py`** -> camada de dados pura (sem LLM). Parseia `knowledge_graph.md`
   em nós/arestas tipados, carrega `medallion.json` e `bronze/*.json`, e
   constrói os índices: entidade -> silvers/golds, gold -> silver -> bronze,
   vizinhança de 1 salto no grafo. Smoke check embutido (`python data.py`).
2. **`tools.py`** -> seis tools com schemas Anthropic: `search_entities`,
   `get_entity`, `search_golds`, `get_gold`, `get_silvers`, `get_bronze`.
   Busca fuzzy insensível a acentos ("itau" acha Itaú), renderizadores de
   bronze por fonte (Slack/Meet/GitHub/email/Notion), e erros tolerantes
   (sugestões e IDs conhecidos) para o loop nunca quebrar com input ruim.
3. **`answer.py`** -> o loop de agente + CLI. System prompt descreve a
   estrutura do medallion e o contrato da resposta; o loop roda até o modelo
   parar de pedir tools (máx. 15 turnos). Suporta dois providers: modelos
   `claude-*` via API Anthropic e `gemini-*` via API Gemini. O default é
   `gemini-3.5-flash` — vencedor do eval em `eval/` (score 0.929, zero
   alucinações, lineage recall 1.0, ~2.3x mais barato que Opus; ver
   `eval/report.html`). Override com a env `ALIA_MODEL`.

## As tools que o LLM enxerga

O agente não recebe o corpus — recebe seis tools sobre a camada de dados
(`tools.py`), e o system prompt o instrui a seguir o lineage. Todas retornam
JSON; erros voltam como dados (com sugestões e IDs conhecidos), nunca como
exceção, para o loop não quebrar com input ruim.

| Tool | Input | O que devolve |
|---|---|---|
| `search_entities` | `query` (nome/papel/termo) | Até 8 nós do knowledge graph (pessoas, projetos, goals, objectives) por busca fuzzy insensível a acentos: ref, papel, descrição, `active` e `valid_to`. Primeiro passo típico: resolver quem/o quê a pergunta menciona. |
| `get_entity` | `ref` exata (ex: `Person:Bernardo Aires`) | O nó completo + arestas de 1 salto (`member_of`, `collaborates_with`, `RELATES_TO`, com `details` e `valid_to`) + IDs de golds/silvers que citam a entidade. É a tool do "contexto adjacente": é por ela que o agente descobre sozinho, p.ex., que o dono do entity layer está saindo. Refs quase-corretas são resolvidas via busca. |
| `search_golds` | `query` (tema/entidade) | Narrativas gold rankeadas por overlap com título, narrativa, topic_key e entidades: id, topic_key, título, entity_refs. Ponto de entrada do lineage. |
| `get_gold` | `gold_id` | A narrativa completa + `silver_refs` + o lineage resolvido até os bronzes (`lineage.silvers`, `lineage.bronzes`). |
| `get_silvers` | `silver_ids` (lista) | As interpretações silver completas: texto, project_ref, entity_refs, `bronze_refs` e timestamp. Aceita lote para descer o lineage numa chamada. |
| `get_bronze` | `bronze_id` | O datapoint bruto renderizado como texto legível por fonte (thread de Slack, transcrição de Meet, PR do GitHub, thread de email, página de Notion) + quais silvers o citam (lineage reverso). Evidência primária para os fatos centrais. |

A travessia esperada espelha o medallion: pergunta -> `search_entities` /
`search_golds` -> `get_gold` -> `get_silvers` -> `get_bronze`, com
`get_entity` abrindo o grafo lateralmente. O loop rastreia quais IDs foram
de fato consultados por essas tools — é disso que sai o rodapé verificado
de lineage.

## Decisões e porquês

- **Agentic tool-use em vez de RAG ou prompt único.** O corpus cabe inteiro
  num prompt (~35KB), então "funcionar" era fácil. Escolhi o loop agêntico
  porque a travessia question -> grafo -> gold -> silver -> bronze *é* o produto
  da Alia -> o programa demonstra o mecanismo, não só o resultado. E escala:
  com 10.000 silvers, o prompt único morre; as tools não mudam.
- **Lineage verificado, não declarado.** O rodapé "Lineage consultado" é
  construído rastreando as tool calls reais do loop, não extraído do texto do
  modelo. IDs citados no rodapé não podem ser alucinados. No primeiro teste o
  modelo citou um gold que não tinha buscado (pegou a informação de arestas do
  grafo); adicionei uma regra no prompt -> se um ID aparece só como referência
  dentro de outro resultado, busque antes de citar -> e o problema sumiu.
- **Contexto adjacente via arestas do grafo.** `get_entity` devolve as arestas
  de 1 salto com `valid_to`. É isso que faz o caso demo emergir naturalmente:
  perguntar sobre alinhamento leva a `Project:Entity Layer`, cujo dono tem
  `valid_to: 2026-04-24` -> o agente encontra a saída do Henrique sozinho, sem
  hardcode do caso.
- **Busca fuzzy simples** (overlap de tokens + fold de acentos) em vez de
  embeddings. Com 31 nós e 6 golds, embeddings seriam over-engineering; o
  modelo compensa reformulando a query quando a primeira busca falha.

## O que me surpreendeu

- **A questão thin-data se respondeu melhor do que eu esperava.** Perguntei
  sobre o LinkedIn Outreach (zero silvers/golds dedicados): o agente disse
  exatamente o que falta nos dados e ainda generalizou o padrão de risco ->
  Lucas é dono único e está migrando para o core, o mesmo padrão que acabou
  de quebrar produção com a saída do Henrique. Isso veio das arestas do
  grafo, não de nenhuma narrativa pronta.
- **O dataset é auto-referente**: o silver-005 descreve o Gold verbose
  surfaceando a saída do Henrique numa pergunta sobre alinhamento -> que é
  literalmente o comportamento que o assessment pede para reproduzir. O
  agente percebe isso e cita como validação do produto.
- **Formato dos refs no KG é irregular** -> arestas usam
  `Project:Gold Synthesis:Project` (label duplicado no fim) enquanto nós usam
  `Project:Gold Synthesis`. Normalizei no parser. Também não existe
  `datapoint-7.json`; nenhum silver referencia um bronze inexistente, então
  tratei como lacuna intencional do dataset.

## O que ficou de fora / com mais tempo

- **Cache e latência**: cada pergunta custa 4–12 chamadas de API (30–90s).
  Um cache de respostas por pergunta (como o próprio Gold da Alia faz,
  segundo silver-022) seria o próximo passo óbvio.
- **Validação de citações pós-resposta**: hoje o rodapé é verificado, mas as
  citações inline vêm do modelo. Um passo determinístico que confere cada
  `[id]` inline contra o conjunto consultado (e remove/marca os não
  verificados) fecharia o gap de vez.
- **Filtro temporal**: `valid_from`/`valid_to` são expostos mas não há uma
  tool "estado do mundo na data X". Perguntas retrospectivas ("quem era dono
  do entity layer em janeiro?") funcionam pelo raciocínio do modelo, não por
  construção.
- **Avaliação sistemática**: rodei as 4 perguntas do README + 2 de stress
  (thin-data e multi-nó). Com more tempo, faria um conjunto de perguntas com
  lineage esperado e verificaria cobertura automaticamente.

## Como rodar

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
echo "GEMINI_API_KEY=..." > .env       # default: gemini-3.5-flash
echo "ANTHROPIC_API_KEY=sk-..." >> .env  # só se usar ALIA_MODEL=claude-*
.venv/bin/python answer.py "Onde está a negociação com o NGCash?"

# outro modelo:
ALIA_MODEL=claude-sonnet-5 .venv/bin/python answer.py "..."
```

Saídas das 6 perguntas (4 do README + 2 extras) em `sample_output.txt`,
incluindo o trace das tool calls de cada run.
