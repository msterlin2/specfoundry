"""Consistency Checker — validates cross-spec correctness via LLM audit."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..ir import SpecIR
from ..llm.base import LLMClient, Message
from ..utils import extract_json

_AUDITOR_SYSTEM = """\
You are a spec auditor reviewing a set of specification documents for consistency,
completeness, and correctness. Your job is to find contradictions, gaps, and ambiguities
that would cause a coding agent to make wrong assumptions.

Return JSON only:
{
  "score": <0-100>,
  "critical": [
    {
      "type": "undefined_entity | api_mismatch | workflow_gap | security_inconsistency | missing_acceptance | naming_inconsistency | contradiction",
      "description": "string",
      "files": ["filename"],
      "suggestion": "string"
    }
  ],
  "warnings": [
    {
      "type": "string",
      "description": "string",
      "files": ["filename"],
      "suggestion": "string"
    }
  ]
}
"""

_AUDIT_PROMPT = """\
Review these specification files for consistency and completeness.

Spec IR (source of truth):
{ir_json}

Generated specification files:
{files_content}

Check for:
1. Entities referenced in workflows or APIs but not defined in the domain model
2. API routes or schemas that contradict each other across files
3. Workflows that are mentioned but missing actor / trigger / failure modes / acceptance tests
4. Auth or security mentioned in UX/API files but not reflected in the security spec
5. Features or workflows with no acceptance criteria
6. The same concept named differently across files
7. Conflicting statements about technology choices, constraints, or behavior

Return the JSON audit report.
"""


class ConsistencyChecker:
    def __init__(self, client: LLMClient, console: Console):
        self.client = client
        self.console = console

    def run(self, ir: SpecIR, outputs: dict[str, str]) -> dict:
        """Run the audit. Returns the report dict."""
        self.console.print("\n[bold]Running cross-spec consistency check…[/bold]")

        files_content = _format_files(outputs)
        prompt = _AUDIT_PROMPT.format(
            ir_json=ir.to_json(),
            files_content=files_content,
        )

        report: dict = {"score": 0, "critical": [], "warnings": []}
        try:
            resp = self.client.generate(
                messages=[Message(role="user", content=prompt)],
                system=_AUDITOR_SYSTEM,
                max_tokens=4096,
                temperature=0.2,
            )
            data = extract_json(resp)
            if isinstance(data, dict):
                report = data
        except Exception as exc:
            self.console.print(f"[yellow]Warning: consistency check failed ({exc})[/yellow]")

        self._show_report(report)
        return report

    def _show_report(self, report: dict) -> None:
        score = report.get("score", 0)
        color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
        critical = report.get("critical", [])
        warnings = report.get("warnings", [])

        self.console.print(
            Panel(
                f"Consistency score: [{color}]{score}/100[/{color}]  "
                f"| Critical issues: [red]{len(critical)}[/red]  "
                f"| Warnings: [yellow]{len(warnings)}[/yellow]",
                title="[bold]Consistency Report[/bold]",
                border_style=color,
            )
        )

        if critical:
            table = Table(title="Critical Issues", show_header=True, header_style="bold red")
            table.add_column("Type", style="red", width=24)
            table.add_column("Description")
            table.add_column("Suggestion", style="dim")
            for issue in critical:
                table.add_row(
                    issue.get("type", "unknown"),
                    issue.get("description", ""),
                    issue.get("suggestion", ""),
                )
            self.console.print(table)

        if warnings:
            table = Table(title="Warnings", show_header=True, header_style="bold yellow")
            table.add_column("Type", style="yellow", width=24)
            table.add_column("Description")
            for w in warnings:
                table.add_row(w.get("type", "unknown"), w.get("description", ""))
            self.console.print(table)


def _format_files(outputs: dict[str, str]) -> str:
    parts = []
    for filename, content in outputs.items():
        # Truncate very long files to avoid context overflow
        excerpt = content if len(content) <= 8000 else content[:8000] + "\n…[truncated]"
        parts.append(f"=== {filename} ===\n{excerpt}")
    return "\n\n".join(parts)
