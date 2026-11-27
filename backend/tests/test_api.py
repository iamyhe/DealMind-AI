import hashlib
import json
import logging
import math
import re

import pytest
from fastapi.testclient import TestClient

import main as backend_main
from conftest import FORBIDDEN_FIELDS
from main import REQUIRED_REPORT_SECTIONS, REPORT_PATH, read_db, session_refs

LEGACY_SUMMARY_FIELDS = {
    "period",
    "total_valid_sessions",
    "sessions_with_view",
    "sessions_with_cart",
    "sessions_with_purchase",
    "overall_purchase_rate_pct",
    "view_to_purchase_rate_pct",
    "session_cart_abandonment_rate_pct",
}
AOV_SUMMARY_FIELDS = {"historical_aov_pos", "historical_aov_signed"}
SUMMARY_FIELDS = LEGACY_SUMMARY_FIELDS | AOV_SUMMARY_FIELDS

LIST_ITEM_FIELDS = {
    "id",
    "session_start",
    "first_cart_time",
    "cart_product_ids_at_first_cart_sec",
    "cart_category_ids_at_first_cart_sec",
    "seconds_to_first_cart",
    "views_before_cart",
    "has_view_before_cart",
    "unique_products_viewed_before_cart",
    "unique_categories_viewed_before_cart",
    "unique_brands_viewed_before_cart",
    "removes_before_cart",
    "unique_products_removed_before_cart",
    "cart_events_at_first_cart_sec",
    "unique_products_carted_at_first_cart_sec",
    "has_multi_products_at_first_cart_sec",
    "avg_cart_price_at_first_cart_sec",
    "avg_viewed_price_before_cart",
    "max_viewed_price_before_cart",
    "price_ratio_cart_to_view",
    "any_cart_brand_at_first_cart_sec",
    "hour_of_day_utc",
    "day_of_week_utc",
    "user_prior_sessions",
    "user_prior_purchase_sessions",
}

EVENT_FIELDS = {
    "id",
    "event_time",
    "event_type",
    "product_id",
    "category_id",
    "category_code",
    "brand",
    "price",
    "event_phase",
}

VALID_PERIODS = ["ALL", "2019-10", "2019-11", "2019-12", "2020-01", "2020-02"]
SESSION_REF_PATTERN = re.compile(r"^rs_\d{3}$")
SAFE_DETAIL_EVENT_PHASES = {
    "before_first_cart",
    "at_first_cart_second",
    "same_second_other",
}
ALLOWED_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
]
DISALLOWED_CORS_ORIGINS = [
    "http://localhost:5174",
    "http://127.0.0.1:4173",
    "https://example.com",
]
LOCAL_PATH_TEST_PATTERNS = (
    re.compile(r"\\"),
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"),
    re.compile(r"file://", re.IGNORECASE),
    re.compile(r"/(?:home|Users|mnt|var|tmp|etc|opt|usr|srv)/"),
)

EXPECTED_REPORT_STRUCTURE = {
    "meta": {
        "source_file",
        "split",
        "n_sessions",
        "n_users",
        "period_start",
        "period_end",
        "target_column",
        "overall_purchase_rate",
        "n_buyers",
        "n_non_buyers",
        "notes",
    },
    "pre_cart_behavior": {
        "numeric_comparison",
        "flag_comparison",
        "purchase_rate_by_has_view",
        "purchase_rate_by_seconds_to_first_cart",
        "purchase_rate_by_views_before_cart",
        "purchase_rate_by_removes_before_cart",
        "purchase_rate_by_prior_purchase_sessions",
        "purchase_rate_by_multi_product_cart",
        "purchase_rate_by_hour_utc",
        "purchase_rate_by_weekday_utc",
    },
    "catalog_and_brands": {
        "n_categories",
        "n_products",
        "top10_categories_share_of_sessions",
        "top50_products_share_of_sessions",
        "min_sessions_for_rate_ranking",
        "top_categories_by_volume",
        "highest_purchase_rate_categories",
        "lowest_purchase_rate_categories",
        "top_products_by_volume",
        "brand_presence",
    },
    "price_band_cart_behavior": {
        "price_column",
        "band_method",
        "thresholds",
        "bands",
        "cart_vs_viewed_price",
    },
}

EXPECTED_REPORT_ARRAY_LENGTHS = {
    ("pre_cart_behavior", "numeric_comparison"): 13,
    ("pre_cart_behavior", "flag_comparison"): 3,
    ("pre_cart_behavior", "purchase_rate_by_has_view"): 2,
    ("pre_cart_behavior", "purchase_rate_by_seconds_to_first_cart"): 8,
    ("pre_cart_behavior", "purchase_rate_by_views_before_cart"): 6,
    ("pre_cart_behavior", "purchase_rate_by_removes_before_cart"): 4,
    ("pre_cart_behavior", "purchase_rate_by_prior_purchase_sessions"): 4,
    ("pre_cart_behavior", "purchase_rate_by_multi_product_cart"): 2,
    ("pre_cart_behavior", "purchase_rate_by_hour_utc"): 24,
    ("pre_cart_behavior", "purchase_rate_by_weekday_utc"): 7,
    ("catalog_and_brands", "top_categories_by_volume"): 15,
    ("catalog_and_brands", "highest_purchase_rate_categories"): 10,
    ("catalog_and_brands", "lowest_purchase_rate_categories"): 10,
    ("catalog_and_brands", "top_products_by_volume"): 15,
    ("price_band_cart_behavior", "bands"): 3,
    ("price_band_cart_behavior", "cart_vs_viewed_price"): 3,
}

