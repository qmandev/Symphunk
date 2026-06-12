# Pipeline Health Skill

Use when an incident involves a potential deployment regression, service error-rate spike, or CI/CD pipeline anomaly.

## IMPORTANT: Which index to search

**For incidents from `symphunk_devex_demo`**: always query `index=symphunk_devex_demo`. Do NOT use `index=*` or any internal/obs/sec index (`_internal`, `_introspection`, `main`, `symphunk_demo`, `symphunk_sec_demo`).

`symphunk_devex_demo` fields (extracted from `_json` sourcetype):

- `event_type`: `deployment` or `service_metric`
- `service`: service name (e.g., `payment-service`, `notification-service`, `api-gateway-01`)
- `version`: version string currently running (e.g., `2.3.1`)
- `action`: `deploy_complete` (deployment events only)
- `error_rate`: fraction 0.0–1.0 representing the error rate over the interval
- `latency_p99`: p99 request latency in milliseconds
- `req_count`: request count for the interval
- `host`: host name running the service

## Step-by-step investigation

### Step 1 — Deployment timeline

Find all recent deployment events. Record the service name, version deployed, and the exact timestamp — you need the epoch time for Step 2.

```spl
index=symphunk_devex_demo earliest=-30m latest=now() event_type=deployment
| eval deploy_time=strftime(_time, "%H:%M:%S"), deploy_epoch=_time, deploy_ago=round((now()-_time)/60, 1)
| table deploy_time, deploy_epoch, service, version, action, host, deploy_ago
| sort _time
```

### Step 2 — Error rate comparison before vs. after deployment

Replace `<service>` with the affected service name and `<deploy_epoch>` with the Unix epoch from Step 1.

```spl
index=symphunk_devex_demo earliest=-30m latest=now() event_type=service_metric service=<service>
| eval window=if(_time < <deploy_epoch>, "pre_deploy", "post_deploy")
| stats avg(error_rate) AS avg_error_rate
        max(error_rate) AS max_error_rate
        avg(latency_p99) AS avg_latency
        count AS samples
  BY window
| eval error_pct=round(avg_error_rate*100, 2),
       max_error_pct=round(max_error_rate*100, 2),
       avg_latency=round(avg_latency, 0)
| table window, error_pct, max_error_pct, avg_latency, samples
```

**Interpret the result:**
- `pre_deploy` error_pct much lower than `post_deploy` → deployment is likely the cause
- `pre_deploy` error_pct already elevated (≥ 2%) → error predates the deploy → likely false alarm

### Step 3 — Blast radius: check all services for correlated degradation

If only the deployed service is degraded and others are stable, that confirms the deployment as the cause.
If multiple services degraded at the same time, suspect an infrastructure issue, not the deploy.

```spl
index=symphunk_devex_demo earliest=-30m latest=now() event_type=service_metric
| stats avg(error_rate) AS avg_error_rate
        max(error_rate) AS max_error_rate
        avg(latency_p99) AS avg_latency
  BY service
| eval error_pct=round(avg_error_rate*100, 2),
       max_error_pct=round(max_error_rate*100, 2),
       avg_latency=round(avg_latency, 0)
| sort -max_error_rate
| table service, error_pct, max_error_pct, avg_latency
```

## Evidence package format

After all three steps, produce:
1. **Deployment summary**: service name, version deployed, time of deployment
2. **Error rate delta**: pre-deploy vs. post-deploy error rate (absolute % and relative change)
3. **Causation assessment**: did the spike start at/after the deploy? Was the rate elevated before?
4. **Blast radius**: which other services are degraded (if any)? Infrastructure vs. service-level cause?
5. **Recommended action**: `investigate-rollback <service> <version>` / `false-alarm — error predates deploy`
6. Confidence Score: <0.0–1.0>

## Performance notes
- Bound time windows to ≤ 30m for triage; expand to ≤ 2h only if baseline context is needed
- `event_type=deployment` and `event_type=service_metric` filters halve the result set before field extraction
- Step 3 is cheap: one `stats avg() BY service` pass over a small bounded dataset
- Prefer Step 1–3 in order; only use `saia_generate_spl` (see spl-assistant skill) for novel correlation queries
