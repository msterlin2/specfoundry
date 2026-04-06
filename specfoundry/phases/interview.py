"""Interview Engine — structured requirements elicitation via LLM-driven Q&A."""
from __future__ import annotations

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..ir import SpecIR
from ..llm.base import LLMClient, Message
from ..utils import extract_json

# ── Prompts ───────────────────────────────────────────────────────────────────

_ANALYST_SYSTEM = """\
You are an expert requirements analyst. Extract structured software requirements from
interview answers and maintain a Spec IR (Intermediate Representation).

The Spec IR follows this exact JSON schema:
{
  "product": {
    "name": "string",
    "summary": "string — 1-2 sentences",
    "app_type": "web | cli | api | mobile | ai-agent | library | other",
    "description": "string — detailed description"
  },
  "users": [
    {"role": "string", "goals": ["string"], "permissions": ["string"]}
  ],
  "workflows": [
    {
      "name": "string",
      "actor": "string — user role",
      "trigger": "string — what initiates this",
      "steps": ["string — ordered steps"],
      "success_result": "string",
      "failure_modes": ["string"],
      "acceptance_tests": ["string — testable criteria"]
    }
  ],
  "entities": [
    {
      "name": "string",
      "fields": [{"name": "string", "type": "string", "required": true, "description": "string"}],
      "invariants": ["string — business rules"],
      "lifecycle": "string — states the entity passes through",
      "relationships": ["string — e.g. 'belongs to User'"]
    }
  ],
  "apis": [
    {
      "method": "GET|POST|PUT|DELETE|PATCH",
      "path": "string — e.g. /api/v1/resource",
      "auth": "string",
      "request_schema": {"field": "type"},
      "response_schema": {"field": "type"},
      "error_conditions": ["string"],
      "rate_limits": "string",
      "idempotent": false
    }
  ],
  "background_jobs": [
    {
      "name": "string",
      "trigger": "string — schedule or event",
      "inputs": ["string"],
      "outputs": ["string"],
      "retries": 3,
      "timeout_seconds": 300,
      "observability": "string — what to log/alert on",
      "human_override": "string — how humans can intervene"
    }
  ],
  "deployment": {
    "target": "string — e.g. docker on VPS, k8s, serverless",
    "cloud": "string — AWS/GCP/Azure/self-hosted",
    "backend_framework": "string — FastAPI/Express/Django/etc",
    "frontend_framework": "string — React/Vue/none/etc",
    "database": "string — PostgreSQL/SQLite/MongoDB/etc",
    "cache": "string — Redis/none/etc",
    "message_queue": "string — RabbitMQ/SQS/none/etc"
  },
  "security": {
    "auth_method": "string — JWT/API key/OAuth/session",
    "authorization_model": "string — RBAC/ABAC/none",
    "data_sensitivity": "string — public/internal/confidential/restricted",
    "compliance": ["string — GDPR/HIPAA/SOC2/etc"]
  },
  "quality_attributes": ["string — e.g. 99.9% uptime, sub-100ms p99 latency"],
  "acceptance_criteria": ["string — testable done criteria"],
  "open_questions": ["string — unresolved questions needing clarification"],
  "is_ai_heavy": false
}

Rules:
- Be thorough and generous when extracting. Capture every detail mentioned.
- Infer reasonable values where the user has provided hints.
- Preserve all existing IR content and merge new information into it.
- Return ONLY the complete updated IR as valid JSON. No prose, no fences.
"""

_INTERVIEWER_SYSTEM = """\
You are conducting a structured requirements interview for a software project.
Your goal is to ask ONE targeted, high-value question that fills the most important gap.
Return JSON only: {"question": "...", "domain": "..."}
"""

_FALLBACK_QUESTIONS: dict[str, str] = {
    "product overview": (
        "What is the name of this project, and can you give me a one-sentence description of what it does?"
    ),
    "user roles": (
        "Who are the primary users of this system? "
        "List each role and describe what they need to accomplish."
    ),
    "user workflows": (
        "Walk me through the 3–5 most important actions a user performs in this system, "
        "step by step."
    ),
    "data model / entities": (
        "What are the key data entities in this system (e.g. User, Order, Invoice)? "
        "For each one, list its important fields."
    ),
    "API contracts": (
        "What API endpoints will this system expose? "
        "Describe the most important ones including method, path, and what they return."
    ),
    "deployment / infrastructure": (
        "Where and how will this system be deployed? "
        "What is the tech stack (language, framework, database, hosting)?"
    ),
    "security / authentication": (
        "How will users or clients authenticate? "
        "Is there role-based access control or other authorization logic?"
    ),
    "quality attributes": (
        "What are the performance and reliability requirements? "
        "For example: expected load, latency targets, uptime SLA, data retention."
    ),
    "acceptance criteria": (
        "What does 'done' look like for this project? "
        "List the key criteria that must be true for the system to be considered complete."
    ),
}

