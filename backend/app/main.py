from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from jose import jwt, JWTError

from app.auth.router import router as auth_router, limiter as auth_limiter
from app.config import get_settings
from app.database import engine, get_session
from sqlmodel import SQLModel
from app.routers import health_router, clients_router, invoices_router, payments_router

settings = get_settings()


from app.logging import setup_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered SaaS for invoice automation and cashflow intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

import uuid
from app.logging import request_id_ctx
import time

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())
    request_id_ctx.set(req_id)
    
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Process-Time"] = str(process_time)
    
    return response

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting - register limiter and exception handler
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

import logging
import traceback
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException

logger = logging.getLogger("uvicorn.error")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": exc.detail
            }
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Something went wrong"
            }
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "details": jsonable_encoder(exc.errors())
            }
        }
    )


# JWT Auth Middleware for protected routes
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Extract user and workspace from JWT for protected routes."""
    protected_paths = ["/api/v1/clients", "/api/v1/invoices", "/api/v1/payments"]
    
    # Skip auth for non-protected routes
    if not any(str(request.url.path).startswith(path) for path in protected_paths):
        return await call_next(request)
    
    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        request.state.user = None
        request.state.workspace_id = None
        return await call_next(request)
    
    token = auth_header.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        
        user_id = payload.get("sub")
        
        # Fetch full User object from database
        from app.models.user import User
        from sqlmodel import select
        
        from app.database import async_session_maker
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = result.scalar_one_or_none()
            if user and user.is_active:
                request.state.user = user
                request.state.workspace_id = user.workspace_id
                # Safe logging
                logger.info("Authenticated request", extra={"user_id": str(user.id), "workspace_id": str(user.workspace_id), "path": request.url.path})
            else:
                request.state.user = None
                request.state.workspace_id = None
            
    except Exception as e:
        logger.warning(f"Auth error: {type(e).__name__}")
        request.state.user = None
        request.state.workspace_id = None
    
    return await call_next(request)


# Include routers
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(clients_router, prefix="/api/v1")
app.include_router(invoices_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
    }
