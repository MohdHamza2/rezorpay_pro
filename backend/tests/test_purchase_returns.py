"""Wave 23 — purchase return lifecycle tests.

Covers: create → submit → approve → dispatch (stock-out + auto supplier debit
note) → complete, received-cap invariant (create, cumulative, cancel-frees-cap),
illegal transitions, GRN-004 auto-return from disposition, zero-stock-out
dispatch, workspace isolation, member-role gate, PRN sequence format.

The SPO→GRN→disposition fixture chain is built through the public API, mirroring
test_e2e_grn, so every test exercises the real service + router stack.
"""

import asyncio
import re
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.auth.utils import hash_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: E402, F401, F403
from app.models.inventory import InventoryLevel, InventoryTransaction  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

settings = get_settings()

TEST_DATABASE_URL = (
    settings.DATABASE_URL
    if settings.DATABASE_URL.endswith("_test")
    else settings.DATABASE_URL + "_test"
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def override_get_session():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_setup())
    yield

    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)

    asyncio.run(_teardown())


def register_and_token():
    email = f"pr_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": "PR Tester",
            "workspace_name": "PR Workspace",
        },
    )
    if r.status_code != 201:
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "securepassword123"},
        )
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["data"]["workspace_id"]


def member_token(workspace_id):
    email = f"prmem_{uuid.uuid4().hex[:8]}@example.com"

    async def _insert() -> None:
        async with TestingSessionLocal() as session:
            session.add(
                User(
                    workspace_id=uuid.UUID(workspace_id),
                    email=email,
                    password_hash=hash_password("securepassword123"),
                    name="PR Member",
                    role=UserRole.MEMBER,
                )
            )
            await session.commit()

    asyncio.run(_insert())
    r = client.post(
        "/auth/login", json={"email": email, "password": "securepassword123"}
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


def build_purchase_chain(
    token,
    *,
    received=10,
    accepted=None,
    rejected=0,
    damaged=0,
    unit_price=50,
    qty_confirmed=None,
):
    """SPO → ack → GRN → disposition, returns id map."""
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=headers)
    workspace_id = me.json()["data"]["workspace_id"]

    sup = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={
            "name": "ReturnCo",
            "supplier_code": f"RET{uuid.uuid4().hex[:4]}",
            "email": "r@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    )
    assert sup.status_code in (200, 201), sup.text
    supplier_id = sup.json()["data"]["id"]

    wh = client.post(
        "/api/v1/inventory/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"WH{uuid.uuid4().hex[:4]}", "address": "x"},
    )
    assert wh.status_code in (200, 201), wh.text
    warehouse_id = wh.json()["data"]["id"]
    bin_r = client.post(
        f"/api/v1/inventory/warehouses/{warehouse_id}/bins",
        headers=headers,
        json={"code": "BIN1"},
    )
    assert bin_r.status_code in (200, 201), bin_r.text

    uom = client.post(
        "/api/v1/products/uom",
        headers=headers,
        json={"name": "UOM", "code": "UOM1"},
    )
    uom_id = uom.json()["data"]["id"]
    prod = client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "PROD", "internal_sku": "PROD1", "base_uom_id": uom_id},
    )
    assert prod.status_code in (200, 201), prod.text
    product_id = prod.json()["data"]["id"]

    confirmed = qty_confirmed or received
    spo = client.post(
        "/api/v1/spos",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "procurement_method": "DIRECT",
            "warehouse_id": warehouse_id,
            "currency": "AED",
            "items": [
                {
                    "product_id": product_id,
                    "description": "Widget A",
                    "uom_id": uom_id,
                    "quantity_ordered": confirmed,
                    "unit_price": unit_price,
                    "vat_rate": 5.0,
                    "line_number": 1,
                }
            ],
        },
    )
    assert spo.status_code in (200, 201), spo.text
    spo_id = spo.json()["data"]["id"]
    spo_item_id = spo.json()["data"]["items"][0]["id"]

    for action in ("submit-approval", "approve", "send"):
        r = client.post(f"/api/v1/spos/{spo_id}/{action}", headers=headers)
        assert r.status_code in (200, 201, 202), (action, r.text)

    ack = client.post(
        f"/api/v1/spos/{spo_id}/items/acknowledge",
        headers=headers,
        json={
            "lines": {
                spo_item_id: {"quantity_confirmed": confirmed, "unit_price": unit_price}
            }
        },
    )
    assert ack.status_code in (200, 201), ack.text

    grn = client.post(
        "/api/v1/grns",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "spo_id": spo_id,
            "warehouse_id": warehouse_id,
            "received_date": "2026-09-05",
        },
    )
    assert grn.status_code == 201, grn.text
    grn_id = grn.json()["data"]["id"]
    client.post(f"/api/v1/grns/{grn_id}/start-receiving", headers=headers)

    item_r = client.post(
        f"/api/v1/grns/{grn_id}/items",
        headers=headers,
        json={
            "spo_item_id": spo_item_id,
            "product_id": product_id,
            "internal_sku": "PROD1",
            "description": "Widget A",
            "uom_id": uom_id,
            "quantity_received": received,
        },
    )
    assert item_r.status_code in (200, 201), item_r.text
    grn_item_id = item_r.json()["data"]["items"][0]["id"]

    client.post(f"/api/v1/grns/{grn_id}/stage-for-inspection", headers=headers)

    accepted = accepted if accepted is not None else received - rejected - damaged
    disp = {
        "quantity_accepted": accepted,
        "quantity_damaged": damaged,
        "quantity_rejected": rejected,
    }
    if damaged:
        disp["damage_reason"] = "Scratched and bent during transit"
    if rejected:
        disp["rejection_reason"] = "Failed quality inspection entirely"
    r = client.post(
        f"/api/v1/grns/{grn_id}/items/{grn_item_id}/disposition",
        headers=headers,
        json=disp,
    )
    assert r.status_code == 200, r.text

    return {
        "workspace_id": workspace_id,
        "supplier_id": supplier_id,
        "warehouse_id": warehouse_id,
        "grn_id": grn_id,
        "grn_item_id": grn_item_id,
        "product_id": product_id,
        "uom_id": uom_id,
        "spo_item_id": spo_item_id,
        "unit_price": unit_price,
    }


