from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

import click

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


@click.group()
def cli() -> None:
    """Symphunk — one conductor, many agents, one Splunk."""


@cli.command()
def run() -> None:
    """Start the orchestrator polling loop (routes obs and sec incidents automatically)."""
    from symphunk.config import settings
    from symphunk.splunk.kvstore import KVStore
    from symphunk.harness.mcp_client import MCPClient
    from symphunk.harness.tools import ToolRegistry
    from symphunk.harness.skills import load_all
    from symphunk.harness.engine import Engine
    from symphunk.harness.budget import SearchBudget
    from symphunk.agents.obs_agent import ObsAgent
    from symphunk.agents.sec_agent import SecAgent
    from symphunk.agents.dev_ex_agent import DevExAgent
    from symphunk.orchestrator.poller import Poller
    from symphunk.orchestrator.dispatcher import Dispatcher

    async def _run() -> None:
        kv = KVStore()
        async with MCPClient(settings.mcp_url, settings.mcp_token) as mcp:
            registry = ToolRegistry()
            registry.from_mcp(mcp.tool_schemas())
            obs_skills = load_all("obs")
            sec_skills = load_all("sec")
            devex_skills = load_all("devex")
            click.echo(
                f"MCP connected — {len(registry)} tools, "
                f"{len(obs_skills)} obs skills, {len(sec_skills)} sec skills, "
                f"{len(devex_skills)} devex skills loaded"
            )

            poller = Poller(kv)
            dispatcher = Dispatcher(kv)

            def make_agent(incident: dict):
                agent_type = incident.get("agent_type", "obs")
                budget = SearchBudget(max_searches=settings.max_searches_per_run)
                if agent_type == "sec":
                    engine = Engine(
                        mcp, registry, sec_skills,
                        incident_id=incident.get("id", ""),
                        budget=budget,
                    )
                    return SecAgent(incident, engine, kv)
                if agent_type == "devex":
                    engine = Engine(
                        mcp, registry, devex_skills,
                        incident_id=incident.get("id", ""),
                        budget=budget,
                    )
                    return DevExAgent(incident, engine, kv)
                engine = Engine(
                    mcp, registry, obs_skills,
                    incident_id=incident.get("id", ""),
                    budget=budget,
                )
                return ObsAgent(incident, engine, kv)

            await poller.run_forever(lambda inc: dispatcher.dispatch(inc, make_agent))

    asyncio.run(_run())


@cli.command("load-sample-data")
def load_sample_data() -> None:
    """Inject CPU-spike demo scenario into index=symphunk_demo and update the detection search."""
    from symphunk.config import settings
    from symphunk.splunk.rest import SplunkREST
    from symphunk.splunk.sample_data import ensure_index, inject

    # Detection SPL: aggregate by host, flag cpu_pct > 80, emit alert fields.
    # max_cpu > 95 → "high"; 80-95 → "medium" so the ~92% demo peak stays medium and can auto-resolve.
    # Group by host only (host is Splunk metadata; service is a JSON-extracted field).
    _DETECTION_SPL = (
        'index=symphunk_demo earliest=-15m latest=now() NOT host="localhost:*"'
        ' | stats avg(cpu_pct) AS avg_cpu max(cpu_pct) AS max_cpu'
        ' sum(error_count) AS total_errors avg(req_per_sec) AS avg_rps'
        ' count AS event_count BY host'
        ' | where max_cpu > 80 AND event_count >= 2'
        ' | eval title="CPU spike on ".host,'
        ' severity=if(max_cpu > 95, "high", "medium"),'
        ' description="CPU at ".round(max_cpu,1)."% avg=".round(avg_cpu,1)'
        ' ." errors=".total_errors." rps=".round(avg_rps,1)." on ".host'
        ' | fields title severity description host max_cpu total_errors avg_rps'
    )

    async def _run() -> None:
        rest = SplunkREST()
        try:
            await ensure_index(rest._client)
            click.echo(f"Index symphunk_demo ready")

            count = await inject(settings.hec_token)
            click.echo(f"Injected {count} sample events (baseline + CPU-spike anomaly)")

            # Update symphunk_obs_demo to use real detection SPL instead of | makeresults
            r = await rest._client.post(
                f"https://{settings.splunk_host}:{settings.splunk_port}"
                "/services/saved/searches/symphunk_obs_demo",
                data={"search": _DETECTION_SPL, "output_mode": "json"},
            )
            if r.status_code in (200, 201):
                click.echo("Updated symphunk_obs_demo to real CPU-spike detection SPL")
            else:
                click.echo(f"Warning: saved search update returned {r.status_code}", err=True)
        finally:
            await rest.aclose()

        click.echo(
            "\nReady. To trigger an investigation:\n"
            "  1. Wait up to 5 min for the cron, OR manually dispatch:\n"
            "     curl -sk -u admin:changeme123! -X POST "
            "https://localhost:8089/services/saved/searches/symphunk_obs_demo/dispatch"
            " -d 'dispatch.now=true&force_dispatch=true&trigger_actions=1'\n"
            "  2. symphunk run"
        )

    asyncio.run(_run())


