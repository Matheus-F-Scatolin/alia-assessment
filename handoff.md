# HANDOFF — Alia Chat UI

You are building a local chat app on top of an existing, working agentic Q&A
system. Read this whole file before writing any code.

## Context: what already exists (do not rebuild it)

This repo answers questions about a fictional company ("Alia") grounded in a
medallion dataset. Everything below is on `main` and works:

- `data.py` — pure data layer. `Medallion()` loads and indexes everything:
  - `knowledge_graph.md` → `m.nodes` (dict ref→Node: Person/Project/Goal/Objective,
    with `props` incl. `role`, `description`, `valid_from`, `valid_to`; `node.active`
    is False for ended nodes, e.g. Henrique Silva who is leaving) and `m.edges`
    (Edge: source/rel/target/props, rels: `member_of`, `collaborates_with`, `RELATES_TO`).
  - `medallion.json` → `m.silvers` (20), `m.golds` (6) — golds have `silver_refs`,
    silvers have `bronze_refs` (the lineage).
  - `bronze/*.json` → `m.bronzes` (9 raw datapoints: slack/meet/github/email/notion).
  - Helpers: `m.lineage_of_gold(id)`, `m.neighbors(ref)`, plus indexes
    `m.silvers_by_entity`, `m.golds_by_entity`, `m.golds_by_silver`, `m.edges_by_node`.
- `tools.py` — six agent tools + Anthropic schemas in `TOOLS`, dispatched via
  `run_tool(medallion, name, args)`: `search_entities`, `get_entity`,
  `search_golds`, `get_gold`, `get_silvers`, `get_bronze`.
- `answer.py` — CLI agent loop (Claude tool-use). Importable pieces you should
  reuse: `SYSTEM_PROMPT`, `MODEL`, `load_env()`. The loop itself is ~40 lines in
  `answer()`; **copy it into your server and add event hooks** rather than
  importing the function — you need to emit an event per tool call / text chunk.
- `.env` — has `ANTHROPIC_API_KEY` (and `GEMINI_API_KEY`, irrelevant to you).
  Python venv: `.venv/` with `anthropic` installed.

Run `python data.py` and `python tools.py` (smoke checks) and
`.venv/bin/python answer.py "Onde está a negociação com o NGCash?"` once, to see
the real behavior — including the stderr tool-call trace and the verified
"Lineage consultado" footer. Your UI is essentially a beautiful live rendering
of exactly that trace + answer.

## Hard boundaries — another agent works on this repo in parallel

A second agent owns evals (`eval/` directory) and may touch root files. To
guarantee zero merge conflicts:

- **Create everything under `ui/`.** Server, frontend, static assets, docs.
- **Never edit**: `data.py`, `tools.py`, `answer.py`, `NOTES.md`, `README.md`,
  `sample_output.txt`, root `requirements.txt`, root `.gitignore`,
  `medallion.json`, `knowledge_graph.md`, `bronze/**`, `eval/**`, `handoff.md`.
- Dependencies go in `ui/requirements.txt` (and `ui/package.json` if you use a
  build step — prefer not to, see below). Ignores go in `ui/.gitignore`.
- Import root modules by adding the repo root to `sys.path` from `ui/server.py`.
- Work on branch `feat/ui`; every commit touches only `ui/`.
- Server port: **8410** (chosen to not collide with anything else here).

## The mission

A local chat app (PT-BR interface) to ask questions about Alia, that makes the
*mechanism* visible and gorgeous: you watch the agent traverse the knowledge
graph and the medallion lineage in real time, then read a grounded answer with
clickable evidence.

### Architecture (suggested, keep it lean)

- `ui/server.py` — FastAPI + uvicorn, serves the frontend statics and:
  - `GET /api/graph` → full KG: `{nodes: [{ref,label,name,role,active,valid_to}], edges: [{source,rel,target,details,valid_to}]}`
  - `GET /api/corpus` → golds/silvers/bronzes (id, title/text, refs) for the evidence drawer, plus the 4 README example questions.
  - `POST /api/ask` `{question, model?}` → **SSE stream** of events (one JSON per `data:` line):
    - `{"type":"tool_call","seq":n,"name":"get_gold","args":{...}}`
    - `{"type":"tool_result","seq":n,"summary":"gold-002 · Alinhamento…","full":{...},"touched":{"entities":[...],"golds":[...],"silvers":[...],"bronzes":[...]}}`
    - `{"type":"text_delta","text":"..."}` (use the Anthropic streaming API for the final turn)
    - `{"type":"lineage","gold":[...],"silver":[...],"bronze":[...]}` (the *verified* set — build it from the tool calls you ran, exactly like `answer.py` does; never parse it out of model text)
    - `{"type":"done","stats":{"latency_s":…,"tool_calls":…,"input_tokens":…,"output_tokens":…}}` / `{"type":"error","message":…}`
  - Derive `touched` server-side from each tool result (refs/ids present in it) —
    the frontend uses it to light up the graph live.
