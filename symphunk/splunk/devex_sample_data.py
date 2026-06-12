from __future__ import annotations

import json
import logging
import time

import httpx

from symphunk.config import settings

logger = logging.getLogger(__name__)

INDEX = "symphunk_devex_demo"
_SOURCETYPE = "_json"


def _make_events() -> list[dict]:
    """
    Build ~40 events representing two deployment scenarios:

    Scenario A — payment-service v2.3.1 (REGRESSION):
      Baseline (T-22m → T-13m): error_rate ~0.2%, latency ~120ms (healthy)
      Deployment event (T-12m): version 2.3.1 deployed
      Regression (T-11m → T-3m): error_rate ~8.4%, latency ~850ms

    Scenario B — notification-service v1.8.0 (FALSE ALARM):
      Pre-deploy elevated (T-22m → T-16m): error_rate ~4.5%, latency ~300ms (already degraded)
      Deployment event (T-15m): version 1.8.0 deployed
      Post-deploy (T-14m → T-5m): error_rate ~5.0%, latency ~320ms (barely changed)

    Stable services for blast-radius check (api-gateway-01, web-frontend-01):
      error_rate ~0.1% throughout — confirms regression is service-specific.
    """
    now = time.time()
    events: list[dict] = []

    # --- Scenario A: payment-service — healthy baseline ---
    baseline_offsets = [22, 20, 18, 16, 14.5, 13.5]
    for offset in baseline_offsets:
        events.append({
            "time": now - offset * 60,
            "host": "pay-svc-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "service_metric",
                "service": "payment-service",
                "version": "2.3.0",
                "error_rate": 0.002,
                "latency_p99": 118 + (offset % 3) * 4,
                "req_count": 480 + int(offset) * 5,
                "host": "pay-svc-01",
            },
        })

    # --- Scenario A: deployment event ---
    events.append({
        "time": now - 12 * 60,
        "host": "pay-svc-01",
        "sourcetype": _SOURCETYPE,
        "index": INDEX,
        "event": {
            "event_type": "deployment",
            "service": "payment-service",
            "version": "2.3.1",
            "action": "deploy_complete",
            "host": "pay-svc-01",
            "deploy_by": "ci-pipeline",
        },
    })

    # --- Scenario A: regression window ---
    regression_offsets_and_rates = [
        (11.0, 0.072, 720),
        (10.0, 0.082, 850),
        (9.0,  0.088, 890),
        (8.0,  0.085, 860),
        (7.0,  0.083, 840),
        (6.0,  0.086, 870),
        (5.0,  0.084, 855),
        (4.0,  0.081, 820),
        (3.0,  0.079, 800),
    ]
    for offset, error_rate, latency in regression_offsets_and_rates:
        events.append({
            "time": now - offset * 60,
            "host": "pay-svc-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "service_metric",
                "service": "payment-service",
                "version": "2.3.1",
                "error_rate": error_rate,
                "latency_p99": latency,
                "req_count": 430,
                "host": "pay-svc-01",
            },
        })

    # --- Scenario B: notification-service — already elevated before deploy ---
    pre_deploy_offsets = [22, 20, 18.5, 17, 15.5]
    for offset in pre_deploy_offsets:
        events.append({
            "time": now - offset * 60,
            "host": "notify-svc-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "service_metric",
                "service": "notification-service",
                "version": "1.7.9",
                "error_rate": 0.043 + (offset % 5) * 0.002,
                "latency_p99": 295 + int(offset) % 20,
                "req_count": 210,
                "host": "notify-svc-01",
            },
        })

    # --- Scenario B: deployment event ---
    events.append({
        "time": now - 15 * 60,
        "host": "notify-svc-01",
        "sourcetype": _SOURCETYPE,
        "index": INDEX,
        "event": {
            "event_type": "deployment",
            "service": "notification-service",
            "version": "1.8.0",
            "action": "deploy_complete",
            "host": "notify-svc-01",
            "deploy_by": "ci-pipeline",
        },
    })

    # --- Scenario B: post-deploy (barely changed — false alarm) ---
    post_deploy_offsets_b = [14, 12.5, 11, 9.5, 8, 6.5]
    for offset in post_deploy_offsets_b:
        events.append({
            "time": now - offset * 60,
            "host": "notify-svc-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "service_metric",
                "service": "notification-service",
                "version": "1.8.0",
                "error_rate": 0.048 + (int(offset * 10) % 5) * 0.001,
                "latency_p99": 310 + int(offset) % 25,
                "req_count": 205,
                "host": "notify-svc-01",
            },
        })

    # --- Stable services: api-gateway-01 (confirms regression is service-specific) ---
    for offset in [20, 16, 12, 8, 4]:
        events.append({
            "time": now - offset * 60,
            "host": "api-gateway-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "service_metric",
                "service": "api-gateway-01",
                "version": "3.1.0",
                "error_rate": 0.001,
                "latency_p99": 48 + offset % 8,
                "req_count": 920,
                "host": "api-gateway-01",
            },
        })

    # --- Stable services: web-frontend-01 ---
    for offset in [19, 15, 11, 7, 3]:
        events.append({
            "time": now - offset * 60,
            "host": "web-frontend-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "service_metric",
                "service": "web-frontend-01",
                "version": "5.2.1",
                "error_rate": 0.001,
                "latency_p99": 52 + offset % 10,
                "req_count": 1200,
                "host": "web-frontend-01",
            },
        })

    return events


async def ensure_index(rest_client: httpx.AsyncClient) -> None:
    url = f"https://{settings.splunk_host}:{settings.splunk_port}/services/data/indexes"
    r = await rest_client.post(url, data={"name": INDEX, "datatype": "event", "output_mode": "json"})
    if r.status_code == 409:
        logger.debug("Index already exists: %s", INDEX)
    else:
        r.raise_for_status()
        logger.info("Created index: %s", INDEX)


async def inject(hec_token: str) -> int:
    url = f"{settings.hec_url}/services/collector/event"
    events = _make_events()
    payload = "\n".join(json.dumps(e) for e in events)

    async with httpx.AsyncClient(verify=False) as client:
        r = await client.post(
            url,
            content=payload.encode(),
            headers={
                "Authorization": f"Splunk {hec_token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        r.raise_for_status()
        result = r.json()
        if result.get("text") != "Success":
            raise RuntimeError(f"HEC returned error: {result}")

    logger.info("Injected %d devex sample events → index=%s", len(events), INDEX)
    return len(events)
