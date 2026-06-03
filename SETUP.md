# Symphunk — Setup Guide

This guide covers the one-time setup required before the first demo run. Takes ~20 minutes.

---

## 1. Start Splunk

```bash
# Start Docker Desktop first (menu bar icon must be steady, not animated)
open -a Docker

# From the Symphunk/ directory:
docker compose -f infra/docker-compose.yml up -d

# Wait ~2 min, then verify:
docker compose -f infra/docker-compose.yml ps
# Status column should show: healthy
```

Splunk Web: **http://localhost:8000** — `admin` / value of `SPLUNK_PASSWORD` (default: `changeme123!`)

Ports: `8000` (Web UI), `8088` (HEC, HTTPS), `8089` (REST, HTTPS)

---

## 2. Install Splunk Apps

In Splunk Web → **Apps → Find More Apps** (requires Splunk.com login):

| App | Splunkbase ID | Notes |
|---|---|---|
| MCP Server for Splunk | **7931** | Install v1.2.0 exactly |
| Splunk AI Assistant (SAIA) | **7245** | Requires SAIA tenant setup (see step 3) |
| Splunk AI Toolkit | **2890** | Optional for demo but install for completeness |

After installing, restart Splunk when prompted.

---

## 3. Configure SAIA Tenant

After installing the AI Assistant app:
1. In Splunk Web, open the **Splunk AI Assistant** app
2. Complete the tenant configuration wizard
3. Select **US region** for the cloud backend
4. Submit the tenant code — activation takes a few minutes

> **Trial clock note**: SAIA activation is one-time and does not expire on its own. The `saia_*` MCP tools require a cloud-connected and activated SAIA tenant.

---

## 4. Create a Splunk Role and Tokens

### 4a. Create the `symphunk` role

Settings → **Access Controls → Roles → New Role**:

- Name: `symphunk`
- Inherit from: `user`
- Capabilities to add: `mcp_tool_execute`, `mcp_tool_admin`, `edit_tokens_own`

### 4b. Mint a standard REST token

Settings → **Tokens → New Token**:

- Audience: `symphunk-rest`
- User: `admin`
- Expiration: set to ~90 days out

Copy the token — this is your `SPLUNK_TOKEN` (used for REST 8089 calls: KV Store, dashboards, HEC).

### 4c. Mint an encrypted MCP token

In the **MCP Server for Splunk** app → **Configuration** → generate an encrypted token:

- User: `admin`
- Expiration: ~180 days out

Copy the **encrypted** token value — this is your `MCP_TOKEN`.

> **Important**: the MCP token is encrypted and MCP-only. Using it against REST 8089 returns 401. Keep `SPLUNK_TOKEN` and `MCP_TOKEN` separate.

### 4d. Mint a HEC token

Settings → **Data Inputs → HTTP Event Collector → New Token**:

- Name: `symphunk-hec`
- Source type: `_json`
- Default index: `main`
- Indexer acknowledgement: disabled

Copy the token — this is your `HEC_TOKEN`.

> **Trial clock note**: HEC tokens persist as long as the container volume persists (`splunk-etc` named volume). They survive `docker compose stop/start`. They are lost if you `docker compose down -v` (removes volumes).

---

## 5. Find the MCP Endpoint URL

In the **MCP Server for Splunk** app → **Status** page, two endpoints are listed:

| Endpoint | Notes |
|---|---|
| `https://localhost:8089/services/mcp` | Direct HTTPS; self-signed cert → needs `verify=False` |
| `http://localhost:8000/en-US/splunkd/__raw/services/mcp` | HTTP via Splunk Web proxy; no SSL issue |

**Use the HTTP proxy endpoint for local dev** — set as `MCP_URL` in `.env`.

---

## 6. Configure `.env`

```bash
cp .env.example .env
```

Fill in all values:

