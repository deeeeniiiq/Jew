# Clew Codex Context

This file is the repository-specific context for Codex-style coding agents working in Clew.

The global hardmode contract still applies. This file adds **project truth**, **architecture boundaries**, and **workflow expectations** specific to Clew.

## Read first

Before changing the product, read:

- [Shared agent context](docs/agents/PROJECT_CONTEXT.md)
- [Agent workflow](docs/agents/WORKFLOW.md)
- [Architecture](docs/ARCHITECTURE.md)
- [ADR index](docs/adr/README.md)

## What Clew is

Product identity lives in [`docs/agents/PROJECT_CONTEXT.md`](docs/agents/PROJECT_CONTEXT.md#product-identity). Read it before making product-shape changes.

## Core product invariants

These are non-negotiable:

1. The graph is the center of truth.
2. AI must not silently mutate the graph.
3. Accepted graph changes must stay reversible through snapshots.
4. The UI must remain graph-first instead of dashboard-first.
5. Local `main` and hosted product surfaces stay separate in emphasis.

If a change weakens any of those, it is a regression even if it looks convenient.

## Engineering stance

- Prefer explicit boundaries over fast hacks.
- Keep model I/O inside visible contracts.
- Prefer fail-closed over fake success.
- Do not add hidden semantic routing or silent fallback behavior.
- Build for long-term clarity, not one seed graph or one happy-path demo.

## Frontend stance

- The graph is the main surface, not decoration.
- Overlays must support the graph instead of replacing it.
- Avoid admin-dashboard vibes unless the user benefit is obvious.
- Portfolio-quality UI matters because product perception matters here.

## Backend stance

- The repository and snapshot layer are first-class.
- Proposal validation matters more than “the model probably meant well”.
- If the model or a tool call cannot satisfy a contract, reject explicitly.
- Side effects should remain legible through routes, repository, contracts, and traces.

## Local commands

Start local dev:

```bash
./scripts/dev.sh
```

Stop listeners:

```bash
./scripts/stop_dev.sh
```

Reset local DB:

```bash
./scripts/reset_db.sh
```

Verify frontend:

```bash
cd frontend && npm run typecheck && npm run build
```

Verify backend:

```bash
PYTHONPATH=backend ./.venv/bin/python -m unittest discover -s backend/tests -v
```

## If you are working on docs

There are two documentation layers:

- `docs/site_faq/` = product-facing docs source
- `docs/` = engineering and repo docs

Do not mix them casually.

## If you are working on agent behavior

Treat the selected model as the decision engine.

Fix bad behavior by improving:

- role
- context pack
- examples
- JSON contract
- validation boundary

Do **not** fix bad behavior with:

- keyword routers
- hand-written semantic overrides
- hidden fallback models
- case-specific prompt hacks disguised as architecture

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
