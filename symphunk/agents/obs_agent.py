from __future__ import annotations

import logging
import re

from symphunk.agents.base import BaseAgent
from symphunk.harness.skills import load_all
from symphunk.orchestrator.state import IncidentStatus

logger = logging.getLogger(__name__)

_AUTO_RESOLVE_THRESHOLD = 0.8


class ObsAgent(BaseAgent):
    async def run(self) -> dict:
        logger.info("ObsAgent starting incident=%s severity=%s", self.incident_id, self.incident.get("severity"))

        skills = load_all("obs")
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

        logger.info("ObsAgent done incident=%s status=%s confidence=%.2f", self.incident_id, status.value, confidence)
        return evidence

    def _build_prompt(self) -> str:
        return (
            f"Investigate the following observability incident:\n\n"
            f"ID: {self.incident_id}\n"
            f"Title: {self.incident.get('title', 'Unknown')}\n"
            f"Severity: {self.incident.get('severity', 'low')}\n"
            f"Description: {self.incident.get('description', '')}\n\n"
            "Use the loaded skills to run diagnostic SPL searches. "
            "Prefer tstats. Bound time windows to ≤ 7 days. "
            "Correlate related events and map service dependencies if relevant. "
            "Conclude with a root cause summary and: Confidence: <0.0–1.0>"
        )


def _extract_confidence(text: str) -> float:
    match = re.search(r"confidence[:\s]+([01](?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    return 0.5
