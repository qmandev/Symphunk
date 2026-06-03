# Symphunk

> **One conductor, many agents, one Splunk.**

Symphunk is an agentic AI operations layer for Splunk built for the [Splunk Agentic Ops Hackathon](https://splunk.devpost.com). A single orchestrator polls Splunk for alert-triggered incidents, dispatches specialized agents that investigate and correlate via the **Splunk MCP Server**, and writes proof-of-work evidence back into Splunk dashboards before auto-resolving or escalating — all under one governance model.

**Thesis**: agentic ops should *shrink* the tool count and the toil, not grow them. One orchestrator, one tool layer, one Splunk — with a budget-conscious SPL strategy that doesn't starve the search tier.

---

## How It Works

```
Splunk saved search (anomaly detection SPL)
  │  alert fires
  ▼
symphunk_ingest alert action  ──►  KV Store symphunk_incidents  (status=New)
                                          │
                                   ┌──────▼──────────────────────────────┐
                                   │  Orchestrator  (asyncio poll loop)  │
                                   │  poller → concurrency gate          │
                                   │  → state: New → Investigating       │
                                   └──────┬──────────────────────────────┘
                                          │  one task / incident
                                   ┌──────▼──────────────────────────────┐
                                   │  ObsAgent  (Claude + harness)        │
                                   │  load skills → run SPL via MCP      │
                                   │  → correlate → evidence + confidence │
                                   └──┬──────────────────────────────┬───┘
                    read: 14 MCP tools                     write: KV + HEC telemetry
                    (splunk_*/saia_*)                              │
                          ▼                                        ▼
                  Splunk Enterprise                    index=summary → Dashboard Studio
                  index=symphunk_demo              (4 KPI tiles + Investigation Results table)
                                                   status=Resolved ✓  or  Escalated ⚠
```

**Splunk AI capabilities used:**
- **Splunk MCP Server** (v1.2.0) — 14 tools (`splunk_*` + `saia_*`) form the entire read backbone
- **SAIA** (`saia_generate_spl`, `saia_optimize_spl`, `saia_explain_spl`, `saia_ask_splunk_question`) — hybrid SPL strategy: curated skill templates for hot-path queries, `saia_generate_spl` for novel/exploratory ones
- **Splunk Developer License** (10 GB/day) + Splunk AI Toolkit

**Agent tier separation (DD6):** the agent runs as an external Reasoning/Agentic Tier client — it is never co-located on indexers or search heads. All reads go through the MCP Server; all writes go through REST 8089.

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

## Setup (one-time)

See **[SETUP.md](SETUP.md)** for the full walkthrough. The short version:

```bash
# 1. Start Splunk in Docker
docker compose -f infra/docker-compose.yml up -d

# 2. Install Splunk apps via Web UI → Apps → Find More Apps:
#    MCP Server for Splunk (7931 v1.2.0), Splunk AI Assistant (7245), AI Toolkit (2890)

# 3. Create tokens + copy .env
cp .env.example .env
# Fill: SPLUNK_TOKEN, MCP_TOKEN, HEC_TOKEN, ANTHROPIC_API_KEY, SPLUNK_PASSWORD

# 4. Install Python deps + initialise KV Store
uv sync --python 3.11
uv run symphunk kv-init

# 5. Install the alert action app + create the demo saved search
uv run symphunk deploy-alert

# 6. Deploy the proof-of-work dashboard
uv run symphunk deploy-dashboard
```

---

## Demo Run (end-to-end)

After setup, a single scripted run demonstrates the full agentic pipeline:

```bash
# 1. Inject the deterministic CPU-spike anomaly scenario (30 events: baseline + anomaly)
uv run symphunk load-sample-data

# 2. Dispatch the saved-search alert manually (fires the alert action → incident in KV)
curl -sk -u admin:${SPLUNK_PASSWORD} -X POST \
  "https://localhost:8089/services/saved/searches/symphunk_obs_demo/dispatch" \
  -d "dispatch.now=true&force_dispatch=true&trigger_actions=1"

# 3. Start the orchestrator — ObsAgent picks up the incident, investigates, resolves
uv run symphunk run
```

What you'll see in the terminal:
```
INFO  MCP connected — 14 tools, 3 skills loaded
INFO  Poller found 1 incident(s) with status=New
INFO  ObsAgent starting incident=<id> severity=medium
INFO  [tool] splunk_run_query → per-host CPU summary
INFO  [tool] splunk_run_query → z-score timeline
INFO  [tool] saia_generate_spl → cascade correlation query
INFO  [tool] splunk_run_query → cascade results
INFO  ObsAgent done incident=<id> status=Resolved confidence=0.82
```

Then open the dashboard: **http://localhost:8000/en-US/app/search/symphunk_obs**

| Tile | Value |
|---|---|
| Incidents Processed | 1 |
| Auto-Resolved | 1 |
| Avg Confidence | 0.82 |
| Escalated | 0 |

The Investigation Results table shows the root cause, blast radius (api-gateway-01 secondary impact), and recommended action — all written autonomously by the agent.

---

## CLI Reference

```bash
uv run symphunk run                # Start orchestrator polling loop
uv run symphunk seed               # Insert synthetic incident (testing)
uv run symphunk load-sample-data   # Inject CPU-spike demo scenario into Splunk
uv run symphunk deploy-alert       # Install alert action app + create saved search
uv run symphunk deploy-dashboard   # Push Dashboard Studio definition to Splunk
uv run symphunk kv-init            # (Re-)create the four KV Store collections
uv run symphunk clean-incidents    # Delete incidents by status (default: New)
```

---

## Project Structure

```
infra/
  docker-compose.yml              # Splunk Enterprise local dev environment
symphunk/
  config.py                       # Pydantic settings (reads .env)
  cli.py                          # CLI entry point
  harness/
    engine.py                     # Claude tool-use loop + prompt caching
    mcp_client.py                 # Splunk MCP Server client (streamable HTTP)
    tools.py                      # Merged MCP + local tool registry
    skills.py                     # On-demand markdown skill loader
    memory.py                     # Cross-incident KV Store context
    permissions.py                # Read-vs-action classification + approval gate
    hooks.py                      # PreToolUse / PostToolUse lifecycle
    budget.py                     # SearchBudget: caps, tstats preference, time bounds
  orchestrator/
    poller.py                     # Poll KV incidents (status=New)
    dispatcher.py                 # Two-level concurrency gate
    state.py                      # State machine: New→Investigating→Resolved/Escalated
  agents/
    base.py                       # Agent base class
    obs_agent.py                  # ObsAgent: triage, correlate, evidence assembly
  splunk/
    rest.py                       # REST 8089 client (httpx)
    kvstore.py                    # KV Store CRUD (batch_save upsert)
    hec.py                        # HEC event emit (HTTPS, Docker cert)
    sample_data.py                # Deterministic CPU-spike demo scenario (30 events)
    alert_setup.py                # REST helpers: conf reload, saved search creation
    alert_action/
      symphunk_alert_action/      # Splunk app: custom alert action
        bin/symphunk_ingest.py    # Reads session_key from stdin, writes to KV
        default/alert_actions.conf
skills/obs/
  anomaly-triage.md               # SPL templates for metric anomaly detection
  service-dependency.md           # Blast-radius and service correlation queries
  diagnostic-spl.md               # General-purpose diagnostic SPL + budget guidelines
dashboards/
  symphunk_obs.json               # Dashboard Studio definition (proof-of-work)
tests/                            # 24 unit tests (no live Splunk required)
```

---

## MCP Tools (verified, v1.2.0)

14 tools confirmed live across two namespaces:

**`splunk_*`** (read-only): `splunk_run_query`, `splunk_run_saved_search`, `splunk_get_indexes`, `splunk_get_index_info`, `splunk_get_info`, `splunk_get_metadata`, `splunk_get_knowledge_objects`, `splunk_get_kv_store_collections`, `splunk_get_user_info`, `splunk_get_user_list`

**`saia_*`**: `saia_generate_spl`, `saia_explain_spl`, `saia_optimize_spl`, `saia_ask_splunk_question`

MCP v1.2.0 exposes read-only tools. All writes (KV Store, dashboards, HEC telemetry) go through REST 8089.

---

## Design Decisions

Eight architectural decisions drive the implementation — see [`splunkAgenticOpsDesign.md`](../splunkAgenticOpsDesign.md) for the full design and v2 re-evaluation:

| Decision | What it means |
|---|---|
| **DD3** Hybrid SPL | Curated skill templates for repeatable hot-path queries; `saia_generate_spl` for novel/exploratory ones |
| **DD5** Search budget | Every SPL query consumes a CPU core. `SearchBudget` caps searches per run (10), prefers `tstats`/accelerated DMs, and bounds time windows to recent data |
| **DD6** Tier separation | Agent runs as an external client — never on indexers or search heads |
| **DD7** Anti-sprawl | One orchestrator, one tool layer, one governance model — new agents reuse the same harness |
| **DD8** Self-observability | Agent emits its own reasoning telemetry via HEC → `index=summary` → Dashboard Studio (currently investigation evidence; full OTel traces are stretch) |

---

## Development

```bash
# Run unit tests (no live Splunk needed)
uv run pytest -v

# MCP connectivity smoke test (Splunk must be running)
uv run python smoke.py
```

---

## Hackathon

**Event**: [Splunk Agentic Ops Hackathon](https://splunk.devpost.com) — "Reimagine the future of agentic operations using Splunk AI"

**Track**: Observability — anti-sprawl consolidation + AI Agent Monitoring narrative

**Required Splunk AI capabilities satisfied**:
- Splunk MCP Server (the entire read tool backbone — 14 tools, every agent action)
- SAIA AI Assistant (`saia_*` tools — used for novel SPL generation)
- Splunk Developer License (10 GB/day) + Splunk AI Toolkit installed

---

## License

Apache 2.0
