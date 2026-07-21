"""Shared test configuration — ensures DB connections are cleaned up."""

import asyncio
import pytest


@pytest.fixture(autouse=True)
def reset_db_singleton():
    """Reset the database singleton before each test to prevent connection leaks."""
    import database
    database._db = None
    yield
    # Force close any remaining connection
    if database._db is not None:
        try:
            asyncio.get_event_loop().run_until_complete(database._db.close())
        except Exception:
            pass
        database._db = None
