from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_admin_user
from app.infrastructure.auth.auth_service import hash_password
from app.infrastructure.database.models import FeedbackModel, ListeningHistoryModel, UserModel
from app.infrastructure.database.session import get_db_session

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserResponse(BaseModel):
    id: UUID
    username: str
    email: str | None
    display_name: str | None
    is_guest: bool
    is_admin: bool
    created_at: datetime
    first_used_at: datetime
    last_used_at: datetime | None
    songs_played_count: int


class AdminUserUpdateRequest(BaseModel):
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=6)


class AdminStatsResponse(BaseModel):
    total_users: int
    guest_users: int
    admin_users: int


class AdminFeedbackResponse(BaseModel):
    id: UUID
    feedback_type: str
    title: str
    description: str
    contact_email: str | None
    status: str
    created_at: datetime
    username: str | None
    user_email: str | None
    admin_response: str | None
    responded_at: datetime | None


class AdminFeedbackUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|resolved|closed)$")
    admin_response: str | None = Field(default=None, min_length=1, max_length=5000)


async def _activity_by_user(session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, dict]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(
            ListeningHistoryModel.user_id,
            func.count(ListeningHistoryModel.id),
            func.min(ListeningHistoryModel.played_at),
            func.max(ListeningHistoryModel.played_at),
        )
        .where(ListeningHistoryModel.user_id.in_(user_ids))
        .group_by(ListeningHistoryModel.user_id)
    )
    return {
        user_id: {
            "songs_played_count": count,
            "first_played_at": first_at,
            "last_used_at": last_at,
        }
        for user_id, count, first_at, last_at in rows.all()
    }


def _admin_user_response(user: UserModel, activity: dict | None) -> AdminUserResponse:
    songs_played = 0
    first_used_at = user.created_at
    last_used_at = None
    if activity:
        songs_played = activity["songs_played_count"]
        if activity["first_played_at"]:
            first_used_at = activity["first_played_at"]
        last_used_at = activity["last_used_at"]
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_guest=user.is_guest,
        is_admin=user.is_admin,
        created_at=user.created_at,
        first_used_at=first_used_at,
        last_used_at=last_used_at,
        songs_played_count=songs_played,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    admin: UserModel = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(select(UserModel).order_by(UserModel.created_at.desc()))
    users = result.scalars().all()
    activity = await _activity_by_user(session, [u.id for u in users])
    return [_admin_user_response(u, activity.get(u.id)) for u in users]


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(
    admin: UserModel = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    total = await session.scalar(select(func.count()).select_from(UserModel))
    guests = await session.scalar(
        select(func.count()).select_from(UserModel).where(UserModel.is_guest.is_(True))
    )
    admins = await session.scalar(
        select(func.count()).select_from(UserModel).where(UserModel.is_admin.is_(True))
    )
    return AdminStatsResponse(
        total_users=total or 0,
        guest_users=guests or 0,
        admin_users=admins or 0,
    )


def _admin_feedback_response(entry: FeedbackModel, user: UserModel | None) -> AdminFeedbackResponse:
    return AdminFeedbackResponse(
        id=entry.id,
        feedback_type=entry.feedback_type,
        title=entry.title,
        description=entry.description,
        contact_email=entry.contact_email,
        status=entry.status,
        created_at=entry.created_at,
        username=user.username if user else None,
        user_email=user.email if user else None,
        admin_response=entry.admin_response,
        responded_at=entry.responded_at,
    )


@router.get("/feedback", response_model=list[AdminFeedbackResponse])
async def list_feedback(
    status: str | None = Query(default=None, pattern="^(open|in_progress|resolved|closed)$"),
    feedback_type: str | None = Query(default=None, pattern="^(bug|feature)$"),
    admin: UserModel = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    query = select(FeedbackModel, UserModel).outerjoin(UserModel, FeedbackModel.user_id == UserModel.id)
    if status:
        query = query.where(FeedbackModel.status == status)
    if feedback_type:
        query = query.where(FeedbackModel.feedback_type == feedback_type)
    query = query.order_by(FeedbackModel.created_at.desc()).limit(100)
    rows = await session.execute(query)
    return [_admin_feedback_response(entry, user) for entry, user in rows.all()]


@router.patch("/feedback/{feedback_id}", response_model=AdminFeedbackResponse)
async def update_feedback(
    feedback_id: UUID,
    body: AdminFeedbackUpdateRequest,
    admin: UserModel = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    if body.status is None and not body.admin_response:
        raise HTTPException(status_code=400, detail="Provide status and/or admin_response")

    result = await session.execute(
        select(FeedbackModel, UserModel)
        .outerjoin(UserModel, FeedbackModel.user_id == UserModel.id)
        .where(FeedbackModel.id == feedback_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found")

    entry, user = row
    if body.status is not None:
        entry.status = body.status
    if body.admin_response is not None:
        entry.admin_response = body.admin_response.strip()
        entry.responded_at = datetime.now(UTC)
        if entry.status == "open":
            entry.status = "resolved"

    await session.flush()
    return _admin_feedback_response(entry, user)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    body: AdminUserUpdateRequest,
    admin: UserModel = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.is_admin is not None:
        if user.id == admin.id and not body.is_admin:
            raise HTTPException(status_code=400, detail="Cannot remove your own admin role")
        user.is_admin = body.is_admin

    if body.password:
        user.hashed_password = hash_password(body.password)

    await session.flush()
    activity = await _activity_by_user(session, [user.id])
    return _admin_user_response(user, activity.get(user.id))
