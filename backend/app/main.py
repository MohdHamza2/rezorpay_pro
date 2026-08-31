import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException

from app.auth.router import router as auth_router
from app.config import get_settings
from app.database import engine
from app.limiter import limiter
from app.logging import request_id_ctx, setup_logging
from app.routers import (
    clients_router,
    health_router,
    invoices_router,
    payments_router,
)
from app.routers.dashboard import router as dashboard_router
from app.routers.workspaces import router as workspaces_router
from app.routers.products import router as products_router
from app.routers.suppliers import router as suppliers_router
from app.routers.inventory import router as inventory_router
from app.routers.procurement import router as procurement_router
from app.routers.rfq import router as rfq_router
from app.routers.spo import router as spo_router
from app.routers.grn import router as grn_router
from app.routers.supplier_invoices import router as supplier_invoices_router
from app.routers.quotations import router as quotations_router
from app.routers.customer_purchase_orders import (
    router as customer_purchase_orders_router,
)

settings = get_settings()
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging(settings.ENVIRONMENT)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered SaaS for invoice automation and cashflow intelligence",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================
# Middleware
# ============================


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
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============================
# Exception Handlers
# ============================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        error = {
            "code": detail.get("code"),
            "message": detail.get("message", ""),
        }
        if detail.get("field"):
            error["field"] = detail["field"]
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": error},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": "HTTP_ERROR", "message": detail},
        },
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
                "message": "Something went wrong",
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "details": jsonable_encoder(exc.errors()),
            },
        },
    )


# ============================
# Routers
# ============================

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(clients_router, prefix="/api/v1")
app.include_router(invoices_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(procurement_router, prefix="/api/v1")
app.include_router(rfq_router, prefix="/api/v1")
app.include_router(spo_router, prefix="/api/v1")
app.include_router(grn_router, prefix="/api/v1")
app.include_router(supplier_invoices_router, prefix="/api/v1")
app.include_router(quotations_router, prefix="/api/v1")
app.include_router(customer_purchase_orders_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
    }
