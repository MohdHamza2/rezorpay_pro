from app.routers.health import router as health_router
from app.routers.clients import router as clients_router
from app.routers.invoices import router as invoices_router
from app.routers.payments import router as payments_router

__all__ = [
    "health_router",
    "clients_router",
    "invoices_router",
    "payments_router",
]