_MAX_QUESTIONS = 15
_COMPLETENESS_THRESHOLD = 0.75
_MIN_QUESTIONS_BEFORE_OFFER = 4


class InterviewEngine:
    def __init__(self, client: LLMClient, console: Console):
        self.client = client
        self.console = console
        self._file_context: str = ""   # contents of user-supplied reference files

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(
        self,
        idea: str,
        ir: SpecIR,
        resume: bool = False,
        context_files: list[tuple[str, str]] | None = None,
    ) -> SpecIR:
        """Drive the interview loop. Returns the populated SpecIR.

        context_files: list of (filename, content) pairs loaded from --file flags.
        When resume=True the initial idea extraction is skipped and the user
        is shown a brief context summary of what was already covered.
        """
        # Build the file context block injected into every LLM call.
        if context_files:
            self._file_context = _format_context_files(context_files)
            self._show_files_loaded(context_files)
        else:
            self._file_context = ""

        if resume and ir.interview_transcript:
            self._show_resume_context(ir)
        else:
            self.console.print(
                Panel(
                    "[bold]Starting requirements interview.[/bold]\n"
                    "Answer each question in plain language. "
                    "Type [bold cyan]done[/bold cyan] at any prompt to stop early.",
                    title="[bold green]Spec Foundry — Interview[/bold green]",
                    border_style="green",
                )
            )
            # Seed: process the initial idea (and any reference files) first.
            ir = self._extract_ir("Describe your project idea", idea, ir)
            ir.interview_transcript.append({"q": "Initial idea", "a": idea})
            self.console.print("[dim]Initial idea processed.[/dim]")

        question_count = 0

        while question_count < _MAX_QUESTIONS:
            completeness = ir.compute_completeness()
            missing = ir.missing_domains()

            # Offer to finish once threshold is met
            if completeness >= _COMPLETENESS_THRESHOLD and question_count >= _MIN_QUESTIONS_BEFORE_OFFER:
                self._show_ir_summary(ir)
                answer = click.prompt(
                    "\nSpec IR looks solid. Press Enter to proceed, or type more detail",
                    default="",
                    show_default=False,
                )
                if not answer.strip() or answer.strip().lower() in (
                    "done", "proceed", "finish", "continue", "yes", "y"
                ):
                    break
                # Treat anything they typed as additional context
                ir = self._extract_ir("Additional context", answer, ir)
                ir.interview_transcript.append({"q": "Additional context", "a": answer})
                break

            if not missing:
                break

            question = self._next_question(ir, missing)
            if not question:
                break

            self.console.print(f"\n[bold cyan]>>[/bold cyan] {question}")
            answer = click.prompt("  Answer", prompt_suffix=" ")

            if answer.strip().lower() in ("done", "skip", "finish", "exit", "quit", "q"):
                break
            if not answer.strip():
                continue

            ir = self._extract_ir(question, answer, ir)
            ir.interview_transcript.append({"q": question, "a": answer})
            question_count += 1

        ir.compute_completeness()
        return ir

    # ── Private helpers ────────────────────────────────────────────────────────

    def _next_question(self, ir: SpecIR, missing: list[str]) -> str | None:
        """Ask the LLM to pick the best next question given the current IR gaps."""
        if not missing:
            return None

        focus = missing[0]
        file_section = (
            f"\nReference files provided by user:\n{self._file_context}\n"
            if self._file_context else ""
        )
        prompt = (
            f"Current Spec IR:\n{ir.to_json()}\n"
            + file_section
            + f"\nDomains still needing information: {', '.join(missing)}\n"
            f"Priority domain: {focus}\n\n"
            f"Generate ONE specific, high-value question targeting: {focus}"
        )
        try:
            resp = self.client.generate(
                messages=[Message(role="user", content=prompt)],
                system=_INTERVIEWER_SYSTEM,
                max_tokens=256,
                temperature=0.4,
            )
            data = extract_json(resp)
            if isinstance(data, dict) and "question" in data:
                return data["question"]
        except Exception:
            pass

        return _FALLBACK_QUESTIONS.get(focus, f"Can you tell me more about {focus}?")

    def _extract_ir(self, question: str, answer: str, ir: SpecIR) -> SpecIR:
        """Call LLM to merge new Q&A (and any reference files) into the IR."""
        file_section = (
            f"\nReference files provided by user:\n{self._file_context}\n"
            if self._file_context else ""
        )
        prompt = (
            f"Current Spec IR:\n{ir.to_json()}\n"
            + file_section
            + f"\nInterview exchange:\n"
            f"Question: {question}\n"
            f"Answer: {answer}\n\n"
            "Extract ALL information from this answer and the reference files, "
            "then return the complete updated Spec IR as JSON."
        )
        try:
            resp = self.client.generate(
                messages=[Message(role="user", content=prompt)],
                system=_ANALYST_SYSTEM,
                max_tokens=4096,
                temperature=0.2,
            )
            data = extract_json(resp)
            if isinstance(data, dict):
                return SpecIR.from_dict(data)
        except Exception as exc:
            self.console.print(f"[yellow]Warning: IR update failed ({exc}), continuing.[/yellow]")
        return ir

    def _show_files_loaded(self, context_files: list[tuple[str, str]]) -> None:
        """Banner listing which reference files were loaded."""
        lines = [
            f"[cyan]{name}[/cyan]  [dim]({len(content):,} chars)[/dim]"
            for name, content in context_files
        ]
        self.console.print(
            Panel(
                "\n".join(lines),
                title="[bold]Reference files loaded[/bold]",
                border_style="dim",
            )
        )

    def _show_resume_context(self, ir: SpecIR) -> None:
        """Display a context recap when resuming a mid-interview session."""
        transcript = ir.interview_transcript
        last = transcript[-1] if transcript else {}
        last_q = last.get("q", "")
        last_a = last.get("a", "")

        # Work out which domains are already covered vs still missing
        all_domains = list(_FALLBACK_QUESTIONS.keys())
        missing = ir.missing_domains()
        covered = [d for d in all_domains if d not in missing]

        covered_str = ", ".join(covered) if covered else "nothing yet"
        missing_str = ", ".join(missing) if missing else "everything looks covered"

        body = (
            f"[bold]Resuming interview for:[/bold] "
            f"[cyan]{ir.product.name or '(unnamed project)'}[/cyan]\n\n"
            f"[bold]Covered so far:[/bold] {covered_str}\n"
            f"[bold]Still needed:[/bold]   {missing_str}\n"
        )
        if last_q:
            short_a = last_a[:80] + ("..." if len(last_a) > 80 else "")
            body += f'\n[dim]Last exchange — Q: "{last_q}"\n              A: "{short_a}"[/dim]'

        self.console.print(
            Panel(
                body,
                title="[bold yellow]Spec Foundry — Resuming Interview[/bold yellow]",
                border_style="yellow",
            )
        )
        suffix = ""
        if self._file_context:
            suffix = "  Reference files are included in every question.\n"
        self.console.print(
            f"[dim]Continuing from where we left off. {suffix}"
            "Type [bold cyan]done[/bold cyan] at any prompt to stop.[/dim]\n"
        )

    def _show_ir_summary(self, ir: SpecIR) -> None:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold]Project[/bold]", ir.product.name or "(unnamed)")
        summary = ir.product.summary or ""
        table.add_row("[bold]Summary[/bold]", summary[:100] + ("…" if len(summary) > 100 else ""))
        table.add_row("[bold]Users[/bold]", ", ".join(u.role for u in ir.users) or "—")
        table.add_row("[bold]Workflows[/bold]", str(len(ir.workflows)))
        table.add_row("[bold]Entities[/bold]", str(len(ir.entities)))
        table.add_row("[bold]APIs[/bold]", str(len(ir.apis)))
        table.add_row("[bold]Background Jobs[/bold]", str(len(ir.background_jobs)))
        color = "green" if ir.completeness >= 0.8 else "yellow" if ir.completeness >= 0.6 else "red"
        table.add_row("[bold]Completeness[/bold]", f"[{color}]{ir.completeness:.0%}[/{color}]")
        self.console.print(Panel(table, title="[bold]Spec IR Summary[/bold]", border_style="blue"))


# ── Module-level helpers ───────────────────────────────────────────────────────

def _format_context_files(files: list[tuple[str, str]]) -> str:
    """Format reference files into a single block for LLM injection.

    Each file is truncated at 6 000 chars to keep prompts manageable.
    """
    parts = []
    for name, content in files:
        if len(content) > 6000:
            content = content[:6000] + f"\n...[truncated — {len(content):,} chars total]"
        parts.append(f"--- {name} ---\n{content}")
    return "\n\n".join(parts)
