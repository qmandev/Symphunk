from __future__ import annotations

import json
import logging
import time

import httpx

from symphunk.config import settings

logger = logging.getLogger(__name__)

INDEX = "symphunk_demo"
_SOURCETYPE = "_json"


def _make_events() -> list[dict]:
    """
    Build 30 events: 5 baseline time-points (-20m→-12m) + 5 anomaly time-points (-10m→now),
    3 hosts each. CPU z-score ≈ 69 at peak — unambiguous anomaly.
    """
    now = time.time()
    events: list[dict] = []

    # --- Baseline: low CPU, no errors ---
    # host is top-level in the HEC payload so Splunk metadata host = our host name.
    # Fields inside "event" are extracted by _json sourcetype KV_MODE=json.
    baseline_hosts = [
        ("web-frontend-01", "web-frontend", 23.2, 41.0, 102.0, 0),
        ("web-frontend-02", "web-frontend", 21.5, 38.5,  97.0, 0),
        ("api-gateway-01",  "api-gateway",  17.3, 33.0, 198.0, 0),
    ]
    for offset_min in range(20, 10, -2):  # -20m, -18m, -16m, -14m, -12m
        t = now - offset_min * 60
        for host, service, cpu, mem, rps, errs in baseline_hosts:
            events.append({
                "time": t,
                "host": host,          # top-level → Splunk metadata host field
                "sourcetype": _SOURCETYPE,
                "index": INDEX,
                "event": {
                    "service": service,
                    "cpu_pct": cpu + (20 - offset_min) * 0.1,  # tiny drift
                    "mem_pct": mem,
                    "req_per_sec": rps,
                    "error_count": errs,
                },
            })

    # --- Anomaly: CPU spike on web-frontend, cascade to api-gateway ---
    anomaly_steps = [
        # (min_ago, fe01_cpu, fe01_errs, fe01_rps,  fe02_cpu, fe02_errs, fe02_rps,  gw_cpu, gw_errs, gw_rps)
        (10, 86.0,  28, 45.0,  83.0, 11, 42.0,  35.0,  5, 155.0),
        ( 8, 90.5,  42, 22.0,  87.5, 17, 28.0,  41.0,  9, 120.0),
        ( 6, 92.8,  51, 12.0,  89.0, 20, 18.0,  45.5, 11,  88.0),
        ( 4, 93.4,  58,  7.0,  90.1, 22, 12.0,  47.0, 13,  64.0),
        ( 2, 94.1,  63,  4.0,  90.6, 24,  9.0,  48.3, 14,  51.0),
    ]
    for (min_ago, fe01_cpu, fe01_errs, fe01_rps,
                  fe02_cpu, fe02_errs, fe02_rps,
                  gw_cpu,  gw_errs,  gw_rps) in anomaly_steps:
        t = now - min_ago * 60
        events += [
            {"time": t, "host": "web-frontend-01", "sourcetype": _SOURCETYPE, "index": INDEX, "event": {
                "service": "web-frontend",
                "cpu_pct": fe01_cpu, "mem_pct": 87.0, "req_per_sec": fe01_rps, "error_count": fe01_errs,
            }},
            {"time": t, "host": "web-frontend-02", "sourcetype": _SOURCETYPE, "index": INDEX, "event": {
                "service": "web-frontend",
                "cpu_pct": fe02_cpu, "mem_pct": 80.5, "req_per_sec": fe02_rps, "error_count": fe02_errs,
            }},
            {"time": t, "host": "api-gateway-01", "sourcetype": _SOURCETYPE, "index": INDEX, "event": {
                "service": "api-gateway",
                "cpu_pct": gw_cpu, "mem_pct": 51.0, "req_per_sec": gw_rps, "error_count": gw_errs,
            }},
        ]

    return events


async def ensure_index(rest_client: httpx.AsyncClient) -> None:
    """Create symphunk_demo index if it does not already exist."""
    url = f"https://{settings.splunk_host}:{settings.splunk_port}/services/data/indexes"
    r = await rest_client.post(url, data={"name": INDEX, "datatype": "event", "output_mode": "json"})
    if r.status_code == 409:
        logger.debug("Index already exists: %s", INDEX)
    else:
        r.raise_for_status()
        logger.info("Created index: %s", INDEX)


async def inject(hec_token: str) -> int:
    """Send all sample events to Splunk via HEC. Returns number of events sent."""
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

    logger.info("Injected %d sample events → index=%s", len(events), INDEX)
    return len(events)
