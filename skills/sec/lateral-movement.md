# Lateral Movement Detection Skill

Use when a host may have been compromised and used as a pivot point to reach other internal hosts.

## Key indicators

- SMB connections (port 445) from an endpoint that does not normally initiate them
- First-seen internal connections to new destinations after an auth success
- Large `bytes_out` over SMB — data staging (exfil prep)
- Sequential `SmbConnect → SmbTreeConnect → SmbReadFile/SmbWriteFile` pattern

## Detection SPL (symphunk_sec_demo)

### First-seen SMB pivot (the core lateral-movement signal)

```spl
index=symphunk_sec_demo earliest=-30m latest=now() event_type=network dest_port=445
| stats min(_time) AS first_seen
       count AS connections
       sum(bytes_out) AS total_bytes_out
       values(smb_command) AS smb_commands
  BY src_host, dest_host, user
| eval first_seen=strftime(first_seen, "%Y-%m-%d %H:%M:%S")
| eval data_staging_risk=if(total_bytes_out > 100000, "HIGH", "low")
| sort first_seen
| table first_seen, src_host, dest_host, user, connections, total_bytes_out, data_staging_risk, smb_commands
```

### SMB command sequence reconstruction

```spl
index=symphunk_sec_demo earliest=-30m latest=now() event_type=network dest_port=445
| eval Time=strftime(_time, "%H:%M:%S")
| table Time, src_host, dest_host, user, smb_command, bytes_in, bytes_out
| sort _time
```

### Correlate breach time with pivot time

```spl
index=symphunk_sec_demo earliest=-30m latest=now()
| eval event_class=case(
    event_type="authentication" AND action="success", "BREACH",
    event_type="network" AND dest_port=445, "SMB_PIVOT",
    1=1, "other"
  )
| where event_class IN ("BREACH", "SMB_PIVOT")
| eval Time=strftime(_time, "%H:%M:%S")
| table Time, event_class, src_ip, src_host, dest_host, user, smb_command
| sort _time
```

## Severity mapping

| Signal | Threat Score contribution |
|---|---|
| SMB pivot within < 5 min of breach | +0.35 |
| `SmbReadFile` or `SmbWriteFile` observed | +0.25 (data staging) |
| `bytes_out` > 500 KB over SMB | +0.15 |
| Multiple dest_hosts reached | +0.10 |
| Pivot user matches breached user | +0.10 |

A confirmed breach + SMB pivot + large bytes_out typically yields Threat Score ≥ 0.85 → Escalate.
