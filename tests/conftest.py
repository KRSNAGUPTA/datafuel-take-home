"""Shared pytest fixtures: project imports + an isolated in-memory DB."""
import os
import sys

import pytest

# Make the project root importable when pytest runs from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import connect, init_db   


@pytest.fixture
def conn():
    """Fresh in-memory SQLite with the full schema. Closed after the test."""
    c = connect(":memory:")
    init_db(c)
    yield c
    c.close()