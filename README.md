# Assessment

You have a mini-medallion of a real-ish company:

- `bronze/*.json` — raw datapoints (Slack threads, Meet transcripts, a GitHub PR, an email thread, a Notion meeting page). Each has a stable `id`.
- `knowledge_graph.md` — people, projects, goals, objectives and the edges between them. Entity refs are `Label:Name` (e.g. `Person:Bernardo Aires`, `Project:Entity Layer`, `Objective:Close NGCash at $6k+`). An empty `valid_to` means the entity is active; a date means it ended or is ending.
- `medallion.json` — silver (interpretations over bronze) and gold (narratives over silver). Silvers link back to bronze IDs and entities; golds link back to silver IDs and entities.

Your job: write a program that answers questions about the company, grounded in this data. Not a summary of the JSON — a real answer that traces the lineage (gold → silver → bronze) and names the people and projects by their role in the graph. The program takes any question as its argument — the examples below are illustrative, not the full set.

```
python answer.py "Bernardo e Lucas estão alinhados sobre as camadas do medallion?"
```

Example questions:

- *Bernardo e Lucas estão alinhados sobre as camadas do medallion?*
- *Por que os agentes do Bernardo quebraram?*
- *O que muda com a saída do Henrique?*
- *Onde está a negociação com o NGCash?*

Good answers:

- Follow the lineage — cite the gold, silver, and bronze IDs you used.
- Use the knowledge graph when the question is about a person, a project, or a goal/objective.
- Surface context the asker didn't ask about, if the data warrants it (the demo case: asking about "alignment" and getting the hidden Henrique-exit risk surfaced).
- Handle questions where the data is thin or spans multiple nodes.
- Respond in Portuguese.

Use any tools you want (Claude Code, Cursor, LLM of choice).

## Ship

- Your code
- `NOTES.md` — what you decided and why, what surprised you, and what you left out / would do with more time
- `sample_output.txt` — your best run on each of the 4 example questions (plus anything else you try)

Commit as you go. Around 1h30.