REPORT_BUCKET_FIELDS = {"bucket", "sessions", "purchase_rate"}
REPORT_HOUR_FIELDS = {"hour", "sessions", "purchase_rate"}
REPORT_WEEKDAY_FIELDS = {"weekday", "sessions", "purchase_rate"}
REPORT_CATEGORY_VOLUME_FIELDS = {"category_id", "sessions", "share", "purchase_rate"}
REPORT_RANKED_CATEGORY_FIELDS = {"category_id", "sessions", "purchase_rate"}
REPORT_PRODUCT_VOLUME_FIELDS = {"product_id", "sessions", "share", "purchase_rate"}
REPORT_BAND_FIELDS = {
    "band",
    "sessions",
    "purchase_rate",
    "price_min",
    "price_median",
    "price_max",
    "median_seconds_to_first_cart",
    "mean_views_before_cart",
    "mean_removes_before_cart",
    "share_has_view",
    "share_multi_product_cart",
    "share_branded",
    "median_prior_sessions",
    "mean_prior_purchase_sessions",
}
REPORT_MOVE_FIELDS = {"move", "sessions", "share", "purchase_rate"}
EXPECTED_REPORT_ROW_FIELDS = {
    ("pre_cart_behavior", "numeric_comparison"): {
        "feature",
        "buyer_mean",
        "non_buyer_mean",
        "buyer_median",
        "non_buyer_median",
    },
    ("pre_cart_behavior", "flag_comparison"): {
        "feature",
        "buyer_share",
        "non_buyer_share",
    },
    ("pre_cart_behavior", "purchase_rate_by_has_view"): REPORT_BUCKET_FIELDS,
    ("pre_cart_behavior", "purchase_rate_by_seconds_to_first_cart"): REPORT_BUCKET_FIELDS,
    ("pre_cart_behavior", "purchase_rate_by_views_before_cart"): REPORT_BUCKET_FIELDS,
    ("pre_cart_behavior", "purchase_rate_by_removes_before_cart"): REPORT_BUCKET_FIELDS,
    ("pre_cart_behavior", "purchase_rate_by_prior_purchase_sessions"): REPORT_BUCKET_FIELDS,
    ("pre_cart_behavior", "purchase_rate_by_multi_product_cart"): REPORT_BUCKET_FIELDS,
    ("pre_cart_behavior", "purchase_rate_by_hour_utc"): REPORT_HOUR_FIELDS,
    ("pre_cart_behavior", "purchase_rate_by_weekday_utc"): REPORT_WEEKDAY_FIELDS,
    ("catalog_and_brands", "top_categories_by_volume"): REPORT_CATEGORY_VOLUME_FIELDS,
    ("catalog_and_brands", "highest_purchase_rate_categories"): REPORT_RANKED_CATEGORY_FIELDS,
    ("catalog_and_brands", "lowest_purchase_rate_categories"): REPORT_RANKED_CATEGORY_FIELDS,
    ("catalog_and_brands", "top_products_by_volume"): REPORT_PRODUCT_VOLUME_FIELDS,
    ("price_band_cart_behavior", "bands"): REPORT_BAND_FIELDS,
    ("price_band_cart_behavior", "cart_vs_viewed_price"): REPORT_MOVE_FIELDS,
}


def _assert_no_forbidden_fields(payload: dict) -> None:
    assert not (set(payload) & FORBIDDEN_FIELDS)


def _assert_public_event(event: dict) -> None:
    assert set(event) == EVENT_FIELDS
    _assert_no_forbidden_fields(event)


def _assert_event_order(events: list[dict]) -> None:
    assert events == sorted(events, key=lambda event: (event["event_time"], event["id"]))


def _is_detail_event(event) -> bool:
    return event["event_phase"] in SAFE_DETAIL_EVENT_PHASES and event["event_type"] != "purchase"


def _is_outcome_event(event) -> bool:
    return not _is_detail_event(event)


def _all_session_refs(client) -> list[str]:
    response = client.get("/api/replay-sessions", params={"page": 1, "size": 100})
    assert response.status_code == 200
    return [item["id"] for item in response.json()["items"]]


def _db_summary_row(period: str) -> dict:
    with read_db() as connection:
        row = connection.execute(
            "SELECT * FROM funnel_summary WHERE period = ?", (period,)
        ).fetchone()
    assert row is not None
    return dict(row)


def _source_report() -> dict:
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _nested(payload, *path):
    value = payload
    for part in path:
        value = value[part]
    return value


def _assert_no_local_paths(payload) -> None:
    if isinstance(payload, str):
        for pattern in LOCAL_PATH_TEST_PATTERNS:
            assert not pattern.search(payload), payload
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            _assert_no_local_paths(key)
            _assert_no_local_paths(value)
        return
    if isinstance(payload, list):
        for value in payload:
            _assert_no_local_paths(value)


def _set_nested(payload, value, *path) -> None:
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


def _assert_generic_report_failure(response, caplog, temp_path) -> None:
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert str(temp_path) not in response.text
    assert "Traceback" not in response.text
    assert any(
        record.name == backend_main.logger.name and record.levelno >= logging.ERROR
        for record in caplog.records
    )
    assert str(temp_path) not in caplog.text
    assert "Traceback" not in caplog.text


def _report_snapshot() -> tuple[int, int, str]:
    stat = REPORT_PATH.stat()
    return (
        stat.st_size,
        stat.st_mtime_ns,
        hashlib.sha256(REPORT_PATH.read_bytes()).hexdigest(),
    )


@pytest.fixture
def report_snapshot() -> tuple[int, int, str]:
    return _report_snapshot()


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_summary_default_period(client):
    response = client.get("/api/summary")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SUMMARY_FIELDS
    assert body["period"] == "ALL"
    assert isinstance(body["total_valid_sessions"], int)
    assert body["total_valid_sessions"] > 0
    for field in SUMMARY_FIELDS - {"period"}:
        assert isinstance(body[field], (int, float))


@pytest.mark.parametrize("period", VALID_PERIODS)
def test_summary_valid_periods(client, period):
    response = client.get("/api/summary", params={"period": period})

    assert response.status_code == 200
    assert response.json()["period"] == period


def test_summary_invalid_period_returns_422(client):
    response = client.get("/api/summary", params={"period": "1999-01"})

    assert response.status_code == 422


def test_summary_all_includes_aov_fields(client):
    response = client.get("/api/summary")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SUMMARY_FIELDS
    assert AOV_SUMMARY_FIELDS <= set(body)
    db_row = _db_summary_row("ALL")
    for field in AOV_SUMMARY_FIELDS:
        assert body[field] == db_row[field]
        assert isinstance(body[field], (int, float))


@pytest.mark.parametrize("period", VALID_PERIODS)
def test_summary_aov_matches_database_for_every_period(client, period):
    response = client.get("/api/summary", params={"period": period})

    assert response.status_code == 200
    body = response.json()
    db_row = _db_summary_row(period)
    assert body["period"] == period
    for field in AOV_SUMMARY_FIELDS:
        assert body[field] == db_row[field]
        assert isinstance(body[field], (int, float))


def test_summary_aov_differs_by_period_using_database_values(client):
    api_values = {}
    db_values = {}
    for period in VALID_PERIODS:
        response = client.get("/api/summary", params={"period": period})
        assert response.status_code == 200
        body = response.json()
        db_row = _db_summary_row(period)
        api_values[period] = tuple(body[field] for field in sorted(AOV_SUMMARY_FIELDS))
        db_values[period] = tuple(db_row[field] for field in sorted(AOV_SUMMARY_FIELDS))

    assert api_values == db_values
    assert len(set(db_values.values())) > 1


def test_summary_legacy_fields_unchanged(client):
    for period in VALID_PERIODS:
        response = client.get("/api/summary", params={"period": period})
        assert response.status_code == 200
        body = response.json()
        db_row = _db_summary_row(period)
        assert set(body) == LEGACY_SUMMARY_FIELDS | AOV_SUMMARY_FIELDS
        for field in LEGACY_SUMMARY_FIELDS:
            assert body[field] == db_row[field]


