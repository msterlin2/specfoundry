"""Handoff Generator — produces START-HERE.md and BUILD-PROMPT.md."""
from __future__ import annotations

from rich.console import Console

from ..ir import SpecIR
from ..llm.base import LLMClient, Message

_START_HERE_SYSTEM = """\
You are writing a START-HERE.md guide for a coding agent who will implement a software project.
The guide should be clear, concise, and tell the agent exactly how to approach the spec pack.
Write in Markdown. Be direct and practical.
"""

_START_HERE_PROMPT = """\
Write a START-HERE.md for the following project spec pack.

Project: {name}
Summary: {summary}
Spec files included:
{file_list}

The guide should cover:
1. What this spec pack is and what the project does (2-3 sentences)
2. How to read the files (suggested order)
3. Key architectural decisions already made
4. Implementation approach (phased, what to build first)
5. How to handle ambiguity (surface it, don't assume)
6. The definition of done for the whole project
"""

_BUILD_PROMPT_SYSTEM = """\
You are writing a BUILD-PROMPT.md that will be given verbatim to a coding agent.
It must be unambiguous, normative, and leave no room for guessing.
Use MUST/SHALL/SHOULD. Write in Markdown.
"""

_BUILD_PROMPT_PROMPT = """\
Write a BUILD-PROMPT.md for this project that a coding agent will use as its primary directive.

Project: {name}
Summary: {summary}
Tech stack: {tech_stack}
Spec files: {file_list}
Acceptance criteria:
{acceptance_criteria}

The BUILD-PROMPT.md MUST:
1. Instruct the agent to read ALL spec files before writing any code
2. Specify the implementation order (data model → storage → workflows → APIs → frontend → jobs)
3. State that specs are canonical and the agent MUST NOT improvise missing requirements
4. Require the agent to validate each component against its Definition of Done
5. Require the agent to use system.dot as the architecture reference
6. Require the agent to log all unresolved ambiguities rather than guessing
7. Include the full acceptance criteria as a checklist
"""


class HandoffGenerator:
    def __init__(self, client: LLMClient, console: Console):
        self.client = client
        self.console = console

    def run(self, ir: SpecIR, outputs: dict[str, str]) -> tuple[str, str]:
        """Generate START-HERE.md and BUILD-PROMPT.md. Returns (start_here, build_prompt)."""
        file_list = "\n".join(f"- {f}" for f in sorted(outputs.keys()))
        ac = "\n".join(f"- {c}" for c in ir.acceptance_criteria) or "- (see spec files)"

        tech_stack = (
            f"{ir.deployment.backend_framework or 'unspecified backend'} / "
            f"{ir.deployment.frontend_framework or 'no frontend'} / "
            f"{ir.deployment.database or 'unspecified database'}"
        )

        self.console.print("[bold]Generating START-HERE.md…[/bold]")
        start_here = self.client.generate(
            messages=[Message(
                role="user",
                content=_START_HERE_PROMPT.format(
                    name=ir.product.name,
                    summary=ir.product.summary,
                    file_list=file_list,
                ),
            )],
            system=_START_HERE_SYSTEM,
            max_tokens=2048,
            temperature=0.3,
        )

        self.console.print("[bold]Generating BUILD-PROMPT.md…[/bold]")
        build_prompt = self.client.generate(
            messages=[Message(
                role="user",
                content=_BUILD_PROMPT_PROMPT.format(
                    name=ir.product.name,
                    summary=ir.product.summary,
                    tech_stack=tech_stack,
                    file_list=file_list,
                    acceptance_criteria=ac,
                ),
            )],
            system=_BUILD_PROMPT_SYSTEM,
            max_tokens=2048,
            temperature=0.3,
        )

        self.console.print("[green]OK[/green] Handoff files generated")
        return start_here, build_prompt
