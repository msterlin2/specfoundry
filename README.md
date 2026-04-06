# Spec Foundry

Turn a one-sentence product idea into a complete, agent-executable specification pack — ready to hand to Claude Code, Codex, or any other autonomous coding agent.

Spec Foundry runs a structured requirements interview, builds a machine-readable Spec IR (intermediate representation), generates a multi-file markdown spec pack, validates cross-spec consistency, produces a DOT architecture graph, and writes a ready-to-use build prompt.

Inspired by software factories as described by https://factory.strongdm.ai/. This hopefully helps with createing the spec and .dot file to feed into the factory.

---

## How it works

```
Your idea
   │
   ▼
Interactive interview          ← LLM asks targeted questions per domain
   │                              (users, workflows, entities, APIs, deployment, …)
   ▼
Spec IR  (spec-ir.json)        ← canonical structured representation
   │
   ├──▶ Spec planner           ← decides which files to generate
   │
   ├──▶ Spec composer          ← writes each markdown file in parallel
   │         00-product-overview.md
   │         01-system-architecture.md
   │         02-domain-model.md
   │         03-user-workflows.md
   │         04-api-contracts.md
   │         05-data-storage.md
   │         06-frontend-ux.md          (if UI)
   │         07-background-jobs.md      (if async jobs)
   │         08-security-and-auth.md
   │         09-observability-and-ops.md
   │         10-testing-and-acceptance.md
   │         11-agent-loop.md           (if AI-heavy)
   │         … up to 14 files
   │
   ├──▶ Consistency checker    ← finds undefined entities, API mismatches, gaps
   │
   ├──▶ DOT generator          ← system.dot (actors, entities, workflows, APIs)
   │
   └──▶ Handoff generator      ← START-HERE.md + BUILD-PROMPT.md
```

Every stage is checkpointed. Interrupt at any point and resume exactly where you left off.

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/yourname/specfoundry
cd specfoundry
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -e .
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # default provider
# or
export OPENAI_API_KEY=sk-...
```

---

## Quick start

```bash
specfoundry new "A pricing database for financial market data"
```

Spec Foundry will ask you 5–10 targeted questions (users, workflows, entities, APIs, deployment, security, acceptance criteria), then generate a full spec pack in `./output/a-pricing-database-for-financial-market-data/`.

---

## Usage

### `specfoundry new`

Start a new project from a one-sentence idea.

```bash
specfoundry new [IDEA] [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--provider` | `-p` | `anthropic` | LLM provider: `anthropic`, `openai`, `local` |
| `--model` | `-m` | `claude-sonnet-4-6` | Model name |
| `--api-key` | `-k` | env var | API key (falls back to `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) |
| `--output` | `-o` | `./output/<slug>/` | Output directory |
| `--file` | `-f` | — | Reference file(s) to include as interview context (repeatable) |
| `--no-gates` | | — | Skip human approval gates for fully automated runs |

**Examples:**

```bash
# Basic — prompted for idea if omitted
specfoundry new

# Idea as argument
specfoundry new "A multi-tenant SaaS invoicing platform"

# With reference files (field definitions, existing requirements, schemas, etc.)
specfoundry new "Customer loyalty programme" \
  --file requirements.md \
  --file db-schema.sql

# Use OpenAI GPT-4o instead
specfoundry new "My app" --provider openai --model gpt-4o

# Use a local Ollama model
specfoundry new "My app" --provider local --model llama3

# Fully automated (no prompts) — useful in CI or scripts
specfoundry new "Inventory management system" \
  --no-gates \
  --output ./specs/inventory
```

### `specfoundry resume`

Resume a run that was interrupted (Ctrl-C, crash, network error, etc.).

```bash
specfoundry resume OUTPUT_DIR [OPTIONS]
```

Accepts the same `--provider`, `--model`, `--api-key`, `--no-gates`, and `--file` options as `new`.

```bash
# Resume from the last checkpoint
specfoundry resume ./output/a-pricing-database-for-financial-market-data

# Resume and supply additional reference files
specfoundry resume ./output/my-project --file updated-schema.md
```

The run continues from the exact phase it was in — mid-interview resumes show a recap of what was covered and what is still needed.

---

## Reference files (`--file`)

You can point Spec Foundry at any text file — markdown, plain text, CSV, SQL schema, OpenAPI YAML, existing requirements docs — and its contents will be included as context in every LLM call during the interview. This means the analyst role can extract structured requirements directly from your files rather than asking you to re-type them.

```bash
# Single file
specfoundry new "Order management system" --file existing-requirements.md

# Multiple files
specfoundry new "Analytics platform" \
  --file product-brief.md \
  --file data-dictionary.csv \
  --file api-sketch.yaml
```

