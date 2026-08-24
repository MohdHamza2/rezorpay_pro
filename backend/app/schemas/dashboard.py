from pydantic import BaseModel
from decimal import Decimal
import uuid
from typing import Dict, Any

class DashboardStatsResponse(BaseModel):
    total_invoices: int
    outstanding_balance: Decimal
    pending_prs: int
    active_rfqs: int
    unposted_grns: int
