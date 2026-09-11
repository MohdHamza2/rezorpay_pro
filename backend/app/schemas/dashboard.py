from pydantic import BaseModel
from decimal import Decimal


class DashboardStatsResponse(BaseModel):
    total_invoices: int
    outstanding_balance: Decimal
    pending_prs: int
    active_rfqs: int
    unposted_grns: int
    # AR PDC Outstanding — operational metric, not a balance due component
    ar_pdc_outstanding_count: int = 0
    ar_pdc_outstanding_amount: Decimal = Decimal("0.00")
