import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel

from app.main import app
from app.database import get_session
from app.config import get_settings

settings = get_settings()

# Use a test database
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "invoicesaas", "invoicesaas_test"
)

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def override_get_session():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


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
    register_data = {
        "email": "test@example.com",
        "password": "securepassword123",
        "name": "Test User",
        "workspace_name": "Test Workspace"
    }
    response = client.post("/auth/register", json=register_data)
    assert response.status_code == 201
    tokens = response.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    
    # Login
    login_data = {
        "email": "test@example.com",
        "password": "securepassword123"
    }
    response = client.post("/auth/login", json=login_data)
    assert response.status_code == 200
    tokens = response.json()
    assert "access_token" in tokens
    
    # Get current user
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    user = response.json()
    assert user["email"] == "test@example.com"
    assert user["role"] == "owner"
