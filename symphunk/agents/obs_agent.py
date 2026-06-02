from __future__ import annotations

import logging
import re

from symphunk.agents.base import BaseAgent
from symphunk.orchestrator.state import IncidentStatus
from symphunk.splunk.hec import HEC

logger = logging.getLogger(__name__)

_AUTO_RESOLVE_THRESHOLD = 0.8


class ObsAgent(BaseAgent):
    async def run(self) -> dict:
        logger.info("ObsAgent starting incident=%s severity=%s", self.incident_id, self.incident.get("severity"))

        result = await self._engine.run(
            self._build_prompt(),
            severity=self.incident.get("severity", "low"),
        )
        conclusion = result["conclusion"]
        confidence = _extract_confidence(conclusion)

        status = (
            IncidentStatus.RESOLVED
            if confidence >= _AUTO_RESOLVE_THRESHOLD
            and self.incident.get("severity", "low") not in ("high", "critical")
            else IncidentStatus.ESCALATED
        )

        evidence = {
            "conclusion": conclusion,
            "confidence": confidence,
            "status": status,
            "recommended_action": "auto-resolved" if status == IncidentStatus.RESOLVED else "escalate",
            "severity": self.incident.get("severity", "low"),
        }
        await self.write_evidence(evidence)
        await self._kv.upsert("symphunk_incidents", {**self.incident, "status": status}, key_field="id")

        # Emit compact telemetry to summary index for the proof-of-work dashboard.
        try:
            hec = HEC()
            await hec.emit(
                {
                    "incident_id": self.incident_id,
                    "title": self.incident.get("title", ""),
                    "severity": self.incident.get("severity", "low"),
                    "source_search": self.incident.get("source_search", ""),
                    "status": status.value,
                    "confidence": confidence,
                    "recommended_action": evidence["recommended_action"],
                },
                source="symphunk:evidence",
                sourcetype="_json",
                index="summary",
            )
            await hec.aclose()
        except Exception as exc:
            logger.warning("HEC telemetry emit failed: %s", exc)

        logger.info("ObsAgent done incident=%s status=%s confidence=%.2f", self.incident_id, status.value, confidence)
        return evidence

    def _build_prompt(self) -> str:
        lines = [
            "Investigate the following observability incident:\n",
            f"ID: {self.incident_id}",
            f"Title: {self.incident.get('title', 'Unknown')}",
            f"Severity: {self.incident.get('severity', 'low')}",
            f"Description: {self.incident.get('description', '')}",
        ]
        if self.incident.get("source_search"):
            lines.append(f"Source alert: {self.incident['source_search']}")
        if self.incident.get("raw_result"):
            lines.append(f"Alert trigger data: {self.incident['raw_result']}")
        lines += [
            "",
            "IMPORTANT: The application metrics are in index=symphunk_demo ONLY.",
            "Do NOT search index=* or any internal index (_internal, _introspection, main).",
            "Those contain Splunk platform data, not the web-frontend metrics you need.",
            "",
            "Start with Step 1 from the Anomaly Triage skill (per-host summary on symphunk_demo),",
            "then Step 2 (z-score timeline), then Step 3 (cascade).",
            "Build an evidence package: anomaly timeline, z-score magnitude, blast-radius, root cause.",
            "End with: Confidence: <0.0–1.0>",
        ]
        return "\n".join(lines)


def _extract_confidence(text: str) -> float:
    # Strip markdown bold/italic markers before matching so "**0.82**" works.
    clean = re.sub(r"\*+", "", text)
    match = re.search(r"confidence[:\s]+([01](?:\.\d+)?)", clean, re.IGNORECASE)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    return 0.5
