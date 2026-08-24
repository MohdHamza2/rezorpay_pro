from fastapi import APIRouter, status, Depends
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from app.database import get_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", status_code=status.HTTP_200_OK)
@router.get("", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy", "service": "invoicesaas-api"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Database not ready")
