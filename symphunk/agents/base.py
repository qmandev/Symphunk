from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, incident: dict, engine, kvstore) -> None:
        self.incident = incident
        self._engine = engine
        self._kv = kvstore

    @property
    def incident_id(self) -> str:
        return self.incident.get("id", "unknown")

    @abstractmethod
    async def run(self) -> dict:
        ...

    async def write_evidence(self, evidence: dict) -> None:
        await self._kv.upsert(
            "symphunk_evidence",
            {"incident_id": self.incident_id, **evidence},
            key_field="incident_id",
        )
        logger.info("Evidence written incident=%s", self.incident_id)