def test_summary_aov_does_not_affect_other_endpoints(client):
    replay = client.get("/api/replay-sessions", params={"page": 1, "size": 20})
    assert replay.status_code == 200
    assert replay.json()["total"] == 100
    assert replay.json()["items"][0]["id"] == "rs_001"

    detail = client.get("/api/replay-sessions/rs_001")
    outcome = client.get("/api/replay-sessions/rs_001/outcome")
    assert detail.status_code == 200
    assert outcome.status_code == 200
    for event in detail.json()["events"]:
        _assert_public_event(event)
        assert _is_detail_event(event)
    assert set(outcome.json()) == {"actual_outcome", "events"}

    cors = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert cors.status_code == 200
    assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"

    predict = client.post("/api/predict", json={})
    assert predict.status_code == 422


def test_summary_keeps_readonly_database_guard(client):
    with read_db() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1

    response = client.get("/api/summary")
    assert response.status_code == 200


def test_cart_behavior_report_success(client, report_snapshot):
    response = client.get("/api/reports/cart-behavior")

    assert response.status_code == 200
    body = response.json()
    assert body == _source_report()
    assert set(REQUIRED_REPORT_SECTIONS) <= set(body)
    _assert_no_local_paths(body)
    assert str(REPORT_PATH) not in response.text
    assert "cart_behavior_summary.json" not in response.text
    assert _report_snapshot() == report_snapshot


def test_cart_behavior_report_expected_structure(client, report_snapshot):
    body = client.get("/api/reports/cart-behavior").json()

    for section, expected_keys in EXPECTED_REPORT_STRUCTURE.items():
        assert set(body[section]) == expected_keys

    for (section, key), expected_length in EXPECTED_REPORT_ARRAY_LENGTHS.items():
        assert isinstance(body[section][key], list)
        assert len(body[section][key]) == expected_length

    for (section, key), expected_fields in EXPECTED_REPORT_ROW_FIELDS.items():
        for row in body[section][key]:
            assert set(row) == expected_fields

    brand = body["catalog_and_brands"]["brand_presence"]
    assert set(brand) == {"cart_item_has_brand", "distinct_brands_viewed_before_cart"}
    assert len(brand["cart_item_has_brand"]) == 2
    assert len(brand["distinct_brands_viewed_before_cart"]) == 4
    for row in brand["cart_item_has_brand"]:
        assert set(row) == REPORT_BUCKET_FIELDS
    for row in brand["distinct_brands_viewed_before_cart"]:
        assert set(row) == REPORT_BUCKET_FIELDS

    thresholds = body["price_band_cart_behavior"]["thresholds"]
    assert set(thresholds) == {"low_max", "mid_max"}
    assert all(isinstance(value, (int, float)) for value in thresholds.values())
    assert len(body["meta"]["notes"]) == 4
    assert all(isinstance(note, str) for note in body["meta"]["notes"])
    assert _report_snapshot() == report_snapshot


def test_cart_behavior_report_values_match_source_report(client, report_snapshot):
    source = _source_report()
    body = client.get("/api/reports/cart-behavior").json()

    assert body == source
    representative_paths = (
        ("meta", "source_file"),
        ("meta", "split"),
        ("meta", "n_sessions"),
        ("meta", "overall_purchase_rate"),
        ("meta", "notes", 3),
        ("pre_cart_behavior", "numeric_comparison", 0, "buyer_mean"),
        ("pre_cart_behavior", "purchase_rate_by_has_view", 1, "purchase_rate"),
        ("catalog_and_brands", "n_categories"),
        ("catalog_and_brands", "top10_categories_share_of_sessions"),
        ("catalog_and_brands", "top_products_by_volume", 0, "product_id"),
        ("price_band_cart_behavior", "thresholds", "low_max"),
        ("price_band_cart_behavior", "bands", 2, "purchase_rate"),
    )
    for path in representative_paths:
        assert _nested(body, *path) == _nested(source, *path)
    assert _report_snapshot() == report_snapshot


def test_cart_behavior_report_is_loaded_from_file_on_each_request(
    client, tmp_path, monkeypatch
):
    source = _source_report()
    temp_report = tmp_path / "cart_behavior_summary.json"
    source["meta"]["n_sessions"] = 123456789
    temp_report.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(backend_main, "REPORT_PATH", temp_report)

    response = client.get("/api/reports/cart-behavior")

    assert response.status_code == 200
    assert response.json()["meta"]["n_sessions"] == 123456789
    assert response.json() != _source_report()


def test_cart_behavior_report_passes_through_validated_additive_sections(
    client, tmp_path, monkeypatch
):
    source = _source_report()
    source["future_section"] = {
        "description": "Buyer/non-buyer comparison for train split",
        "items": [{"bucket": "A/B test", "value": 1}],
    }
    temp_report = tmp_path / "cart_behavior_summary.json"
    temp_report.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(backend_main, "REPORT_PATH", temp_report)

    response = client.get("/api/reports/cart-behavior")
    body = response.json()

    assert response.status_code == 200
    assert set(REQUIRED_REPORT_SECTIONS) <= set(body)
    assert body["future_section"] == source["future_section"]
    assert body == source
    _assert_no_local_paths(body)


def test_cart_behavior_report_works_from_another_working_directory(
    client, tmp_path, monkeypatch, report_snapshot
):
    source = _source_report()
    monkeypatch.chdir(tmp_path)

    response = client.get("/api/reports/cart-behavior")

    assert response.status_code == 200
    assert response.json() == source
    assert _report_snapshot() == report_snapshot


def test_cart_behavior_report_missing_file_returns_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(backend_main, "REPORT_PATH", tmp_path / "missing.json")

    response = client.get("/api/reports/cart-behavior")

    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


def test_cart_behavior_report_malformed_json_returns_500(
    client, tmp_path, monkeypatch, caplog
):
    invalid_report = tmp_path / "cart_behavior_summary.json"
    invalid_report.write_text('{"meta":', encoding="utf-8")
    monkeypatch.setattr(backend_main, "REPORT_PATH", invalid_report)

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/reports/cart-behavior")

    _assert_generic_report_failure(response, caplog, invalid_report)


@pytest.mark.parametrize(
    "kind",
    ["top_level_list", "missing_sections", "section_not_object"],
)
def test_cart_behavior_report_unexpected_structure_returns_500(
    client, tmp_path, monkeypatch, caplog, kind
):
    source = _source_report()
    if kind == "top_level_list":
        unexpected = []
    elif kind == "missing_sections":
        unexpected = {"meta": {}}
    else:
        unexpected = dict(source)
        unexpected["pre_cart_behavior"] = []

    unexpected_report = tmp_path / "cart_behavior_summary.json"
    unexpected_report.write_text(json.dumps(unexpected), encoding="utf-8")
    monkeypatch.setattr(backend_main, "REPORT_PATH", unexpected_report)

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/reports/cart-behavior")

    _assert_generic_report_failure(response, caplog, unexpected_report)


