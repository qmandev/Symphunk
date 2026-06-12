# SPL Assistant Skill

Use `saia_generate_spl` for novel or exploratory queries that are not covered by the Pipeline Health or Impact Analysis templates. Use pre-built templates first — they are performance-tuned and budget-efficient.

## When to use saia_generate_spl

- The investigation has a specific question the template queries don't address
- You need to correlate across two different event types (e.g., deployment events with network events)
- The affected service name or field differs from the template placeholders in a non-obvious way
- You want to generate a per-minute or per-request granularity breakdown

## Effective prompts for saia_generate_spl

Pass a precise, context-rich description. Include:
- The target index (`index=symphunk_devex_demo`)
- The field names you expect (`error_rate`, `latency_p99`, `event_type`, `service`, `version`)
- The time bounds (`earliest=-30m`)
- What the output should look like (table, stats, timechart)

**Example prompt to saia_generate_spl:**
> "Write SPL for index=symphunk_devex_demo, earliest=-30m. Find all service_metric events for service=payment-service. Compute the average and max error_rate for each 1-minute bucket using timechart. Show the deployment timestamp (from event_type=deployment for the same service) as a vertical annotation if possible, otherwise just output the timechart."

## Use saia_explain_spl to verify generated queries

After generating SPL with `saia_generate_spl`, use `saia_explain_spl` if the query uses unfamiliar commands or joins. A query that looks correct but searches `index=*` or uses expensive `transaction` commands should be rewritten before running.

## Use saia_optimize_spl for performance

If a generated query uses `search` commands after the initial search, or lacks time bounds, pass it to `saia_optimize_spl` before running. This matters most when `req_count` or `latency_p99` aggregations span hours rather than minutes.

## Budget reminder

Every SPL query consumes a search-tier CPU core. For deployment-regression triage:
- Steps 1–3 from the Pipeline Health skill = 3 searches (budget: cheap)
- One Impact Analysis query = 1 search (budget: cheap)
- Each `saia_generate_spl` + run pair = 2 tool calls + 1 search (budget: moderate)

Stay within the 10-search cap. If the budget fires, conclude with the evidence already gathered rather than retrying.
