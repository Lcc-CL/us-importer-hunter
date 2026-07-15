"""Redis client factory.

The client is created during application lifespan and stored on
``app.state`` — no module-level global client.
"""

from redis.asyncio import Redis


def create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)
