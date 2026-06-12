# Symphunk — Design Document

## Architecture

Splunk alerts and saved searches become the work queue. A centralized orchestrator continuously polls Splunk for new incidents. For each one, it dispatches a specialized agent that uses Splunk MCP tools to investigate, correlate, and remediate — delivering proof-of-work back into Splunk dashboards before closing the loop autonomously or escalating to humans.

Splunk is both the data backbone and the work tracker. All agent state lives in the KV Store. The agent runs in an external Reasoning/Agentic Tier — an external client of Splunk, never co-located on indexers or search heads — analogous to a Data Collection Node. This keeps the agent from contending for search-tier resources and matches Splunk's validated infrastructure model.

```
        EXTERNAL TELEMETRY (OTel-standardized — DD7)
                          │
                          ▼  (UF / HF / HEC / SC4S)
┌───────────────────────────────────────────────────────────────┐
│  SPLUNK PLATFORM  (Collection → Indexing → Search tiers)      │
│  ES Notable Events │ ITSI Episodes │ KV Store │ Hosted Models  │
└───────────────┬───────────────────────────────▲───────────────┘
   read (MCP `splunk_*`/`saia_*`, REST 8089)     │ actions via
                │                                 │ Adaptive Response
                ▼                                 │ / SOAR / dashboards
┌───────────────────────────────────────────────────────────────┐
│  REASONING / AGENTIC TIER  (external — DD6, DCN-like)         │
│                                                               │
│   ┌─────────────┐   polls incidents, gates concurrency        │
│   │ Orchestrator│   (Availability + Scalability pillars)      │
│   └──────┬──────┘                                             │
│   ┌──────┴───────────────┬──────────────────┐                 │
│   ▼ ObsAgent             ▼ SecAgent          ▼ DevExAgent      │
│   └──── shared HARNESS: tools · skills(hybrid) · memory(KV) ──┘
│         · permissions(RBAC via MCP token) · approval gate      │
│                                                               │
│   SELF-OBSERVABILITY (DD8): emits OTel about its own reasoning │
│      └──► HEC ──► Splunk Observability AI Agent Monitoring ───┘
└───────────────────────────────────────────────────────────────┘
        ONE orchestrator · ONE governance model = consolidation, NOT sprawl (DD5/DD7)
```

### The 5 SVA Pillars as Design Pillars

Splunk's Validated Architecture defines five infrastructure pillars. Each one directly constrains how the agent behaves:

| Pillar | What it forces in the agentic design |
|---|---|
| **Availability** | Stateless workers; orchestrator recovers by re-polling Splunk, holding no persistent retry state. No agent is a single point of failure. |
| **Performance** | **Every SPL search consumes a CPU core; no free core = queued search.** A naive agent firing many concurrent searches starves the search tier. Agents must budget searches, prefer `tstats`/accelerated data models/summary indexes, bound time windows to recent data (95% of searches are ≤7 days), and sample for fast triage before committing to full-fidelity deep dives. |
| **Scalability** | Two-level concurrency gating (`max_concurrent_agents` + per-state limits); the agent tier scales independently of Splunk. |
| **Security** | Agent inherits Splunk RBAC via the MCP token (public-key encrypted, non-reusable outside MCP context); least-privilege role; human-in-the-loop approval gate; full audit trail. |
| **Manageability** | One centrally-governed orchestrator; config in version control; the agent monitors its own health. |

---

## Design Decisions

### DD1 — Splunk as Work Tracker
The orchestrator polls **ES Notable Events / ITSI Episodes** via MCP/REST as the job queue. Each alert or incident is one isolated agent task. State transitions (`New → Investigating → Resolved/Escalated`) write back to the **KV Store** — all state lives inside Splunk, no external database. ITSI Event iQ already correlates and deduplicates alerts, so the agent subscribes to grouped episodes rather than raw alert noise.

### DD2 — Splunk MCP Server as the Tool Backbone
Every agent action goes through the Splunk MCP Server. The agent is an **external client of the search tier**: read path uses MCP `splunk_*` tools and REST (8089); action path uses Adaptive Response, SOAR, and dashboard writes — never touching the collection or indexing tier. The MCP Server's self-describing JSON schemas let agents discover available tools at runtime without hardcoded coupling to Splunk API details.

### DD3 — Hybrid SPL Strategy
Use a **hybrid**: curated skill templates (markdown, loaded on demand) for high-stakes, repeatable, performance-tuned queries — and `saia_generate_spl` for novel or exploratory queries where flexibility matters more than a pre-tuned template. Skills also encode the performance budget (which queries are cheap vs. expensive), so the agent knows which path to take before it searches.