def create_return(token, chain, qty, price=None, return_type="EXCESS"):
    body = {
        "supplier_id": chain["supplier_id"],
        "grn_id": chain["grn_id"],
        "return_date": "2026-09-06",
        "reason": "Returning surplus goods",
        "items": [
            {
                "grn_item_id": chain["grn_item_id"],
                "quantity": qty,
                "unit_price": price if price is not None else chain["unit_price"],
                "return_type": return_type,
            }
        ],
    }
    return client.post(
        "/api/v1/purchase-returns",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


async def _prn_ledger_rows(reference_id: str) -> list[dict]:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.reference_type == "PRN",
                InventoryTransaction.reference_id == uuid.UUID(reference_id),
            )
        )
        return [
            {
                "transaction_type": t.transaction_type.value,
                "quantity": t.quantity,
                "reason": t.reason,
            }
            for t in result.scalars().all()
        ]


async def _on_hand(chain: dict) -> Decimal:
    async with TestingSessionLocal() as session:
        result = await session.execute(
            select(InventoryLevel).where(
                InventoryLevel.workspace_id == uuid.UUID(chain["workspace_id"]),
                InventoryLevel.product_id == uuid.UUID(chain["product_id"]),
                InventoryLevel.warehouse_id == uuid.UUID(chain["warehouse_id"]),
            )
        )
        level = result.scalar_one_or_none()
        return Decimal(level.on_hand) if level else Decimal(0)