@pytest.mark.parametrize(
    "path, value, needle",
    [
        (
            ("meta", "source_file"),
            "Generated from /home/yn/report.json",
            "/home/yn/report.json",
        ),
        (
            ("meta", "split"),
            "See file://C:/data/x.parquet",
            "file://C:/data/x.parquet",
        ),
        (
            ("meta", "target_column"),
            r"Generated from C:\data\x.parquet",
            r"C:\data\x.parquet",
        ),
        (
            ("meta", "notes", 0),
            r"See \\server\share\x.json",
            r"\\server\share\x.json",
        ),
        (("meta", "/tmp/report.json"), "secret", "/tmp/report.json"),
        (
            ("price_band_cart_behavior", "thresholds", "C:/data/leak.json"),
            1,
            "C:/data/leak.json",
        ),
    ],
    ids=[
        "embedded-unix",
        "embedded-file-url",
        "embedded-windows-drive",
        "embedded-unc",
        "path-like-key",
        "nested-path-like-key",
    ],
)
def test_cart_behavior_report_rejects_embedded_local_paths(
    client, tmp_path, monkeypatch, caplog, path, value, needle
):
    source = _source_report()
    _set_nested(source, value, *path)
    unsafe_report = tmp_path / "cart_behavior_summary.json"
    unsafe_report.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(backend_main, "REPORT_PATH", unsafe_report)

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/reports/cart-behavior")

    _assert_generic_report_failure(response, caplog, unsafe_report)
    assert needle not in response.text


def test_cart_behavior_report_directory_path_returns_500(
    client, tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(backend_main, "REPORT_PATH", tmp_path)

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/reports/cart-behavior")

    _assert_generic_report_failure(response, caplog, tmp_path)


def test_cart_behavior_report_requests_keep_files_read_only(client, report_snapshot):
    before = report_snapshot
    with read_db() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1

    for _ in range(2):
        response = client.get("/api/reports/cart-behavior")
        assert response.status_code == 200

    assert _report_snapshot() == before
    sidecars = [
        backend_main.DB_PATH.with_name(backend_main.DB_PATH.name + suffix)
        for suffix in ("-journal", "-wal", "-shm")
    ]
    assert not [path for path in sidecars if path.exists()]


def test_cart_behavior_report_does_not_change_existing_endpoints(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    summary = client.get("/api/summary")
    assert summary.status_code == 200
    assert set(summary.json()) == SUMMARY_FIELDS

    replay = client.get("/api/replay-sessions", params={"page": 1, "size": 20})
    assert replay.status_code == 200
    assert replay.json()["total"] == 100

    predict = client.post("/api/predict", json={})
    assert predict.status_code == 422


def test_cart_behavior_report_cors(client, report_snapshot):
    for origin in ALLOWED_CORS_ORIGINS:
        response = client.get(
            "/api/reports/cart-behavior", headers={"Origin": origin}
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin

    for origin in DISALLOWED_CORS_ORIGINS:
        response = client.get(
            "/api/reports/cart-behavior", headers={"Origin": origin}
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    assert _report_snapshot() == report_snapshot


def test_replay_sessions_default_pagination(client):
    response = client.get("/api/replay-sessions")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "page", "size", "total"}
    assert body["page"] == 1
    assert body["size"] == 20
    assert body["total"] == 100
    assert len(body["items"]) == 20

    for index, item in enumerate(body["items"], start=1):
        assert set(item) == LIST_ITEM_FIELDS
        assert item["id"] == f"rs_{index:03d}"
        assert SESSION_REF_PATTERN.match(item["id"])
        _assert_no_forbidden_fields(item)


def test_replay_sessions_custom_pagination(client):
    response = client.get("/api/replay-sessions", params={"page": 2, "size": 7})

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["size"] == 7
    assert body["total"] == 100
    assert len(body["items"]) == 7
    assert body["items"][0]["id"] == "rs_008"


def test_replay_sessions_out_of_range_page(client):
    response = client.get("/api/replay-sessions", params={"page": 999, "size": 20})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["page"] == 999
    assert body["size"] == 20
    assert body["total"] == 100


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"size": 0},
        {"size": 101},
        {"page": "abc"},
        {"size": "abc"},
    ],
)
def test_invalid_pagination_returns_422(client, params):
    response = client.get("/api/replay-sessions", params=params)

    assert response.status_code == 422


def test_replay_session_detail(client):
    response = client.get("/api/replay-sessions/rs_001")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"session", "events"}
    assert body["session"]["id"] == "rs_001"
    assert set(body["session"]) == LIST_ITEM_FIELDS
    _assert_no_forbidden_fields(body["session"])
    assert isinstance(body["events"], list)
    assert len(body["events"]) > 0

    for event in body["events"]:
        _assert_public_event(event)
        assert event["event_phase"] in SAFE_DETAIL_EVENT_PHASES
        assert event["event_type"] != "purchase"

    _assert_event_order(body["events"])


@pytest.mark.parametrize(
    "path",
    [
        "/api/replay-sessions/does-not-exist",
        "/api/replay-sessions/does-not-exist/outcome",
    ],
)
def test_unknown_session_returns_404(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


def test_actual_target_only_exposed_by_outcome(client):
    list_response = client.get("/api/replay-sessions")
    assert list_response.status_code == 200
    session_ref = list_response.json()["items"][0]["id"]
    _assert_no_forbidden_fields(list_response.json()["items"][0])

    detail_response = client.get(f"/api/replay-sessions/{session_ref}")
    assert detail_response.status_code == 200
    _assert_no_forbidden_fields(detail_response.json()["session"])
    for event in detail_response.json()["events"]:
        _assert_public_event(event)
        assert _is_detail_event(event)

    outcome_response = client.get(f"/api/replay-sessions/{session_ref}/outcome")
    assert outcome_response.status_code == 200
    outcome = outcome_response.json()
    assert set(outcome) == {"actual_outcome", "events"}
    assert outcome["actual_outcome"] in (0, 1)
    for event in outcome["events"]:
        _assert_public_event(event)
        assert _is_outcome_event(event)


@pytest.mark.parametrize("payload", [None, {}, {"foo": "bar"}])
def test_predict_rejects_missing_or_unknown_body(client, payload):
    if payload is None:
        response = client.post("/api/predict")
    else:
        response = client.post("/api/predict", json=payload)

    assert response.status_code == 422


def test_detail_events_respect_safe_allowlist_for_all_sessions(client):
    refs = _all_session_refs(client)
    assert len(refs) == 100

    for ref in refs:
        response = client.get(f"/api/replay-sessions/{ref}")
        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) > 0

        for event in events:
            _assert_public_event(event)
            assert _is_detail_event(event)
            assert event["event_phase"] != "after_first_cart_outcome"
            assert event["event_type"] != "purchase"

        _assert_event_order(events)


