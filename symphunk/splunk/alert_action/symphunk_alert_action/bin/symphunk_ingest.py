#!/usr/bin/env python3
"""
Splunk custom alert action: write the triggering alert to symphunk_incidents KV Store.
Splunk calls this script with a JSON payload on stdin when a saved search fires.
Uses the session_key from the payload for auth — no hard-coded credentials.
"""
from __future__ import annotations

import datetime
import json
import ssl
import sys
import urllib.error
import urllib.request
import uuid


def _kv_batch_save(server_uri: str, session_key: str, record: dict) -> None:
    url = (
        f"{server_uri}/servicesNS/nobody/search"
        "/storage/collections/data/symphunk_incidents/batch_save"
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        data=json.dumps([record]).encode(),
        headers={
            "Authorization": f"Splunk {session_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        sys.stderr.write(
            f"[symphunk_ingest] KV write failed {exc.code}: {exc.read().decode()}\n"
        )
        raise


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"[symphunk_ingest] Failed to parse stdin JSON: {exc}\n")
        sys.exit(1)

    session_key = payload.get("session_key", "")
    server_uri = payload.get("server_uri", "https://localhost:8089")
    search_name = payload.get("search_name", "unknown")
    result = payload.get("result", {})

    if not session_key:
        sys.stderr.write("[symphunk_ingest] No session_key in payload\n")
        sys.exit(1)

    severity = result.get("severity") or result.get("urgency") or "medium"
    if severity not in ("low", "medium", "high", "critical"):
        severity = "medium"

    title = result.get("title") or search_name
    description = result.get("description") or f"Alert fired: {search_name}"

    key = str(uuid.uuid4())
    incident = {
        "_key": key,
        "id": key,
        "title": title,
        "severity": severity,
        "status": "New",
        "description": description,
        "source_search": search_name,
        "alert_time": datetime.datetime.utcnow().isoformat() + "Z",
        "raw_result": json.dumps(result),
    }

    _kv_batch_save(server_uri, session_key, incident)
    sys.stdout.write(
        f"[symphunk_ingest] Incident created id={key} title={title!r} severity={severity}\n"
    )


if __name__ == "__main__":
    main()
