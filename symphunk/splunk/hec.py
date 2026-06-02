from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from symphunk.config import settings

logger = logging.getLogger(__name__)


class HEC:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            verify=False,  # self-signed cert in Docker
            headers={"Authorization": f"Splunk {settings.hec_token}"},
        )

    async def emit(
        self,
        event: Any,
        *,
        source: str = "symphunk",
        sourcetype: str = "_json",
        index: str = "main",
    ) -> None:
        payload = {
            "time": time.time(),
            "source": source,
            "sourcetype": sourcetype,
            "index": index,
            "event": event,
        }
        r = await self._client.post(
            f"{settings.hec_url}/services/collector/event",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        logger.debug("HEC emit source=%s", source)

    async def aclose(self) -> None:
        await self._client.aclose()
