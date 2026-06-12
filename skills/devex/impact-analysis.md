# Impact Analysis Skill

Use after the Pipeline Health 3-step investigation to score the regression and determine blast radius severity.

## When to use

Use this skill when:
- Step 2 (error rate comparison) shows a clear pre/post delta AND Step 3 shows isolated service impact
- You need to confirm temporal correlation: exactly when did the error rate cross the anomaly threshold?
- You want to check if latency degradation followed the same pattern as error rate

## Regression timeline: minute-by-minute error rate

Reconstruct the exact minute the error rate spiked relative to the deployment time.
Replace `<service>` and `<deploy_epoch>`.

```spl
index=symphunk_devex_demo earliest=-30m latest=now() event_type=service_metric service=<service>
| eval minutes_from_deploy=round((_time - <deploy_epoch>) / 60, 1)
| eval error_pct=round(error_rate*100, 2)
| table _time, minutes_from_deploy, error_pct, latency_p99, req_count
| sort _time
```

**Interpret:**
- If `minutes_from_deploy` ≈ 0 to +2 when error_pct first spikes → strong temporal correlation
- If error_pct was already spiking at `minutes_from_deploy` < 0 → predates deploy → false alarm

## Confidence scoring guide

| Signal | Confidence contribution |
|---|---|
| Error rate × 4 or more after deploy | +0.35 |
| Spike starts within 2 min of deploy | +0.25 |
| Other services stable (blast radius isolated) | +0.20 |
| Latency degradation mirrors error rate | +0.10 |
| Baseline error rate below 1% pre-deploy | +0.10 |
| Error rate elevated pre-deploy | −0.30 |
| Multiple services degraded simultaneously | −0.25 |
| No deployment event found in last 30m | −0.40 |

Sum the applicable contributions to derive your Confidence Score (cap at 1.0, floor at 0.0).

## Latency correlation check

If error rate delta is clear, also check p99 latency to confirm service-level impact vs. upstream timeout:

```spl
index=symphunk_devex_demo earliest=-30m latest=now() event_type=service_metric service=<service>
| eval window=if(_time < <deploy_epoch>, "pre_deploy", "post_deploy")
| stats avg(latency_p99) AS avg_p99 max(latency_p99) AS max_p99 BY window
| eval avg_p99=round(avg_p99, 0), max_p99=round(max_p99, 0)
| table window, avg_p99, max_p99
```

High p99 post-deploy alongside high error rate confirms the service is struggling (not just downstream timeouts inflating the error count).

## Recommended action language

Use these exact phrases so the evidence package is actionable:
- **Regression confirmed**: `investigate-rollback <service> <version>` — engineer should review logs and consider rollback
- **False alarm**: `false-alarm` — error spike predates deploy or no temporal correlation; no action required
- **Ambiguous**: `monitor-<service>` — insufficient data; watch for 10 more minutes before deciding
