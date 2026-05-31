# Diagnostic SPL Skill

General-purpose diagnostic queries for observability triage. Use these as building blocks.
Always prefer `tstats` for initial scans; drop to raw `search` only for field-level detail on small result sets.

## Budget Guidelines
| Query type | Cost | When to use |
|---|---|---|
| `tstats` over index | Low | Always for initial triage |
| `tstats` over data model | Very low | When a data model is accelerated |
| `search` with time bounds | Medium | When field-level detail is needed |
| `search` without time bounds | High | Avoid — always set `earliest`/`latest` |

## SPL Templates

### Event volume by sourcetype (last 1 hour)
```spl
| tstats count WHERE index=* earliest=-1h latest=now() BY sourcetype
| sort -count
```

### Top noisy hosts
```spl
| tstats count WHERE index=* earliest=-1h latest=now() BY host
| sort -count | head 10
```

### Keyword search with bounded window (use saia_generate_spl for novel queries)
```spl
index=* earliest=-1h latest=now() <keyword>
| stats count BY host sourcetype
| sort -count
```

### Summary index lookup (fastest for recurring checks)
```spl
index=summary sourcetype=<summary_sourcetype> earliest=-1h latest=now()
| stats sum(count) BY orig_host
```

## Generating Novel SPL
For queries not covered by these templates, use `saia_generate_spl` with a clear natural-language description.
Example: "Generate SPL to find hosts where CPU utilisation exceeded 90% in the last hour using the Infrastructure data model."
