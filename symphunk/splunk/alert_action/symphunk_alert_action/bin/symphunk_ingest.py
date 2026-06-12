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


def _kv_batch_save(server_uri: str, session_key: str, records: list) -> None:
    """Write one or more incident records to KV Store in a single batch_save call."""
    url = (
        f"{server_uri}/servicesNS/nobody/search"
        "/storage/collections/data/symphunk_incidents/batch_save"
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        data=json.dumps(records).encode(),
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


def _results_from_api(server_uri: str, session_key: str, sid: str) -> list[dict]:
    """Fetch all result rows for a search job via the REST API (JSON, all rows)."""
    url = f"{server_uri}/services/search/v2/jobs/{sid}/results?output_mode=json&count=0"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Splunk {session_key}"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("results", [])
    except Exception as exc:
        sys.stderr.write(f"[symphunk_ingest] Could not fetch results via API: {exc}\n")
        return []


def _make_incident(result: dict, search_name: str) -> dict:
    severity = result.get("severity") or result.get("urgency") or "medium"
    if severity not in ("low", "medium", "high", "critical"):
        severity = "medium"
    title = result.get("title") or search_name
    description = result.get("description") or f"Alert fired: {search_name}"
    agent_type = result.get("agent_type", "obs")
    src_ip = result.get("src_ip", "")
    key = str(uuid.uuid4())
    return {
        "_key": key,
        "id": key,
        "title": title,
        "severity": severity,
        "status": "New",
        "description": description,
        "source_search": search_name,
        "agent_type": agent_type,
        "src_ip": src_ip,
        "alert_time": datetime.datetime.utcnow().isoformat() + "Z",
        "raw_result": json.dumps(result),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"[symphunk_ingest] Failed to parse stdin JSON: {exc}\n")
        sys.exit(1)

    session_key = payload.get("session_key", "")
    server_uri = payload.get("server_uri", "https://localhost:8089")
    search_name = payload.get("search_name", "unknown")

    if not session_key:
        sys.stderr.write("[symphunk_ingest] No session_key in payload\n")
        sys.exit(1)

    # Fetch all result rows via REST API (handles Splunk's binary .srs.zst results_file).
    # Fall back to the single-row `result` field if the API call fails.
    sid = payload.get("sid", "")
    results = _results_from_api(server_uri, session_key, sid) if sid else []
    if not results:
        result = payload.get("result", {})
        results = [result] if result else []

    if not results:
        sys.stderr.write("[symphunk_ingest] No results in payload\n")
        sys.exit(0)

    incidents = [_make_incident(r, search_name) for r in results]
    _kv_batch_save(server_uri, session_key, incidents)

    for inc in incidents:
        sys.stdout.write(
            f"[symphunk_ingest] Incident created id={inc['id']} "
            f"title={inc['title']!r} severity={inc['severity']} agent_type={inc['agent_type']}\n"
        )


if __name__ == "__main__":
    main()
