"""Orchestrator — drives the full pipeline through the state machine.

State transitions:
  INIT → INTERVIEW → IR_READY → PLANNED → COMPOSED → VALIDATED → DOT_GENERATED → COMPLETE

Human-in-loop gates:
  • Before PLANNED  : review IR, approve / modify
  • Before COMPLETE : review spec pack, approve / request changes
"""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .checkpoint import Checkpoint, CheckpointManager
from .ir import SpecIR
from .llm.base import LLMClient
from .phases.interview import InterviewEngine
from .phases.planner import SpecPlanner
from .phases.composer import SpecComposer
from .phases.consistency_checker import ConsistencyChecker
from .phases.dot_generator import DotGenerator
from .phases.handoff import HandoffGenerator
from .repo_manager import RepoManager
from .state_machine import State, transition


class Orchestrator:
    def __init__(
        self,
        client: LLMClient,
        output_dir: Path,
        console: Console,
        human_gates: bool = True,
    ):
        self.client = client
        self.output_dir = output_dir
        self.console = console
        self.human_gates = human_gates
        self.checkpoint_mgr = CheckpointManager(output_dir)

        # Phases
        self.interview = InterviewEngine(client, console)
        self.planner = SpecPlanner(client, console)
        self.composer = SpecComposer(client, console)
        self.checker = ConsistencyChecker(client, console)
        self.dot_gen = DotGenerator(console)
        self.handoff = HandoffGenerator(client, console)
        self.repo = RepoManager(output_dir, console)

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(
        self,
        idea: str,
        context_files: list[tuple[str, str]] | None = None,
    ) -> None:
        """Run from INIT (or resume from checkpoint if one exists)."""
        if self.checkpoint_mgr.exists():
            try:
                cp = self.checkpoint_mgr.load()
            except Exception as exc:
                self.console.print(f"[red]Failed to load checkpoint: {exc}[/red]")
                if not click.confirm("Start fresh instead?", default=True):
                    raise SystemExit(1)
                cp = Checkpoint(state=State.INIT, ir=SpecIR(), idea=idea)
            else:
                # Prefer the saved idea; fall back to the CLI argument if not stored.
                if not cp.idea and idea:
                    cp.idea = idea
                self.console.print(
                    f"[yellow]Resuming from checkpoint:[/yellow] {cp.state.value}"
                )
        else:
            cp = Checkpoint(
                state=State.INIT,
                ir=SpecIR(),
                idea=idea,
            )

        try:
            cp = self._drive(cp, context_files=context_files or [])
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted — checkpoint saved.[/yellow]")
            self.checkpoint_mgr.save(cp)
            raise SystemExit(0)

    # ── Pipeline driver ────────────────────────────────────────────────────────

    def _drive(
        self, cp: Checkpoint, context_files: list[tuple[str, str]] | None = None
    ) -> Checkpoint:
        # ── INIT → INTERVIEW ──────────────────────────────────────────────────
        if cp.state == State.INIT:
            cp.state = transition(cp.state, State.INTERVIEW)
            self._save(cp)

        # ── INTERVIEW → IR_READY ──────────────────────────────────────────────
        if cp.state == State.INTERVIEW:
            # Guard: if the session was interrupted before the idea was captured,
            # prompt for it now rather than sending an empty string to the LLM.
            if not cp.idea and not cp.ir.interview_transcript:
                cp.idea = click.prompt("What is your project idea?")
                self._save(cp)

            # Resume mid-interview when the transcript already has entries.
            resuming = bool(cp.ir.interview_transcript)
            cp.ir = self.interview.run(
                cp.idea, cp.ir, resume=resuming, context_files=context_files or []
            )
            cp.state = transition(cp.state, State.IR_READY)
            self._save(cp)

        # ── Gate 1: review IR ─────────────────────────────────────────────────
        if cp.state == State.IR_READY:
            if self.human_gates:
                cp.ir = self._gate_review_ir(cp.ir)
            cp.spec_plan = self.planner.run(cp.ir)
            cp.state = transition(cp.state, State.PLANNED)
            self._save(cp)

        # ── PLANNED → COMPOSED ────────────────────────────────────────────────
        if cp.state == State.PLANNED:
            cp.outputs = self.composer.run(cp.ir, cp.spec_plan)
            cp.state = transition(cp.state, State.COMPOSED)
            self._save(cp)

        # ── COMPOSED → VALIDATED ──────────────────────────────────────────────
        if cp.state == State.COMPOSED:
            report = self.checker.run(cp.ir, cp.outputs)
            # If critical issues found, offer to fix before continuing
            if report.get("critical") and self.human_gates:
                self._gate_critical_issues(report)
            cp.state = transition(cp.state, State.VALIDATED)
            self._save(cp)

        # ── VALIDATED → DOT_GENERATED ─────────────────────────────────────────
        if cp.state == State.VALIDATED:
            dot = self.dot_gen.run(cp.ir)
            cp.outputs["system.dot"] = dot
            cp.state = transition(cp.state, State.DOT_GENERATED)
            self._save(cp)

        # ── Gate 2: review spec pack ──────────────────────────────────────────
        if cp.state == State.DOT_GENERATED:
            if self.human_gates:
                self._gate_review_specs(cp)
            start_here, build_prompt = self.handoff.run(cp.ir, cp.outputs)
            dot = cp.outputs.pop("system.dot")
            self.repo.write_all(cp.ir, cp.outputs, dot, start_here, build_prompt)
            cp.state = transition(cp.state, State.COMPLETE)
            self._save(cp)

        self.console.print(
            Panel(
                f"[bold green]OK Spec pack written to:[/bold green] {self.output_dir}",
                border_style="green",
            )
        )
        return cp

    # ── Human-in-loop gates ────────────────────────────────────────────────────

    def _gate_review_ir(self, ir: SpecIR) -> SpecIR:
        """Gate 1: show IR, let user approve or add clarification."""
        self.console.print(
            Panel(
                Syntax(ir.to_yaml(), "yaml", theme="monokai", word_wrap=True),
                title="[bold]Spec IR — review before spec generation[/bold]",
                border_style="blue",
            )
        )
        while True:
            choice = click.prompt(
                "\n[A]pprove and continue  [C]larify / add more info",
                default="A",
            ).strip().upper()

            if choice in ("A", ""):
                break
            elif choice == "C":
                extra = click.prompt("What would you like to add or change?")
                if extra.strip():
                    from .phases.interview import InterviewEngine
                    engine = InterviewEngine(self.client, self.console)
                    ir = engine._extract_ir("User clarification", extra, ir)
                    ir.compute_completeness()
                    self.console.print("[green]IR updated.[/green]")
                break
            else:
                self.console.print("Please enter A or C.")
        return ir

    def _gate_critical_issues(self, report: dict) -> None:
        """Warn about critical consistency issues. User can abort or continue."""
        n = len(report.get("critical", []))
        self.console.print(
            f"\n[red bold]{n} critical consistency issue(s) found.[/red bold]"
        )
        cont = click.confirm("Continue anyway?", default=False)
        if not cont:
            raise SystemExit(1)

    def _gate_review_specs(self, cp: Checkpoint) -> None:
        """Gate 2: show generated file list, allow user to regenerate specific files."""
        self.console.print("\n[bold]Generated spec files:[/bold]")
        for filename in sorted(cp.outputs.keys()):
            self.console.print(f"  [cyan]-[/cyan] {filename}")

        regen = click.prompt(
            "\nPress Enter to generate handoff files, or name a file to regenerate",
            default="",
            show_default=False,
        ).strip()

        if regen:
            # Find matching entry in spec_plan
            entry = next(
                (e for e in cp.spec_plan if e["filename"] == regen), None
            )
            if entry:
                self.console.print(f"[bold]Regenerating {regen}…[/bold]")
                from .phases.composer import SpecComposer, _make_sibling_summary
                composer = SpecComposer(self.client, self.console)
                cp.outputs[regen] = composer._generate_file(
                    cp.ir,
                    entry["title"],
                    entry["responsibility"],
                    _make_sibling_summary(cp.spec_plan),
                )
                self.console.print(f"[green]OK {regen} regenerated.[/green]")
            else:
                self.console.print(f"[yellow]File {regen!r} not in plan, skipping.[/yellow]")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _save(self, cp: Checkpoint) -> None:
        self.checkpoint_mgr.save(cp)