@cli.command()
@click.option("--title", default="Synthetic anomaly spike", help="Incident title")
@click.option("--severity", default="low", type=click.Choice(["low", "medium", "high", "critical"]))
def seed(title: str, severity: str) -> None:
    """Insert a synthetic incident into KV Store for demo/testing."""
    from symphunk.splunk.kvstore import KVStore

    async def _seed() -> None:
        kv = KVStore()
        incident = {
            "id": str(uuid.uuid4()),
            "title": title,
            "severity": severity,
            "status": "New",
            "description": f"Synthetic incident for testing: {title}",
        }
        await kv.upsert("symphunk_incidents", incident, key_field="id")
        click.echo(f"Seeded incident id={incident['id']} title={title!r} severity={severity}")
        await kv.aclose()

    asyncio.run(_seed())


@cli.command("kv-init")
def kv_init() -> None:
    """Create the four KV Store collections."""
    from symphunk.splunk.kvstore import KVStore

    async def _init() -> None:
        kv = KVStore()
        await kv.init_collections()
        click.echo("KV collections initialised: symphunk_incidents, symphunk_evidence, symphunk_memory, symphunk_audit")
        await kv.aclose()

    asyncio.run(_init())


@cli.command("deploy-alert")
@click.option("--container", default="symphunk-splunk", help="Docker container name")
def deploy_alert(container: str) -> None:
    """Install the alert action app into Splunk and create the demo saved search."""
    import subprocess
    from pathlib import Path
    from symphunk.splunk.rest import SplunkREST
    from symphunk.splunk.alert_setup import reload_alert_actions_conf, create_demo_saved_search

    app_src = Path(__file__).parent / "splunk" / "alert_action" / "symphunk_alert_action"
    if not app_src.exists():
        click.echo(f"Alert action app not found at {app_src}", err=True)
        return

    dest = f"{container}:/opt/splunk/etc/apps/symphunk_alert_action"
    result = subprocess.run(
        ["docker", "cp", str(app_src), dest],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(f"docker cp failed:\n{result.stderr}", err=True)
        return
    click.echo(f"Alert action app copied to container ({dest})")

    subprocess.run(
        ["docker", "exec", container, "chown", "-R", "splunk:splunk",
         "/opt/splunk/etc/apps/symphunk_alert_action"],
        capture_output=True,
    )

    async def _setup() -> None:
        import httpx
        rest = SplunkREST()
        try:
            # Fast path: reload conf and check if the stanza appeared.
            await reload_alert_actions_conf(rest)
            try:
                await rest.get("/configs/conf-alert_actions/symphunk_ingest")
                click.echo("Alert action registered (no restart needed)")
            except httpx.HTTPStatusError:
                # New app not visible yet — Splunk needs a restart to scan etc/apps.
                click.echo("New app not yet visible — restarting Splunk (this takes ~90s)...")
                subprocess.run(
                    ["docker", "exec", container, "/opt/splunk/bin/splunk", "restart",
                     "-auth", "admin:changeme123!"],
                    capture_output=True,
                )
                # Poll health until Splunk is back.
                import time
                for _ in range(24):
                    time.sleep(5)
                    try:
                        r = await rest._client.get(
                            "http://localhost:8000/en-US/account/login"
                        )
                        if r.status_code == 200:
                            click.echo("Splunk back up")
                            break
                    except Exception:
                        pass
                else:
                    click.echo("Splunk did not come back in time — check container logs", err=True)
                    return

            await create_demo_saved_search(rest)
            click.echo("Demo saved search created: symphunk_obs_demo (cron: */5 * * * *)")
            click.echo("Alert action wired. Run 'symphunk run' to start the triage loop.")
        finally:
            await rest.aclose()

    asyncio.run(_setup())


@cli.command("clean-incidents")
@click.option("--status", default="New", help="Delete incidents with this status (default: New)")
def clean_incidents(status: str) -> None:
    """Delete all incidents in KV Store with the given status (default: New)."""
    from symphunk.splunk.kvstore import KVStore

    async def _clean() -> None:
        kv = KVStore()
        rows = await kv.query("symphunk_incidents", filter={"status": status})
        if not rows:
            click.echo(f"No incidents with status={status}")
            await kv.aclose()
            return
        for row in rows:
            key = row.get("_key") or row.get("id", "")
            await kv.delete_by_key("symphunk_incidents", key_field="_key", key_value=key)
        click.echo(f"Deleted {len(rows)} incidents with status={status}")
        await kv.aclose()

    asyncio.run(_clean())


async def _ensure_hec_index(rest, index_name: str) -> None:
    """Add index_name to the symphunk-hec token's allowed-indexes list if not already present."""
    from symphunk.config import settings
    # Splunk double-encodes the colon+slashes in the HEC token path
    base = f"https://{settings.splunk_host}:{settings.splunk_port}"
    path = "/servicesNS/nobody/launcher/data/inputs/http/http%3A%252F%252Fsymphunk-hec"
    try:
        r = await rest._client.get(f"{base}{path}?output_mode=json")
        content = r.json().get("entry", [{}])[0].get("content", {})
        current = content.get("indexes", [])
        if isinstance(current, str):
            current = [i.strip() for i in current.split(",") if i.strip()]
        if index_name not in current:
            new_indexes = ",".join(current + [index_name])
            await rest._client.post(
                f"{base}{path}",
                data={"index": "main", "indexes": new_indexes, "output_mode": "json"},
            )
            click.echo(f"HEC token updated: added {index_name} to allowed indexes")
    except Exception as exc:
        click.echo(f"Warning: could not auto-update HEC token indexes ({exc}). "
                   f"If injection fails, add '{index_name}' manually in Splunk Web → Settings → Data Inputs → HTTP Event Collector → symphunk-hec.", err=True)


@cli.command("load-sec-data")
def load_sec_data() -> None:
    """Inject security attack scenario into index=symphunk_sec_demo and update the detection search."""
    from symphunk.config import settings
    from symphunk.splunk.rest import SplunkREST
    from symphunk.splunk.sec_sample_data import ensure_index, inject

    # Detection SPL: group auth events by src_ip; flag IPs with > 5 failures or any success after failures.
    # Two incidents produced:
    #   185.220.101.45 → severity=high (50 failures + 3 successes)
    #   10.0.1.50      → severity=medium (15 failures, 0 successes)
    _SEC_DETECTION_SPL = (
        "index=symphunk_sec_demo earliest=-30m latest=now() event_type=authentication"
        " | stats count(eval(action=\"failure\")) AS failures"
        " count(eval(action=\"success\")) AS successes"
        " values(dest_host) AS targets"
        " BY src_ip"
        " | where failures > 5 OR successes > 0"
        " | eval title=\"Auth anomaly from \".src_ip,"
        " severity=if(failures > 20 AND successes > 0, \"high\", \"medium\"),"
        " description=failures.\" failures, \".successes.\" successes from \".src_ip,"
        " agent_type=\"sec\""
        " | fields title, severity, description, src_ip, agent_type, failures, successes"
    )

    async def _run() -> None:
        rest = SplunkREST()
        try:
            await ensure_index(rest._client)
            click.echo("Index symphunk_sec_demo ready")

            # Ensure the HEC token is authorised to write to this index.
            # The original token was minted with a fixed allowed-indexes list; add symphunk_sec_demo if missing.
            await _ensure_hec_index(rest, "symphunk_sec_demo")

            count = await inject(settings.hec_token)
            click.echo(f"Injected {count} security sample events (brute-force + lateral movement scenario)")

            r = await rest._client.post(
                f"https://{settings.splunk_host}:{settings.splunk_port}"
                "/services/saved/searches/symphunk_sec_demo",
                data={"search": _SEC_DETECTION_SPL, "output_mode": "json"},
            )
            if r.status_code in (200, 201):
                click.echo("Updated symphunk_sec_demo to real auth-anomaly detection SPL")
            else:
                click.echo(f"Warning: saved search update returned {r.status_code}", err=True)
        finally:
            await rest.aclose()

        click.echo(
            "\nReady. To trigger a security investigation:\n"
            "  1. Wait up to 5 min for the cron, OR manually dispatch:\n"
            "     curl -sk -u admin:$SPLUNK_PASSWORD -X POST "
            "https://localhost:8089/services/saved/searches/symphunk_sec_demo/dispatch"
            " -d 'dispatch.now=true&force_dispatch=true&trigger_actions=1'\n"
            "  2. symphunk run"
        )

    asyncio.run(_run())


@cli.command("deploy-sec-alert")
@click.option("--container", default="symphunk-splunk", help="Docker container name")
def deploy_sec_alert(container: str) -> None:
    """Create the symphunk_sec_demo saved search (requires alert action app already installed)."""
    from symphunk.splunk.rest import SplunkREST
    from symphunk.splunk.alert_setup import create_sec_saved_search

    async def _setup() -> None:
        rest = SplunkREST()
        try:
            await create_sec_saved_search(rest)
            click.echo("Security saved search created: symphunk_sec_demo (cron: */5 * * * *)")
            click.echo("Run 'symphunk load-sec-data' to inject sample events, then 'symphunk run'.")
        finally:
            await rest.aclose()

    asyncio.run(_setup())


@cli.command("deploy-sec-dashboard")
def deploy_sec_dashboard() -> None:
    """Push the security proof-of-work dashboard to Splunk."""
    from symphunk.splunk.rest import SplunkREST

    async def _deploy() -> None:
        import httpx as _httpx
        dash_path = Path(__file__).parent.parent / "dashboards" / "symphunk_sec.json"
        if not dash_path.exists():
            click.echo(f"Dashboard file not found: {dash_path}", err=True)
            return

        rest = SplunkREST()
        json_def = dash_path.read_text()
        eai_data = (
            '<dashboard version="2" theme="dark">'
            "<label>Symphunk — Security Proof-of-Work</label>"
            "<description>Live evidence from Symphunk SecAgent investigations</description>"
            f"<definition><![CDATA[{json_def}]]></definition>"
            "</dashboard>"
        )

        try:
            try:
                await rest.post("/data/ui/views/symphunk_sec", {"eai:data": eai_data})
                click.echo("Dashboard updated: symphunk_sec")
            except _httpx.HTTPStatusError as exc:
                body = exc.response.text
                if exc.response.status_code in (404, 400) and "Could not find" in body:
                    await rest.post(
                        "/data/ui/views",
                        {"name": "symphunk_sec", "eai:data": eai_data},
                    )
                    click.echo("Dashboard created: symphunk_sec")
                else:
                    click.echo(f"Deploy failed ({exc.response.status_code}): {body[:200]}", err=True)
                    raise
            click.echo("Open: http://localhost:8000/en-US/app/search/symphunk_sec")
        finally:
            await rest.aclose()

    asyncio.run(_deploy())


@cli.command("load-devex-data")
def load_devex_data() -> None:
    """Inject deployment regression scenario into index=symphunk_devex_demo and update the detection search."""
    from symphunk.config import settings
    from symphunk.splunk.rest import SplunkREST
    from symphunk.splunk.devex_sample_data import ensure_index, inject

    # Detection SPL: find services with elevated error rates + a recent deployment event.
    # Two incidents produced:
    #   payment-service   → max_error_rate 8.4% > 3% threshold (severity=high)
    #   notification-service → max_error_rate 5.0% > 3% threshold (severity=medium, false alarm)
    _DEVEX_DETECTION_SPL = (
        "index=symphunk_devex_demo earliest=-30m latest=now() event_type=service_metric"
        " | stats avg(error_rate) AS avg_error_rate max(error_rate) AS max_error_rate"
        " avg(latency_p99) AS avg_latency count AS event_count"
        " BY service"
        " | where max_error_rate > 0.03 AND event_count >= 3"
        ' | eval title="Deployment regression check: ".service,'
        ' severity=if(max_error_rate > 0.07, "high", "medium"),'
        ' description="Error rate ".round(max_error_rate*100,1)."% detected on ".service." — checking for deploy correlation",'
        ' agent_type="devex"'
        " | fields title, severity, description, service, avg_error_rate, max_error_rate, avg_latency, agent_type"
    )

    async def _run() -> None:
        rest = SplunkREST()
        try:
            await ensure_index(rest._client)
            click.echo("Index symphunk_devex_demo ready")

            await _ensure_hec_index(rest, "symphunk_devex_demo")

            count = await inject(settings.hec_token)
            click.echo(f"Injected {count} devex sample events (2 services: regression + false alarm)")

            r = await rest._client.post(
                f"https://{settings.splunk_host}:{settings.splunk_port}"
                "/services/saved/searches/symphunk_devex_demo",
                data={"search": _DEVEX_DETECTION_SPL, "output_mode": "json"},
            )
            if r.status_code in (200, 201):
                click.echo("Updated symphunk_devex_demo to real deployment-regression detection SPL")
            else:
                click.echo(f"Warning: saved search update returned {r.status_code}", err=True)
        finally:
            await rest.aclose()

        click.echo(
            "\nReady. To trigger a devex investigation:\n"
            "  1. Wait up to 5 min for the cron, OR manually dispatch:\n"
            "     curl -sk -u admin:$SPLUNK_PASSWORD -X POST "
            "https://localhost:8089/services/saved/searches/symphunk_devex_demo/dispatch"
            " -d 'dispatch.now=true&force_dispatch=true&trigger_actions=1'\n"
            "  2. symphunk run"
        )

    asyncio.run(_run())


@cli.command("deploy-devex-alert")
@click.option("--container", default="symphunk-splunk", help="Docker container name")
def deploy_devex_alert(container: str) -> None:
    """Create the symphunk_devex_demo saved search (requires alert action app already installed)."""
    from symphunk.splunk.rest import SplunkREST
    from symphunk.splunk.alert_setup import create_devex_saved_search

    async def _setup() -> None:
        rest = SplunkREST()
        try:
            await create_devex_saved_search(rest)
            click.echo("DevEx saved search created: symphunk_devex_demo (cron: */5 * * * *)")
            click.echo("Run 'symphunk load-devex-data' to inject sample events, then 'symphunk run'.")
        finally:
            await rest.aclose()

    asyncio.run(_setup())


@cli.command("deploy-devex-dashboard")
def deploy_devex_dashboard() -> None:
    """Push the Platform & Developer Experience proof-of-work dashboard to Splunk."""
    from symphunk.splunk.rest import SplunkREST

    async def _deploy() -> None:
        import httpx as _httpx
        dash_path = Path(__file__).parent.parent / "dashboards" / "symphunk_devex.json"
        if not dash_path.exists():
            click.echo(f"Dashboard file not found: {dash_path}", err=True)
            return

        rest = SplunkREST()
        json_def = dash_path.read_text()
        eai_data = (
            '<dashboard version="2" theme="dark">'
            "<label>Symphunk — Platform &amp; Developer Experience</label>"
            "<description>Live evidence from Symphunk DevExAgent deployment regression analysis</description>"
            f"<definition><![CDATA[{json_def}]]></definition>"
            "</dashboard>"
        )

        try:
            try:
                await rest.post("/data/ui/views/symphunk_devex", {"eai:data": eai_data})
                click.echo("Dashboard updated: symphunk_devex")
            except _httpx.HTTPStatusError as exc:
                body = exc.response.text
                if exc.response.status_code in (404, 400) and "Could not find" in body:
                    await rest.post(
                        "/data/ui/views",
                        {"name": "symphunk_devex", "eai:data": eai_data},
                    )
                    click.echo("Dashboard created: symphunk_devex")
                else:
                    click.echo(f"Deploy failed ({exc.response.status_code}): {body[:200]}", err=True)
                    raise
            click.echo("Open: http://localhost:8000/en-US/app/search/symphunk_devex")
        finally:
            await rest.aclose()

    asyncio.run(_deploy())


@cli.command("deploy-dashboard")
def deploy_dashboard() -> None:
    """Push the proof-of-work dashboard to Splunk."""
    from symphunk.splunk.rest import SplunkREST

    async def _deploy() -> None:
        import httpx as _httpx
        dash_path = Path(__file__).parent.parent / "dashboards" / "symphunk_obs.json"
        if not dash_path.exists():
            click.echo(f"Dashboard file not found: {dash_path}", err=True)
            return

        rest = SplunkREST()
        # Ensure KV Store inputlookup transforms exist (idempotent).
        for coll in ("symphunk_incidents", "symphunk_evidence"):
            try:
                await rest.post(
                    "/data/transforms/lookups",
                    {"name": coll, "collection": coll,
                     "external_type": "kvstore", "fields_list": "*"},
                )
            except _httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409:
                    raise  # 409 = already exists, that's fine
        click.echo("KV Store lookup transforms registered")

        # Dashboard Studio format: XML envelope with JSON inside CDATA.
        json_def = dash_path.read_text()
        eai_data = (
            '<dashboard version="2" theme="dark">'
            "<label>Symphunk — Observability Proof-of-Work</label>"
            "<description>Live evidence from Symphunk ObsAgent investigations</description>"
            f"<definition><![CDATA[{json_def}]]></definition>"
            "</dashboard>"
        )

        try:
            # Try update; if the view doesn't exist yet, create it.
            try:
                await rest.post("/data/ui/views/symphunk_obs", {"eai:data": eai_data})
                click.echo("Dashboard updated: symphunk_obs")
            except _httpx.HTTPStatusError as exc:
                body = exc.response.text
                if exc.response.status_code in (404, 400) and "Could not find" in body:
                    await rest.post(
                        "/data/ui/views",
                        {"name": "symphunk_obs", "eai:data": eai_data},
                    )
                    click.echo("Dashboard created: symphunk_obs")
                else:
                    click.echo(f"Deploy failed ({exc.response.status_code}): {body[:200]}", err=True)
                    raise
            click.echo("Open: http://localhost:8000/en-US/app/search/symphunk_obs")
        finally:
            await rest.aclose()

    asyncio.run(_deploy())


