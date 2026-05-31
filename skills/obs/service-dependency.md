# Service Dependency Skill

Use when an incident may involve cascading failures or cross-service impact. Helps map which services
are affected and trace the blast radius.

## Approach
1. Identify the origin service from the incident title/description
2. Search for correlated errors in dependent services within the same time window
3. Use host/sourcetype groupings as a proxy for service boundaries

## SPL Templates

### Correlated error spread across hosts
```spl
| tstats count WHERE index=* (error OR ERROR OR FATAL) earliest=-1h latest=now() BY host sourcetype _time span=5m
| stats sum(count) AS total_errors BY host sourcetype
| sort -total_errors
| head 20
```

### Identify hosts with simultaneous spikes (blast radius)
```spl
| tstats count WHERE index=* earliest=-30m latest=now() BY host _time span=1m
| eventstats avg(count) AS avg stdev(count) AS stdev BY host
| eval anomalous=if((count - avg) / stdev > 2, 1, 0)
| stats sum(anomalous) AS spike_minutes BY host
| where spike_minutes > 3
| sort -spike_minutes
```

### Timeline of first error appearance per host
```spl
| tstats min(_time) AS first_error WHERE index=* (error OR ERROR OR FATAL) earliest=-2h latest=now() BY host
| eval first_error=strftime(first_error, "%H:%M:%S")
| sort first_error
```

## Interpretation
- Hosts with the earliest `first_error` timestamps are likely the origin
- Hosts with high `spike_minutes` are in the blast radius
- Shared sourcetypes between anomalous hosts suggest a common dependency
