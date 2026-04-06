"""Spec Foundry CLI entry point."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# Load .env from the current working directory (or any parent) before
# anything reads os.environ, so ANTHROPIC_API_KEY etc. are available.
load_dotenv()

from . import __version__
from .llm.base import make_client
from .orchestrator import Orchestrator
from .utils import slugify

# Default models per provider
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "local": "llama3",
}

console = Console()


@click.group()
@click.version_option(__version__, prog_name="specfoundry")
def main():
    """Spec Foundry — turn ideas into agent-executable specification packs."""


# ── specfoundry new ───────────────────────────────────────────────────────────

@main.command()
@click.argument("idea", required=False)
@click.option(
    "--provider", "-p",
    default="anthropic",
    type=click.Choice(["anthropic", "openai", "local"], case_sensitive=False),
    show_default=True,
    help="LLM provider.",
)
@click.option(
    "--model", "-m",
    default=None,
    help="Model name. Defaults: anthropic=claude-sonnet-4-6, openai=gpt-4o, local=llama3.",
)
@click.option(
    "--api-key", "-k",
    default=None,
    envvar=["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
    help="API key (reads ANTHROPIC_API_KEY / OPENAI_API_KEY env vars automatically).",
)
@click.option(
    "--output", "-o",
    default=None,
    help="Output directory. Default: ./output/<project-slug>/",
)
@click.option(
    "--no-gates",
    is_flag=True,
    default=False,
    help="Skip human-in-loop approval gates (fully automated run).",
)
@click.option(
    "--file", "-f", "context_files",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Reference file(s) included as context during the interview "
         "(may be specified multiple times).",
)
def new(idea, provider, model, api_key, output, no_gates, context_files):
    """Start a new spec project from IDEA (a one-sentence description).

    If IDEA is omitted you will be prompted for it.

    Examples:\n
      specfoundry new "A pricing database for financial market data"\n
      specfoundry new --provider openai --model gpt-4o "My SaaS app"\n
      specfoundry new "My project" --file requirements.md --file schema.txt\n
      specfoundry new --no-gates "My project"
    """
    _print_banner()

    if not idea:
        idea = click.prompt("Describe your project idea")

    resolved_model = model or _DEFAULT_MODELS[provider]
    resolved_api_key = _resolve_api_key(provider, api_key)

    try:
        client = make_client(provider, resolved_model, resolved_api_key)
    except Exception as exc:
        console.print(f"[red]Error creating LLM client: {exc}[/red]")
        sys.exit(1)

    output_dir = _resolve_output_dir(output, idea)
    console.print(f"[dim]Provider:[/dim]  {provider} / {resolved_model}")
    console.print(f"[dim]Output:  [/dim]  {output_dir}\n")

    loaded = _load_context_files(context_files)

    orchestrator = Orchestrator(
        client=client,
        output_dir=output_dir,
        console=console,
        human_gates=not no_gates,
    )
    orchestrator.run(idea, context_files=loaded)


# ── specfoundry resume ────────────────────────────────────────────────────────

@main.command()
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--provider", "-p", default="anthropic",
              type=click.Choice(["anthropic", "openai", "local"], case_sensitive=False))
@click.option("--model", "-m", default=None)
@click.option("--api-key", "-k", default=None)
@click.option("--no-gates", is_flag=True, default=False)
@click.option(
    "--file", "-f", "context_files",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Additional reference file(s) to include as context (may be specified multiple times).",
)
def resume(output_dir, provider, model, api_key, no_gates, context_files):
    """Resume a previously interrupted spec run from OUTPUT_DIR."""
    _print_banner()

    cp_file = Path(output_dir) / ".specfoundry" / "checkpoint.json"
    if not cp_file.exists():
        console.print(f"[red]No checkpoint found in {output_dir}[/red]")
        sys.exit(1)

    resolved_model = model or _DEFAULT_MODELS[provider]
    resolved_api_key = _resolve_api_key(provider, api_key)

    try:
        client = make_client(provider, resolved_model, resolved_api_key)
    except Exception as exc:
        console.print(f"[red]Error creating LLM client: {exc}[/red]")
        sys.exit(1)

    loaded = _load_context_files(context_files)

    orchestrator = Orchestrator(
        client=client,
        output_dir=Path(output_dir),
        console=console,
        human_gates=not no_gates,
    )
    orchestrator.run(idea="", context_files=loaded)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    console.print(
        Panel(
            f"[bold cyan]Spec Foundry[/bold cyan]  [dim]v{__version__}[/dim]\n"
            "Autonomous specification generator for LLM-driven development",
            border_style="cyan",
        )
    )


def _resolve_output_dir(output: str | None, idea: str) -> Path:
    if output:
        return Path(output)
    # Derive a slug from the first few words of the idea
    slug = slugify(idea[:60])
    return Path("output") / slug


def _load_context_files(paths: tuple[str, ...]) -> list[tuple[str, str]]:
    """Read each file path and return (filename, content) pairs."""
    result: list[tuple[str, str]] = []
    for p in paths:
        path = Path(p)
        try:
            result.append((path.name, path.read_text(encoding="utf-8")))
        except Exception as exc:
            console.print(f"[yellow]Warning: could not read {p}: {exc}[/yellow]")
    return result


def _resolve_api_key(provider: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "local": None,
    }
    env_var = env_map.get(provider)
    return os.environ.get(env_var) if env_var else None
