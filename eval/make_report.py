"""Generate eval/report.html from eval/results/results.json.

Self-contained dark-theme HTML: leaderboard, score heatmap, findings,
and full drill-down (answer + judge booleans + lineage) per run.

    python eval/make_report.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent
OUT = EVAL_DIR / "report.html"

LAYER = {"gold": "#D9A441", "silver": "#9BA8B5", "bronze": "#C08552"}


def esc(s) -> str:
    return html.escape(str(s))


def score_color(s: float | None) -> str:
    if s is None:
        return "#333a45"
    # red -> amber -> green
    if s >= 0.7:
        return f"hsl({100 + (s - 0.7) * 100:.0f}, 45%, 32%)"
    return f"hsl({s / 0.7 * 45:.0f}, 55%, 30%)"


def checklist(items: list[str], hits: list[bool], invert=False) -> str:
    rows = []
    for item, hit in zip(items, hits):
        bad = hit if invert else not hit
        mark = ("✗" if invert else "✓") if hit else ("·" if invert else "✗")
        cls = "bad" if bad else "ok"
        rows.append(f'<li class="{cls}"><span class="mark">{mark}</span>{esc(item)}</li>')
    return "<ul class='checklist'>" + "".join(rows) + "</ul>"


def main() -> None:
    data = json.loads((EVAL_DIR / "results" / "results.json").read_text())
    eval_set = json.loads((EVAL_DIR / "eval_set.json").read_text())
    by_qid = {q["id"]: q for q in eval_set["questions"]}
    qids = [q["id"] for q in eval_set["questions"]]
    meta, board, runs = data["meta"], data["leaderboard"], data["runs"]
    models = [a["model"] for a in board]  # leaderboard order

    def row_of(model, qid):
        return next((r for r in runs[model] if r["question_id"] == qid), None)

    # --- leaderboard ---------------------------------------------------------
    lb_rows = ""
    for i, a in enumerate(board):
        lb_rows += f"""<tr>
<td class="rank">{i + 1}</td><td class="model">{esc(a['model'])}</td>
<td class="num big">{a['mean_score']:.3f}</td>
<td class="num">{a['correct']}/{a['n']}</td>
<td class="num {'warn' if a['hallucinations'] else ''}">{a['hallucinations']}</td>
<td class="num">{a['mean_lineage_recall']}</td>
<td class="num">{a['cites_lineage']}/{a['n']}</td>
<td class="num">{a['mean_latency_s']}s</td>
<td class="num">{a['mean_tool_calls']}</td>
</tr>"""

    # --- heatmap -------------------------------------------------------------
    qlabels = "".join(
        f"<th title='{esc(by_qid[q]['question'])}'>{esc(q.split('_')[0])}</th>"
        for q in qids)
    hm_rows = ""
    for m in models:
        cells = ""
        for qid in qids:
            r = row_of(m, qid)
            j = (r or {}).get("judge") or {}
            s = j.get("score")
            label = "—" if s is None else f"{s:.2f}"
            halo = "◆ " if j.get("hallucination") else ""
            cells += (f"<td style='background:{score_color(s)}'>"
                      f"<a href='#{esc(m)}--{esc(qid)}'>{halo}{label}</a></td>")
        hm_rows += f"<tr><td class='model'>{esc(m)}</td>{cells}</tr>"

    # --- findings ------------------------------------------------------------
    per_q_mean = {
        qid: sum((row_of(m, qid) or {}).get("judge", {}).get("score", 0)
                 for m in models) / len(models)
        for qid in qids}
    hardest = sorted(per_q_mean, key=per_q_mean.get)[:3]
    halluc_items = ""
    for m in models:
        for r in runs[m]:
            j = r.get("judge") or {}
            if j.get("hallucination"):
                halluc_items += (f"<li><b>{esc(m)}</b> × {esc(r['question_id'])}: "
                                 f"{esc(j.get('notes', ''))}</li>")
    hardest_items = "".join(
        f"<li><b>{esc(q)}</b> (média {per_q_mean[q]:.2f}) — {esc(by_qid[q]['question'])}</li>"
        for q in hardest)

    # --- drill-down ----------------------------------------------------------
    detail_html = ""
    for m in models:
        detail_html += f"<h3 class='model-h'>{esc(m)}</h3>"
        for qid in qids:
            r = row_of(m, qid)
            if not r:
                continue
            q, j = by_qid[qid], r.get("judge") or {}
            s = j.get("score")
            badge = "—" if s is None else f"{s:.2f}"
            hal = " <span class='halluc'>◆ hallucination</span>" if j.get("hallucination") else ""
            lin = "".join(
                f"<span class='chip' style='border-color:{LAYER[l]};color:{LAYER[l]}'>"
                f"{esc(i)}</span>"
                for l in ("gold", "silver", "bronze") for i in r["fetched"][l])
            detail_html += f"""