def test_outcome_events_respect_complement_for_all_sessions(client):
    refs = _all_session_refs(client)
    assert len(refs) == 100

    for ref in refs:
        response = client.get(f"/api/replay-sessions/{ref}/outcome")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"actual_outcome", "events"}
        assert body["actual_outcome"] in (0, 1)

        for event in body["events"]:
            _assert_public_event(event)
            assert _is_outcome_event(event)

        _assert_event_order(body["events"])


@pytest.mark.parametrize("ref", ["rs_001", "rs_002"])
def test_detail_and_outcome_partition_all_events(client, ref):
    detail_response = client.get(f"/api/replay-sessions/{ref}")
    outcome_response = client.get(f"/api/replay-sessions/{ref}/outcome")
    assert detail_response.status_code == 200
    assert outcome_response.status_code == 200

    detail_events = detail_response.json()["events"]
    outcome_events = outcome_response.json()["events"]
    detail_ids = [event["id"] for event in detail_events]
    outcome_ids = [event["id"] for event in outcome_events]

    assert len(detail_ids) == len(set(detail_ids))
    assert len(outcome_ids) == len(set(outcome_ids))
    assert not (set(detail_ids) & set(outcome_ids))

    ref_to_session = session_refs()
    with read_db() as connection:
        rows = connection.execute(
            "SELECT id, event_phase, event_type FROM replay_session_events "
            "WHERE user_session = ? ORDER BY id",
            (ref_to_session[ref],),
        ).fetchall()

    database_ids = [row["id"] for row in rows]
    assert len(database_ids) == len(set(database_ids))
    assert set(detail_ids) | set(outcome_ids) == set(database_ids)
    assert len(detail_ids) + len(outcome_ids) == len(database_ids)

    for row in rows:
        expected_ids = detail_ids if _is_detail_event(row) else outcome_ids
        assert row["id"] in expected_ids


@pytest.mark.parametrize(
    "ref, expected_outcome, expected_withheld, expected_purchases",
    [
        ("rs_001", 0, 4, 0),
        ("rs_002", 1, 45, 7),
    ],
)
def test_known_reveal_regressions(
    client, ref, expected_outcome, expected_withheld, expected_purchases
):
    detail_response = client.get(f"/api/replay-sessions/{ref}")
    assert detail_response.status_code == 200
    for event in detail_response.json()["events"]:
        _assert_public_event(event)
        assert _is_detail_event(event)
        assert event["event_phase"] != "after_first_cart_outcome"
        assert event["event_type"] != "purchase"

    outcome_response = client.get(f"/api/replay-sessions/{ref}/outcome")
    assert outcome_response.status_code == 200
    outcome = outcome_response.json()
    assert set(outcome) == {"actual_outcome", "events"}
    assert outcome["actual_outcome"] == expected_outcome
    assert len(outcome["events"]) == expected_withheld
    assert (
        sum(event["event_type"] == "purchase" for event in outcome["events"])
        == expected_purchases
    )
    for event in outcome["events"]:
        _assert_public_event(event)
        assert _is_outcome_event(event)


def test_same_second_other_policy_when_present(client):
    with read_db() as connection:
        rows = connection.execute(
            "SELECT user_session, id, event_type FROM replay_session_events "
            "WHERE event_phase = 'same_second_other'"
        ).fetchall()

    if not rows:
        return

    ref_by_session = {key: ref for ref, key in session_refs().items()}
    for user_session in {row["user_session"] for row in rows}:
        ref = ref_by_session[user_session]
        detail_response = client.get(f"/api/replay-sessions/{ref}")
        outcome_response = client.get(f"/api/replay-sessions/{ref}/outcome")
        assert detail_response.status_code == 200
        assert outcome_response.status_code == 200

        detail_ids = {event["id"] for event in detail_response.json()["events"]}
        outcome_ids = {event["id"] for event in outcome_response.json()["events"]}

        for row in rows:
            if row["user_session"] != user_session:
                continue
            if row["event_type"] == "purchase":
                assert row["id"] in outcome_ids
                assert row["id"] not in detail_ids
            else:
                assert row["id"] in detail_ids
                assert row["id"] not in outcome_ids