Files over 6,000 characters are automatically truncated with a note. The extracted information is merged into the Spec IR, so it persists through checkpoints even if you do not re-supply the files on resume.

---

## Output structure

```
output/my-project/
├── 00-product-overview.md
├── 01-system-architecture.md
├── 02-domain-model.md
├── 03-user-workflows.md
├── 04-api-contracts.md
├── 05-data-storage.md
├── 08-security-and-auth.md
├── 09-observability-and-ops.md
├── 10-testing-and-acceptance.md
├── system.dot              ← Graphviz architecture graph
├── spec-ir.json            ← canonical intermediate representation
├── spec-ir.yaml            ← same, YAML format
├── START-HERE.md           ← reading guide for the coding agent
├── BUILD-PROMPT.md         ← drop this into Claude Code / Codex
└── .specfoundry/
    └── checkpoint.json     ← resume state
```

### Handing off to a coding agent

```bash
# Using Claude Code
cd output/my-project
claude "$(cat BUILD-PROMPT.md)"

# Or paste BUILD-PROMPT.md contents into any chat-based coding assistant
```

### Viewing the architecture graph

```bash
# Render with Graphviz
dot -Tpng system.dot -o system.png && open system.png

# Or use any online Graphviz renderer (paste system.dot contents)
```

---

## Spec file structure

Every generated spec file follows the same template, written for coding-agent consumption:

1. **Purpose** — why this file exists
2. **Scope** — what it covers
3. **Non-Goals** — explicit exclusions
4. **Design Principles** — normative constraints (MUST / SHALL / SHOULD)
5. **Concepts and Domain Entities** — types, fields, invariants
6. **Flows and Algorithms** — step-by-step behaviour
7. **Interfaces and Schemas** — API contracts, data shapes
8. **Failure Handling** — error paths, retries, timeouts
9. **Security and Permissions** — auth, authorization, data sensitivity
10. **Observability** — logging, metrics, alerting
11. **Definition of Done** — testable checklist the implementation must satisfy

---

## Providers and models

| Provider | Default model | Env var |
|----------|--------------|---------|
| `anthropic` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| `local` | `llama3` | — (Ollama at `http://localhost:11434`) |

Override the model with `--model`:

```bash
specfoundry new "My project" --provider anthropic --model claude-opus-4-6
specfoundry new "My project" --provider openai --model gpt-4-turbo
specfoundry new "My project" --provider local --model mistral
```

---

## Human-in-loop gates

By default, Spec Foundry pauses twice for human review:

1. **After the interview** — shows the full Spec IR in YAML. You can approve, or type clarifications that get merged back into the IR before spec generation begins.
2. **After spec generation** — shows the list of generated files. You can approve, or name a specific file to regenerate before the handoff files are written.

Skip both gates for scripted / CI use with `--no-gates`.

---

## Resuming and checkpoints

A checkpoint is saved after every phase transition. If the run is interrupted for any reason:

```bash
specfoundry resume ./output/my-project
```

The tool picks up from the last completed phase. Mid-interview resumes display a summary:

```
Resuming Interview for: PriceDB
Covered so far:  product overview, user roles, data model
Still needed:    deployment / infrastructure, security, acceptance criteria

Last exchange — Q: "What are the key data entities?"
              A: "PriceRecord, Source, ImportJob..."
```

---

## Architecture

```
specfoundry/
├── cli.py                      Click entry point (new, resume)
├── orchestrator.py             Pipeline driver + human gates
├── state_machine.py            INIT → INTERVIEW → IR_READY → … → COMPLETE
├── ir.py                       SpecIR dataclasses + JSON/YAML serialisation
├── checkpoint.py               Atomic checkpoint save/load
├── repo_manager.py             Atomic file writes to output directory
├── utils.py                    JSON extraction, slugify
├── llm/
│   ├── base.py                 LLMClient interface + make_client factory
│   ├── anthropic_client.py     Retry + backoff + streaming
│   ├── openai_client.py
│   └── local_client.py         Ollama HTTP adapter
└── phases/
    ├── interview.py            Structured Q&A, domain gap detection
    ├── planner.py              Spec file plan (deterministic + LLM refinement)
    ├── composer.py             Parallel spec file generation
    ├── consistency_checker.py  Cross-spec LLM audit
    ├── dot_generator.py        Deterministic DOT graph from IR
    └── handoff.py              START-HERE.md + BUILD-PROMPT.md
```

---

## License

MIT
=======
# specfoundry
Used to turn ideas into LLM consumable specs using structured interactive questioning.
>>>>>>> 814290e1ba7f3a3f59d0096bbc0fa24e7dca547f
