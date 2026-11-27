import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import DB_PATH, app  # noqa: E402

FORBIDDEN_FIELDS = {"user_id", "user_session", "target_purchased_after_cart"}
SQLITE_SIDECARS = ("-journal", "-wal", "-shm")


def _sidecar_paths() -> list[Path]:
    return [DB_PATH.with_name(DB_PATH.name + suffix) for suffix in SQLITE_SIDECARS]


@pytest.fixture(scope="session", autouse=True)
def database_snapshot():
    """Fail the suite if any test changes the database."""
    assert not [path for path in _sidecar_paths() if path.exists()]
    before = (DB_PATH.stat().st_mtime_ns, DB_PATH.stat().st_size)

    yield

    after = (DB_PATH.stat().st_mtime_ns, DB_PATH.stat().st_size)
    assert after == before
    assert not [path for path in _sidecar_paths() if path.exists()]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client
