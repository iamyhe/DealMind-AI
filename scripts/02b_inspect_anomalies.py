import json
from pathlib import Path
import duckdb

PROCESSED_DIR = Path("data/processed")
PARQUET_FILES = [
    (PROCESSED_DIR / m).as_posix()
    for m in [
        "2019-Oct.parquet",
        "2019-Nov.parquet",
        "2019-Dec.parquet",
        "2020-Jan.parquet",
        "2020-Feb.parquet",
    ]
]


def inspect_anomalies():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC';")
    files_sql = ", ".join(f"'{f}'" for f in PARQUET_FILES)
    con.execute(f"CREATE VIEW raw_events AS SELECT * FROM read_parquet([{files_sql}]);")

    neg_products = con.execute("""
        SELECT product_id, category_id, brand, event_type,
               COUNT(*) AS cnt, MIN(price) AS min_p, MAX(price) AS max_p
        FROM raw_events
        WHERE price < 0
        GROUP BY product_id, category_id, brand, event_type
        ORDER BY cnt DESC
        LIMIT 15
    """).fetchall()

    neg_session_context = con.execute("""
        WITH neg_sess AS (
            SELECT DISTINCT user_session
            FROM raw_events
            WHERE price < 0 AND user_session IS NOT NULL AND TRIM(user_session) <> ''
        )
        SELECT
            COUNT(DISTINCT r.user_session) AS sessions_with_neg_price,
            COUNT(DISTINCT r.user_session) FILTER (WHERE r.event_type = 'purchase' AND r.price > 0) AS also_have_pos_purchase,
            COUNT(*) FILTER (WHERE r.price < 0) AS neg_rows_in_valid_sessions,
            ROUND(SUM(r.price) FILTER (WHERE r.event_type = 'purchase' AND r.price < 0), 2) AS sum_neg_purchase,
            ROUND(SUM(r.price) FILTER (WHERE r.event_type = 'purchase' AND r.price > 0), 2) AS sum_pos_purchase_same_sessions
        FROM raw_events r
        JOIN neg_sess n ON r.user_session = n.user_session
    """).fetchone()

    same_second_stats = con.execute("""
        WITH first_cart AS (
            SELECT user_session, MIN(event_time) AS t0
            FROM raw_events
            WHERE event_type = 'cart' AND user_session IS NOT NULL AND TRIM(user_session) <> ''
            GROUP BY user_session
        )
        SELECT
            COUNT(*) AS total_cart_sessions,
            COUNT(*) FILTER (WHERE views_same_sec > 0) AS sessions_with_view_at_same_sec,
            COUNT(*) FILTER (WHERE removes_same_sec > 0) AS sessions_with_remove_at_same_sec,
            COUNT(*) FILTER (WHERE distinct_cart_prods_at_t0 > 1) AS sessions_with_multi_products_at_t0
        FROM (
            SELECT
                fc.user_session,
                COUNT(*) FILTER (WHERE e.event_type = 'view' AND e.event_time = fc.t0) AS views_same_sec,
                COUNT(*) FILTER (WHERE e.event_type = 'remove_from_cart' AND e.event_time = fc.t0) AS removes_same_sec,
                COUNT(DISTINCT e.product_id) FILTER (WHERE e.event_type = 'cart' AND e.event_time = fc.t0) AS distinct_cart_prods_at_t0
            FROM first_cart fc
            JOIN raw_events e
              ON e.user_session = fc.user_session
             AND e.event_time = fc.t0
            GROUP BY fc.user_session
        )
    """).fetchone()

    result = {
        "negative_price_products_top15": [
            {
                "product_id": r[0], "category_id": r[1], "brand": r[2],
                "event_type": r[3], "count": int(r[4]),
                "min_price": float(r[5]), "max_price": float(r[6]),
            }
            for r in neg_products
        ],
        "negative_price_session_context": {
            "sessions_with_neg_price": int(neg_session_context[0]),
            "also_have_pos_purchase": int(neg_session_context[1]),
            "neg_rows_in_valid_sessions": int(neg_session_context[2]),
            "sum_neg_purchase": float(neg_session_context[3] or 0),
            "sum_pos_purchase_same_sessions": float(neg_session_context[4] or 0),
        },
        "same_second_first_cart_audit": {
            "total_cart_sessions": int(same_second_stats[0]),
            "sessions_with_view_at_same_sec": int(same_second_stats[1]),
            "sessions_with_remove_at_same_sec": int(same_second_stats[2]),
            "sessions_with_multi_products_at_t0": int(same_second_stats[3]),
        },
    }

    print(json.dumps(result, indent=2))
    con.close()


if __name__ == "__main__":
    inspect_anomalies()