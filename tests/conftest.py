"""Tests run on SQLite by default. Set TEST_DATABASE_URL to a *local, throwaway* Postgres to run the same
tests against Postgres (what Supabase uses). The schema is dropped before each test, so remote URLs are refused."""
import os
import re

import pytest

from worker.db import DB

TEST_PG = os.getenv("TEST_DATABASE_URL", "")


def _local(url: str) -> bool:
    return bool(re.search(r"@(localhost|127\.0\.0\.1)[:/]|host=/", url))


@pytest.fixture
def make_db(tmp_path):
    def make() -> DB:
        if TEST_PG:
            assert _local(TEST_PG), "TEST_DATABASE_URL must point at a local throwaway Postgres (never Supabase)"
            import psycopg
            with psycopg.connect(TEST_PG, autocommit=True) as c:
                c.execute("drop schema if exists public cascade")
                c.execute("create schema public")
            return DB(url=TEST_PG)
        return DB(url="", sqlite_path=str(tmp_path / "t.db"))
    return make
