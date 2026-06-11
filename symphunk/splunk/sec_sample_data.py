from __future__ import annotations

import json
import logging
import time

import httpx

from symphunk.config import settings

logger = logging.getLogger(__name__)

INDEX = "symphunk_sec_demo"
_SOURCETYPE = "_json"


def _make_events() -> list[dict]:
    """
    Build ~65 security events representing a credential-stuffing + lateral-movement attack:

    Act 1 (T-18m → T-10m): 50 auth failures from 185.220.101.45 (Tor exit node) against web-frontend-01
    Act 2 (T-9m):           1 auth success from same IP (account compromised)
    Act 2b (T-8m):          2 more successes (attacker confirms access)
    Act 3 (T-7m → T-5m):   4 SMB connections from web-frontend-01 → db-server-01:445 (lateral movement)

    Second cluster (T-15m → T-12m): 15 auth failures from internal 10.0.1.50 (misconfigured scanner, no breach)
    """
    now = time.time()
    events: list[dict] = []

    # --- Act 1: brute-force auth failures from external Tor exit node ---
    failure_offsets = [
        18, 17.8, 17.5, 17.2, 17.0,  # slow start
        16.8, 16.5, 16.2, 16.0, 15.8,
        15.5, 15.2, 15.0, 14.8, 14.5,
        14.2, 14.0, 13.8, 13.5, 13.2,
        13.0, 12.8, 12.5, 12.2, 12.0,
        11.8, 11.5, 11.2, 11.0, 10.8,  # rate accelerates
        10.6, 10.4, 10.2, 10.0, 9.8,
        9.6, 9.4, 9.2, 9.0, 8.8,
        8.6, 8.4, 8.2, 8.0, 7.8,
        7.6, 7.4, 7.2, 7.0, 6.8,  # 50 failures total
    ]
    usernames = [
        "admin", "administrator", "root", "svc_account", "deploy",
        "backup", "jenkins", "splunk", "monitor", "webapp",
    ]
    for i, offset in enumerate(failure_offsets):
        events.append({
            "time": now - offset * 60,
            "host": "web-frontend-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "authentication",
                "action": "failure",
                "src_ip": "185.220.101.45",
                "dest_host": "web-frontend-01",
                "dest_port": 443,
                "user": usernames[i % len(usernames)],
                "app": "ssh",
                "bytes_out": 0,
                "reason": "invalid_credentials",
            },
        })

    # --- Act 2: successful breach from same IP ---
    for offset, user in [(9.0, "svc_account"), (8.5, "svc_account"), (8.0, "deploy")]:
        events.append({
            "time": now - offset * 60,
            "host": "web-frontend-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "authentication",
                "action": "success",
                "src_ip": "185.220.101.45",
                "dest_host": "web-frontend-01",
                "dest_port": 443,
                "user": user,
                "app": "ssh",
                "bytes_out": 1240,
                "reason": "authenticated",
            },
        })

    # --- Act 3: SMB lateral movement web-frontend-01 → db-server-01 ---
    smb_steps = [
        (7.0, "SmbConnect",    512,    4096),
        (6.5, "SmbTreeConnect",256,    2048),
        (6.2, "SmbReadFile",   128, 1024000),  # large read — data staging
        (5.5, "SmbWriteFile",  256,  512000),  # writes back
    ]
    for offset, smb_cmd, bytes_in, bytes_out in smb_steps:
        events.append({
            "time": now - offset * 60,
            "host": "web-frontend-01",
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "network",
                "action": "allowed",
                "src_ip": "10.0.1.10",        # web-frontend-01's internal IP
                "src_host": "web-frontend-01",
                "dest_ip": "10.0.1.20",
                "dest_host": "db-server-01",
                "dest_port": 445,
                "protocol": "SMB",
                "smb_command": smb_cmd,
                "bytes_in": bytes_in,
                "bytes_out": bytes_out,
                "user": "svc_account",
            },
        })

    # --- Second cluster: internal misconfigured scanner (benign) ---
    internal_offsets = [15, 14.5, 14.0, 13.5, 13.0, 12.8, 12.5, 12.2, 12.0, 11.8, 11.5, 11.2, 11.0, 10.8, 10.5]
    scanner_targets = ["web-frontend-01", "web-frontend-02", "api-gateway-01", "db-server-01", "monitoring-01"]
    for i, offset in enumerate(internal_offsets):
        events.append({
            "time": now - offset * 60,
            "host": scanner_targets[i % len(scanner_targets)],
            "sourcetype": _SOURCETYPE,
            "index": INDEX,
            "event": {
                "event_type": "authentication",
                "action": "failure",
                "src_ip": "10.0.1.50",
                "dest_host": scanner_targets[i % len(scanner_targets)],
                "dest_port": 22,
                "user": "admin",
                "app": "ssh",
                "bytes_out": 0,
                "reason": "invalid_credentials",
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

    logger.info("Injected %d security sample events → index=%s", len(events), INDEX)
    return len(events)