- `ui/static/` — **no build step**: one `index.html` + ES modules + CDN pins.
  Recommended libs: `force-graph` (or `d3-force`) for the graph, `marked` +
  `DOMPurify` for rendering the answer markdown. If you strongly prefer
  React/Vite, you may, but the no-build version ships faster and is easier for
  the reviewer to run: `uvicorn ui.server:app --port 8410`.

### Design brief — this must NOT look like AI slop

First, load a design skill if one is available to you (e.g. the
`frontend-design` skill from github.com/anthropics/skills, or your platform's
artifact/web design skill) — and then still follow this brief:

- **Concept**: "instrument panel for a knowledge machine". Dark, calm,
  editorial. The medallion gives you a native palette — use it as the *only*
  accent system: bronze `#C08552`-ish, silver `#9BA8B5`-ish, gold `#D9A441`-ish
  over a near-black blue-gray base (`#0E1116` / `#161B22` surfaces). Entity
  labels get 4 muted hues (Person/Project/Goal/Objective) used consistently in
  chat chips AND graph nodes — color = meaning, never decoration.
- **Type**: one text face (Inter or IBM Plex Sans) + one mono (JetBrains Mono)
  for IDs, tool names, timestamps. Strong typographic hierarchy; generous
  whitespace; max ~72ch answer column.
- **Motion**: restrained and purposeful — tool-call rows slide in as they
  happen; graph nodes pulse once when touched; no bouncing, no shimmer.
- **Banned**: purple/blue gradient hero, glassmorphism everywhere, emoji as
  section headers, sparkle icons, generic "AI assistant" avatars, cards with
  1px borders + huge shadows on white.
- Empty states, loading states, and error states all designed, not default.

### Features

P0 — the core loop:
1. Chat pane: question in, streamed answer out (markdown). Inline `[gold-002]`
   citations rendered as small colored chips (color by layer) — click opens an
   **evidence drawer** showing that gold/silver/bronze's actual content, with
   its own lineage links (gold → its silvers → their bronzes).
2. **Agent timeline**: a live side rail showing each tool call as it streams —
   tool name (mono), args, collapsible result preview, elapsed time. This is
   the "watch it think" moment; make it the signature element.
3. Example-question chips (the 4 from the README) on the empty state.
4. Verified-lineage footer per answer (from the `lineage` event), as chips.

P1 — the graph (the showpiece):
5. Full knowledge-graph view (force layout): nodes colored by label, sized by
   degree; inactive nodes (`valid_to` set — e.g. Henrique) rendered dashed/faded
   with a "saindo 2026-04-24"-style tag; edge tooltip shows `details`.
6. **Live question overlay**: while a question runs, dim the graph and light up
   nodes/edges as tool results touch them (`touched` event data), leaving a
   highlighted "evidence trail" subgraph when done. Toggle: full graph ⇄ trail
   only. This is the single coolest thing you can build here — prioritize it.
7. Lineage view of the trail as a 3-layer left-to-right DAG (gold → silver →
   bronze), clickable into the evidence drawer.

P2 — polish:
8. Meta-feature (do this, it's a great touch): the dataset itself contains a UI
   spec — silver-015/016 record Alia's advisors deciding that *entity-sourced
   evidence must be visually distinct from silver-sourced evidence* ("estado"
   vs "evento"): a different chip shape/color, kept inline, clickable to a side
   card. **Implement their spec**: citations to KG entities get a different
   chip shape than gold/silver/bronze citations, and both stay inline.
9. History sidebar (localStorage), model picker (default from `ALIA_MODEL` env
   or `claude-sonnet-5`), per-answer stats (latency, tool calls, tokens),
   keyboard: `/` focuses input, `Esc` closes drawer.

### Acceptance checklist

- `cd <repo> && .venv/bin/pip install -r ui/requirements.txt && .venv/bin/uvicorn ui.server:app --port 8410` then open `http://localhost:8410` — works with zero other setup (`.env` already present).
- Ask "O que muda com a saída do Henrique?" → tool calls stream in the timeline,
  graph lights up Entity Layer / Henrique / handoff objective, answer arrives
  with clickable citation chips, verified lineage footer matches the trail.
- All 6 tool types render sensibly in the timeline; errors (bad model name, no
  API key) show a designed error state, not a blank screen.
- `git diff main --name-only` shows only `ui/**` files.