@pytest.mark.parametrize("origin", ALLOWED_CORS_ORIGINS)
def test_cors_get_from_allowed_origin(client, origin):
    response = client.get("/api/health", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", ALLOWED_CORS_ORIGINS)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_cors_preflight_from_allowed_origin(client, origin, method):
    response = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed_methods = {
        item.strip().upper()
        for item in response.headers.get("access-control-allow-methods", "").split(",")
        if item.strip()
    }
    assert method in allowed_methods
    assert "content-type" in response.headers.get("access-control-allow-headers", "").lower()


@pytest.mark.parametrize("origin", DISALLOWED_CORS_ORIGINS)
def test_cors_disallowed_origin_gets_no_allow_origin(client, origin):
    get_response = client.get("/api/health", headers={"Origin": origin})
    assert get_response.status_code == 200
    assert "access-control-allow-origin" not in get_response.headers

    preflight = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert "access-control-allow-origin" not in preflight.headers


@pytest.mark.parametrize("origin", ALLOWED_CORS_ORIGINS)
def test_cors_never_wildcard_or_credentials(client, origin):
    get_response = client.get("/api/health", headers={"Origin": origin})
    assert get_response.headers.get("access-control-allow-origin") != "*"
    assert get_response.headers.get("access-control-allow-credentials") != "true"

    preflight = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") != "*"
    assert preflight.headers.get("access-control-allow-credentials") != "true"


def test_cors_does_not_change_endpoint_behavior(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    summary = client.get("/api/summary")
    assert summary.status_code == 200
    assert summary.json()["period"] == "ALL"

    predict = client.post("/api/predict", json={"foo": "bar"})
    assert predict.status_code == 422


# --- Prediction integration (temporary fakes only; no model artifact) ------

VALID_FEATURES = {
    "seconds_to_first_cart": 42,
    "views_before_cart": 3,
    "has_view_before_cart": 1,
    "unique_products_viewed_before_cart": 2,
    "unique_categories_viewed_before_cart": 1,
    "unique_brands_viewed_before_cart": 1,
    "removes_before_cart": 0,
    "unique_products_removed_before_cart": 0,
    "cart_events_at_first_cart_sec": 1,
    "unique_products_carted_at_first_cart_sec": 2,
    "has_multi_products_at_first_cart_sec": 0,
    "avg_cart_price_at_first_cart_sec": 40.5,
    "avg_viewed_price_before_cart": 35.25,
    "max_viewed_price_before_cart": 60.0,
    "price_ratio_cart_to_view": 1.15,
    "any_cart_brand_at_first_cart_sec": 1,
    "hour_of_day_utc": 14,
    "day_of_week_utc": 3,
    "user_prior_sessions": 5,
    "user_prior_purchase_sessions": 2,
}

NULLABLE_FEATURES = {
    "avg_viewed_price_before_cart",
    "max_viewed_price_before_cart",
    "price_ratio_cart_to_view",
    "avg_cart_price_at_first_cart_sec",
}
BINARY_FEATURES = {
    "has_view_before_cart",
    "has_multi_products_at_first_cart_sec",
    "any_cart_brand_at_first_cart_sec",
}


class FakeDataFrame:
    """Minimal DataFrame stand-in; pandas is not installed in this environment."""

    def __init__(self, data, columns):
        self.data = data
        self.columns = list(columns)


class FakePandas:
    def __init__(self):
        self.frames = []

    def DataFrame(self, data, columns):
        frame = FakeDataFrame(data, columns)
        self.frames.append(frame)
        return frame


class FakeEstimator:
    """In-memory stand-in for the trained sklearn pipeline."""

    def __init__(
        self, probabilities=None, classes=None, error=None, feature_names=None
    ):
        self.probabilities = probabilities if probabilities is not None else [[0.17, 0.83]]
        self.classes = classes if classes is not None else [0, 1]
        self.error = error
        self.calls = []
        self._feature_names = (
            list(backend_main.FEATURE_COLUMNS)
            if feature_names is None
            else list(feature_names)
        )

    @property
    def classes_(self):
        return self.classes

    @property
    def feature_names_in_(self):
        return self._feature_names

    def predict_proba(self, values):
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return self.probabilities


class FakeEstimatorWithoutFeatureNames(FakeEstimator):
    @property
    def feature_names_in_(self):
        raise AttributeError("feature_names_in_")


class FakeJoblib:
    def __init__(self, model, error=None):
        self.model = model
        self.error = error
        self.load_calls = 0

    def load(self, path):
        self.load_calls += 1
        if self.error is not None:
            raise self.error
        return self.model


class _ArtifactPath:
    def __init__(self, exists=True):
        self._exists = exists

    def is_file(self):
        return self._exists


@pytest.fixture(autouse=True)
def _clear_model_cache_and_reset_threshold(monkeypatch):
    monkeypatch.delenv(backend_main.PREDICTION_THRESHOLD_ENV, raising=False)
    monkeypatch.setattr(
        backend_main, "PREDICTION_THRESHOLD", backend_main.DEFAULT_PREDICTION_THRESHOLD
    )
    backend_main.load_model.cache_clear()
    yield
    backend_main.load_model.cache_clear()


def _patch_artifact(
    monkeypatch,
    model=None,
    *,
    exists=True,
    load_error=None,
    import_error=None,
    pandas_error=None,
):
    fake_joblib = FakeJoblib(model, error=load_error)
    fake_pandas = FakePandas()
    monkeypatch.setattr(backend_main, "MODEL_PATH", _ArtifactPath(exists))
    if import_error is not None:
        def _broken_import():
            raise import_error

        monkeypatch.setattr(backend_main, "_import_joblib", _broken_import)
    else:
        monkeypatch.setattr(backend_main, "_import_joblib", lambda: fake_joblib)
    if pandas_error is not None:
        def _broken_pandas_import():
            raise pandas_error

        monkeypatch.setattr(backend_main, "_import_pandas", _broken_pandas_import)
    else:
        monkeypatch.setattr(backend_main, "_import_pandas", lambda: fake_pandas)
    backend_main.load_model.cache_clear()
    fake_joblib.pandas = fake_pandas
    return fake_joblib


def _post_predict(client, features):
    return client.post("/api/predict", json={"features": features})


def _mutated_features(**changes):
    features = dict(VALID_FEATURES)
    features.update(changes)
    return features


def _assert_safe_model_error(response):
    assert response.json() == {"detail": "Model Pending/Unavailable"}
    text = response.text.lower()
    for leaked in ("traceback", "model.joblib", "c:\\", "/users/", "backend\\"):
        assert leaked not in text


def test_predict_valid_request_returns_expected_schema(client, monkeypatch):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 200
    assert set(response.json()) == {"model_score", "predicted_class"}
    assert response.json() == {"model_score": 0.83, "predicted_class": 1}


def test_default_prediction_threshold_is_provisional_value(monkeypatch):
    monkeypatch.delenv(backend_main.PREDICTION_THRESHOLD_ENV, raising=False)

    assert backend_main.DEFAULT_PREDICTION_THRESHOLD == 0.12672868322902756
    assert backend_main._load_prediction_threshold() == 0.12672868322902756


def test_prediction_threshold_environment_override_is_respected(monkeypatch):
    monkeypatch.setenv(backend_main.PREDICTION_THRESHOLD_ENV, "0.7")

    assert backend_main._load_prediction_threshold() == 0.7


@pytest.mark.parametrize("raw_value", ["-0.1", "1.1", "not-a-number", "NaN", "Infinity"])
def test_invalid_prediction_threshold_configuration_is_rejected(raw_value):
    with pytest.raises(RuntimeError, match=r"finite number in \[0, 1\]"):
        backend_main._parse_prediction_threshold(raw_value)


@pytest.mark.parametrize(
    "probabilities,threshold,expected_class",
    [
        ([[0.9, 0.1]], 0.2, 0),
        ([[0.9, 0.1]], 0.05, 1),
        ([[0.8732713167709724, 0.12672868322902756]], 0.12672868322902756, 1),
    ],
    ids=["below_threshold", "above_threshold", "exactly_at_threshold"],
)
def test_predicted_class_uses_configured_threshold_boundary(
    client, monkeypatch, probabilities, threshold, expected_class
):
    estimator = FakeEstimator(probabilities=probabilities)
    _patch_artifact(monkeypatch, estimator)
    monkeypatch.setattr(backend_main, "PREDICTION_THRESHOLD", threshold)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 200
    assert response.json()["predicted_class"] == expected_class


def test_predicted_class_uses_runtime_threshold_override(client, monkeypatch):
    estimator = FakeEstimator(probabilities=[[0.17, 0.83]])
    _patch_artifact(monkeypatch, estimator)
    monkeypatch.setenv(backend_main.PREDICTION_THRESHOLD_ENV, "0.9")
    monkeypatch.setattr(
        backend_main,
        "PREDICTION_THRESHOLD",
        backend_main._load_prediction_threshold(),
    )

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 200
    assert response.json() == {"model_score": 0.83, "predicted_class": 0}


def test_predict_passes_single_dataframe_in_exact_feature_order(client, monkeypatch):
    estimator = FakeEstimator()
    fake = _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 200
    assert len(estimator.calls) == 1
    frame = estimator.calls[0]
    assert isinstance(frame, FakeDataFrame)
    assert list(frame.columns) == list(backend_main.FEATURE_COLUMNS)
    assert frame.data == [
        [float(VALID_FEATURES[name]) for name in backend_main.FEATURE_COLUMNS]
    ]
    assert all(isinstance(value, float) for value in frame.data[0])
    assert fake.pandas.frames == [frame]


@pytest.mark.parametrize("feature", sorted(NULLABLE_FEATURES))
def test_predict_accepts_null_in_nullable_feature_and_passes_nan(
    client, monkeypatch, feature
):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, _mutated_features(**{feature: None}))

    assert response.status_code == 200
    frame = estimator.calls[0]
    index = list(backend_main.FEATURE_COLUMNS).index(feature)
    value = frame.data[0][index]
    assert isinstance(value, float)
    assert math.isnan(value)
    for column, actual in zip(frame.columns, frame.data[0]):
        if column == feature:
            continue
        assert isinstance(actual, float)
        assert actual == VALID_FEATURES[column]


def test_predict_accepts_all_nullable_features_together(client, monkeypatch):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)
    features = dict(VALID_FEATURES)
    for feature in NULLABLE_FEATURES:
        features[feature] = None

    response = _post_predict(client, features)

    assert response.status_code == 200
    frame = estimator.calls[0]
    for column, value in zip(frame.columns, frame.data[0]):
        assert isinstance(value, float)
        if column in NULLABLE_FEATURES:
            assert math.isnan(value)
        else:
            assert value == VALID_FEATURES[column]


