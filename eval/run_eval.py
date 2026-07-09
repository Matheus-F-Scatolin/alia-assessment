"""Eval orchestrator: run every (model, question) pair, judge, aggregate.

Usage:
    python eval/run_eval.py                        # all models, all questions
    python eval/run_eval.py --models claude-haiku-4-5-20251001 --questions q01,q02
    python eval/run_eval.py --skip-existing        # resume an interrupted run

Writes eval/results/<model>.json incrementally (one file per model, safe to
resume) and eval/results/results.json with everything + aggregates at the end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from answer import load_env  # noqa: E402
from eval.agents import run_model  # noqa: E402
from eval.judge import judge_answer, lineage_recall, JUDGE_MODEL  # noqa: E402

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"

DEFAULT_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
]

MAX_ATTEMPTS = 3


def run_one(question: dict, model: str) -> dict:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        run = run_model(question["question"], model)
        if run["error"] is None and run["text"].strip():
            break
        if attempt < MAX_ATTEMPTS:
            time.sleep(10 * attempt)  # rate-limit / transient backoff
    return {"question_id": question["id"], "model": model, **run,
            "lineage_recall": lineage_recall(question["expected_lineage"],
                                             run["fetched"])}


def aggregate(model: str, rows: list[dict]) -> dict:
    graded = [r for r in rows if r.get("judge")]
    scores = [r["judge"]["score"] for r in graded]
    recalls = [r["lineage_recall"] for r in graded if r["lineage_recall"] is not None]
    return {
        "model": model,
        "n": len(rows),
        "mean_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "correct": sum(1 for r in graded if r["judge"]["correct"]),
        "hallucinations": sum(1 for r in graded if r["judge"]["hallucination"]),
        "mean_lineage_recall": round(sum(recalls) / len(recalls), 3) if recalls else None,
        "cites_lineage": sum(1 for r in graded if r["judge"]["cites_lineage"]),
        "mean_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 1),
        "mean_tool_calls": round(sum(len(r["tool_calls"]) for r in rows) / len(rows), 1),
        "errors": sum(1 for r in rows if r["error"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--questions", default="", help="comma-separated id prefixes, e.g. q01,q05")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    load_env()
    import anthropic
    judge_client = anthropic.Anthropic()

    eval_set = json.loads((EVAL_DIR / "eval_set.json").read_text())
    questions = eval_set["questions"]
    if args.questions:
        prefixes = tuple(p.strip() for p in args.questions.split(","))
        questions = [q for q in questions if q["id"].startswith(prefixes)]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    by_qid = {q["id"]: q for q in questions}

    RESULTS_DIR.mkdir(exist_ok=True)
    all_rows: dict[str, list[dict]] = {m: [] for m in models}

    # phase 1: run the agents ------------------------------------------------
    jobs = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for model in models:
            model_file = RESULTS_DIR / f"{model}.json"
            existing = {}
            if args.skip_existing and model_file.exists():
                existing = {r["question_id"]: r
                            for r in json.loads(model_file.read_text())}
            for q in questions:
                if q["id"] in existing:
                    all_rows[model].append(existing[q["id"]])
                    continue
                jobs.append(pool.submit(run_one, q, model))
        done = 0
        for fut in as_completed(jobs):
            row = fut.result()
            all_rows[row["model"]].append(row)
            done += 1
            status = "ERROR: " + row["error"] if row["error"] else f"{row['latency_s']}s, {len(row['tool_calls'])} tools"
            print(f"[{done}/{len(jobs)}] {row['model']} × {row['question_id']} — {status}", flush=True)

    # phase 2: judge ---------------------------------------------------------
    def judge_row(row: dict) -> dict:
        if row.get("judge"):
            return row
        try:
            row["judge"] = judge_answer(judge_client, by_qid[row["question_id"]],
                                        row["text"])
        except Exception as e:
            row["judge_error"] = f"{type(e).__name__}: {e}"
        return row

    to_judge = [r for rows in all_rows.values() for r in rows]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(judge_row, to_judge))
    print(f"judged {sum(1 for r in to_judge if r.get('judge'))}/{len(to_judge)} answers")

    # phase 3: persist -------------------------------------------------------
    for model, rows in all_rows.items():
        rows.sort(key=lambda r: r["question_id"])
        (RESULTS_DIR / f"{model}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1))

    combined = {
        "meta": {
            "eval": eval_set["meta"]["name"],
            "judge_model": JUDGE_MODEL,
            "run_finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "models": models,
            "n_questions": len(questions),
        },
        "leaderboard": sorted((aggregate(m, r) for m, r in all_rows.items()),
                              key=lambda a: -a["mean_score"]),
        "runs": {m: rows for m, rows in all_rows.items()},
    }
    out = RESULTS_DIR / "results.json"
    out.write_text(json.dumps(combined, ensure_ascii=False, indent=1))
    print(f"\nwrote {out}")
    for a in combined["leaderboard"]:
        print(f"  {a['model']:<32} score={a['mean_score']:.3f} "
              f"correct={a['correct']}/{a['n']} halluc={a['hallucinations']} "
              f"lineage={a['mean_lineage_recall']}")


if __name__ == "__main__":
    main()
