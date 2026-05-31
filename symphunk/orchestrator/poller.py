from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from symphunk.config import settings
from symphunk.orchestrator.state import IncidentStatus

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, kvstore) -> None:
        self._kv = kvstore

    async def poll(self) -> AsyncIterator[dict]:
        results = await self._kv.query(
            "symphunk_incidents",
            filter={"status": IncidentStatus.NEW},
        )
        for incident in results:
            logger.info("Poller found incident id=%s title=%s", incident.get("id"), incident.get("title"))
            yield incident

    async def run_forever(self, on_incident) -> None:
        logger.info("Poller started (interval=%ds)", settings.poll_interval_seconds)
        while True:
            try:
                async for incident in self.poll():
                    await on_incident(incident)
            except Exception:
                logger.exception("Poller error")
            await asyncio.sleep(settings.poll_interval_seconds)
