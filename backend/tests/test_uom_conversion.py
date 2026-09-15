"""Wave 31 Item 2.9 — UOM conversion resolver tests.

Covers the reusable resolver in ``app.services.uom_conversion_service``
(Option 1 scope: resolver + tests only, no consumer rewiring):

- pure-core semantics: identity, base<->non-base legs, two-hop paths,
  no-path ``None``, invalid-row handling, full-precision division,
  determinism;
- DB loader boundary: scoped bulk load, unknown/cross-workspace
  product → 404, cross-workspace/cross-product row isolation,
  no per-leg N+1 queries.

Follows the suite's standard harness: sync ``TestClient`` against a real
PostgreSQL ``_test`` database, module-scoped schema create/drop, direct
``asyncio.run`` session inserts. Existing award/product conversion
behavior is asserted unchanged only via the untouched regression suites
(``test_products.py``, ``test_rfq_awards.py``); no test here expects the
award flow to resolve multi-hop paths.
"""

import asyncio
import sys
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import get_settings
from app.database import get_session
from app.main import app

# Import all models so SQLModel.metadata is fully populated before create_all
from app.models import *  # noqa: F401, F403
from app.models.product import Product, ProductUOMConversion, UnitOfMeasure
from app.services.uom_conversion_service import (
    convert_quantity,
    convert_quantity_for_product,
    resolve_factor,
    resolve_factor_for_product,
)

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


