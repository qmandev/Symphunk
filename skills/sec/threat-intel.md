# Threat Intelligence Skill

Use to assess whether a source IP is suspicious, known-malicious, or benign based on observable attributes in the data.

## IP classification heuristics (no external lookup required)

Since this environment has no live threat-intel feed, classify IPs by observable behavior and known ranges.

### External IP risk signals

| Indicator | Risk level |
|---|---|
| IP is in `185.220.0.0/16` | HIGH — Tor exit node range (well-known) |
| IP is in `45.142.0.0/16`, `45.141.0.0/16` | HIGH — common VPN/proxy ranges used in credential stuffing |
| IP is in `23.129.0.0/16` | HIGH — known anonymizing relay range |
| > 20 auth failures + ≥ 1 success | HIGH — credential stuffing confirmed |
| > 10 auth failures, 0 successes, single username | MEDIUM — password spray |
| > 5 auth failures, 0 successes, many usernames | MEDIUM — credential stuffing without breach |
| < 5 auth failures, 0 successes | LOW — likely misconfiguration |

### Internal IP risk signals

| Indicator | Risk level |
|---|---|
| RFC1918 source (10.x, 172.16-31.x, 192.168.x) + auth failures to multiple hosts | MEDIUM — internal scanner or misconfigured service |
| RFC1918 source + SMB connections + no prior auth record | HIGH — compromised host lateral movement |
| RFC1918 source + < 5 failures + single target | LOW — likely misconfigured service account |

## SPL: classify src_ip in-query

```spl
index=symphunk_sec_demo earliest=-30m latest=now() event_type=authentication
| stats count(eval(action="failure")) AS failures
       count(eval(action="success")) AS successes
  BY src_ip
| eval ip_class=case(
    match(src_ip, "^185\.220\."), "TOR_EXIT_NODE",
    match(src_ip, "^45\.14[12]\."), "KNOWN_VPN_RANGE",
    match(src_ip, "^10\.") OR match(src_ip, "^192\.168\.") OR match(src_ip, "^172\.(1[6-9]|2[0-9]|3[01])\."), "INTERNAL",
    1=1, "UNKNOWN_EXTERNAL"
  )
| eval risk=case(
    ip_class="TOR_EXIT_NODE" AND successes > 0, "CRITICAL",
    ip_class="TOR_EXIT_NODE", "HIGH",
    ip_class="KNOWN_VPN_RANGE" AND failures > 10, "HIGH",
    ip_class="INTERNAL" AND failures > 10, "MEDIUM",
    1=1, "LOW"
  )
| table src_ip, ip_class, risk, failures, successes
```

## Threat Score guide

Use these as inputs to your final Threat Score assessment:

- `CRITICAL` risk IP (Tor + breach): score 0.90–1.00 → always Escalate
- `HIGH` risk IP (Tor, no breach yet): score 0.75–0.90 → Escalate if severity=high
- `MEDIUM` risk (internal scanner, no breach): score 0.40–0.65 → investigate further before resolving
- `LOW` risk: score 0.10–0.35 → likely benign, can Resolve with note

Adjust score upward if lateral movement (port 445 activity) is also present — combine with lateral-movement skill findings.
