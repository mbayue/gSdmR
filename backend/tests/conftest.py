"""Shared test configuration — ensures clean process exit after tests."""

import os
import pytest


@pytest.fixture(autouse=True)
def reset_db_singleton():
    """Reset the database singleton before each test."""
    import database
    database._db = None
    yield
    database._db = None


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Force-kill the process after all tests to avoid aiosqlite thread hang."""
    os._exit(0)
