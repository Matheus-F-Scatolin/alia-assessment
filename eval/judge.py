"""LLM judge for the eval — claude-opus-4-8, blind to the producing model.

The judge only emits booleans (per rubric item); the score is computed in
code per the formula in eval_set.json meta.grading. Lineage recall is NOT
judged here — the runner computes it deterministically from tracked tool
calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

JUDGE_MODEL = "claude-opus-4-8"

JUDGE_TOOL = {
    "name": "grade",
    "description": "Report the grading of the candidate answer against the rubric.",
    "input_schema": {
        "type": "object",
        "properties": {
            "must_include_hits": {"type": "array", "items": {"type": "boolean"}},
            "nuance_hits": {"type": "array", "items": {"type": "boolean"}},
            "must_not_violations": {"type": "array", "items": {"type": "boolean"}},
            "cites_lineage": {"type": "boolean"},
            "answers_in_portuguese": {"type": "boolean"},
            "notes": {"type": "string"},
        },
        "required": ["must_include_hits", "nuance_hits", "must_not_violations",
                     "cites_lineage", "answers_in_portuguese", "notes"],
    },
}

JUDGE_PROMPT = """\
You are grading an answer produced by an anonymous QA system about a company \
called Alia, against a hand-verified rubric. Be strict but fair.

Rules:
- A rubric item counts as PRESENT if the answer states it with equivalent \
meaning, in any wording or language. Numbers must match within rounding \
($6k ~ $6.0k ok; $5k vs $6k not ok). When the rubric gives a specific date, \
the answer must match to the day (naming the weekday that corresponds to it \
also counts, e.g. 'terça' for 2026-04-21).
- must_not items are VIOLATED only if the answer affirmatively states the \
forbidden thing; merely omitting information is not a violation.
- cites_lineage: true if the answer cites at least one gold/silver/bronze ID \
inline or in a lineage footer (e.g. [silver-004], gold-002).
- Output one boolean per rubric item, in order, via the `grade` tool. \
`notes`: one sentence on the main gap, if any.

<question>
{question}

</question>
<gold_answer>
{gold_answer}
</gold_answer>

<rubric>
must_include:
{must_include}

nuance:
{nuance}

must_not:
{must_not}
</rubric>

<candidate_answer>
{answer}
</candidate_answer>
"""


def _fmt_items(items: list[str]) -> str:
    return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))


def judge_answer(client, question: dict, answer_text: str) -> dict:
    """Returns the judge dict + computed score. `client` is anthropic.Anthropic()."""
    rubric = question["rubric"]
    prompt = JUDGE_PROMPT.format(
        question=question["question"],
        gold_answer=question["gold_answer"],
        must_include=_fmt_items(rubric["must_include"]),
        nuance=_fmt_items(rubric["nuance"]),
        must_not=_fmt_items(rubric["must_not"]),
        answer=answer_text or "(empty answer)",
    )
    response = client.messages.create(
        model=JUDGE_MODEL, max_tokens=2000,
        tools=[JUDGE_TOOL], tool_choice={"type": "tool", "name": "grade"},
        messages=[{"role": "user", "content": prompt}],
    )
    grade = next(b.input for b in response.content if b.type == "tool_use")

    # normalize list lengths defensively (judge occasionally miscounts)
    for key, ref in (("must_include_hits", rubric["must_include"]),
                     ("nuance_hits", rubric["nuance"]),
                     ("must_not_violations", rubric["must_not"])):
        hits = list(grade.get(key, []))[: len(ref)]
        hits += [False] * (len(ref) - len(hits))
        grade[key] = hits

    must_frac = sum(grade["must_include_hits"]) / len(rubric["must_include"])
    nuance_frac = sum(grade["nuance_hits"]) / len(rubric["nuance"])
    score = 0.7 * must_frac + 0.3 * nuance_frac
    hallucination = any(grade["must_not_violations"])
    if hallucination:
        score = min(score, 0.25)

    return {**grade, "score": round(score, 3), "hallucination": hallucination,
            "correct": score >= 0.7}


def lineage_recall(expected: dict, fetched: dict) -> float | None:
    """Deterministic: fraction of core expected IDs actually fetched,
    averaged over non-empty layers. None if no layer has expectations."""
    fracs = []
    for layer in ("gold", "silver", "bronze"):
        core = set(expected.get(layer, []))
        if core:
            fracs.append(len(core & set(fetched.get(layer, []))) / len(core))
    return round(sum(fracs) / len(fracs), 3) if fracs else None
