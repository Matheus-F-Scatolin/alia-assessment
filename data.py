"""Data layer for the Alia medallion.

Loads and indexes the three sources:
  - knowledge_graph.md  -> entity nodes (Person/Project/Goal/Objective) and edges
  - medallion.json      -> silver (interpretations) and gold (narratives)
  - bronze/*.json       -> raw datapoints (slack, meet, github, email, notion)

Everything is exposed through a single `Medallion` object with lookup and
lineage indexes. No LLM calls here — this module is pure and deterministic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------

@dataclass
class Node:
    ref: str                # "Person:Bernardo Aires"
    label: str              # "Person"
    name: str               # "Bernardo Aires"
    props: dict = field(default_factory=dict)  # role, description, valid_from, valid_to

    @property
    def active(self) -> bool:
        return not self.props.get("valid_to")


@dataclass
class Edge:
    source: str             # node ref
    rel: str                # "member_of", "collaborates_with", "RELATES_TO"
    target: str             # node ref
    props: dict = field(default_factory=dict)  # details, valid_from, valid_to


def _normalize_ref(raw: str) -> str:
    """Edge targets sometimes carry a trailing label, e.g.
    'Project:Gold Synthesis:Project' -> 'Project:Gold Synthesis'."""
    parts = raw.split(":")
    if len(parts) >= 3 and parts[-1] == parts[0]:
        return ":".join(parts[:-1])
    return raw


def parse_knowledge_graph(path: Path) -> tuple[dict[str, Node], list[Edge]]:
    text = path.read_text(encoding="utf-8")

    nodes: dict[str, Node] = {}
    for m in re.finditer(r"^#### (\w+:.+?)\n((?:^- .+\n?)*)", text, re.MULTILINE):
        ref = m.group(1).strip()
        label, name = ref.split(":", 1)
        props = dict(re.findall(r"^- (\w+): ?(.*)$", m.group(2), re.MULTILINE))
        nodes[ref] = Node(ref=ref, label=label, name=name, props=props)

    edges: list[Edge] = []
    edge_re = re.compile(
        r"^- \((.+?)\) -\[(\w+)\]-> \((.+?)\)\n((?:^  \w+: .*\n?)*)", re.MULTILINE
    )
    for m in edge_re.finditer(text):
        props = dict(re.findall(r"^  (\w+): (.*)$", m.group(4), re.MULTILINE))
        edges.append(Edge(
            source=_normalize_ref(m.group(1)),
            rel=m.group(2),
            target=_normalize_ref(m.group(3)),
            props=props,
        ))
    return nodes, edges


# ---------------------------------------------------------------------------
# Medallion container
# ---------------------------------------------------------------------------

class Medallion:
    def __init__(self, root: Path = ROOT):
        self.nodes, self.edges = parse_knowledge_graph(root / "knowledge_graph.md")

        med = json.loads((root / "medallion.json").read_text(encoding="utf-8"))
        self.silvers: dict[str, dict] = {s["id"]: s for s in med["silver"]}
        self.golds: dict[str, dict] = {g["id"]: g for g in med["gold"]}

        self.bronzes: dict[str, dict] = {}
        for f in sorted((root / "bronze").glob("*.json")):
            b = json.loads(f.read_text(encoding="utf-8"))
            self.bronzes[b["id"]] = b

        # --- indexes ---
        self.edges_by_node: dict[str, list[Edge]] = {}
        for e in self.edges:
            self.edges_by_node.setdefault(e.source, []).append(e)
            self.edges_by_node.setdefault(e.target, []).append(e)

        self.silvers_by_entity: dict[str, list[str]] = {}
        for s in self.silvers.values():
            for ref in set(s.get("entity_refs", [])) | {s.get("project_ref")}:
                if ref:
                    self.silvers_by_entity.setdefault(ref, []).append(s["id"])

        self.golds_by_entity: dict[str, list[str]] = {}
        for g in self.golds.values():
            for ref in g.get("entity_refs", []):
                self.golds_by_entity.setdefault(ref, []).append(g["id"])

        # silver -> golds that cite it (reverse lineage)
        self.golds_by_silver: dict[str, list[str]] = {}
        for g in self.golds.values():
            for sid in g.get("silver_refs", []):
                self.golds_by_silver.setdefault(sid, []).append(g["id"])

    # --- lineage traversal -------------------------------------------------

    def lineage_of_gold(self, gold_id: str) -> dict:
        """Full gold -> silver -> bronze lineage tree (IDs only)."""
        gold = self.golds[gold_id]
        silver_ids = gold.get("silver_refs", [])
        bronze_ids = sorted({
            b for sid in silver_ids
            for b in self.silvers.get(sid, {}).get("bronze_refs", [])
        })
        return {"gold": gold_id, "silvers": silver_ids, "bronzes": bronze_ids}

    def neighbors(self, ref: str) -> list[dict]:
        """1-hop graph neighborhood of an entity, with edge context."""
        out = []
        for e in self.edges_by_node.get(ref, []):
            other = e.target if e.source == ref else e.source
            out.append({
                "rel": e.rel,
                "direction": "out" if e.source == ref else "in",
                "node": other,
                "details": e.props.get("details", ""),
                "valid_to": e.props.get("valid_to", ""),
            })
        return out


def _smoke():
    m = Medallion()
    assert len(m.nodes) == 31, len(m.nodes)
    assert len(m.edges) == 39, len(m.edges)
    assert len(m.silvers) == 20 and len(m.golds) == 6 and len(m.bronzes) == 9
    assert not m.nodes["Person:Henrique Silva"].active          # leaving
    assert m.nodes["Person:Bernardo Aires"].active
    lin = m.lineage_of_gold("gold-002")
    assert lin["silvers"] == ["silver-004", "silver-002", "silver-005"]
    assert "bronze-meet-002" in lin["bronzes"]
    assert any(n["node"] == "Person:Henrique Silva"
               for n in m.neighbors("Project:Entity Layer"))
    print(f"OK — {len(m.nodes)} nodes, {len(m.edges)} edges, "
          f"{len(m.silvers)} silvers, {len(m.golds)} golds, {len(m.bronzes)} bronzes")


if __name__ == "__main__":
    _smoke()
