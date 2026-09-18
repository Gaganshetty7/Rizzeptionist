"""
Shared fixtures for appointment integration tests.

Uses the same DATABASE_URL / engine that the production service module
uses, so every test hits the real database and exercises real locking.
"""

import pytest

from db import DATABASE_URL, create_engine, create_session_factory

# Build a dedicated engine + session factory for test setup/teardown queries.
# book_appointment() already creates its own sessions via _session_factory
# inside the service module — this one is only for arranging and verifying
# test data.
#
# Prefixed with underscore to avoid pytest collecting it as a test
# (PytestCollectionWarning).
_engine = create_engine(DATABASE_URL)
db_session_factory = create_session_factory(_engine)


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engines():
    """Dispose connection pools after the test session ends."""
    yield
    await _engine.dispose()

    # Also dispose the service module's engine so no connections leak.
    from appointments.service import _engine as service_engine
    await service_engine.dispose()