@pytest.mark.parametrize(
    "feature", [name for name in VALID_FEATURES if name not in NULLABLE_FEATURES]
)
def test_predict_rejects_null_for_non_nullable_features(client, monkeypatch, feature):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, _mutated_features(**{feature: None}))

    assert response.status_code == 422
    assert not estimator.calls


@pytest.mark.parametrize("feature", list(VALID_FEATURES))
def test_predict_rejects_each_missing_feature(client, monkeypatch, feature):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)
    features = {key: value for key, value in VALID_FEATURES.items() if key != feature}

    response = _post_predict(client, features)

    assert response.status_code == 422
    assert not estimator.calls


def test_predict_rejects_extra_top_level_key(client, monkeypatch):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)
    payload = {"features": dict(VALID_FEATURES), "unexpected": 1}

    response = client.post("/api/predict", json=payload)

    assert response.status_code == 422
    assert not estimator.calls


@pytest.mark.parametrize("feature", list(VALID_FEATURES))
def test_predict_rejects_negative_values(client, monkeypatch, feature):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, _mutated_features(**{feature: -1}))

    assert response.status_code == 422
    assert not estimator.calls


@pytest.mark.parametrize("feature", sorted(BINARY_FEATURES))
@pytest.mark.parametrize("value", [0, 1])
def test_predict_accepts_only_binary_zero_and_one(client, monkeypatch, feature, value):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, _mutated_features(**{feature: value}))

    assert response.status_code == 200
    frame = estimator.calls[0]
    index = list(backend_main.FEATURE_COLUMNS).index(feature)
    assert frame.data[0][index] == value


@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("feature", list(VALID_FEATURES))
def test_predict_rejects_boolean_values_as_numbers(client, monkeypatch, feature, value):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, _mutated_features(**{feature: value}))

    assert response.status_code == 422
    assert not estimator.calls


@pytest.mark.parametrize("feature", sorted(NULLABLE_FEATURES))
def test_predict_accepts_decimal_values_for_continuous_features(
    client, monkeypatch, feature
):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)
    decimal_value = 12.75

    response = _post_predict(
        client, _mutated_features(**{feature: decimal_value})
    )

    assert response.status_code == 200
    frame = estimator.calls[0]
    index = list(backend_main.FEATURE_COLUMNS).index(feature)
    assert frame.data[0][index] == decimal_value


@pytest.mark.parametrize(
    "value,expected_status",
    [
        (2, 200),
        (2.0, 200),
        (0, 200),
        (0.0, 200),
        (2.5, 422),
        (-1, 422),
        (-1.0, 422),
        (True, 422),
        (False, 422),
        ("2", 422),
    ],
    ids=[
        "integer_two",
        "float_two",
        "integer_zero",
        "float_zero",
        "fractional",
        "negative_integer",
        "negative_float",
        "true",
        "false",
        "numeric_string",
    ],
)
def test_user_prior_purchase_sessions_validation(client, monkeypatch, value, expected_status):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(
        client, _mutated_features(user_prior_purchase_sessions=value)
    )

    assert response.status_code == expected_status
    if expected_status == 200:
        frame = estimator.calls[0]
        index = list(backend_main.FEATURE_COLUMNS).index(
            "user_prior_purchase_sessions"
        )
        actual = frame.data[0][index]
        assert isinstance(actual, float)
        assert actual == float(value)
    else:
        assert not estimator.calls


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_user_prior_purchase_sessions_rejects_non_finite_values(
    client, monkeypatch, token
):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)
    body = json.dumps({"features": VALID_FEATURES}).replace(
        '"user_prior_purchase_sessions": 2',
        f'"user_prior_purchase_sessions": {token}',
    )

    response = client.post(
        "/api/predict", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert not estimator.calls


@pytest.mark.parametrize(
    "feature_names",
    [
        list(reversed(backend_main.FEATURE_COLUMNS)),
        [
            "unexpected" if index == 0 else name
            for index, name in enumerate(backend_main.FEATURE_COLUMNS)
        ],
        list(backend_main.FEATURE_COLUMNS)[:-1],
    ],
)
def test_predict_rejects_model_feature_contract_mismatch(
    client, monkeypatch, feature_names
):
    estimator = FakeEstimator(feature_names=feature_names)
    fake = _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)
    assert not estimator.calls
    assert not fake.pandas.frames


def test_predict_rejects_model_without_feature_names(client, monkeypatch):
    estimator = FakeEstimatorWithoutFeatureNames()
    fake = _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)
    assert not estimator.calls
    assert not fake.pandas.frames


def test_predict_missing_pandas_returns_safe_response(client, monkeypatch):
    estimator = FakeEstimator()
    _patch_artifact(
        monkeypatch, estimator, pandas_error=ImportError("missing pandas")
    )

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)
    assert not estimator.calls


