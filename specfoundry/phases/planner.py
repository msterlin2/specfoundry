"""Spec Planner — converts the IR into a concrete spec file plan."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..ir import SpecIR
from ..llm.base import LLMClient, Message
from ..utils import extract_json

# ── Standard file catalogue ────────────────────────────────────────────────────

_STANDARD_FILES = [
    {
        "filename": "00-product-overview.md",
        "title": "Product Overview",
        "responsibility": "Purpose, goals, target users, non-goals, quality attributes.",
        "always": True,
    },
    {
        "filename": "01-system-architecture.md",
        "title": "System Architecture",
        "responsibility": "Component diagram, service boundaries, data flow, technology choices.",
        "always": True,
    },
    {
        "filename": "02-domain-model.md",
        "title": "Domain Model",
        "responsibility": "All domain entities: fields, invariants, lifecycle, relationships.",
        "always": True,
    },
    {
        "filename": "03-user-workflows.md",
        "title": "User Workflows",
        "responsibility": "Every workflow: actor, trigger, steps, success/failure paths, acceptance tests.",
        "always": True,
    },
    {
        "filename": "04-api-contracts.md",
        "title": "API Contracts",
        "responsibility": "All endpoints: method, path, auth, request/response schemas, error codes.",
        "requires": "apis",
    },
    {
        "filename": "05-data-storage.md",
        "title": "Data Storage",
        "responsibility": "Database schema, indexes, migration strategy, retention, backup.",
        "always": True,
    },
    {
        "filename": "06-frontend-ux.md",
        "title": "Frontend & UX",
        "responsibility": "Pages, component hierarchy, state management, routing, accessibility.",
        "requires": "frontend",
    },
    {
        "filename": "07-background-jobs.md",
        "title": "Background Jobs",
        "responsibility": "Every async process: trigger, inputs, outputs, retries, timeouts, monitoring.",
        "requires": "background_jobs",
    },
    {
        "filename": "08-security-and-auth.md",
        "title": "Security & Auth",
        "responsibility": "Auth mechanism, authorization model, secrets management, compliance.",
        "always": True,
    },
    {
        "filename": "09-observability-and-ops.md",
        "title": "Observability & Ops",
        "responsibility": "Logging, metrics, tracing, alerting, deployment, scaling.",
        "always": True,
    },
    {
        "filename": "10-testing-and-acceptance.md",
        "title": "Testing & Acceptance",
        "responsibility": "Test strategy, unit/integration/e2e tests, acceptance criteria, test data.",
        "always": True,
    },
]

_AI_FILES = [
    {
        "filename": "11-agent-loop.md",
        "title": "Agent Loop",
        "responsibility": "Orchestration loop, tool use, context management, subagent design.",
    },
    {
        "filename": "12-tooling-contracts.md",
        "title": "Tooling Contracts",
        "responsibility": "Tool schema, execution rules, parallel execution, result aggregation.",
    },
    {
        "filename": "13-llm-provider-abstraction.md",
        "title": "LLM Provider Abstraction",
        "responsibility": "Provider interface, adapters, streaming, retry, timeout, model selection.",
    },
    {
        "filename": "14-context-and-memory.md",
        "title": "Context & Memory",
        "responsibility": "Context window management, memory types, retrieval, eviction strategy.",
    },
]

_SYSTEM_PROMPT = """\
You are a software architect planning a specification document set.
Given a Spec IR, decide which files should be generated and what each one covers.
Return a JSON array of file objects. Do not include files that are not relevant.
Return JSON only, no prose.
"""


class SpecPlanner:
    def __init__(self, client: LLMClient, console: Console):
        self.client = client
        self.console = console

    def run(self, ir: SpecIR) -> list[dict]:
        """Return the ordered list of spec files to generate."""
        plan = self._build_initial_plan(ir)
        plan = self._refine_with_llm(plan, ir)
        self._show_plan(plan)
        return plan

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _build_initial_plan(self, ir: SpecIR) -> list[dict]:
        """Deterministically select files based on IR content."""
        plan: list[dict] = []
        for entry in _STANDARD_FILES:
            if entry.get("always"):
                plan.append(_make_entry(entry))
                continue
            req = entry.get("requires", "")
            if req == "apis" and ir.apis:
                plan.append(_make_entry(entry))
            elif req == "frontend" and ir.deployment.frontend_framework not in ("", "none", "None"):
                plan.append(_make_entry(entry))
            elif req == "background_jobs" and ir.background_jobs:
                plan.append(_make_entry(entry))

        if ir.is_ai_heavy:
            for entry in _AI_FILES:
                plan.append(_make_entry(entry))

        return plan

    def _refine_with_llm(self, plan: list[dict], ir: SpecIR) -> list[dict]:
        """Let the LLM propose additions or removals based on the full IR."""
        prompt = (
            f"Spec IR:\n{ir.to_json()}\n\n"
            f"Current file plan:\n{_plan_summary(plan)}\n\n"
            "Review this plan. Add, remove, or adjust files based on the IR content. "
            "Return the complete updated plan as a JSON array with keys: "
            "filename, title, responsibility, depends_on."
        )
        try:
            resp = self.client.generate(
                messages=[Message(role="user", content=prompt)],
                system=_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.2,
            )
            data = extract_json(resp)
            if isinstance(data, list) and data:
                # Validate entries and fill missing keys
                refined = []
                for item in data:
                    if isinstance(item, dict) and "filename" in item:
                        refined.append({
                            "filename": item["filename"],
                            "title": item.get("title", item["filename"]),
                            "responsibility": item.get("responsibility", ""),
                            "depends_on": item.get("depends_on", []),
                        })
                if refined:
                    return refined
        except Exception:
            pass
        return plan

    def _show_plan(self, plan: list[dict]) -> None:
        table = Table(title="Spec File Plan", show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=3)
        table.add_column("File", style="cyan")
        table.add_column("Covers")
        for i, entry in enumerate(plan, 1):
            resp = entry.get("responsibility", "")
            short = resp[:70] + ("…" if len(resp) > 70 else "")
            table.add_row(str(i), entry["filename"], short)
        self.console.print(table)


def _make_entry(entry: dict) -> dict:
    return {
        "filename": entry["filename"],
        "title": entry["title"],
        "responsibility": entry["responsibility"],
        "depends_on": [],
    }


def _plan_summary(plan: list[dict]) -> str:
    lines = []
    for p in plan:
        lines.append(f"- {p['filename']}: {p['responsibility']}")
    return "\n".join(lines)
