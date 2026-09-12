from __future__ import annotations

import pytest
from django.db import connection


@pytest.fixture(scope="session", autouse=True)
def _terminate_stray_db_connections(django_db_setup, django_db_blocker):
    """Force-close lingering connections before the test database is dropped.

    Django's live server opens a database connection per request thread and
    only closes it when the underlying socket closes. Keep-alive sockets
    don't close right away, and Playwright keeps its `page.request` sockets
    (used by `test_account_journey`'s `page.request.post()` calls) open for
    reuse, so a connection can still be alive after the last test finishes.
    That makes teardown's `DROP DATABASE` fail intermittently with "database
    ... is being accessed by other users". Depending on `django_db_setup`
    here guarantees this runs before its teardown, since fixtures tear down
    in reverse dependency order.
    """
    yield
    with django_db_blocker.unblock():
        if connection.vendor != "postgresql":
            return
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
