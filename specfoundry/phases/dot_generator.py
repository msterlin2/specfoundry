"""DOT Graph Generator — deterministic system.dot from the Spec IR.

Node types  : module (box), entity (ellipse), workflow (diamond), api (hexagon), job (rect)
Edge types  : dependency (solid), data_flow (dashed), invokes (dotted)
"""
from __future__ import annotations

import re

from rich.console import Console

from ..ir import SpecIR


_HEADER = (
    'digraph system {\n'
    '  rankdir=LR;\n'
    '  fontname="Helvetica";\n'
    '  node [fontname="Helvetica", fontsize=11];\n'
    '  edge [fontname="Helvetica", fontsize=9];\n'
)

_FOOTER = "}\n"


class DotGenerator:
    def __init__(self, console: Console):
        self.console = console

    def run(self, ir: SpecIR) -> str:
        """Return the complete DOT source for the system graph."""
        lines: list[str] = [_HEADER]

        lines += self._actors(ir)
        lines += self._entities(ir)
        lines += self._workflows(ir)
        lines += self._apis(ir)
        lines += self._jobs(ir)
        lines += self._edges(ir)

        lines.append(_FOOTER)
        dot = "\n".join(lines)
        self.console.print("[green]OK[/green] DOT graph generated (system.dot)")
        return dot

    # ── Node groups ────────────────────────────────────────────────────────────

    def _actors(self, ir: SpecIR) -> list[str]:
        if not ir.users:
            return []
        out = ["  // Actors (user roles)"]
        out.append("  subgraph cluster_actors {")
        out.append('    label="Actors"; style=dashed; color=grey;')
        for u in ir.users:
            n = _node_id(u.role)
            out.append(f'    {n} [shape=oval, style=filled, fillcolor="#e8f5e9", label="{u.role}"];')
        out.append("  }")
        return out

    def _entities(self, ir: SpecIR) -> list[str]:
        if not ir.entities:
            return []
        out = ["  // Domain entities"]
        out.append("  subgraph cluster_entities {")
        out.append('    label="Domain Model"; style=dashed; color=grey;')
        for e in ir.entities:
            n = _node_id(e.name)
            out.append(f'    {n} [shape=ellipse, style=filled, fillcolor="#fff9c4", label="{e.name}"];')
        out.append("  }")
        return out

    def _workflows(self, ir: SpecIR) -> list[str]:
        if not ir.workflows:
            return []
        out = ["  // Workflows"]
        out.append("  subgraph cluster_workflows {")
        out.append('    label="Workflows"; style=dashed; color=grey;')
        for w in ir.workflows:
            n = _node_id(w.name) + "_wf"
            out.append(f'    {n} [shape=diamond, style=filled, fillcolor="#e3f2fd", label="{w.name}"];')
        out.append("  }")
        return out

    def _apis(self, ir: SpecIR) -> list[str]:
        if not ir.apis:
            return []
        out = ["  // API endpoints"]
        out.append("  subgraph cluster_apis {")
        out.append('    label="APIs"; style=dashed; color=grey;')
        for a in ir.apis:
            label = f"{a.method} {a.path}"
            n = _node_id(f"{a.method}_{a.path}")
            out.append(f'    {n} [shape=hexagon, style=filled, fillcolor="#fce4ec", label="{label}"];')
        out.append("  }")
        return out

    def _jobs(self, ir: SpecIR) -> list[str]:
        if not ir.background_jobs:
            return []
        out = ["  // Background jobs"]
        out.append("  subgraph cluster_jobs {")
        out.append('    label="Background Jobs"; style=dashed; color=grey;')
        for j in ir.background_jobs:
            n = _node_id(j.name) + "_job"
            out.append(
                f'    {n} [shape=rect, style="filled,dashed", fillcolor="#f3e5f5", label="{j.name}"];'
            )
        out.append("  }")
        return out

    # ── Edges ──────────────────────────────────────────────────────────────────

    def _edges(self, ir: SpecIR) -> list[str]:
        out = ["  // Edges"]
        entity_names = {e.name for e in ir.entities}

        # Actor → Workflow  (invokes)
        for w in ir.workflows:
            if w.actor:
                actor_n = _node_id(w.actor)
                wf_n = _node_id(w.name) + "_wf"
                out.append(
                    f'  {actor_n} -> {wf_n} [label="initiates", style=dotted, arrowhead=open];'
                )

        # Workflow → Entity  (data_flow — infer from step text)
        for w in ir.workflows:
            wf_n = _node_id(w.name) + "_wf"
            referenced = _entities_referenced(" ".join(w.steps), entity_names)
            for ename in referenced:
                e_n = _node_id(ename)
                out.append(
                    f"  {wf_n} -> {e_n} [style=dashed, arrowhead=normal, "
                    f'label="data_flow", color=steelblue];'
                )

        # API → Entity  (dependency — infer from path)
        for a in ir.apis:
            api_n = _node_id(f"{a.method}_{a.path}")
            referenced = _entities_referenced(a.path, entity_names)
            for ename in referenced:
                e_n = _node_id(ename)
                out.append(
                    f"  {api_n} -> {e_n} [style=solid, arrowhead=normal, "
                    f'label="dependency"];'
                )

        # Entity relationships
        for e in ir.entities:
            for rel in e.relationships:
                target_name = _extract_entity_name(rel, entity_names)
                if target_name:
                    out.append(
                        f'  {_node_id(e.name)} -> {_node_id(target_name)} '
                        f'[label="{rel[:30]}", style=solid, arrowhead=open, color=darkgoldenrod];'
                    )

        # Background jobs → Entity
        for j in ir.background_jobs:
            job_n = _node_id(j.name) + "_job"
            all_text = " ".join(j.inputs + j.outputs + [j.trigger])
            referenced = _entities_referenced(all_text, entity_names)
            for ename in referenced:
                out.append(
                    f'  {job_n} -> {_node_id(ename)} [style=dashed, arrowhead=open, '
                    f'label="processes", color=purple];'
                )

        return out


# ── Utility ────────────────────────────────────────────────────────────────────

def _node_id(text: str) -> str:
    """Convert arbitrary text to a valid DOT identifier."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", text)
    s = re.sub(r"_+", "_", s).strip("_")
    if s and s[0].isdigit():
        s = "n_" + s
    return s or "node"


def _entities_referenced(text: str, entity_names: set[str]) -> list[str]:
    """Find entity names mentioned in free text."""
    return [n for n in entity_names if n.lower() in text.lower()]


def _extract_entity_name(relationship: str, entity_names: set[str]) -> str | None:
    """Extract a known entity name from a relationship string like 'belongs to User'."""
    for name in entity_names:
        if name.lower() in relationship.lower():
            return name
    return None