def test_full_lifecycle_with_auto_sdn_and_stock_out():
    token, _ = register_and_token()
    chain = build_purchase_chain(token, received=10)
    r = create_return(token, chain, qty="4")
    assert r.status_code == 201, r.text
    pr = r.json()["data"]
    assert pr["status"] == "DRAFT"
    assert re.match(r"^PRN-\d{4}-\d{4}$", pr["prn_number"])

    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        f"/api/v1/purchase-returns/{pr['id']}/submit-for-supplier-approval",
        json={},
        headers=headers,
    )
    assert r.json()["data"]["status"] == "PENDING_SUPPLIER"
    assert r.json()["data"]["items"][0]["total_price"] == "200.00"

    item_id = pr["items"][0]["id"]
    before = asyncio.run(_on_hand(chain))

    for action in ("approve", "dispatch", "complete"):
        r = client.post(
            f"/api/v1/purchase-returns/{pr['id']}/{action}",
            json={},
            headers=headers,
        )
        assert r.status_code == 200, (action, r.text)

    dispatched = client.get(
        f"/api/v1/purchase-returns/{pr['id']}", headers=headers
    ).json()["data"]
    assert dispatched["status"] == "COMPLETED"
    assert dispatched["items"][0]["stock_out_qty"] == "4.0000"
    assert dispatched["total_value"] == "200.00"

    after = asyncio.run(_on_hand(chain))
    assert before - after == Decimal("4")

    rows = asyncio.run(_prn_ledger_rows(item_id))
    assert len(rows) == 1
    assert rows[0]["transaction_type"] == "ISSUE"
    assert rows[0]["quantity"] == Decimal("-4")
    assert rows[0]["reason"] == "PURCHASE_RETURN"

    lst = client.get(
        "/api/v1/supplier-debit-notes", headers={"Authorization": f"Bearer {token}"}
    )
    assert lst.status_code == 200, lst.text
    notes = lst.json()["data"]
    assert len(notes) == 1
    note = notes[0]
    assert note["status"] == "ISSUED"
    assert note["source_type"] == "PURCHASE_RETURN"
    assert note["amount"] == "200.00"
    assert note["dn_number"].startswith("SDN-")


def test_received_cap_invariant_at_create_and_cumulative():
    token, _ = register_and_token()
    chain = build_purchase_chain(token, received=10)

    over = create_return(token, chain, qty="11")
    assert over.status_code == 400, over.text
    assert over.json()["error"]["code"] == "RETURN_QTY_EXCEEDS_RECEIVED"

    first = create_return(token, chain, qty="6")
    assert first.status_code == 201, first.text

    second_over = create_return(token, chain, qty="5")
    assert second_over.status_code == 400, second_over.text
    assert second_over.json()["error"]["code"] == "RETURN_QTY_EXCEEDS_RECEIVED"

    second_ok = create_return(token, chain, qty="4")
    assert second_ok.status_code == 201, second_ok.text


def test_submit_reenforces_cap_and_cancel_frees_it():
    token, _ = register_and_token()
    chain = build_purchase_chain(token, received=10)

    r1 = create_return(token, chain, qty="8")
    r2 = create_return(token, chain, qty="3")
    assert r2.status_code == 400, r2.text

    headers = {"Authorization": f"Bearer {token}"}
    cancel = client.post(
        f"/api/v1/purchase-returns/{r1.json()['data']['id']}/cancel",
        json={},
        headers=headers,
    )
    assert cancel.json()["data"]["status"] == "CANCELLED"

    r3 = create_return(token, chain, qty="9")
    assert r3.status_code == 201, r3.text

    # an at-cap return submits cleanly (no self-rejection double count)
    submit = client.post(
        f"/api/v1/purchase-returns/{r3.json()['data']['id']}/submit-for-supplier-approval",
        json={},
        headers=headers,
    )
    assert submit.status_code == 200, submit.text


