from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_admin_user
from app.infrastructure.auth.auth_service import hash_password
from app.infrastructure.database.models import UserModel
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


class AdminUserUpdateRequest(BaseModel):
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=6)


class AdminStatsResponse(BaseModel):
    total_users: int
    guest_users: int
    admin_users: int


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    admin: UserModel = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(select(UserModel).order_by(UserModel.created_at.desc()))
    users = result.scalars().all()
    return [
        AdminUserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            display_name=u.display_name,
            is_guest=u.is_guest,
            is_admin=u.is_admin,
            created_at=u.created_at,
        )
        for u in users
    ]


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
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_guest=user.is_guest,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )
