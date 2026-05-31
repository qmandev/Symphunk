from __future__ import annotations

import logging

import httpx

from symphunk.config import settings

logger = logging.getLogger(__name__)

_BASE = f"https://{settings.splunk_host}:{settings.splunk_port}/services"


class SplunkREST:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            verify=False,  # self-signed cert in Docker
            headers={"Authorization": f"Bearer {settings.splunk_token}"},
        )

    async def get(self, path: str, **params) -> dict:
        params.setdefault("output_mode", "json")
        r = await self._client.get(f"{_BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()

    async def post(self, path: str, data: dict) -> dict:
        data.setdefault("output_mode", "json")
        r = await self._client.post(f"{_BASE}{path}", data=data)
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()
