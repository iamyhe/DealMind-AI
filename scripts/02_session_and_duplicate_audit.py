import json
import shutil
from pathlib import Path
import duckdb

PROCESSED_DIR = Path("data/processed")
TMP_DIR = PROCESSED_DIR / "_duckdb_tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

PARQUET_FILES = [
    (PROCESSED_DIR / "2019-Oct.parquet").as_posix(),
    (PROCESSED_DIR / "2019-Nov.parquet").as_posix(),
    (PROCESSED_DIR / "2019-Dec.parquet").as_posix(),
    (PROCESSED_DIR / "2020-Jan.parquet").as_posix(),
    (PROCESSED_DIR / "2020-Feb.parquet").as_posix(),
]


def run_session_and_duplicate_audit():
    for f in PARQUET_FILES:
        if not Path(f).exists():
            raise FileNotFoundError(f"Missing Parquet file: {f}")

    con = duckdb.connect()
    try:
        con.execute(f"SET temp_directory = '{TMP_DIR.as_posix()}';")
        files_sql = ", ".join(f"'{f}'" for f in PARQUET_FILES)
        con.execute(f"CREATE VIEW raw_events AS SELECT * FROM read_parquet([{files_sql}]);")

        print("1/4 Auditing exact duplicate rows by event_type...")
        dup_rows = con.execute("""
            WITH grouped AS (
                SELECT event_type, COUNT(*) AS cnt
                FROM raw_events
                GROUP BY
                    event_time, event_type, product_id, category_id,
                    category_code, brand, price, user_id, user_session
            )
            SELECT
                event_type,
                CAST(SUM(cnt - 1) AS BIGINT) AS extra_duplicate_rows,
                CAST(COUNT(*) FILTER (WHERE cnt > 1) AS BIGINT) AS duplicated_groups
            FROM grouped
            GROUP BY event_type
            ORDER BY extra_duplicate_rows DESC
        """).fetchall()

        duplicates_by_event = {
            ev: {"extra_duplicate_rows": int(extra), "duplicated_groups": int(grps)}
            for ev, extra, grps in dup_rows
        }
        total_extra_dups = sum(v["extra_duplicate_rows"] for v in duplicates_by_event.values())

        print("2/4 Auditing entity counts and session-user integrity...")
        entity_row = con.execute("""
            SELECT
                COUNT(DISTINCT product_id) AS products,
                COUNT(DISTINCT category_id) AS category_ids,
                COUNT(DISTINCT brand) AS brands,
                COUNT(DISTINCT user_id) AS users,
                COUNT(DISTINCT user_session) FILTER (
                    WHERE user_session IS NOT NULL AND TRIM(user_session) <> ''
                ) AS valid_sessions
            FROM raw_events
        """).fetchone()

        multi_user_sessions = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT user_session
                FROM raw_events
                WHERE user_session IS NOT NULL AND TRIM(user_session) <> ''
                GROUP BY user_session
                HAVING COUNT(DISTINCT user_id) > 1
            )
        """).fetchone()[0]

        print("3/4 Computing session-level funnel & AOV (valid sessions, price > 0)...")
        con.execute("""
            CREATE TEMP TABLE session_stats AS
            SELECT
                user_session,
                MIN(event_time) AS session_start,
                MAX(event_time) AS session_end,
                BOOL_OR(event_type = 'view') AS has_view,
                BOOL_OR(event_type = 'cart') AS has_cart,
                BOOL_OR(event_type = 'remove_from_cart') AS has_remove,
                BOOL_OR(event_type = 'purchase') AS has_purchase,
                MIN(event_time) FILTER (WHERE event_type = 'cart') AS first_cart_time,
                MAX(event_time) FILTER (WHERE event_type = 'purchase') AS last_purchase_time,
                MIN(event_time) FILTER (WHERE event_type = 'purchase') AS first_purchase_time,
                SUM(price) FILTER (WHERE event_type = 'purchase') AS purchase_total_price
            FROM raw_events
            WHERE user_session IS NOT NULL
              AND TRIM(user_session) <> ''
              AND price > 0
            GROUP BY user_session
        """)

        funnel = con.execute("""
            SELECT
                COUNT(*) AS total_valid_sessions,
                COUNT(*) FILTER (WHERE has_view) AS sessions_with_view,
                COUNT(*) FILTER (WHERE has_cart) AS sessions_with_cart,
                COUNT(*) FILTER (WHERE has_purchase) AS sessions_with_purchase,
                COUNT(*) FILTER (WHERE has_view AND has_purchase) AS sessions_with_view_and_purchase,
                COUNT(*) FILTER (WHERE NOT has_view AND has_purchase) AS sessions_with_purchase_without_view,
                COUNT(*) FILTER (WHERE has_cart AND NOT has_purchase) AS sessions_with_cart_without_purchase,
                COUNT(*) FILTER (WHERE has_cart AND has_purchase) AS sessions_with_cart_and_purchase,
                COUNT(*) FILTER (WHERE has_cart AND has_purchase AND last_purchase_time > first_cart_time) AS purchase_strictly_after_first_cart,
                COUNT(*) FILTER (WHERE has_cart AND has_purchase AND last_purchase_time = first_cart_time) AS purchase_same_second_as_first_cart,
                COUNT(*) FILTER (WHERE has_cart AND has_purchase AND last_purchase_time < first_cart_time) AS purchase_only_before_first_cart,
                AVG(purchase_total_price) FILTER (WHERE has_purchase) AS historical_aov
            FROM session_stats
        """).fetchone()

        print("4/4 Auditing boundary & cross-split sessions...")
        boundaries = con.execute("""
            SELECT
                COUNT(*) FILTER (WHERE session_start < TIMESTAMPTZ '2019-10-02 00:00:00+00') AS first_day_sessions,
                COUNT(*) FILTER (WHERE session_end >= TIMESTAMPTZ '2020-02-29 00:00:00+00') AS last_day_sessions,
                COUNT(*) FILTER (
                    WHERE session_start < TIMESTAMPTZ '2020-01-01 00:00:00+00'
                      AND session_end >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
                ) AS cross_train_val_sessions,
                COUNT(*) FILTER (
                    WHERE session_start < TIMESTAMPTZ '2020-02-01 00:00:00+00'
                      AND session_end >= TIMESTAMPTZ '2020-02-01 00:00:00+00'
                ) AS cross_val_test_sessions
            FROM session_stats
        """).fetchone()

        split_cart_counts = con.execute("""
            SELECT
                CASE
                    WHEN session_start >= TIMESTAMPTZ '2019-10-02 00:00:00+00'
                     AND session_end < TIMESTAMPTZ '2020-01-01 00:00:00+00' THEN 'train (Oct 2 - Dec 31)'
                    WHEN session_start >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
                     AND session_end < TIMESTAMPTZ '2020-02-01 00:00:00+00' THEN 'val (Jan)'
                    WHEN session_start >= TIMESTAMPTZ '2020-02-01 00:00:00+00'
                     AND session_end < TIMESTAMPTZ '2020-02-29 00:00:00+00' THEN 'test (Feb 1 - Feb 28)'
                    ELSE 'excluded_boundary'
                END AS split_name,
                COUNT(*) AS total_sessions,
                COUNT(*) FILTER (WHERE has_cart) AS cart_sessions,
                COUNT(*) FILTER (WHERE has_cart AND has_purchase AND last_purchase_time > first_cart_time) AS positive_intent_sessions,
                COUNT(*) FILTER (WHERE has_purchase) AS purchase_sessions
            FROM session_stats
            GROUP BY split_name
            ORDER BY split_name
        """).fetchall()

        total_sess, s_view, s_cart, s_purch, s_vp, s_p_noview, s_cart_nopurch, s_cart_purch, p_after, p_same, p_before, aov = funnel

        report = {
            "exact_duplicates": {
                "total_extra_duplicate_rows": int(total_extra_dups),
                "by_event_type": duplicates_by_event,
            },
            "unique_entities_raw": {
                "products": int(entity_row[0]),
                "category_ids": int(entity_row[1]),
                "brands": int(entity_row[2]),
                "users": int(entity_row[3]),
                "valid_sessions": int(entity_row[4]),
                "sessions_shared_by_multiple_users": int(multi_user_sessions),
            },
            "clean_session_funnel_price_gt_0": {
                "total_valid_sessions": int(total_sess),
                "sessions_with_view": int(s_view),
                "sessions_with_cart": int(s_cart),
                "sessions_with_purchase": int(s_purch),
                "sessions_with_view_and_purchase": int(s_vp),
                "sessions_with_purchase_without_view": int(s_p_noview),
                "sessions_with_cart_without_purchase": int(s_cart_nopurch),
                "sessions_with_cart_and_purchase": int(s_cart_purch),
                "overall_purchase_rate_pct": round((s_purch / total_sess) * 100, 2),
                "view_to_purchase_rate_pct": round((s_vp / s_view) * 100, 2),
                "session_cart_abandonment_rate_pct": round((s_cart_nopurch / s_cart) * 100, 2),
                "historical_aov_recorded_units": round(float(aov), 2),
            },
            "purchase_timing_relative_to_first_cart": {
                "purchase_strictly_after_first_cart": int(p_after),
                "purchase_same_second_as_first_cart": int(p_same),
                "purchase_only_before_first_cart": int(p_before),
            },
            "boundary_sessions": {
                "first_day_sessions_2019_10_01": int(boundaries[0]),
                "last_day_sessions_2020_02_29": int(boundaries[1]),
                "cross_train_val_boundary": int(boundaries[2]),
                "cross_val_test_boundary": int(boundaries[3]),
            },
            "temporal_split_preview": [
                {
                    "split": row[0],
                    "total_sessions": int(row[1]),
                    "cart_sessions": int(row[2]),
                    "positive_intent_sessions": int(row[3]),
                    "positive_rate_pct": round((row[3] / row[2]) * 100, 2) if row[2] else 0.0,
                    "purchase_sessions": int(row[4]),
                }
                for row in split_cart_counts
            ],
        }

        out_path = PROCESSED_DIR / "session_and_duplicate_audit.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        print("\n=== SESSION & DUPLICATE AUDIT COMPLETE ===")
        print(json.dumps(report, indent=2))
        print(f"\nSaved report to: {out_path}")
    finally:
        con.close()
        shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    run_session_and_duplicate_audit()