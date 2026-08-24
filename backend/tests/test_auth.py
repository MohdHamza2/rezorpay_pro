import pytest
import uuid
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import get_session
from app.config import get_settings
# Import all models so SQLModel.metadata is populated before create_all
from app.models import *  # noqa: F401, F403

settings = get_settings()

# Use a test database
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "invoicesaas", "invoicesaas_test"
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
    """Create all tables before tests run, drop them after."""
    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == settings.APP_NAME


def test_register_and_login():
    # Register
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    register_data = {
        "email": test_email,
        "password": "securepassword123",
        "name": "Test User",
        "workspace_name": "Test Workspace"
    }
    response = client.post("/auth/register", json=register_data)
    if response.status_code != 201:
        print(response.json())
    assert response.status_code == 201
    tokens = response.json()["data"]
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # Login
    login_data = {
        "email": test_email,
        "password": "securepassword123"
    }
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    tokens = response.json()["data"]
    assert "access_token" in tokens

    # Get current user
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    user = response.json()["data"]
    assert user["email"] == test_email
    assert user["role"] == "OWNER"
