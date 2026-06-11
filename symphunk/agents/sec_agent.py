from __future__ import annotations

import logging
import re

from symphunk.agents.base import BaseAgent
from symphunk.orchestrator.state import IncidentStatus
from symphunk.splunk.hec import HEC

logger = logging.getLogger(__name__)

_AUTO_RESOLVE_THRESHOLD = 0.75


class SecAgent(BaseAgent):
    async def run(self) -> dict:
        logger.info("SecAgent starting incident=%s severity=%s", self.incident_id, self.incident.get("severity"))

        result = await self._engine.run(
            self._build_prompt(),
            severity=self.incident.get("severity", "low"),
        )
        conclusion = result["conclusion"]
        threat_score = _extract_threat_score(conclusion)

        status = (
            IncidentStatus.RESOLVED
            if threat_score >= _AUTO_RESOLVE_THRESHOLD
            and self.incident.get("severity", "low") not in ("high", "critical")
            else IncidentStatus.ESCALATED
        )

        evidence = {
            "conclusion": conclusion,
            "confidence": threat_score,
            "status": status,
            "recommended_action": "auto-resolved" if status == IncidentStatus.RESOLVED else "escalate-to-soc",
            "severity": self.incident.get("severity", "low"),
        }
        await self.write_evidence(evidence)
        await self._kv.upsert("symphunk_incidents", {**self.incident, "status": status}, key_field="id")

        try:
            hec = HEC()
            await hec.emit(
                {
                    "incident_id": self.incident_id,
                    "title": self.incident.get("title", ""),
                    "severity": self.incident.get("severity", "low"),
                    "src_ip": self.incident.get("src_ip", ""),
                    "source_search": self.incident.get("source_search", ""),
                    "status": status.value,
                    "threat_score": threat_score,
                    "recommended_action": evidence["recommended_action"],
                },
                source="symphunk:sec_evidence",
                sourcetype="_json",
                index="summary",
            )
            await hec.aclose()
        except Exception as exc:
            logger.warning("HEC telemetry emit failed: %s", exc)

        logger.info("SecAgent done incident=%s status=%s threat_score=%.2f", self.incident_id, status.value, threat_score)
        return evidence

    def _build_prompt(self) -> str:
        lines = [
            "Investigate the following security incident:\n",
            f"ID: {self.incident_id}",
            f"Title: {self.incident.get('title', 'Unknown')}",
            f"Severity: {self.incident.get('severity', 'low')}",
            f"Description: {self.incident.get('description', '')}",
        ]
        if self.incident.get("src_ip"):
            lines.append(f"Source IP: {self.incident['src_ip']}")
        if self.incident.get("source_search"):
            lines.append(f"Source alert: {self.incident['source_search']}")
        if self.incident.get("raw_result"):
            lines.append(f"Alert trigger data: {self.incident['raw_result']}")
        lines += [
            "",
            "IMPORTANT: The security events are in index=symphunk_sec_demo ONLY.",
            "Do NOT search index=* or any internal/obs index (_internal, main, symphunk_demo).",
            "",
            "Follow this investigation sequence:",
            "1. Use the IOC Triage skill: Step 1 (auth anomaly summary by src_ip) →",
            "   Step 2 (attack timeline for the highest-volume IP) →",
            "   Step 3 (lateral movement check on port 445).",
            "2. Use the Threat Intelligence skill to classify the src_ip risk level.",
            "3. Use the Lateral Movement skill if SMB connections are found.",
            "4. Build an evidence package: auth timeline, IP classification, blast radius, root cause.",
            "End with: Threat Score: <0.0–1.0>",
        ]
        return "\n".join(lines)


def _extract_threat_score(text: str) -> float:
    clean = re.sub(r"\*+", "", text)
    match = re.search(r"threat\s+score[:\s]+(-?[01](?:\.\d+)?)", clean, re.IGNORECASE)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    # Fallback: also accept "confidence:" phrasing in case Claude uses it
    match = re.search(r"confidence[:\s]+(-?[01](?:\.\d+)?)", clean, re.IGNORECASE)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    return 0.5
