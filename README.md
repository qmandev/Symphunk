# Symphunk

> **One conductor, many agents, one Splunk.**

Symphunk is an agentic AI operations layer for Splunk, built for the [Splunk Agentic Ops Hackathon](https://splunk.devpost.com). An orchestrator polls Splunk for incidents, dispatches specialized agents that investigate and correlate via the Splunk MCP Server, and writes proof-of-work evidence back into Splunk dashboards before auto-resolving or escalating — all under one governance model.

**Thesis**: agentic ops should *shrink* the tool count and the toil, not grow them. One orchestrator, one tool layer, one Splunk.

---

## Architecture

```
Saved-search alert ──► KV "symphunk_incidents" (status=New)
                                  │ poll
                        ┌─────────▼──────────┐
                        │    Orchestrator     │
                        │ poller · dispatcher │
                        │   state machine     │
                        └─────────┬──────────┘
                                  │ one task / incident
                        ┌─────────▼──────────┐
                        │      ObsAgent       │
                        │  load skills        │
                        │  → SPL via MCP      │
                        │  → correlate        │
                        │  → evidence package │
                        └───┬─────────────┬───┘
              read: MCP splunk_/saia_    write: KV + summary index
                        ▼                     ▼
               Splunk Enterprise        Proof-of-work
                (Docker, local)           Dashboard
```

The agent lives in its own **Reasoning/Agentic Tier** — an external client of Splunk, never co-located on indexers or search heads. All writes go through REST 8089; all reads go through the Splunk MCP Server.

**Self-observability (stretch)**: the agent emits OTel traces about its own reasoning via HEC into Splunk Observability Cloud's AI Agent Monitoring.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Docker Desktop | 28+ |
| Python | 3.11+ |
| [uv](https://docs.astral.sh/uv/) | latest |
| Anthropic API key | — |
| Splunk.com account | for Splunkbase app installs |

---

## Quick Start

### 1. Start Splunk

```bash
open -a Docker   # start Docker Desktop first

docker compose -f infra/docker-compose.yml up -d

# wait ~2 min, then check:
docker compose -f infra/docker-compose.yml ps   # Status: healthy
```

Splunk Web: http://localhost:8000 — login `admin` / your `SPLUNK_PASSWORD`.

### 2. Install Splunk apps (one-time)

Via Splunk Web → Apps → Find More Apps (requires Splunk.com login):

| App | Splunkbase ID |
|---|---|
| MCP Server for Splunk | 7931 (v1.2.0) |
| Splunk AI Assistant (SAIA) | 7245 |
| Splunk AI Toolkit | 2890 |

After installing SAIA, complete the tenant setup wizard to connect it to the Splunk AI cloud backend.

### 3. Configure credentials

```bash
cp .env.example .env
# Fill in: SPLUNK_TOKEN, MCP_TOKEN, HEC_TOKEN, ANTHROPIC_API_KEY, SPLUNK_PASSWORD
```

Two separate Splunk tokens are required (do not swap them):

| Variable | Source | Used for |
|---|---|---|
| `SPLUNK_TOKEN` | Settings → Tokens → New Token | REST 8089 — KV Store, dashboard deploy |
| `MCP_TOKEN` | MCP Server app → encrypted token | MCP tools only — will 401 against REST |
| `HEC_TOKEN` | Settings → Data Inputs → HTTP Event Collector | Telemetry ingest on port 8088 |

MCP endpoint for local dev (no SSL issues):
```
MCP_URL=http://localhost:8000/en-US/splunkd/__raw/services/mcp
```

### 4. Install Python dependencies

```bash
uv sync --python 3.11
```

### 5. Initialise KV Store collections

```bash
uv run symphunk kv-init
```

Creates: `symphunk_incidents`, `symphunk_evidence`, `symphunk_memory`, `symphunk_audit`.

---

## Usage

```bash
# Start the orchestrator polling loop
uv run symphunk run

# Seed a synthetic incident for testing/demo
uv run symphunk seed --title "CPU spike on web-01" --severity medium

# Push the proof-of-work dashboard to Splunk
uv run symphunk deploy-dashboard

# Re-create KV collections (idempotent)
uv run symphunk kv-init
```

---

## Project Structure

```
infra/
  docker-compose.yml        # Splunk Enterprise local dev environment
symphunk/
  config.py                 # Pydantic settings (reads from .env)
  cli.py                    # CLI entry point
  harness/
    engine.py               # Claude tool-use loop + prompt caching
    mcp_client.py           # Splunk MCP Server client (streamable HTTP)
    tools.py                # Merged MCP + local tool registry
    skills.py               # On-demand markdown skill loader
    memory.py               # Cross-incident KV Store context
    permissions.py          # Read-vs-action classification + approval gate
    hooks.py                # PreToolUse / PostToolUse lifecycle
    budget.py               # SearchBudget: caps, tstats preference, time bounds
  orchestrator/
    poller.py               # Poll KV incidents (status=New)
    dispatcher.py           # Two-level concurrency gate
    state.py                # State machine: New→Investigating→Resolved/Escalated
  agents/
    base.py                 # Agent base class
    obs_agent.py            # ObsAgent: triage, correlate, evidence assembly
  splunk/
    rest.py                 # REST 8089 client (httpx)
    kvstore.py              # KV Store CRUD
    hec.py                  # HEC event emit
skills/obs/
  anomaly-triage.md         # SPL templates for metric anomaly detection
  service-dependency.md     # Blast-radius and service correlation queries
  diagnostic-spl.md         # General-purpose diagnostic SPL + budget guidelines
dashboards/
  symphunk_obs.json         # Proof-of-work Dashboard Studio definition
tests/                      # 24 unit tests (no live Splunk required)
```

---

## MCP Tools (verified, v1.2.0)

14 tools confirmed live across two namespaces:

**`splunk_*`** (read-only): `splunk_run_query`, `splunk_run_saved_search`, `splunk_get_indexes`, `splunk_get_index_info`, `splunk_get_info`, `splunk_get_metadata`, `splunk_get_knowledge_objects`, `splunk_get_kv_store_collections`, `splunk_get_user_info`, `splunk_get_user_list`

**`saia_*`**: `saia_generate_spl`, `saia_explain_spl`, `saia_optimize_spl`, `saia_ask_splunk_question`

MCP v1.2.0 exposes read-only tools. All writes (KV Store, dashboards, HEC) go through REST 8089.

---

## Development

```bash
# Run tests (no live Splunk needed)
uv run pytest -v

# MCP connectivity smoke test (Splunk must be running)
uv run python smoke.py
```

---

## Design Decisions

Eight architectural decisions drive the implementation — see [`splunkAgenticOpsDesign.md`](../splunkAgenticOpsDesign.md) for the full design and v2 re-evaluation. Key constraints:

- **DD6**: Agent runs in its own tier — never co-located on indexers or search heads
- **DD7**: Anti-sprawl positioning — one orchestrator, one tool layer, one governance model
- **DD3**: Hybrid SPL strategy — curated skill templates for repeatable queries, `saia_generate_spl` for novel ones
- **DD8**: Self-observability (stretch) — agent emits OTel traces via HEC into Splunk AI Agent Monitoring

---

## Hackathon

**Event**: [Splunk Agentic Ops Hackathon](https://splunk.devpost.com) — "Reimagine the future of agentic operations using Splunk AI"

**Track**: Observability (primary) — anti-sprawl consolidation + OTel + AI Agent Monitoring narrative

**Required tech satisfied**: Splunk MCP Server (tool backbone) + SAIA (`saia_*` tools) + Splunk Developer License

---

## License

MIT