```
SPLUNK_HOST=localhost
SPLUNK_PORT=8089
SPLUNK_TOKEN=<your REST token from step 4b>

MCP_URL=http://localhost:8000/en-US/splunkd/__raw/services/mcp
MCP_TOKEN=<your encrypted MCP token from step 4c>

HEC_TOKEN=<your HEC token from step 4d>
HEC_URL=https://localhost:8088

ANTHROPIC_API_KEY=<your Anthropic API key>
SPLUNK_PASSWORD=<your Splunk admin password>
```

---

## 7. Install Python Dependencies

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync --python 3.11
```

Installs ~43 packages into `.venv`. Verify with:

```bash
uv run symphunk --help
```

---

## 8. Initialise KV Store Collections

```bash
uv run symphunk kv-init
```

Creates four KV Store collections: `symphunk_incidents`, `symphunk_evidence`, `symphunk_memory`, `symphunk_audit`.

---

## 9. Install the Alert Action App

```bash
uv run symphunk deploy-alert
```

This:
1. Copies `symphunk_alert_action/` into the container via `docker cp`
2. Fixes file ownership (`chown splunk:splunk`)
3. Reloads `alert_actions.conf`
4. **If it's the first install**: automatically restarts Splunk (~90s) and polls until it's back
5. Creates the `symphunk_obs_demo` saved search (cron: every 5 minutes)

---

## 10. Deploy the Dashboard

```bash
uv run symphunk deploy-dashboard
```

Creates the **Symphunk — Observability Proof-of-Work** Dashboard Studio view at:
**http://localhost:8000/en-US/app/search/symphunk_obs**

---

## Verify the Setup

```bash
# Confirm 14 MCP tools are live
uv run python smoke.py

# Run unit tests (no live Splunk needed)
uv run pytest -v   # should show 24 passed
```

Expected smoke output:
```
Connected — 14 tools:
  saia_ask_splunk_question
  saia_explain_spl
  saia_generate_spl
  saia_optimize_spl
  splunk_get_index_info
  splunk_get_indexes
  splunk_get_info
  splunk_get_knowledge_objects
  splunk_get_kv_store_collections
  splunk_get_metadata
  splunk_get_user_info
  splunk_get_user_list
  splunk_run_query
  splunk_run_saved_search
```

---

## Trial Clock Notes

| Resource | Expires | What happens |
|---|---|---|
| Splunk Developer License | Applied ~2026-06-05; 10 GB/day | Reverts to free 500 MB/day limit if expired |
| REST token (`SPLUNK_TOKEN`) | 90 days from creation | Mint a new one in Settings → Tokens |
| MCP token (`MCP_TOKEN`) | ~180 days from creation | Re-generate in MCP Server app |
| HEC token | Persists with volume | Lost if you `docker compose down -v` — mint a new one |
| SAIA tenant activation | Indefinite once activated | No action needed |
| Splunk container volumes | Persistent named volumes | Survive `stop/start`; lost on `down -v` |

If you need to reset everything from scratch:
```bash
docker compose -f infra/docker-compose.yml down -v   # destroys volumes
docker compose -f infra/docker-compose.yml up -d     # fresh start
# then repeat steps 2–10
```

---

## Troubleshooting

**`docker cp` fails with "no such container"**
- Container name defaults to `symphunk-splunk`. Check with `docker ps` and pass `--container <name>` to `deploy-alert`.

**`MCP connected — 0 tools`**
- SAIA tenant activation is pending. Wait a few minutes and retry.
- Or check the MCP Server Status page in Splunk Web for error details.

**HEC returns 400 / "No data"**
- Verify `HEC_URL=https://localhost:8088` (HTTPS, not HTTP) in `.env`.
- The HEC Global Settings must have SSL enabled (it is by default in Docker).

**`symphunk run` exits immediately without processing incidents**
- No incidents in KV with `status=New`. Run `symphunk seed` or dispatch the saved search.

**Dashboard shows "No results"**
- Run the full demo first (`load-sample-data` → dispatch → `symphunk run`) to populate `index=summary`.
- Verify the time range picker is set to "Last 7 days" or wider.