INVALID_FEATURE_CASES = [
    (
        "missing_key",
        {k: v for k, v in VALID_FEATURES.items() if k != "views_before_cart"},
    ),
    ("extra_key", _mutated_features(unexpected=1)),
    ("string_integer", _mutated_features(views_before_cart="3")),
    ("bool_integer", _mutated_features(views_before_cart=True)),
    ("bool_real", _mutated_features(price_ratio_cart_to_view=False)),
    ("null_integer", _mutated_features(views_before_cart=None)),
    ("string_real", _mutated_features(avg_cart_price_at_first_cart_sec="40.5")),
    ("invalid_binary", _mutated_features(has_view_before_cart=2)),
    ("negative_binary", _mutated_features(any_cart_brand_at_first_cart_sec=-1)),
    ("bool_binary", _mutated_features(has_multi_products_at_first_cart_sec=True)),
]


@pytest.mark.parametrize(
    "features",
    [case[1] for case in INVALID_FEATURE_CASES],
    ids=[case[0] for case in INVALID_FEATURE_CASES],
)
def test_predict_rejects_invalid_features(client, monkeypatch, features):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, features)

    assert response.status_code == 422
    assert not estimator.calls


NON_FINITE_TOKENS = ["NaN", "Infinity", "-Infinity"]


@pytest.mark.parametrize("token", NON_FINITE_TOKENS)
@pytest.mark.parametrize("feature", sorted(NULLABLE_FEATURES))
def test_predict_rejects_non_finite_numbers(client, monkeypatch, feature, token):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator)
    original = json.dumps(VALID_FEATURES[feature])
    body = json.dumps({"features": VALID_FEATURES}).replace(
        f'"{feature}": {original}', f'"{feature}": {token}'
    )

    response = client.post(
        "/api/predict", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert not estimator.calls


def test_predict_missing_artifact_returns_generic_503(client, monkeypatch):
    estimator = FakeEstimator()
    _patch_artifact(monkeypatch, estimator, exists=False)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)
    assert not estimator.calls


def test_predict_load_failure_returns_safe_response(client, monkeypatch):
    _patch_artifact(
        monkeypatch,
        None,
        load_error=RuntimeError("failed at C:\\secret\\model.joblib"),
    )

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)


def test_predict_missing_dependency_returns_safe_response(client, monkeypatch):
    _patch_artifact(monkeypatch, None, import_error=ImportError("missing joblib"))

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)


def test_predict_proba_failure_returns_safe_response(client, monkeypatch):
    estimator = FakeEstimator(error=RuntimeError("boom at C:\\secret"))
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)


def test_predict_uses_classes_for_score_with_reversed_order(client, monkeypatch):
    estimator = FakeEstimator(probabilities=[[0.83, 0.17]], classes=[1, 0])
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 200
    assert response.json() == {"model_score": 0.83, "predicted_class": 1}


def test_predicted_class_uses_threshold_with_reversed_classes(client, monkeypatch):
    estimator = FakeEstimator(probabilities=[[0.2, 0.8]], classes=[1, 0])
    _patch_artifact(monkeypatch, estimator)
    monkeypatch.setattr(backend_main, "PREDICTION_THRESHOLD", 0.5)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 200
    assert response.json() == {"model_score": 0.2, "predicted_class": 0}


INVALID_OUTPUT_CASES = [
    ("out_of_range", [[1.2, -0.2]], [0, 1]),
    ("nan_score", [[float("nan"), 0.0]], [0, 1]),
    ("inf_score", [[float("inf"), 0.0]], [0, 1]),
    ("bad_classes", [[0.2, 0.8]], [0, 2]),
    ("extra_class", [[0.2, 0.3, 0.5]], [0, 1, 2]),
    ("column_mismatch", [[0.2, 0.3, 0.5]], [0, 1]),
    ("two_rows", [[0.2, 0.8], [0.4, 0.6]], [0, 1]),
    ("flat_output", [0.2, 0.8], [0, 1]),
]


@pytest.mark.parametrize(
    "probabilities,classes",
    [case[1:] for case in INVALID_OUTPUT_CASES],
    ids=[case[0] for case in INVALID_OUTPUT_CASES],
)
def test_predict_rejects_invalid_model_output(
    client, monkeypatch, probabilities, classes
):
    estimator = FakeEstimator(probabilities=probabilities, classes=classes)
    _patch_artifact(monkeypatch, estimator)

    response = _post_predict(client, VALID_FEATURES)

    assert response.status_code == 503
    _assert_safe_model_error(response)


def test_model_is_not_reloaded_on_every_request(client, monkeypatch):
    estimator = FakeEstimator()
    fake_joblib = _patch_artifact(monkeypatch, estimator)

    first = _post_predict(client, VALID_FEATURES)
    second = _post_predict(client, VALID_FEATURES)

    assert first.status_code == 200
    assert second.status_code == 200
    assert fake_joblib.load_calls == 1
    assert len(estimator.calls) == 2


def test_existing_endpoints_still_work_with_prediction_enabled(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/summary").status_code == 200
    assert client.get("/api/replay-sessions", params={"size": 1}).json()["total"] == 100
    assert client.get("/api/reports/cart-behavior").status_code == 200


def test_startup_loads_and_validates_model_before_first_request(monkeypatch):
    estimator = FakeEstimator()
    fake_joblib = _patch_artifact(monkeypatch, estimator)

    with TestClient(backend_main.app) as startup_client:
        assert fake_joblib.load_calls == 1
        assert backend_main.load_model() is estimator
        assert fake_joblib.load_calls == 1

        response = _post_predict(startup_client, VALID_FEATURES)

    assert response.status_code == 200
    assert response.json() == {"model_score": 0.83, "predicted_class": 1}
    assert fake_joblib.load_calls == 1
    assert len(estimator.calls) == 1


def test_startup_model_is_reused_for_every_prediction(monkeypatch):
    estimator = FakeEstimator()
    fake_joblib = _patch_artifact(monkeypatch, estimator)

    with TestClient(backend_main.app) as startup_client:
        responses = [_post_predict(startup_client, VALID_FEATURES) for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert fake_joblib.load_calls == 1
    assert len(estimator.calls) == 3


@pytest.mark.parametrize(
    "model, exists, load_error",
    [
        (None, False, None),
        (None, True, RuntimeError("corrupt artifact")),
        (FakeEstimator(feature_names=["wrong_feature_order"]), True, None),
    ],
    ids=["missing_artifact", "corrupt_artifact", "feature_contract_mismatch"],
)
def test_startup_fails_explicitly_when_model_is_unusable(
    monkeypatch, model, exists, load_error
):
    _patch_artifact(monkeypatch, model, exists=exists, load_error=load_error)

    with pytest.raises(RuntimeError, match="startup"):
        with TestClient(backend_main.app):
            pass
