from __future__ import annotations

import asyncio
import time

import redis.asyncio as redis

from app.core.config import settings

# Token-bucket global rate limiter shared across workers via Redis.
# Refills `rps` tokens per second up to a burst capacity.
_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

local delta = math.max(0, now - ts)
tokens = math.min(capacity, tokens + delta * rate)

local allowed = 0
local wait = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
else
  wait = (requested - tokens) / rate
end

redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 60)
return {allowed, tostring(wait)}
"""


class RateLimiter:
    def __init__(self, client: redis.Redis, rps: float, key: str = "vi:ratelimit"):
        self.client = client
        self.rps = max(rps, 0.1)
        self.capacity = max(rps, 1.0)
        self.key = key
        self._script = client.register_script(_LUA)

    async def acquire(self) -> None:
        while True:
            allowed, wait = await self._script(
                keys=[self.key],
                args=[self.rps, self.capacity, time.time(), 1],
            )
            if int(allowed) == 1:
                return
            await asyncio.sleep(min(float(wait) + 0.01, 5.0))


def make_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)
