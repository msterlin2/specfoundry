"""Spec Composer — generates each markdown spec file from the IR.

Spec files are generated in parallel using a thread pool.
IR writes are serialised (reads here are read-only).
"""
from __future__ import annotations

import concurrent.futures
from typing import Callable

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..ir import SpecIR
from ..llm.base import LLMClient, Message

# ── Prompts ───────────────────────────────────────────────────────────────────

_SPEC_WRITER_SYSTEM = """\
You are an expert software architect writing a specification document for a coding agent.

Rules:
1. Use normative language: MUST, SHALL, SHOULD, MAY.
2. Be precise and unambiguous. Eliminate hidden assumptions.
3. Cover ONLY the responsibility assigned to this file — no duplication from other files.
4. Every feature MUST have a testable acceptance criterion.
5. Every data entity MUST define fields, invariants, lifecycle, and relationships.
6. Every API endpoint MUST define method, path, auth, request schema, response schema, and error conditions.
7. Every workflow MUST define actor, trigger, steps, success result, failure modes, and acceptance tests.
8. Write in Markdown. Use headers, tables, and code blocks appropriately.
"""

_SPEC_TEMPLATE = """\
Write the "{title}" specification file.

This file is responsible for: {responsibility}

Do NOT duplicate content from these other files (which cover their own areas):
{sibling_summary}

Spec IR (source of truth):
{ir_json}

Structure the document with EXACTLY these sections:
# {title}

## Purpose
## Scope
## Non-Goals
## Design Principles
## Concepts and Domain Entities
## Flows and Algorithms
## Interfaces and Schemas
## Failure Handling
## Security and Permissions
## Observability
## Definition of Done

The "Definition of Done" section MUST be a checklist (- [ ] items) of
concrete, testable criteria an implementation must satisfy.
"""


class SpecComposer:
    def __init__(self, client: LLMClient, console: Console):
        self.client = client
        self.console = console

    def run(self, ir: SpecIR, spec_plan: list[dict]) -> dict[str, str]:
        """Generate all spec files in parallel. Returns {filename: content}."""
        outputs: dict[str, str] = {}
        sibling_summary = _make_sibling_summary(spec_plan)

        tasks = [
            (entry["filename"], entry["title"], entry["responsibility"])
            for entry in spec_plan
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
            transient=False,
        ) as progress:
            overall = progress.add_task(
                "[cyan]Composing spec files…", total=len(tasks)
            )

            def generate_one(args: tuple[str, str, str]) -> tuple[str, str]:
                filename, title, responsibility = args
                progress.update(overall, description=f"[cyan]Writing {filename}…")
                content = self._generate_file(ir, title, responsibility, sibling_summary)
                progress.advance(overall)
                return filename, content

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(generate_one, t): t for t in tasks}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        filename, content = future.result()
                        outputs[filename] = content
                    except Exception as exc:
                        filename = futures[future][0]
                        self.console.print(
                            f"[red]Error generating {filename}: {exc}[/red]"
                        )
                        outputs[filename] = f"# {filename}\n\n_Generation failed: {exc}_\n"

        return outputs

    # ── Private ────────────────────────────────────────────────────────────────

    def _generate_file(
        self,
        ir: SpecIR,
        title: str,
        responsibility: str,
        sibling_summary: str,
    ) -> str:
        prompt = _SPEC_TEMPLATE.format(
            title=title,
            responsibility=responsibility,
            sibling_summary=sibling_summary,
            ir_json=ir.to_json(),
        )
        return self.client.generate(
            messages=[Message(role="user", content=prompt)],
            system=_SPEC_WRITER_SYSTEM,
            max_tokens=8096,
            temperature=0.3,
        )


def _make_sibling_summary(spec_plan: list[dict]) -> str:
    lines = [f"- {e['filename']}: {e['responsibility']}" for e in spec_plan]
    return "\n".join(lines)
