"""Shared pytest configuration for the backend test-suite.

conftest.py is imported by pytest before any test module, so it is the right
place to neutralise cross-cutting production behaviour that would otherwise make
the suite flaky.

Auth endpoints (`/auth/register`, `/auth/login`, `/auth/refresh`) are decorated
with ``@limiter.limit(settings.RATE_LIMIT_AUTH)`` (``5/minute`` in dev). The
suite registers and logs in many throwaway users from a single TestClient host,
so with the limiter enabled the Nth call returns 429 and tests fail
non-deterministically depending on ordering. slowapi checks ``limiter.enabled``
at request time, so disabling it here — before the app handles any request —
turns every ``@limiter.limit`` decorator into a no-op for the whole run.
"""

from app.limiter import limiter

limiter.enabled = False
