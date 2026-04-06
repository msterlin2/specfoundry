"""Repository Manager — writes all spec files to the output directory atomically."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.tree import Tree

from .ir import SpecIR


class RepoManager:
    def __init__(self, output_dir: Path, console: Console):
        self.output_dir = output_dir
        self.console = console

    def write_all(
        self,
        ir: SpecIR,
        outputs: dict[str, str],
        dot: str,
        start_here: str,
        build_prompt: str,
    ) -> None:
        """Write every artifact to output_dir. Writes are atomic (tmp → rename)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Spec files
        for filename, content in outputs.items():
            self._write(self.output_dir / filename, content)

        # Handoff files
        self._write(self.output_dir / "START-HERE.md", start_here)
        self._write(self.output_dir / "BUILD-PROMPT.md", build_prompt)

        # DOT graph
        self._write(self.output_dir / "system.dot", dot)

        # Spec IR in both formats
        self._write(self.output_dir / "spec-ir.json", ir.to_json())
        self._write(self.output_dir / "spec-ir.yaml", ir.to_yaml())

        self._show_tree(outputs, dot)

    def _write(self, path: Path, content: str) -> None:
        """Atomic write: write to .tmp then rename."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    def _show_tree(self, outputs: dict[str, str], dot: str) -> None:
        tree = Tree(f"[bold cyan]{self.output_dir}[/bold cyan]")
        for filename in sorted(outputs.keys()):
            tree.add(f"[green]{filename}[/green]")
        tree.add("[green]START-HERE.md[/green]")
        tree.add("[green]BUILD-PROMPT.md[/green]")
        tree.add("[green]system.dot[/green]")
        tree.add("[dim]spec-ir.json[/dim]")
        tree.add("[dim]spec-ir.yaml[/dim]")
        tree.add("[dim].specfoundry/checkpoint.json[/dim]")
        self.console.print(tree)
