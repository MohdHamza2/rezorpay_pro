import asyncio
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from tests.test_ar_statement import _ready, _sent_invoice, _line, _stmt
from app.config import get_settings
from app.database import get_session
from app.main import app
from app.models import *  # noqa: F401, F403
from app.services.credit_control_service import utc_today

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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


def test_stmt_with_tdn():
    headers, client_id = _ready()
    today = utc_today()
    invoice = _sent_invoice(headers, client_id, [_line(price="100.00")])
    # create TDN
    tdn_resp = client.post(
        "/api/v1/debit-notes",
        json={
            "invoice_id": invoice["id"],
            "reason": "PRICE_INCREASE",
            "items": [{"invoice_item_id": invoice["items"][0]["id"], "quantity": "1"}],
        },
        headers=headers,
    )
    assert tdn_resp.status_code == 201, tdn_resp.text
    tdn = tdn_resp.json()["data"]
    # issue TDN
    issue_resp = client.post(
        f"/api/v1/debit-notes/{tdn['id']}/issue", json={}, headers=headers
    )
    assert issue_resp.status_code == 200, issue_resp.text
    # Get stmt
    stmt = _stmt(headers, client_id, today, today)
    assert stmt.status_code == 200, stmt.text
