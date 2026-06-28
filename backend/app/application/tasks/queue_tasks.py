"""Background tasks that need their own DB session."""

import structlog
from uuid import UUID

from app.dependencies import get_queue_service
from app.infrastructure.database.session import async_session_factory

logger = structlog.get_logger()


async def run_queue_sync_background(user_id: UUID) -> None:
    """Refill queue after skip/end without blocking the next-track API response."""
    queue_svc = get_queue_service()
    async with async_session_factory() as session:
        try:
            await queue_svc.sync_queue(session, user_id)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("background_queue_sync_failed", user_id=str(user_id))
