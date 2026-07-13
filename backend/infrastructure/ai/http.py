"""Application-scoped HTTP connection pools for LLM providers."""

from __future__ import annotations

import asyncio

import aiohttp


class AiohttpSessionRegistry:
    """Reuse bounded connection pools while remaining safe across event loops."""

    def __init__(self, *, limit: int = 40, limit_per_host: int = 10) -> None:
        self.limit = limit
        self.limit_per_host = limit_per_host
        self._sessions: dict[tuple[int, str], aiohttp.ClientSession] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    async def get(self, *, provider: str, api_base: str) -> aiohttp.ClientSession:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        key = (loop_id, f"{provider}:{api_base.rstrip('/')}")
        session = self._sessions.get(key)
        if session is not None and not session.closed:
            return session

        lock = self._locks.setdefault(loop_id, asyncio.Lock())
        async with lock:
            session = self._sessions.get(key)
            if session is None or session.closed:
                session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(
                        limit=self.limit,
                        limit_per_host=self.limit_per_host,
                        ttl_dns_cache=300,
                        enable_cleanup_closed=True,
                    )
                )
                self._sessions[key] = session
            return session

    async def close(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        self._locks.clear()
        for session in sessions:
            if not session.closed:
                await session.close()


shared_http_sessions = AiohttpSessionRegistry()


async def close_shared_http_sessions() -> None:
    await shared_http_sessions.close()
