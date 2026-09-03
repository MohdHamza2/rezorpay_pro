import pytest
from tests.test_ar_statement import _ready, _sent_invoice, _line, _stmt
from app.services.credit_control_service import utc_today
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_stmt_with_tdn():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="100.00")])
    # create TDN
    tdn_resp = client.post(
        "/api/v1/tax-debit-notes",
        json={
            "invoice_id": invoice["id"],
            "reason": "PRICE_UPDATE",
            "items": [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}]
        },
        headers=headers
    )
    assert tdn_resp.status_code == 201, tdn_resp.text
    tdn = tdn_resp.json()["data"]
    # issue TDN
    issue_resp = client.post(f"/api/v1/tax-debit-notes/{tdn['id']}/issue", json={}, headers=headers)
    assert issue_resp.status_code == 200, issue_resp.text
    # Get stmt
    stmt = _stmt(headers, client_id, today, today)
    assert stmt.status_code == 200, stmt.text
