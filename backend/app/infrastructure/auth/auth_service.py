import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infrastructure.database.models import (
    RefreshTokenModel,
    SessionModel,
    UserModel,
    UserPreferencesModel,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: UUID, username: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


class AuthService:
    async def register(
        self, session: AsyncSession, username: str, email: str | None, password: str
    ) -> UserModel:
        existing = await session.execute(
            select(UserModel).where(UserModel.username == username)
        )
        if existing.scalar_one_or_none():
            raise ValueError("Username already taken")

        user = UserModel(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            is_guest=False,
        )
        session.add(user)
        await session.flush()
        session.add(UserPreferencesModel(user_id=user.id))
        return user

    async def login(self, session: AsyncSession, username: str, password: str) -> UserModel:
        result = await session.execute(select(UserModel).where(UserModel.username == username))
        user = result.scalar_one_or_none()
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            raise ValueError("Invalid credentials")
        return user

    async def create_guest(self, session: AsyncSession) -> UserModel:
        guest_name = f"guest_{uuid4().hex[:8]}"
        user = UserModel(username=guest_name, is_guest=True)
        session.add(user)
        await session.flush()
        session.add(UserPreferencesModel(user_id=user.id))
        return user

    async def google_login(
        self, session: AsyncSession, google_id: str, email: str, name: str, avatar: str | None
    ) -> UserModel:
        result = await session.execute(select(UserModel).where(UserModel.google_id == google_id))
        user = result.scalar_one_or_none()
        if user:
            return user

        username = name.replace(" ", "_").lower()[:50] or f"user_{uuid4().hex[:6]}"
        user = UserModel(
            username=username,
            email=email,
            google_id=google_id,
            avatar_url=avatar,
            is_guest=False,
        )
        session.add(user)
        await session.flush()
        session.add(UserPreferencesModel(user_id=user.id))
        return user

    async def start_session(
        self, session: AsyncSession, user_id: UUID, device_id: str | None = None
    ) -> SessionModel:
        s = SessionModel(user_id=user_id, device_id=device_id)
        session.add(s)
        await session.flush()
        return s

    async def issue_token_pair(
        self,
        session: AsyncSession,
        user: UserModel,
        device_id: str | None = None,
    ) -> tuple[str, str]:
        access_token = create_access_token(user.id, user.username)
        refresh_token = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_expire_days)
        session.add(
            RefreshTokenModel(
                user_id=user.id,
                token_hash=_hash_refresh_token(refresh_token),
                device_id=device_id,
                expires_at=expires_at,
            )
        )
        await session.flush()
        return access_token, refresh_token

    async def refresh_tokens(
        self,
        session: AsyncSession,
        refresh_token: str,
        device_id: str | None = None,
    ) -> tuple[UserModel, str, str]:
        token_hash = _hash_refresh_token(refresh_token)
        result = await session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        stored = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if (
            not stored
            or stored.revoked_at is not None
            or stored.expires_at <= now
        ):
            raise ValueError("Invalid or expired refresh token")

        user_result = await session.execute(
            select(UserModel).where(UserModel.id == stored.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        stored.revoked_at = now
        access_token, new_refresh_token = await self.issue_token_pair(
            session, user, device_id=device_id or stored.device_id
        )
        return user, access_token, new_refresh_token

    async def revoke_refresh_token(self, session: AsyncSession, refresh_token: str) -> None:
        token_hash = _hash_refresh_token(refresh_token)
        result = await session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
        stored = result.scalar_one_or_none()
        if stored and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