### DD4 — Proof-of-Work via Splunk Dashboard
Before closing an incident or taking a remediation action, the agent writes evidence back to Splunk: correlated search results, timeline of events, confidence/threat score, recommended action. A Dashboard Studio proof-of-work dashboard is the audit trail — it mirrors the **AI Troubleshooting Agent** pattern Splunk ships in Observability Cloud ("evidence-backed summaries, human-verified action plans"). Humans see a complete evidence package, not just an outcome.

### DD5 — Consolidated Agent Specialization (anti-sprawl)
Three specialized agents share **one orchestrator, one MCP tool layer, one harness, one governance model**. This is consolidation, not sprawl. Adding a new agent domain means a new skill set and a new polled source — not a new orchestrator, tool layer, or governance model. The routing primitive is a single KV field (`agent_type`) written by the alert action:
- **ObsAgent**: Metric anomaly detection, log correlation, service dependency mapping, runbook execution
- **SecAgent**: IOC enrichment, lateral movement detection, threat intel classification, SOAR triggering
- **DevExAgent**: CI/CD pipeline health, deployment impact analysis, SPL assistant, dashboard generation

### DD6 — Tier-Respecting Deployment (hard constraint)
The agent runs in its own external **Reasoning/Agentic Tier**, analogous to a Data Collection Node. It is an external client of Splunk and must never be co-located on indexers or search heads. On Splunk Cloud, the MCP Server is the supported modern path (REST 8089 requires a support ticket). This keeps the agent from contending for search-tier resources and respects Splunk's foundational infrastructure model.

### DD7 — Anti-Sprawl Consolidation Positioning
Agentic ops should **shrink** the tool count and the toil, not grow them. The risk is agent sprawl: autonomous systems that deploy new monitoring or remediation agents replicate the exact sprawl problem they were meant to solve. Symphunk is a consolidation layer — one agentic interface over Splunk's already-unified data, standardized on **OTel** for any new telemetry the agent introduces. New telemetry the agent emits (its own reasoning traces) goes via HEC → Splunk, not to a separate observability stack.

### DD8 — The Agent is itself Observable
The agent emits **OTel traces and metrics about its own reasoning** — decisions, tool calls, token cost, latency, confidence — via **HEC** into Splunk, where **Observability Cloud's AI Agent Monitoring** (hallucination, drift, PII leakage, prompt injection, cost) watches it. An agentic-ops tool that Splunk itself monitors closes the loop and directly answers the question "how do you trust the agent?"

---

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Agent runtime | Python + `anthropic` SDK (Claude 4) | Claude API with prompt caching for long SPL skill context |
| Orchestrator | `asyncio` + `apscheduler` | Lightweight polling loop, no heavy framework needed |
| MCP integration | Splunk MCP Server (official, v1.2.0) | 14 tools across `splunk_*` and `saia_*` namespaces |
| Memory/State | Splunk KV Store | All state in Splunk — no external database |
| Skills | Markdown files loaded at runtime | On-demand SPL skill injection; swap skills to change agent domain |
| Hooks | Python decorators on tool calls | `PreToolUse` approval gates, `PostToolUse` audit log |
| Proof-of-work | Splunk Dashboard Studio via REST API | Evidence visible inside Splunk UI |

---

## Track Recommendation

- **Observability (primary)** — The anti-sprawl consolidation thesis + OTel standardization + AI Agent Monitoring + the AI Troubleshooting Agent blueprint all converge in this track. The differentiated narrative is *"an anti-sprawl agentic consolidation layer that is itself observable."* Strong on Potential Impact (green/blue-dollar savings) and Creativity (self-observing agent).
- **Security (strong alternative)** — The cleanest 3-minute demo: triage a notable event → enrich IOC → correlate lateral movement → evidence dashboard → auto-close or escalate. Best if optimizing for a crisp autonomous-action story over the strategic thesis.
- **Platform & Developer Experience** — DevExAgent demonstrates a distinct reasoning pattern: deploy correlation (did this deployment *cause* the error rate change, or was it pre-existing?). The confidence scoring rubric separates true regressions from false alarms without human triage. Strongest case for the hackathon's developer productivity framing.

All three tracks run against the same architecture; only the agent's skill set and the polled source differ — which is itself proof of the consolidation design.

---

## Splunk Platform Reference

### AI/ML Validated Architecture — 3-Tier Model

