from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self, kvstore) -> None:
        self._kv = kvstore
        self._collection = "symphunk_memory"

    async def get(self, key: str) -> dict | None:
        results = await self._kv.query(self._collection, filter={"key": key}, limit=1)
        return results[0] if results else None

    async def set(self, key: str, value: Any, incident_id: str = "") -> None:
        await self._kv.upsert(
            self._collection,
            {"key": key, "value": value, "incident_id": incident_id},
            key_field="key",
        )
        logger.debug("Memory set key=%s incident=%s", key, incident_id)

    async def delete(self, key: str) -> None:
        await self._kv.delete_by_key(self._collection, key_field="key", key_value=key)
