# Anomaly Triage Skill

Use when an incident involves unexpected metric spikes, drops, or deviations from baseline.

## Search Strategy
- Prefer `tstats` over raw `search` — far fewer resources consumed
- Bound time windows to ≤ 7 days; start with 1-hour windows for initial triage
- Use accelerated data models or summary indexes where available
- Report `Confidence: <0.0–1.0>` at the end of your investigation

## SPL Templates

### Spike detection via tstats
```spl
| tstats count WHERE index=* earliest=-1h latest=now() BY _time span=5m host sourcetype
| eventstats avg(count) AS avg_count stdev(count) AS stdev BY host sourcetype
| eval z_score=round((count - avg_count) / stdev, 2)
| where z_score > 3
| sort -z_score
```

### Error rate spike
```spl
| tstats count WHERE index=* (error OR ERROR OR FATAL) earliest=-1h latest=now() BY _time span=5m host
| eventstats avg(count) AS baseline BY host
| eval pct_above=round((count - baseline) / baseline * 100, 1)
| where pct_above > 50
| sort -pct_above
```

### Sustained anomaly (last 6 hours vs prior 24 hours)
```spl
| tstats count WHERE index=* earliest=-6h latest=now() BY host sourcetype
| appendcols [| tstats count AS baseline WHERE index=* earliest=-30h latest=-6h BY host sourcetype]
| eval ratio=round(count / baseline, 2)
| where ratio > 2 OR ratio < 0.5
```

## Performance Notes
- `tstats` requires no field extraction — always try it first
- Avoid `| rex` on large result sets; use `| eval match()` instead
- If a data model is accelerated, `| tstats` over it is the fastest path