| Tier | Name | Core Capability | Key Constraints |
|---|---|---|---|
| 1 | Core SPL | Built-in `anomalydetection`, `predict`, `kmeans`, `outlier`, `trendline` commands | Predefined parameters, search head bottleneck |
| 2 | AI Toolkit | 40+ scikit-learn algorithms, ONNX model import, model stacking, experiment tracking | 1 CPU core default, 15 MB model limit, search-head-only execution |
| 3 | DSDL | GPU-accelerated deep learning via Docker/Kubernetes, JupyterLab, TensorFlow/PyTorch, LLM hosting | REST API transfer overhead, requires container infrastructure |

**Deployment topologies**: S1 (single server) → D1/D11 (distributed) → C1/C3 (clustered single-site) → M2/M4 (multisite). All tiers support all topologies.

**Note**: Embedded AI in Enterprise Security, ITSI, and generative AI assistants follow independent deployment patterns — not covered by the AI/ML SVA.

---

### Splunk AI Product Landscape (2025–2026)

#### Enterprise Security 8.2 — Security Agents
- **Triage Agent**: Autonomous notable event triage with human-in-the-loop approval
- **Malware Reversal Agent**: Automated malware analysis and reversal workflows
- **AI Assistant for Security**: Investigates issues, grounds answers in environment data, reduces manual work
- **Detection Studio**: AI-assisted detection rule authoring and tuning

#### IT Service Intelligence (ITSI) — Observability Intelligence
- **Event iQ**: Automated alert correlation to reduce noise; groups related alerts with clear context
- **Episode Summarization**: Auto-generated overviews of grouped alerts including trends, impact, and root cause

#### Splunk Observability Cloud — Q1 2026 GA Features
- **AI Troubleshooting Agent**: Automatically analyzes metrics/events/logs/traces on alert trigger; generates evidence-backed root cause summaries with human-verified remediation plans
- **AI Agent Monitoring**: Tracks LLM/agent performance across three signal categories:
  - *Performance*: Latency, error rates
  - *Quality & Security*: Hallucinations, bias, drift, accuracy, PII leakage, prompt injection
  - *Cost*: Token usage and expense tracking
- **AI Infrastructure Monitoring**: GPU utilization, memory, tokenomics across Cisco AI PODs, orchestration frameworks, and vector databases

#### AI Canvas
- Collaborative, multi-team investigation hub
- Unifies data and context layers across SecOps, ITOps, NetOps, engineering

---

### Splunk MCP Server (GA: February 4, 2026)

**Protocol**: Streamable HTTP, open MCP standard — universal adapter between AI agents and Splunk.

| Prefix | Source | Example Tools |
|---|---|---|
| `splunk_` | Core platform | SPL search execution, saved search discovery, KV store access, knowledge object exploration |
| `saia_` | AI Assistant (if installed) | `saia_generate_spl`, `saia_explain_spl`, `saia_ask_splunk_question` |

**Security model**: RBAC + public key token encryption (tokens cannot be reused outside MCP context). Admins can enable/disable individual tools globally.

---

### Splunk Hosted Models (GA: February 18, 2026)

| Model | Type | Best For |
|---|---|---|
| `foundation-sec-1.1-8b-instruct` | Security-tuned | Log analysis, event summarization, detection suggestions — purpose-built for machine data |
| GPT OSS 20B | General reasoning | Data exploration, SPL generation, general ops |
| GPT OSS 120B | Advanced reasoning | Complex multi-step analysis, nuanced correlation |

These models are trained on machine data — higher accuracy than general LLMs for SPL generation and log interpretation without fine-tuning.

---

### Machine Data Lake (Alpha: February 2026)

Schema-less preprocessing layer that enriches telemetry before indexing, making raw machine data AI-ready for RAG pipelines, model fine-tuning, and federated analytics via Cisco Data Fabric (Splunk + AWS S3 + Snowflake + Azure).

---

### Design Implications for Splunk Agentic Ops

| Splunk Capability | How It Maps to Our Architecture |
|---|---|
| MCP Server `splunk_*` tools | Primary tool layer for all agent read actions |
| `saia_generate_spl` | Hybrid SPL strategy: novel/exploratory queries generated on demand |
| `foundation-sec-1.1-8b` hosted model | SecAgent first-pass classifier (stretch goal) |
| ITSI Event iQ + Episode Summarization | ObsAgent subscribes to grouped episodes, not raw alert noise |
| ES Notable Events | Orchestrator's work queue |
| KV Store | Harness state layer — agent context, state transitions, investigation history |
| AI Troubleshooting Agent pattern | Blueprint for ObsAgent and DevExAgent's root cause loop: alert → analyze → evidence → remediation plan |
| Machine Data Lake | Future RAG layer for historical incident context |
| RBAC + token security | Agent inherits Splunk role, cannot exceed its access scope |