<details id="{esc(m)}--{esc(qid)}">
<summary><span class="badge" style="background:{score_color(s)}">{badge}</span>
{esc(qid)}{hal}
<span class="meta">{r['latency_s']}s · {len(r['tool_calls'])} tools ·
lineage recall {r['lineage_recall'] if r['lineage_recall'] is not None else 'n/a'}</span></summary>
<div class="body">
<p class="q">{esc(q['question'])}</p>
<div class="cols">
<div><h4>must_include</h4>{checklist(q['rubric']['must_include'], j.get('must_include_hits', []))}
<h4>nuance</h4>{checklist(q['rubric']['nuance'], j.get('nuance_hits', []))}
<h4>must_not</h4>{checklist(q['rubric']['must_not'], j.get('must_not_violations', []), invert=True)}
<p class="notes">Judge: {esc(j.get('notes', '(sem notas)'))}</p></div>
<div><h4>lineage verificado</h4><p>{lin or '<span class="meta">nenhum</span>'}</p>
<h4>resposta</h4><pre>{esc(r['text'])}</pre></div>
</div></div></details>"""

    html_doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alia QA Eval — {esc(meta['eval'])}</title>
<style>
:root {{ --bg:#0E1116; --surface:#161B22; --line:#252c36; --text:#dbe2ea;
  --dim:#8b97a5; --gold:#D9A441; --warn:#e06c75; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:var(--bg); color:var(--text); padding:2.5rem clamp(1rem,4vw,4rem);
  font:15px/1.55 "Inter",-apple-system,"Segoe UI",sans-serif; }}
h1 {{ font-size:1.6rem; letter-spacing:-.02em; }}
h1 span {{ color:var(--gold); }}
h2 {{ margin:2.5rem 0 .9rem; font-size:1.15rem; border-bottom:1px solid var(--line);
  padding-bottom:.45rem; }}
h3.model-h {{ margin:1.8rem 0 .5rem; font-size:1rem; color:var(--gold); }}
h4 {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.08em;
  color:var(--dim); margin:.9rem 0 .3rem; }}
.sub {{ color:var(--dim); margin-top:.4rem; max-width:75ch; }}
table {{ border-collapse:collapse; width:100%; background:var(--surface);
  border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
th,td {{ padding:.5rem .7rem; text-align:left; border-bottom:1px solid var(--line);
  font-size:.86rem; }}
th {{ color:var(--dim); font-weight:600; font-size:.72rem; text-transform:uppercase;
  letter-spacing:.06em; }}
td.num {{ font-variant-numeric:tabular-nums; text-align:right; }}
td.big {{ font-weight:700; color:var(--gold); }}
td.rank {{ color:var(--dim); width:2rem; }}
td.model, .model {{ font-family:"JetBrains Mono",ui-monospace,monospace; font-size:.82rem; }}
td.warn {{ color:var(--warn); font-weight:700; }}
.hm td {{ text-align:center; padding:.45rem .3rem; }}
.hm td a {{ color:var(--text); text-decoration:none; font-variant-numeric:tabular-nums;
  font-size:.8rem; display:block; }}
.legend {{ color:var(--dim); font-size:.8rem; margin-top:.5rem; }}
ul.findings {{ margin:.4rem 0 0 1.2rem; }} ul.findings li {{ margin:.35rem 0; }}
details {{ background:var(--surface); border:1px solid var(--line); border-radius:8px;
  margin:.45rem 0; }}
summary {{ cursor:pointer; padding:.6rem .9rem; display:flex; gap:.7rem;
  align-items:center; flex-wrap:wrap; }}
summary .meta {{ color:var(--dim); font-size:.78rem; margin-left:auto; }}
.badge {{ padding:.1rem .5rem; border-radius:4px; font-weight:700;
  font-variant-numeric:tabular-nums; font-size:.8rem; }}
.halluc {{ color:var(--warn); font-size:.78rem; }}
.body {{ padding:0 1rem 1rem; border-top:1px solid var(--line); }}
.q {{ color:var(--gold); margin:.8rem 0 .2rem; font-style:italic; }}
.cols {{ display:grid; grid-template-columns:minmax(280px,2fr) 3fr; gap:1.4rem; }}
@media (max-width:900px) {{ .cols {{ grid-template-columns:1fr; }} }}
ul.checklist {{ list-style:none; }}
ul.checklist li {{ padding:.12rem 0; font-size:.84rem; }}
ul.checklist .mark {{ display:inline-block; width:1.2rem; font-weight:700; }}
ul.checklist .ok .mark {{ color:#7fb069; }} ul.checklist .bad {{ color:var(--warn); }}
.notes {{ color:var(--dim); font-size:.84rem; margin-top:.8rem; font-style:italic; }}
.chip {{ display:inline-block; border:1px solid; border-radius:999px;
  padding:.05rem .55rem; margin:.12rem .2rem .12rem 0;
  font:0.72rem "JetBrains Mono",monospace; }}
pre {{ white-space:pre-wrap; background:var(--bg); border:1px solid var(--line);
  border-radius:6px; padding:.8rem; font-size:.8rem; max-height:30rem; overflow:auto; }}
.caveat {{ background:var(--surface); border-left:3px solid var(--gold);
  padding:.7rem 1rem; margin-top:1rem; font-size:.86rem; color:var(--dim);
  border-radius:0 6px 6px 0; }}
</style></head><body>
<h1>Alia QA Eval — <span>{esc(meta['eval'])}</span></h1>
<p class="sub">{len(models)} modelos × {meta['n_questions']} perguntas ·
juiz: <b>{esc(meta['judge_model'])}</b> (cego ao modelo avaliado) ·
score = 0.7·must_include + 0.3·nuance; violação de must_not trava em 0.25 ·
lineage recall computado deterministicamente das tool calls rastreadas ·
run: {esc(meta['run_finished'])}</p>

<h2>Leaderboard</h2>
<table><thead><tr><th></th><th>modelo</th><th style="text-align:right">score</th>
<th style="text-align:right">corretas (≥0.7)</th><th style="text-align:right">alucinações</th>
<th style="text-align:right">lineage recall</th><th style="text-align:right">cita IDs</th>
<th style="text-align:right">latência média</th><th style="text-align:right">tools/pergunta</th></tr></thead>
<tbody>{lb_rows}</tbody></table>

<h2>Heatmap — modelo × pergunta</h2>
<table class="hm"><thead><tr><th>modelo</th>{qlabels}</tr></thead>
<tbody>{hm_rows}</tbody></table>
<p class="legend">◆ = violação de must_not (alucinação). Clique numa célula para
abrir o detalhe. Passe o mouse no cabeçalho para ver a pergunta.</p>

<h2>Descobertas</h2>
<ul class="findings">
<li><b>Perguntas mais difíceis:</b></li>{hardest_items}
<li style="margin-top:.8rem"><b>Alucinações (violações de must_not, com a nota do juiz):</b></li>
{halluc_items or '<li>nenhuma</li>'}
</ul>
<div class="caveat"><b>Caveat do juiz:</b> em q02, respostas que enriqueceram o
contexto com fatos legítimos do knowledge graph (ex.: o papel da Livia Kuga no
onboarding pós-assinatura, presente nas arestas do grafo) foram marcadas como
"termos inventados" pelo must_not — essas violações específicas são
possivelmente falsos positivos do juiz, não invenções do modelo. A quebra de
q01 (atribuir a falha dos agentes ao incidente errado) é real em todos os
casos marcados.</div>

<h2>Detalhe por run</h2>
{detail_html}
</body></html>"""

    OUT.write_text(html_doc)
    print(f"wrote {OUT} ({len(html_doc) // 1024} KB)")


if __name__ == "__main__":
    main()