def test_illegal_transitions():
    token, _ = register_and_token()
    chain = build_purchase_chain(token, received=10)
    headers = {"Authorization": f"Bearer {token}"}
    pr = create_return(token, chain, qty="3").json()["data"]

    def act(action, pid):
        return client.post(
            f"/api/v1/purchase-returns/{pid}/{action}", json={}, headers=headers
        )

    # dispatch requires APPROVED
    r = act("dispatch", pr["id"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_STATE"

    # approve requires PENDING_SUPPLIER
    r = act("approve", pr["id"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_STATE"

    # complete requires DISPATCHED
    act("submit-for-supplier-approval", pr["id"])
    r = act("complete", pr["id"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_STATE"

    # reject only from PENDING_SUPPLIER
    r = act("reject", pr["id"])
    assert r.status_code == 200 and r.json()["data"]["status"] == "REJECTED"
    r = act("cancel", pr["id"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_STATE"

    # cancel only from DRAFT / PENDING_SUPPLIER
    pr2 = create_return(token, chain, qty="2").json()["data"]
    act("submit-for-supplier-approval", pr2["id"])
    act("approve", pr2["id"])
    r = act("cancel", pr2["id"])
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_STATE"


def test_grn004_auto_return_quantities_and_price():
    token, _ = register_and_token()
    build_purchase_chain(token, received=10, rejected=5, damaged=5, unit_price=100)

    lst = client.get(
        "/api/v1/purchase-returns", headers={"Authorization": f"Bearer {token}"}
    )
    assert lst.status_code == 200, lst.text
    records = lst.json()["data"]
    assert len(records) == 1
    pr = records[0]
    assert pr["status"] == "DRAFT"
    assert pr["reason"] == "Auto-created from GRN disposition"
    types = sorted((i["return_type"], i["quantity"]) for i in pr["items"])
    assert types == [("DAMAGE", "5.0000"), ("QUALITY_ISSUE", "5.0000")]
    assert all(i["unit_price"] == "100.00" for i in pr["items"])

    # zero accepted → zero on-hand → zero stock-out, still auto-SDN full value
    headers = {"Authorization": f"Bearer {token}"}
    for action in ("submit-for-supplier-approval", "approve", "dispatch"):
        r = client.post(
            f"/api/v1/purchase-returns/{pr['id']}/{action}", json={}, headers=headers
        )
        assert r.status_code == 200, (action, r.text)
    got = client.get(f"/api/v1/purchase-returns/{pr['id']}", headers=headers).json()[
        "data"
    ]
    assert all(i["stock_out_qty"] == "0.0000" for i in got["items"])

    for item_id in (i["id"] for i in got["items"]):
        assert asyncio.run(_prn_ledger_rows(item_id)) == []

    notes = client.get("/api/v1/supplier-debit-notes", headers=headers).json()["data"]
    assert len(notes) == 1
    assert notes[0]["amount"] == "1000.00"


def test_auto_cumulative_cap_with_manual_return():
    token, _ = register_and_token()
    chain = build_purchase_chain(
        token, received=15, rejected=5, damaged=5, accepted=5, unit_price=50
    )

    # auto-return holds 10 of the 15-unit received cap
    manual = create_return(token, chain, qty="6")
    assert manual.status_code == 400, manual.text
    assert manual.json()["error"]["code"] == "RETURN_QTY_EXCEEDS_RECEIVED"

    manual = create_return(token, chain, qty="5")
    assert manual.status_code == 201, manual.text

    auto = next(
        r
        for r in client.get(
            "/api/v1/purchase-returns", headers={"Authorization": f"Bearer {token}"}
        ).json()["data"]
        if r["reason"] == "Auto-created from GRN disposition"
    )

    headers = {"Authorization": f"Bearer {token}"}
    for action in ("submit-for-supplier-approval", "approve", "dispatch"):
        client.post(
            f"/api/v1/purchase-returns/{manual.json()['data']['id']}/{action}",
            json={},
            headers=headers,
        )
    for action in ("submit-for-supplier-approval", "approve", "dispatch"):
        r = client.post(
            f"/api/v1/purchase-returns/{auto['id']}/{action}", json={}, headers=headers
        )
        assert r.status_code == 200, (action, r.text)

    notes = client.get("/api/v1/supplier-debit-notes", headers=headers).json()["data"]
    amounts = sorted(n["amount"] for n in notes)
    assert amounts == ["250.00", "500.00"]


def test_zero_stock_out_when_nothing_available():
    token, _ = register_and_token()
    build_purchase_chain(token, received=10, rejected=10)

    auto = client.get(
        "/api/v1/purchase-returns", headers={"Authorization": f"Bearer {token}"}
    ).json()["data"][0]

    headers = {"Authorization": f"Bearer {token}"}
    for action in ("submit-for-supplier-approval", "approve", "dispatch"):
        r = client.post(
            f"/api/v1/purchase-returns/{auto['id']}/{action}",
            json={},
            headers=headers,
        )
        assert r.status_code == 200, (action, r.text)

    got = client.get(f"/api/v1/purchase-returns/{auto['id']}", headers=headers).json()[
        "data"
    ]
    assert got["items"][0]["stock_out_qty"] == "0.0000"
    assert got["items"][0]["quantity"] == "10.0000"


def test_workspace_isolation_and_member_gate():
    token_a, ws_a = register_and_token()
    chain = build_purchase_chain(token_a, received=10)
    pr = create_return(token_a, chain, qty="3").json()["data"]

    token_b, _ = register_and_token()
    headers_b = {"Authorization": f"Bearer {token_b}"}
    r = client.get(f"/api/v1/purchase-returns/{pr['id']}", headers=headers_b)
    assert r.status_code == 404, r.text
    r = client.post(
        f"/api/v1/purchase-returns/{pr['id']}/submit-for-supplier-approval",
        json={},
        headers=headers_b,
    )
    assert r.status_code == 404, r.text

    member = member_token(ws_a)
    headers_m = {"Authorization": f"Bearer {member}"}
    r = client.post(
        "/api/v1/purchase-returns",
        headers=headers_m,
        json={
            "supplier_id": chain["supplier_id"],
            "grn_id": chain["grn_id"],
            "return_date": "2026-09-06",
            "reason": "Returning surplus goods",
            "items": [
                {
                    "grn_item_id": chain["grn_item_id"],
                    "quantity": "1",
                    "unit_price": "50.00",
                    "return_type": "EXCESS",
                }
            ],
        },
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    r = client.get("/api/v1/purchase-returns", headers=headers_m)
    assert r.status_code == 200, r.text


def test_prn_sequence_format():
    token, _ = register_and_token()
    chain = build_purchase_chain(token, received=10)
    year = datetime.now(timezone.utc).year
    first = create_return(token, chain, qty="2").json()["data"]["prn_number"]
    second = create_return(token, chain, qty="2").json()["data"]["prn_number"]
    assert first == f"PRN-{year}-0001"
    assert second == f"PRN-{year}-0002"


def test_grn_mismatched_supplier_rejected():
    token, _ = register_and_token()
    chain = build_purchase_chain(token, received=10)
    headers = {"Authorization": f"Bearer {token}"}
    sup = client.post(
        "/api/v1/suppliers",
        headers=headers,
        json={
            "name": "OtherSupplier",
            "supplier_code": f"OTH{uuid.uuid4().hex[:4]}",
            "email": "o@example.com",
            "currency": "AED",
            "status": "ACTIVE",
        },
    ).json()["data"]
    r = client.post(
        "/api/v1/purchase-returns",
        headers=headers,
        json={
            "supplier_id": sup["id"],
            "grn_id": chain["grn_id"],
            "return_date": "2026-09-06",
            "reason": "Returning surplus goods",
            "items": [
                {
                    "grn_item_id": chain["grn_item_id"],
                    "quantity": "1",
                    "unit_price": "50.00",
                    "return_type": "EXCESS",
                }
            ],
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE"
