# IOC Triage Skill

Use when an incident involves authentication anomalies, suspicious source IPs, or potential account compromise.

## IMPORTANT: Which index to search

**For incidents from `symphunk_sec_demo`**: always query `index=symphunk_sec_demo`. Do NOT use `index=*` or internal indexes (`_internal`, `_introspection`, `main`, `symphunk_demo`).

`symphunk_sec_demo` fields (extracted from `_json` sourcetype):
- `event_type`: `authentication` or `network`
- `action`: `failure`, `success`, or `allowed`
- `src_ip`: source IP address
- `src_host`: source hostname (network events only)
- `dest_host`: target hostname
- `dest_ip`: target IP (network events only)
- `dest_port`: destination port
- `user`: username attempted or used
- `app`: `ssh` or other application
- `bytes_out`: bytes sent
- `reason`: `invalid_credentials`, `authenticated`, or blank
- `protocol`: `SMB` or blank
- `smb_command`: SMB operation name (network events only)

## Step-by-step investigation (symphunk_sec_demo)

### Step 1 — Auth anomaly summary by source IP

Count failures and successes per source IP. Flag any IP with > 5 failures OR any successes after failures (breach signal).

```spl
index=symphunk_sec_demo earliest=-30m latest=now() event_type=authentication
| stats count(eval(action="failure")) AS failures
       count(eval(action="success")) AS successes
       values(dest_host) AS targets
       values(user) AS users_tried
  BY src_ip
| eval breach=if(successes > 0 AND failures > 5, "YES", "no")
| sort -failures
| table src_ip, failures, successes, breach, targets, users_tried
```

### Step 2 — Attack timeline (authentication events ordered)

Reconstruct the sequence of events for the highest-volume source IP to determine when breach occurred.

```spl
index=symphunk_sec_demo earliest=-30m latest=now() event_type=authentication src_ip=<top_src_ip>
| eval Time=strftime(_time, "%H:%M:%S")
| table Time, action, user, dest_host, reason
| sort _time
```

Replace `<top_src_ip>` with the IP from Step 1 with the highest failure count.

### Step 3 — Lateral movement check (post-breach network activity)

After breach, check for internal network connections from the compromised host to other internal targets.

```spl
index=symphunk_sec_demo earliest=-30m latest=now() event_type=network
| stats count AS connections
       sum(bytes_out) AS total_bytes_out
       values(smb_command) AS smb_ops
       values(dest_host) AS dest_hosts
  BY src_host, dest_host, dest_port, protocol, user
| where dest_port=445 OR dest_port=22 OR dest_port=3389
| sort -connections
| table src_host, dest_host, dest_port, protocol, user, connections, total_bytes_out, smb_ops
```

## Evidence package format

After the three steps, produce:
1. **Auth anomaly summary**: total failures, unique users tried, breach confirmed (yes/no), breach time
2. **Source IP assessment**: internal vs. external, known bad range (see threat-intel skill), Tor exit node
3. **Lateral movement blast radius**: pivot target, protocols used, bytes transferred, data staging risk
4. **Root cause**: credential stuffing / password spray / insider / misconfigured scanner
5. Threat Score: <0.0–1.0>

## Performance Notes
- Bound time windows to ≤ 30m for initial triage
- `event_type=authentication` filter halves the result set before field extraction
- For Step 3, filter by specific ports (445, 22, 3389) rather than returning all network events
