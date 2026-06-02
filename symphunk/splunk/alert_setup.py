from __future__ import annotations

import logging

import httpx

from symphunk.splunk.rest import SplunkREST

logger = logging.getLogger(__name__)

_DEMO_SEARCH_NAME = "symphunk_obs_demo"
# Always returns 1 result so the alert fires on every scheduled run — good for demo.
# In production replace with real SPL (anomaly detection on _internal metrics, etc.).
_DEMO_SPL = (
    "| makeresults"
    ' | eval title="CPU spike on web-frontend",'
    ' severity="medium",'
    ' description="Automated: high CPU utilization detected on web-frontend nodes"'
)


async def reload_alert_actions_conf(rest: SplunkREST) -> None:
    """Re-read alert_actions.conf from all apps without a Splunk restart."""
    try:
        await rest.get("/configs/conf-alert_actions/_reload")
        logger.info("alert_actions.conf reloaded")
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "conf reload returned %s — alert action may need a Splunk restart to appear",
            exc.response.status_code,
        )


async def create_demo_saved_search(
    rest: SplunkREST, *, name: str = _DEMO_SEARCH_NAME
) -> None:
    """Create the demo saved search that fires symphunk_ingest every 5 minutes."""
    data = {
        "name": name,
        "search": _DEMO_SPL,
        "alert.track": "1",
        "alert_type": "always",
        "alert.suppress": "0",
        "actions": "symphunk_ingest",
        "action.symphunk_ingest": "1",
        "cron_schedule": "*/5 * * * *",
        "is_scheduled": "1",
        "dispatch.earliest_time": "-5m",
        "dispatch.latest_time": "now",
    }
    try:
        await rest.post("/saved/searches", data)
        logger.info("Demo saved search created: %s", name)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            logger.info("Demo saved search already exists: %s", name)
        else:
            raise
