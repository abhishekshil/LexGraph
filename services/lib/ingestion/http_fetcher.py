"""Shared HTTP client for public-source adapters.

Purposely conservative:
  - Connect / read timeouts.
  - Token-bucket rate limit per host.
  - Robots.txt compliance (cached).
  - Shared User-Agent advertising the research project and contact.
  - Optional on-disk cache: identical URLs served from the local mirror when
    ``--offline`` or when a recent copy exists.

The `httpx` import is lazy so unit tests that never touch the network don't
need the package.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib import robotparser

from ..core import get_logger, settings


log = get_logger("adapter.http")


USER_AGENT = (
    "LexGraphResearchBot/0.1 (+https://example.invalid/lexgraph) "
    "polite=true; purpose=research"
)


class RateLimiter:
    """Simple token-bucket per host. Safe for a single asyncio loop."""

    def __init__(self, rate_per_sec: float = 1.0, burst: int = 3) -> None:
        self.rate = rate_per_sec
        self.burst = burst
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, host: str) -> None:
        async with self._lock:
            now = time.monotonic()
            tokens, last = self._state.get(host, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < 1.0:
                wait = (1.0 - tokens) / self.rate
                await asyncio.sleep(wait)
                tokens = 0.0
                now = time.monotonic()
            else:
                tokens -= 1.0
            self._state[host] = (tokens, now)


class RobotsCache:
    def __init__(self) -> None:
        self._cache: dict[str, robotparser.RobotFileParser] = {}
        self._lock = asyncio.Lock()

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        async with self._lock:
            rp = self._cache.get(base)
        if rp is None:
            rp = robotparser.RobotFileParser()
            rp.set_url(f"{base}/robots.txt")
            try:
                await asyncio.to_thread(rp.read)
            except Exception as e:  # noqa: BLE001
                log.warning("robots.read_failed", base=base, error=str(e))
                rp = None  # fail-open: be respectful but don't block research
            async with self._lock:
                self._cache[base] = rp  # type: ignore[assignment]
        if rp is None:
            return True
        return bool(rp.can_fetch(USER_AGENT, url))


class HttpFetcher:
    """Rate-limited, robots-respecting async HTTP client with on-disk cache."""

    _instance: "HttpFetcher | None" = None

    def __init__(
        self,
        *,
        cache_root: Path,
        rate_per_sec: float = 1.0,
        timeout_s: float = 30.0,
    ) -> None:
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.rate_limiter = RateLimiter(rate_per_sec=rate_per_sec)
        self.robots = RobotsCache()
        self.timeout_s = timeout_s
        self._client: Any | None = None
        self._client_lock = asyncio.Lock()

    @classmethod
    def shared(cls) -> "HttpFetcher":
        if cls._instance is None:
            root = Path(settings.data_dir) / "raw" / "_http_cache"
            cls._instance = cls(cache_root=root)
        return cls._instance

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is not None:
                return self._client
            import httpx  # type: ignore

            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout_s,
                follow_redirects=True,
            )
            return self._client

    def _cache_path_for(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_root / h[:2] / f"{h}.bin"

    async def get_bytes(
        self,
        url: str,
        *,
        use_cache: bool = True,
        cache_ttl_s: int | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        """Fetch URL bytes. Returns ``(data, headers_subset)``.

        ``cache_ttl_s=None`` means the cached file, if present, is always used.
        Set it to force a re-fetch after N seconds.
        """
        cache = self._cache_path_for(url)
        if use_cache and cache.exists():
            if cache_ttl_s is None or (time.time() - cache.stat().st_mtime) < cache_ttl_s:
                log.debug("http.cache_hit", url=url, path=str(cache))
                return cache.read_bytes(), {"x-cache": "hit"}

        if not await self.robots.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")

        parsed = urlparse(url)
        await self.rate_limiter.acquire(parsed.netloc)

        client = await self._ensure_client()
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)

        headers = {k.lower(): v for k, v in resp.headers.items()}
        log.info(
            "http.fetch",
            url=url,
            status=resp.status_code,
            bytes=len(data),
            content_type=headers.get("content-type", "?"),
        )
        return data, headers

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
