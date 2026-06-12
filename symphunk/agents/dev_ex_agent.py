from __future__ import annotations

import json
import logging
import re

from symphunk.agents.base import BaseAgent
from symphunk.orchestrator.state import IncidentStatus
from symphunk.splunk.hec import HEC

logger = logging.getLogger(__name__)

# High confidence = regression confirmed → escalate for engineer review/rollback decision.
# Low confidence = no clear causal link → resolve as false alarm.
_REGRESSION_THRESHOLD = 0.70


class DevExAgent(BaseAgent):
    async def run(self) -> dict:
        logger.info(
            "DevExAgent starting incident=%s severity=%s",
            self.incident_id, self.incident.get("severity"),
        )

        result = await self._engine.run(
            self._build_prompt(),
            severity=self.incident.get("severity", "medium"),
        )
        conclusion = result["conclusion"]
        confidence = _extract_confidence(conclusion)

        status = (
            IncidentStatus.ESCALATED
            if confidence >= _REGRESSION_THRESHOLD
            or self.incident.get("severity", "medium") in ("high", "critical")
            else IncidentStatus.RESOLVED
        )
        recommended_action = "investigate-rollback" if status == IncidentStatus.ESCALATED else "false-alarm"

        evidence = {
            "conclusion": conclusion,
            "confidence": confidence,
            "status": status,
            "recommended_action": recommended_action,
            "severity": self.incident.get("severity", "medium"),
        }
        await self.write_evidence(evidence)
        await self._kv.upsert("symphunk_incidents", {**self.incident, "status": status}, key_field="id")

        service = _parse_service(self.incident.get("raw_result", ""))
        try:
            hec = HEC()
            await hec.emit(
                {
                    "incident_id": self.incident_id,
                    "title": self.incident.get("title", ""),
                    "severity": self.incident.get("severity", "medium"),
                    "service": service,
                    "source_search": self.incident.get("source_search", ""),
                    "status": status.value,
                    "confidence": confidence,
                    "recommended_action": recommended_action,
                },
                source="symphunk:devex_evidence",
                sourcetype="_json",
                index="summary",
            )
            await hec.aclose()
        except Exception as exc:
            logger.warning("HEC telemetry emit failed: %s", exc)

        logger.info(
            "DevExAgent done incident=%s status=%s confidence=%.2f",
            self.incident_id, status.value, confidence,
        )
        return evidence

    def _build_prompt(self) -> str:
        service = _parse_service(self.incident.get("raw_result", ""))
        lines = [
            "Investigate whether a recent deployment caused a service regression:\n",
            f"ID: {self.incident_id}",
            f"Title: {self.incident.get('title', 'Unknown')}",
            f"Severity: {self.incident.get('severity', 'medium')}",
            f"Description: {self.incident.get('description', '')}",
        ]
        if service:
            lines.append(f"Affected service: {service}")
        if self.incident.get("source_search"):
            lines.append(f"Source alert: {self.incident['source_search']}")
        if self.incident.get("raw_result"):
            lines.append(f"Alert trigger data: {self.incident['raw_result']}")
        lines += [
            "",
            "IMPORTANT: All deployment and service data is in index=symphunk_devex_demo ONLY.",
            "Do NOT search index=* or any other index (_internal, symphunk_demo, symphunk_sec_demo).",
            "",
            "Follow this investigation sequence using the Pipeline Health skill:",
            "1. Step 1 — Deployment timeline: find all deployment events for the affected service in the last 30m.",
            "2. Step 2 — Error rate comparison: compare error rates before and after the deployment timestamp.",
            "   Use the epoch timestamp from Step 1 as the split point.",
            "3. Step 3 — Blast radius: check all services for correlated degradation to rule out infra cause.",
            "4. Causation assessment: did the error spike start AT OR AFTER the deployment?",
            "   Are other services stable? Was the error rate already elevated before the deploy?",
            "5. Build an evidence package: deployment summary, error delta, causation verdict, blast radius.",
            "",
            "Confidence Score guidance:",
            "  > 0.70 — deployment is the likely cause (escalate for engineer review / potential rollback)",
            "  < 0.70 — no clear causal link (error spike predates deploy or is unrelated — false alarm)",
            "End with: Confidence Score: <0.0–1.0>",
        ]
        return "\n".join(lines)


def _parse_service(raw_result: str) -> str:
    try:
        return json.loads(raw_result or "{}").get("service", "")
    except (json.JSONDecodeError, TypeError):
        return ""


def _extract_confidence(text: str) -> float:
    clean = re.sub(r"\*+", "", text)
    match = re.search(r"confidence\s+score[:\s]+(-?[01](?:\.\d+)?)", clean, re.IGNORECASE)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    match = re.search(r"confidence[:\s]+(-?[01](?:\.\d+)?)", clean, re.IGNORECASE)
    if match:
        return min(1.0, max(0.0, float(match.group(1))))
    return 0.5
