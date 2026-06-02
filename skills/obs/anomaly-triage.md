# Anomaly Triage Skill

Use when an incident involves unexpected metric spikes, drops, or deviations from baseline.

## IMPORTANT: Which index to search

**For incidents from `symphunk_obs_demo`**: always query `index=symphunk_demo`. Do NOT use `index=*` or internal indexes (`_internal`, `_introspection`, `main`) — they contain Splunk platform data, not application metrics.

`symphunk_demo` fields (extracted from `_json` sourcetype):
- `host`: `web-frontend-01`, `web-frontend-02`, `api-gateway-01`
- `service`: `web-frontend` or `api-gateway`
- `cpu_pct`: CPU utilisation percent (0–100)
- `mem_pct`: memory utilisation percent (0–100)
- `req_per_sec`: requests per second
- `error_count`: errors in this window

## Step-by-step investigation (symphunk_demo)

### Step 1 — Per-host summary
```spl
index=symphunk_demo earliest=-30m latest=now()
| stats avg(cpu_pct) AS avg_cpu max(cpu_pct) AS max_cpu
        avg(req_per_sec) AS avg_rps sum(error_count) AS total_errors
        count AS samples
  BY host
| sort -max_cpu
```

### Step 2 — Anomaly timeline (z-score over 2-minute buckets)
```spl
index=symphunk_demo earliest=-30m latest=now()
| bin _time span=2m
| stats avg(cpu_pct) AS cpu avg(req_per_sec) AS rps sum(error_count) AS errs BY host _time
| eventstats avg(cpu) AS baseline_cpu stdev(cpu) AS std_cpu BY host
| eval z_score=round((cpu - baseline_cpu) / if(std_cpu > 0, std_cpu, 1), 2)
| sort -z_score
| table host _time cpu rps errs z_score
```

### Step 3 — Service cascade (first anomalous event per host)
```spl
index=symphunk_demo earliest=-30m latest=now()
| stats min(_time) AS first_spike max(cpu_pct) AS peak_cpu sum(error_count) AS total_errors BY host
| eval first_spike=strftime(first_spike, "%H:%M:%S")
| sort first_spike
```

## Generic SPL Templates (for non-demo indexes)

### Spike detection via tstats
```spl
| tstats count WHERE index=<target_index> earliest=-1h latest=now() BY _time span=5m host sourcetype
| eventstats avg(count) AS avg_count stdev(count) AS stdev BY host sourcetype
| eval z_score=round((count - avg_count) / stdev, 2)
| where z_score > 3
| sort -z_score
```

## Performance Notes
- For `symphunk_demo` field-level queries (`cpu_pct`, `error_count`), use raw `search` with bounded windows
- `tstats` only works on indexed metadata fields (host, sourcetype, _time) — not JSON-extracted fields
- Bound time windows to ≤ 30m for initial triage
