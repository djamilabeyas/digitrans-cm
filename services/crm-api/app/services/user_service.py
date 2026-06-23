import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.client import Client


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[Client]:
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None
    return await db.get(Client, uid)
