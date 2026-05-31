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
    """Start the orchestrator polling loop."""
    from symphunk.splunk.kvstore import KVStore
    from symphunk.orchestrator.poller import Poller
    from symphunk.orchestrator.dispatcher import Dispatcher

    async def _run() -> None:
        kv = KVStore()
        poller = Poller(kv)
        dispatcher = Dispatcher(kv)

        async def on_incident(incident: dict) -> None:
            await dispatcher.dispatch(incident, _agent_factory)

        await poller.run_forever(on_incident)

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


@cli.command("deploy-dashboard")
def deploy_dashboard() -> None:
    """Push the proof-of-work dashboard to Splunk."""
    from symphunk.splunk.rest import SplunkREST

    async def _deploy() -> None:
        dash_path = Path(__file__).parent.parent / "dashboards" / "symphunk_obs.json"
        if not dash_path.exists():
            click.echo(f"Dashboard file not found: {dash_path}", err=True)
            return
        rest = SplunkREST()
        definition = json.loads(dash_path.read_text())
        await rest.post("/data/ui/views/symphunk_obs", {"eai:data": json.dumps(definition)})
        click.echo("Dashboard deployed: symphunk_obs")
        await rest.aclose()

    asyncio.run(_deploy())


def _agent_factory(incident: dict):
    raise NotImplementedError("Agent factory not wired — implement in Phase 3")
