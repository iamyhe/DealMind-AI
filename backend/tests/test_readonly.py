from main import DB_PATH, read_db


def test_connection_enables_query_only_guard():
    with read_db() as connection:
        query_only = connection.execute("PRAGMA query_only").fetchone()[0]

    assert query_only == 1


def test_no_sqlite_sidecar_files_exist():
    sidecars = [
        DB_PATH.with_name(DB_PATH.name + suffix)
        for suffix in ("-journal", "-wal", "-shm")
    ]

    assert not [path for path in sidecars if path.exists()]
