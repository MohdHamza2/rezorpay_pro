import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_active_user,
)
from app.config import get_settings
from app.database import get_session
from app.models import User, Workspace
from app.models.user import UserRole
from app.schemas.common import SuccessResponse
from app.limiter import limiter

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)

settings = get_settings()


# Schemas
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    workspace_name: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: str
    workspace_id: uuid.UUID
    is_active: bool
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post(
    "/register",
    response_model=SuccessResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(
    request: Request, data: UserRegister, session: AsyncSession = Depends(get_session)
):
    # Normalize email to lowercase
    email = data.email.lower()

    # Check if email already exists
    result = await session.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create workspace
    workspace_slug = data.workspace_name.lower().replace(" ", "-").replace("_", "-")
    # Check for slug uniqueness - append random suffix if needed
    base_slug = workspace_slug
    counter = 1
    while True:
        result = await session.execute(
            select(Workspace).where(Workspace.slug == workspace_slug)
        )
        if not result.scalar_one_or_none():
            break
        workspace_slug = f"{base_slug}-{counter}"
        counter += 1

    workspace = Workspace(
        name=data.workspace_name,
        slug=workspace_slug,
    )
    session.add(workspace)
    await session.flush()  # Get workspace.id

    # Create user
    user = User(
        workspace_id=workspace.id,
        email=email,
        password_hash=hash_password(data.password),
        name=data.name,
        role=UserRole.OWNER,
        is_active=True,
    )
    session.add(user)
    await session.commit()

    # Generate tokens with workspace_id for multi-tenancy
    access_token = create_access_token(
        {"sub": str(user.id), "workspace_id": str(user.workspace_id)}
    )
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                role=user.role.value,
                workspace_id=user.workspace_id,
                is_active=user.is_active,
                created_at=user.created_at.isoformat() if user.created_at else None,
            ),
        )
    )


@router.post("/login", response_model=SuccessResponse[TokenResponse])
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request, data: UserLogin, session: AsyncSession = Depends(get_session)
):
    # Normalize email
    email = data.email.lower()

    # Find user
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    # Generate tokens with workspace_id for multi-tenancy
    access_token = create_access_token(
        {"sub": str(user.id), "workspace_id": str(user.workspace_id)}
    )
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                role=user.role.value,
                workspace_id=user.workspace_id,
                is_active=user.is_active,
                created_at=user.created_at.isoformat() if user.created_at else None,
            ),
        )
    )


@router.post("/refresh", response_model=SuccessResponse[TokenResponse])
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh_token(
    request: Request,
    data: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
):
    payload = decode_token(data.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user still exists
    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate new tokens with workspace_id
    access_token = create_access_token(
        {"sub": str(user.id), "workspace_id": str(user.workspace_id)}
    )
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                role=user.role.value,
                workspace_id=user.workspace_id,
                is_active=user.is_active,
                created_at=user.created_at.isoformat() if user.created_at else None,
            ),
        )
    )


@router.get("/me", response_model=SuccessResponse[UserResponse])
async def get_me(current_user: User = Depends(get_current_active_user)):
    return SuccessResponse(
        data=UserResponse(
            id=current_user.id,
            email=current_user.email,
            name=current_user.name,
            role=current_user.role.value,
            workspace_id=current_user.workspace_id,
            is_active=current_user.is_active,
            created_at=(
                current_user.created_at.isoformat() if current_user.created_at else None
            ),
        )
    )
