from __future__ import annotations

import asyncio
import logging

from symphunk.config import settings
from symphunk.orchestrator.state import IncidentStatus

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, kvstore) -> None:
        self._kv = kvstore
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_agents)
        self._active = 0

    async def dispatch(self, incident: dict, agent_factory) -> None:
        if self._active >= settings.max_concurrent_agents:
            logger.warning("Concurrency cap (%d) reached; skipping id=%s", settings.max_concurrent_agents, incident.get("id"))
            return

        async with self._semaphore:
            self._active += 1
            try:
                await self._kv.upsert(
                    "symphunk_incidents",
                    {**incident, "status": IncidentStatus.INVESTIGATING},
                    key_field="id",
                )
                agent = agent_factory(incident)
                await agent.run()
            except Exception:
                logger.exception("Agent failed for incident id=%s", incident.get("id"))
            finally:
                self._active -= 1
