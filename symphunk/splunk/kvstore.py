from __future__ import annotations

import json
import logging

import httpx

from symphunk.config import settings

logger = logging.getLogger(__name__)

_COLLECTIONS = ["symphunk_incidents", "symphunk_evidence", "symphunk_memory", "symphunk_audit"]
_CONFIG_URL = f"https://{settings.splunk_host}:{settings.splunk_port}/servicesNS/nobody/search/storage/collections/config"
_DATA_BASE = f"https://{settings.splunk_host}:{settings.splunk_port}/servicesNS/nobody/search/storage/collections/data"


class KVStore:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            verify=False,  # self-signed cert in Docker
            headers={"Authorization": f"Bearer {settings.splunk_token}"},
            timeout=30.0,  # prevent ReadTimeout on stale connections after long MCP runs
        )

    async def init_collections(self) -> None:
        for name in _COLLECTIONS:
            try:
                await self._client.post(_CONFIG_URL, data={"name": name, "output_mode": "json"})
                logger.info("KV collection created: %s", name)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 409:
                    logger.debug("KV collection already exists: %s", name)
                else:
                    raise

    async def query(self, collection: str, filter: dict | None = None, limit: int = 100) -> list[dict]:
        params: dict = {"output_mode": "json", "limit": limit}
        if filter:
            params["query"] = json.dumps(filter)
        r = await self._client.get(f"{_DATA_BASE}/{collection}", params=params)
        r.raise_for_status()
        return r.json()

    async def upsert(self, collection: str, record: dict, *, key_field: str = "_key") -> None:
        # Use batch_save for reliable upsert: creates if _key absent, updates if present.
        save_record = {**record}
        key = record.get(key_field)
        if key and key_field != "_key":
            save_record["_key"] = key  # promote custom id field to Splunk _key
        r = await self._client.post(
            f"{_DATA_BASE}/{collection}/batch_save",
            content=json.dumps([save_record]),
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()

    async def delete_by_key(self, collection: str, *, key_field: str, key_value: str) -> None:
        r = await self._client.delete(f"{_DATA_BASE}/{collection}/{key_value}")
        r.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
