import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_session
from app.auth.dependencies import get_current_user, get_current_workspace_id
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspaces import WorkspaceResponse, WorkspaceUpdate
from app.schemas.common import SuccessResponse
from app.services.credit_control_service import assert_warning_not_after_hold

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get("/me", response_model=SuccessResponse[WorkspaceResponse])
async def get_current_workspace(
    request: Request,
    session: AsyncSession = Depends(get_session),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .where(Workspace.deleted_at.is_(None))
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    return SuccessResponse(data=WorkspaceResponse.model_validate(workspace))


@router.put("/me", response_model=SuccessResponse[WorkspaceResponse])
async def update_current_workspace(
    request: Request,
    workspace_data: WorkspaceUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
):
    result = await session.execute(
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .where(Workspace.deleted_at.is_(None))
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    update_data = workspace_data.model_dump(exclude_unset=True)

    warning_days = update_data.get("credit_warning_days", workspace.credit_warning_days)
    hold_days = update_data.get("credit_hold_days", workspace.credit_hold_days)
    assert_warning_not_after_hold(warning_days, hold_days)

    for field, value in update_data.items():
        setattr(workspace, field, value)

    if update_data:
        workspace.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(workspace)

    return SuccessResponse(data=WorkspaceResponse.model_validate(workspace))
