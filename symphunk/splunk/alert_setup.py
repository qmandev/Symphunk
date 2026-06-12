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

_SEC_SEARCH_NAME = "symphunk_sec_demo"
# Placeholder SPL — load-sec-data replaces this with real detection SPL after injecting events.
_SEC_SPL_PLACEHOLDER = (
    "| makeresults"
    ' | eval title="Auth anomaly detected",'
    ' severity="medium",'
    ' agent_type="sec",'
    ' description="Placeholder: load-sec-data will replace this with real detection SPL"'
)

_DEVEX_SEARCH_NAME = "symphunk_devex_demo"
# Placeholder SPL — load-devex-data replaces this with real detection SPL after injecting events.
_DEVEX_SPL_PLACEHOLDER = (
    "| makeresults"
    ' | eval title="Deployment regression check",'
    ' severity="medium",'
    ' agent_type="devex",'
    ' service="unknown",'
    ' description="Placeholder: load-devex-data will replace this with real detection SPL"'
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
    """Create the obs demo saved search that fires symphunk_ingest every 5 minutes."""
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


async def create_sec_saved_search(
    rest: SplunkREST, *, name: str = _SEC_SEARCH_NAME
) -> None:
    """Create the security demo saved search that fires symphunk_ingest every 5 minutes."""
    data = {
        "name": name,
        "search": _SEC_SPL_PLACEHOLDER,
        "alert.track": "1",
        "alert_type": "always",
        "alert.suppress": "0",
        "actions": "symphunk_ingest",
        "action.symphunk_ingest": "1",
        "cron_schedule": "*/5 * * * *",
        "is_scheduled": "1",
        "dispatch.earliest_time": "-30m",
        "dispatch.latest_time": "now",
    }
    try:
        await rest.post("/saved/searches", data)
        logger.info("Sec demo saved search created: %s", name)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            logger.info("Sec demo saved search already exists: %s", name)
        else:
            raise


async def create_devex_saved_search(
    rest: SplunkREST, *, name: str = _DEVEX_SEARCH_NAME
) -> None:
    """Create the devex demo saved search that fires symphunk_ingest every 5 minutes."""
    data = {
        "name": name,
        "search": _DEVEX_SPL_PLACEHOLDER,
        "alert.track": "1",
        "alert_type": "always",
        "alert.suppress": "0",
        "actions": "symphunk_ingest",
        "action.symphunk_ingest": "1",
        "cron_schedule": "*/5 * * * *",
        "is_scheduled": "1",
        "dispatch.earliest_time": "-30m",
        "dispatch.latest_time": "now",
    }
    try:
        await rest.post("/saved/searches", data)
        logger.info("DevEx demo saved search created: %s", name)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            logger.info("DevEx demo saved search already exists: %s", name)
        else:
            raise