def _register(prefix="owner"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "securepassword123",
            "name": prefix,
            "workspace_name": f"{prefix} Workspace",
        },
    )
    assert r.status_code == 201, f"register failed: {r.text}"
    token = r.json()["data"]["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    return token, me.json()["data"]["workspace_id"]


def _row(workspace_id, product_id, to_uom_id, factor):
    return ProductUOMConversion(
        workspace_id=workspace_id,
        product_id=product_id,
        to_uom_id=to_uom_id,
        conversion_factor=Decimal(str(factor)),
    )


def _seed_world(tag):
    """Workspace with PCS base, BOX=10, CTN=50 on P1, and row-less P2."""
    _, ws = _register(f"uom29_{tag}")
    ws_id = uuid.UUID(ws)

    async def _seed():
        async with TestingSessionLocal() as session:
            pcs = UnitOfMeasure(workspace_id=ws_id, code=f"PCS-{tag}", name="Pieces")
            box = UnitOfMeasure(workspace_id=ws_id, code=f"BOX-{tag}", name="Boxes")
            ctn = UnitOfMeasure(workspace_id=ws_id, code=f"CTN-{tag}", name="Cartons")
            session.add_all([pcs, box, ctn])
            await session.flush()
            p1 = Product(
                workspace_id=ws_id,
                internal_sku=f"SKU1-{tag}",
                name="P1",
                base_uom_id=pcs.id,
            )
            p2 = Product(
                workspace_id=ws_id,
                internal_sku=f"SKU2-{tag}",
                name="P2",
                base_uom_id=pcs.id,
            )
            session.add_all([p1, p2])
            await session.flush()
            session.add_all(
                [
                    _row(ws_id, p1.id, box.id, "10"),
                    _row(ws_id, p1.id, ctn.id, "50"),
                ]
            )
            await session.commit()
            return {
                "workspace_id": ws_id,
                "pcs": pcs.id,
                "box": box.id,
                "ctn": ctn.id,
                "p1": p1.id,
                "p2": p2.id,
            }

    return asyncio.run(_seed())


# ---------- pure core: identity ----------


def test_identity_without_rows_including_base():
    base, other = uuid.uuid4(), uuid.uuid4()
    assert resolve_factor(
        base_uom_id=base, from_uom_id=base, to_uom_id=base, conversions=[]
    ) == Decimal(1)
    assert resolve_factor(
        base_uom_id=base, from_uom_id=other, to_uom_id=other, conversions=[]
    ) == Decimal(1)


# ---------- pure core: direct legs ----------


def test_base_to_non_base_divides():
    ws, prod, base, box = (uuid.uuid4() for _ in range(4))
    rows = [_row(ws, prod, box, "10")]
    # 1 PCS = 1/10 BOX.
    assert resolve_factor(
        base_uom_id=base, from_uom_id=base, to_uom_id=box, conversions=rows
    ) == Decimal("0.1")


def test_non_base_to_base_multiplies():
    ws, prod, base, box = (uuid.uuid4() for _ in range(4))
    rows = [_row(ws, prod, box, "10")]
    # 1 BOX = 10 PCS.
    assert resolve_factor(
        base_uom_id=base, from_uom_id=box, to_uom_id=base, conversions=rows
    ) == Decimal("10")


# ---------- pure core: two-hop through base ----------


def test_two_hop_non_base_to_non_base():
    ws, prod, base, box, ctn = (uuid.uuid4() for _ in range(5))
    rows = [_row(ws, prod, box, "10"), _row(ws, prod, ctn, "50")]
    # 1 BOX = 10 PCS = 10/50 CTN.
    assert resolve_factor(
        base_uom_id=base, from_uom_id=box, to_uom_id=ctn, conversions=rows
    ) == Decimal("0.2")
    # 1 CTN = 50 PCS = 50/10 BOX.
    assert resolve_factor(
        base_uom_id=base, from_uom_id=ctn, to_uom_id=box, conversions=rows
    ) == Decimal("5")


# ---------- pure core: no path ----------


def test_no_path_when_source_row_missing():
    ws, prod, base, box, ctn = (uuid.uuid4() for _ in range(5))
    rows = [_row(ws, prod, ctn, "50")]
    assert (
        resolve_factor(
            base_uom_id=base, from_uom_id=box, to_uom_id=ctn, conversions=rows
        )
        is None
    )
    assert (
        resolve_factor(
            base_uom_id=base, from_uom_id=box, to_uom_id=base, conversions=rows
        )
        is None
    )


def test_no_path_when_target_row_missing():
    ws, prod, base, box, ctn = (uuid.uuid4() for _ in range(5))
    rows = [_row(ws, prod, box, "10")]
    assert (
        resolve_factor(
            base_uom_id=base, from_uom_id=box, to_uom_id=ctn, conversions=rows
        )
        is None
    )
    assert (
        resolve_factor(
            base_uom_id=base, from_uom_id=base, to_uom_id=ctn, conversions=rows
        )
        is None
    )


# ---------- pure core: invalid rows, precision, determinism ----------


def test_zero_and_negative_rows_are_ignored():
    ws, prod, base, box, ctn = (uuid.uuid4() for _ in range(5))
    rows = [
        _row(ws, prod, box, "0"),
        _row(ws, prod, ctn, "-4"),
    ]
    assert (
        resolve_factor(
            base_uom_id=base, from_uom_id=box, to_uom_id=base, conversions=rows
        )
        is None
    )
    assert (
        resolve_factor(
            base_uom_id=base, from_uom_id=base, to_uom_id=ctn, conversions=rows
        )
        is None
    )
    assert (
        resolve_factor(
            base_uom_id=base, from_uom_id=box, to_uom_id=ctn, conversions=rows
        )
        is None
    )


def test_repeating_decimal_stays_full_precision():
    ws, prod, base, third = (uuid.uuid4() for _ in range(4))
    rows = [_row(ws, prod, third, "3")]
    # base -> non-base divides: 1 base unit = 1/3 THIRD (repeating).
    factor = resolve_factor(
        base_uom_id=base, from_uom_id=base, to_uom_id=third, conversions=rows
    )
    assert factor == Decimal(1) / Decimal(3)
    # Must not be quantized to the 6dp storage scale or to fils.
    assert factor != Decimal("0.333333")
    assert len(str(factor).split(".")[1]) > 6


def test_resolve_is_deterministic():
    ws, prod, base, box, ctn = (uuid.uuid4() for _ in range(5))
    rows = [_row(ws, prod, box, "10"), _row(ws, prod, ctn, "50")]
    kwargs = dict(base_uom_id=base, from_uom_id=box, to_uom_id=ctn)
    seen = {resolve_factor(conversions=rows, **kwargs) for _ in range(5)}
    assert seen == {Decimal("0.2")}


def test_convert_quantity_wrapper_math_and_none():
    ws, prod, base, box, ctn = (uuid.uuid4() for _ in range(5))
    rows = [_row(ws, prod, box, "10"), _row(ws, prod, ctn, "50")]
    assert convert_quantity(
        base_uom_id=base,
        from_uom_id=box,
        to_uom_id=base,
        quantity=Decimal("3"),
        conversions=rows,
    ) == Decimal("30")
    assert convert_quantity(
        base_uom_id=base,
        from_uom_id=box,
        to_uom_id=ctn,
        quantity=Decimal("3"),
        conversions=rows,
    ) == Decimal("0.6")
    missing = uuid.uuid4()
    assert (
        convert_quantity(
            base_uom_id=base,
            from_uom_id=missing,
            to_uom_id=base,
            quantity=Decimal("3"),
            conversions=rows,
        )
        is None
    )


# ---------- DB loader boundary ----------


def test_loader_unknown_and_cross_workspace_product_404():
    world_a = _seed_world("a404")
    world_b = _seed_world("b404")

    async def _run():
        async with TestingSessionLocal() as session:
            with pytest.raises(HTTPException) as exc:
                await resolve_factor_for_product(
                    session,
                    world_a["workspace_id"],
                    uuid.uuid4(),
                    world_a["box"],
                    world_a["pcs"],
                )
            assert exc.value.status_code == 404
            # Product exists, but in another workspace → still 404.
            with pytest.raises(HTTPException) as exc2:
                await resolve_factor_for_product(
                    session,
                    world_b["workspace_id"],
                    world_a["p1"],
                    world_a["box"],
                    world_a["pcs"],
                )
            assert exc2.value.status_code == 404

    asyncio.run(_run())


def test_loader_identity_and_two_hop_end_to_end():
    world = _seed_world("e2e")

    async def _run():
        async with TestingSessionLocal() as session:
            assert await resolve_factor_for_product(
                session,
                world["workspace_id"],
                world["p1"],
                world["box"],
                world["box"],
            ) == Decimal(1)
            assert await resolve_factor_for_product(
                session,
                world["workspace_id"],
                world["p1"],
                world["box"],
                world["ctn"],
            ) == Decimal("0.2")
            assert await convert_quantity_for_product(
                session,
                world["workspace_id"],
                world["p1"],
                world["ctn"],
                world["box"],
                Decimal("2"),
            ) == Decimal("10")

    asyncio.run(_run())


def test_loader_cross_product_rows_are_isolated():
    world = _seed_world("xprod")

    async def _run():
        async with TestingSessionLocal() as session:
            # P2 shares the base UOM but owns no rows: BOX rows of P1
            # must not resolve for P2.
            assert (
                await resolve_factor_for_product(
                    session,
                    world["workspace_id"],
                    world["p2"],
                    world["box"],
                    world["pcs"],
                )
                is None
            )

    asyncio.run(_run())


def test_loader_cross_workspace_rows_are_isolated():
    world_a = _seed_world("xwa")
    world_b = _seed_world("xwb")

    async def _run():
        async with TestingSessionLocal() as session:
            # A's BOX row must not resolve for B's product, even though
            # the from_uom UUID is a real conversion elsewhere.
            assert (
                await resolve_factor_for_product(
                    session,
                    world_b["workspace_id"],
                    world_b["p1"],
                    world_a["box"],
                    world_b["pcs"],
                )
                is None
            )

    asyncio.run(_run())


def test_loader_ignores_beneath_api_invalid_rows():
    world = _seed_world("badrow")

    async def _insert_and_resolve():
        async with TestingSessionLocal() as session:
            rogue = UnitOfMeasure(
                workspace_id=world["workspace_id"],
                code="ROGUE-badrow",
                name="Rogue",
            )
            session.add(rogue)
            await session.flush()
            session.add_all(
                [
                    ProductUOMConversion(
                        workspace_id=world["workspace_id"],
                        product_id=world["p2"],
                        to_uom_id=rogue.id,
                        conversion_factor=Decimal("0"),
                    ),
                ]
            )
            await session.commit()
            return await resolve_factor_for_product(
                session,
                world["workspace_id"],
                world["p2"],
                rogue.id,
                world["pcs"],
            )

    assert asyncio.run(_insert_and_resolve()) is None


def test_loader_uses_bulk_load_without_per_leg_queries():
    world = _seed_world("bulk")

    async def _run():
        async with TestingSessionLocal() as session:
            calls = {"count": 0}
            original_execute = session.execute

            async def _counting_execute(*args, **kwargs):
                calls["count"] += 1
                return await original_execute(*args, **kwargs)

            session.execute = _counting_execute  # type: ignore[method-assign]
            try:
                factor = await resolve_factor_for_product(
                    session,
                    world["workspace_id"],
                    world["p1"],
                    world["box"],
                    world["ctn"],
                )
            finally:
                session.execute = original_execute  # type: ignore[method-assign]
            return factor, calls["count"]

    factor, query_count = asyncio.run(_run())
    assert factor == Decimal("0.2")
    # One scoped product load + one bulk conversion load; resolution
    # itself performs zero queries (no per-leg N+1).
    assert query_count <= 2
