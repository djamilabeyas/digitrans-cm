"""
Client Redis avec gestion offline-first.
En cas d'indisponibilité réseau (coupures Douala), les opérations
d'écriture sont mises en file d'attente locale pour synchronisation
ultérieure.
"""

import json
from typing import Any, Optional
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

OFFLINE_QUEUE_KEY = "offline:sync:queue"


class RedisClient:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def connect(self):
        self._client = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        await self._client.ping()

    async def close(self):
        if self._client:
            await self._client.close()

    async def ping(self) -> bool:
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self._client.get(key)
            return json.loads(value) if value else None
        except Exception as e:
            logger.warning("Redis GET échec", extra={"key": key, "error": str(e)})
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        try:
            await self._client.setex(key, ttl, json.dumps(value, default=str))
            return True
        except Exception as e:
            logger.warning("Redis SET échec", extra={"key": key, "error": str(e)})
            return False

    async def delete(self, key: str):
        try:
            await self._client.delete(key)
        except Exception:
            pass

    async def enqueue_offline_operation(self, operation: dict) -> bool:
        """
        Empile une opération dans la file offline pour synchronisation
        différée lors du retour de connectivité.
        """
        try:
            payload = json.dumps({**operation, "queued_at": __import__('time').time()})
            await self._client.rpush(OFFLINE_QUEUE_KEY, payload)
            await self._client.expire(OFFLINE_QUEUE_KEY, settings.REDIS_OFFLINE_QUEUE_TTL)
            logger.info("Opération mise en file offline", extra={"op": operation.get("type")})
            return True
        except Exception as e:
            logger.error("Impossible de mettre en file offline", extra={"error": str(e)})
            return False

    async def dequeue_offline_operations(self, batch_size: int = 50) -> list:
        """Retire et retourne un batch d'opérations à synchroniser."""
        try:
            pipe = self._client.pipeline()
            for _ in range(batch_size):
                pipe.lpop(OFFLINE_QUEUE_KEY)
            results = await pipe.execute()
            return [json.loads(r) for r in results if r]
        except Exception as e:
            logger.error("Erreur dépile offline", extra={"error": str(e)})
            return []

    async def get_offline_queue_size(self) -> int:
        try:
            return await self._client.llen(OFFLINE_QUEUE_KEY)
        except Exception:
            return -1


redis_client = RedisClient()
