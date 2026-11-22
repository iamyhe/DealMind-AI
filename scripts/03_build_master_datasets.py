import json
import shutil
import sqlite3
from pathlib import Path
import duckdb

PROCESSED_DIR = Path("data/processed")
DB_PATH = Path("data/dealmind.db")
TMP_DIR = PROCESSED_DIR / "_duckdb_tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

PARQUET_FILES = [
    (PROCESSED_DIR / "2019-Oct.parquet").as_posix(),
    (PROCESSED_DIR / "2019-Nov.parquet").as_posix(),
    (PROCESSED_DIR / "2019-Dec.parquet").as_posix(),
    (PROCESSED_DIR / "2020-Jan.parquet").as_posix(),
    (PROCESSED_DIR / "2020-Feb.parquet").as_posix(),
]

RFM_REFERENCE_DATE = "2020-03-01 00:00:00+00"


def build_master_datasets():
    for f in PARQUET_FILES:
        if not Path(f).exists():
            raise FileNotFoundError(f"Missing Parquet file: {f}")

    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC';")
        con.execute(f"SET temp_directory = '{TMP_DIR.as_posix()}';")
        files_sql = ", ".join(f"'{f}'" for f in PARQUET_FILES)
        con.execute(f"CREATE VIEW raw_events AS SELECT * FROM read_parquet([{files_sql}]);")

        print("1/6 Filtering valid single-user sessions (retaining all price values for behavioral analysis)...")
        con.execute("""
            CREATE TEMP TABLE multi_user_sessions AS
            SELECT user_session
            FROM raw_events
            WHERE user_session IS NOT NULL AND TRIM(user_session) <> ''
            GROUP BY user_session
            HAVING COUNT(DISTINCT user_id) > 1
        """)

        con.execute("""
            CREATE TEMP VIEW valid_events AS
            SELECT r.*
            FROM raw_events r
            LEFT JOIN multi_user_sessions m ON r.user_session = m.user_session
            WHERE r.user_session IS NOT NULL
              AND TRIM(r.user_session) <> ''
              AND m.user_session IS NULL
        """)

        print("2/6 Building session summary and strict temporal splits (UTC)...")
        con.execute("""
            CREATE TEMP TABLE session_summary AS
            WITH agg AS (
                SELECT
                    user_session,
                    ANY_VALUE(user_id) AS user_id,
                    MIN(event_time) AS session_start,
                    MAX(event_time) AS session_end,
                    BOOL_OR(event_type = 'view') AS has_view,
                    BOOL_OR(event_type = 'cart') AS has_cart,
                    BOOL_OR(event_type = 'remove_from_cart') AS has_remove,
                    BOOL_OR(event_type = 'purchase') AS has_purchase,
                    BOOL_OR(event_type = 'purchase' AND price > 0) AS has_pos_purchase,
                    MIN(event_time) FILTER (WHERE event_type = 'cart') AS first_cart_time,
                    MAX(event_time) FILTER (WHERE event_type = 'purchase') AS last_purchase_time,
                    SUM(price) FILTER (WHERE event_type = 'purchase') AS purchase_total_signed,
                    SUM(price) FILTER (WHERE event_type = 'purchase' AND price > 0) AS purchase_total_pos
                FROM valid_events
                GROUP BY user_session
            )
            SELECT
                *,
                CASE
                    WHEN session_start >= TIMESTAMPTZ '2019-10-02 00:00:00+00'
                     AND session_end < TIMESTAMPTZ '2020-01-01 00:00:00+00' THEN 'train'
                    WHEN session_start >= TIMESTAMPTZ '2020-01-01 00:00:00+00'
                     AND session_end < TIMESTAMPTZ '2020-02-01 00:00:00+00' THEN 'val'
                    WHEN session_start >= TIMESTAMPTZ '2020-02-01 00:00:00+00'
                     AND session_end < TIMESTAMPTZ '2020-02-29 00:00:00+00' THEN 'test'
                    ELSE 'excluded'
                END AS split
            FROM agg
        """)

        print("3/6 Building strictly leak-free Purchase Intent datasets (train / val / test)...")
        con.execute("""
            CREATE TEMP TABLE user_cum_history AS
            WITH ordered AS (
                SELECT
                    user_id,
                    session_end,
                    COUNT(*) OVER (
                        PARTITION BY user_id
                        ORDER BY session_end ASC, user_session ASC
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS cum_sessions,
                    SUM(CAST(has_purchase AS BIGINT)) OVER (
                        PARTITION BY user_id
                        ORDER BY session_end ASC, user_session ASC
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS cum_purchase_sessions
                FROM session_summary
            )
            SELECT
                user_id,
                session_end,
                MAX(cum_sessions) AS cum_sessions,
                MAX(cum_purchase_sessions) AS cum_purchase_sessions
            FROM ordered
            GROUP BY user_id, session_end
        """)

        con.execute("""
            CREATE TEMP TABLE eligible_cart_sessions AS
            SELECT
                user_session,
                user_id,
                session_start,
                session_end,
                first_cart_time,
                split,
                CASE
                    WHEN has_purchase AND last_purchase_time > first_cart_time THEN 1
                    ELSE 0
                END AS target_purchased_after_cart
            FROM session_summary
            WHERE has_cart
              AND split IN ('train', 'val', 'test')
              AND NOT (has_purchase AND last_purchase_time = first_cart_time)
        """)

        con.execute("""
            CREATE TEMP TABLE intent_features AS
            WITH pre_and_snapshot AS (
                SELECT
                    s.user_session,
                    s.user_id,
                    s.session_start,
                    s.first_cart_time,
                    s.split,
                    s.target_purchased_after_cart,
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'view' AND e.event_time < s.first_cart_time
                    ) AS views_before_cart,
                    COUNT(DISTINCT e.product_id) FILTER (
                        WHERE e.event_type = 'view' AND e.event_time < s.first_cart_time
                    ) AS unique_products_viewed_before_cart,
                    COUNT(DISTINCT e.category_id) FILTER (
                        WHERE e.event_type = 'view' AND e.event_time < s.first_cart_time
                    ) AS unique_categories_viewed_before_cart,
                    COUNT(DISTINCT e.brand) FILTER (
                        WHERE e.event_type = 'view' AND e.event_time < s.first_cart_time AND e.brand IS NOT NULL
                    ) AS unique_brands_viewed_before_cart,
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'remove_from_cart' AND e.event_time < s.first_cart_time
                    ) AS removes_before_cart,
                    COUNT(DISTINCT e.product_id) FILTER (
                        WHERE e.event_type = 'remove_from_cart' AND e.event_time < s.first_cart_time
                    ) AS unique_products_removed_before_cart,
                    AVG(e.price) FILTER (
                        WHERE e.event_type = 'view' AND e.event_time < s.first_cart_time AND e.price > 0
                    ) AS avg_viewed_price_before_cart,
                    MAX(e.price) FILTER (
                        WHERE e.event_type = 'view' AND e.event_time < s.first_cart_time AND e.price > 0
                    ) AS max_viewed_price_before_cart,
                    COUNT(*) FILTER (
                        WHERE e.event_type = 'cart' AND e.event_time = s.first_cart_time
                    ) AS cart_events_at_first_cart_sec,
                    COUNT(DISTINCT e.product_id) FILTER (
                        WHERE e.event_type = 'cart' AND e.event_time = s.first_cart_time
                    ) AS unique_products_carted_at_first_cart_sec,
                    AVG(e.price) FILTER (
                        WHERE e.event_type = 'cart' AND e.event_time = s.first_cart_time AND e.price > 0
                    ) AS avg_cart_price_at_first_cart_sec,
                    MAX(
                        CASE
                            WHEN e.event_type = 'cart' AND e.event_time = s.first_cart_time AND e.brand IS NOT NULL
                            THEN 1 ELSE 0
                        END
                    ) AS any_cart_brand_at_first_cart_sec,
                    STRING_AGG(DISTINCT e.product_id, ',' ORDER BY e.product_id) FILTER (
                        WHERE e.event_type = 'cart' AND e.event_time = s.first_cart_time
                    ) AS cart_product_ids_at_first_cart_sec,
                    STRING_AGG(DISTINCT e.category_id, ',' ORDER BY e.category_id) FILTER (
                        WHERE e.event_type = 'cart' AND e.event_time = s.first_cart_time
                    ) AS cart_category_ids_at_first_cart_sec
                FROM eligible_cart_sessions s
                JOIN valid_events e
                  ON e.user_session = s.user_session
                 AND (
                       (e.event_time < s.first_cart_time AND e.event_type IN ('view', 'remove_from_cart'))
                    OR (e.event_time = s.first_cart_time AND e.event_type = 'cart')
                 )
                GROUP BY
                    s.user_session, s.user_id, s.session_start,
                    s.first_cart_time, s.split, s.target_purchased_after_cart
            )
            SELECT
                p.user_session,
                p.user_id,
                p.session_start,
                p.first_cart_time,
                p.split,
                p.cart_product_ids_at_first_cart_sec,
                p.cart_category_ids_at_first_cart_sec,
                CAST(DATE_DIFF('second', p.session_start, p.first_cart_time) AS BIGINT) AS seconds_to_first_cart,
                p.views_before_cart,
                CASE WHEN p.views_before_cart > 0 THEN 1 ELSE 0 END AS has_view_before_cart,
                p.unique_products_viewed_before_cart,
                p.unique_categories_viewed_before_cart,
                p.unique_brands_viewed_before_cart,
                p.removes_before_cart,
                p.unique_products_removed_before_cart,
                p.cart_events_at_first_cart_sec,
                p.unique_products_carted_at_first_cart_sec,
                CASE WHEN p.unique_products_carted_at_first_cart_sec > 1 THEN 1 ELSE 0 END AS has_multi_products_at_first_cart_sec,
                ROUND(p.avg_cart_price_at_first_cart_sec, 4) AS avg_cart_price_at_first_cart_sec,
                ROUND(p.avg_viewed_price_before_cart, 4) AS avg_viewed_price_before_cart,
                ROUND(p.max_viewed_price_before_cart, 4) AS max_viewed_price_before_cart,
                CASE
                    WHEN p.avg_cart_price_at_first_cart_sec IS NOT NULL
                     AND p.avg_viewed_price_before_cart IS NOT NULL
                     AND p.avg_viewed_price_before_cart > 0
                    THEN ROUND(p.avg_cart_price_at_first_cart_sec / p.avg_viewed_price_before_cart, 4)
                    ELSE NULL
                END AS price_ratio_cart_to_view,
                p.any_cart_brand_at_first_cart_sec,
                CAST(EXTRACT(HOUR FROM p.first_cart_time) AS INTEGER) AS hour_of_day_utc,
                CAST(EXTRACT(DOW FROM p.first_cart_time) AS INTEGER) AS day_of_week_utc,
                COALESCE(h.cum_sessions, 0) AS user_prior_sessions,
                COALESCE(h.cum_purchase_sessions, 0) AS user_prior_purchase_sessions,
                p.target_purchased_after_cart
            FROM pre_and_snapshot p
            ASOF LEFT JOIN user_cum_history h
              ON p.user_id = h.user_id
             AND p.session_start > h.session_end
        """)

        intent_counts = {}
        for split_name in ("train", "val", "test"):
            out_file = (PROCESSED_DIR / f"intent_{split_name}.parquet").as_posix()
            con.execute(f"""
                COPY (SELECT * FROM intent_features WHERE split = '{split_name}')
                TO '{out_file}' (FORMAT PARQUET, COMPRESSION SNAPPY)
            """)
            row_cnt, pos_cnt = con.execute(f"""
                SELECT COUNT(*), SUM(target_purchased_after_cart)
                FROM intent_features WHERE split = '{split_name}'
            """).fetchone()
            intent_counts[split_name] = {
                "rows": int(row_cnt),
                "positives": int(pos_cnt),
                "positive_rate_pct": round((pos_cnt / row_cnt) * 100, 2) if row_cnt else 0.0,
            }

        print("4/6 Building Purchase Baskets for FP-Growth (positive-price purchase rows only)...")
        basket_counts = {}
        for split_name in ("train", "val", "test"):
            out_file = (PROCESSED_DIR / f"baskets_{split_name}.parquet").as_posix()
            con.execute(f"""
                COPY (
                    SELECT DISTINCT
                        s.user_session,
                        s.session_start,
                        e.product_id
                    FROM session_summary s
                    JOIN valid_events e
                      ON e.user_session = s.user_session
                     AND e.event_type = 'purchase'
                     AND e.price > 0
                    WHERE s.has_purchase
                      AND s.split = '{split_name}'
                )
                TO '{out_file}' (FORMAT PARQUET, COMPRESSION SNAPPY)
            """)
            b_sess, b_pairs = con.execute(f"""
                SELECT COUNT(DISTINCT user_session), COUNT(*)
                FROM read_parquet('{out_file}')
            """).fetchone()
            basket_counts[split_name] = {
                "purchase_sessions": int(b_sess),
                "unique_session_product_pairs": int(b_pairs),
            }

        print("5/6 Building RFM customer table (recorded spend on positive-price purchase rows)...")
        rfm_file = (PROCESSED_DIR / "rfm_customers.parquet").as_posix()
        con.execute(f"""
            COPY (
                SELECT
                    user_id,
                    ROUND(
                        DATE_DIFF('second', MAX(event_time), TIMESTAMPTZ '{RFM_REFERENCE_DATE}') / 86400.0,
                        4
                    ) AS recency_days,
                    COUNT(DISTINCT user_session) AS frequency_sessions,
                    ROUND(SUM(price), 2) AS monetary_total,
                    COUNT(*) AS purchase_events_count,
                    MIN(event_time) AS first_purchase_time,
                    MAX(event_time) AS last_purchase_time
                FROM valid_events
                WHERE event_type = 'purchase'
                  AND price > 0
                GROUP BY user_id
            )
            TO '{rfm_file}' (FORMAT PARQUET, COMPRESSION SNAPPY)
        """)
        rfm_users = con.execute(f"SELECT COUNT(*) FROM read_parquet('{rfm_file}')").fetchone()[0]

        print("6/6 Building lightweight SQLite app database (data/dealmind.db)...")
        products_rows = con.execute("""
            SELECT
                product_id,
                ARG_MAX(category_id, event_time) AS category_id,
                ARG_MAX(category_code, event_time) FILTER (WHERE category_code IS NOT NULL) AS category_code,
                ARG_MAX(brand, event_time) FILTER (WHERE brand IS NOT NULL) AS brand,
                ROUND(ARG_MAX(price, event_time), 2) AS latest_price,
                COUNT(*) FILTER (WHERE event_type = 'view') AS view_count,
                COUNT(*) FILTER (WHERE event_type = 'cart') AS cart_count,
                COUNT(*) FILTER (WHERE event_type = 'purchase' AND price > 0) AS pos_purchase_count
            FROM valid_events
            WHERE price >= 0
            GROUP BY product_id
        """).fetchall()

        funnel_rows = con.execute("""
            WITH base AS (
                SELECT
                    strftime(session_start, '%Y-%m') AS period,
                    has_view, has_cart, has_purchase, has_pos_purchase,
                    purchase_total_signed, purchase_total_pos
                FROM session_summary
            ),
            monthly AS (
                SELECT
                    period,
                    COUNT(*) AS total_valid_sessions,
                    COUNT(*) FILTER (WHERE has_view) AS sessions_with_view,
                    COUNT(*) FILTER (WHERE has_cart) AS sessions_with_cart,
                    COUNT(*) FILTER (WHERE has_purchase) AS sessions_with_purchase,
                    COUNT(*) FILTER (WHERE has_view AND has_purchase) AS sessions_with_view_and_purchase,
                    COUNT(*) FILTER (WHERE NOT has_view AND has_purchase) AS sessions_with_purchase_without_view,
                    COUNT(*) FILTER (WHERE has_cart AND NOT has_purchase) AS sessions_with_cart_without_purchase,
                    ROUND(SUM(purchase_total_signed) FILTER (WHERE has_purchase), 2) AS total_recorded_purchase_signed,
                    ROUND(AVG(purchase_total_signed) FILTER (WHERE has_purchase), 2) AS historical_aov_signed,
                    ROUND(SUM(purchase_total_pos) FILTER (WHERE has_pos_purchase), 2) AS total_recorded_purchase_pos,
                    ROUND(AVG(purchase_total_pos) FILTER (WHERE has_pos_purchase), 2) AS historical_aov_pos
                FROM base
                GROUP BY period
            ),
            overall AS (
                SELECT
                    'ALL' AS period,
                    COUNT(*) AS total_valid_sessions,
                    COUNT(*) FILTER (WHERE has_view) AS sessions_with_view,
                    COUNT(*) FILTER (WHERE has_cart) AS sessions_with_cart,
                    COUNT(*) FILTER (WHERE has_purchase) AS sessions_with_purchase,
                    COUNT(*) FILTER (WHERE has_view AND has_purchase) AS sessions_with_view_and_purchase,
                    COUNT(*) FILTER (WHERE NOT has_view AND has_purchase) AS sessions_with_purchase_without_view,
                    COUNT(*) FILTER (WHERE has_cart AND NOT has_purchase) AS sessions_with_cart_without_purchase,
                    ROUND(SUM(purchase_total_signed) FILTER (WHERE has_purchase), 2) AS total_recorded_purchase_signed,
                    ROUND(AVG(purchase_total_signed) FILTER (WHERE has_purchase), 2) AS historical_aov_signed,
                    ROUND(SUM(purchase_total_pos) FILTER (WHERE has_pos_purchase), 2) AS total_recorded_purchase_pos,
                    ROUND(AVG(purchase_total_pos) FILTER (WHERE has_pos_purchase), 2) AS historical_aov_pos
                FROM base
            )
            SELECT * FROM overall
            UNION ALL
            SELECT * FROM monthly
            ORDER BY period
        """).fetchall()

        replay_sessions_rows = con.execute("""
            WITH candidates AS (
                SELECT
                    user_session,
                    user_id,
                    CAST(session_start AS VARCHAR) AS session_start,
                    CAST(first_cart_time AS VARCHAR) AS first_cart_time,
                    cart_product_ids_at_first_cart_sec,
                    cart_category_ids_at_first_cart_sec,
                    seconds_to_first_cart,
                    views_before_cart,
                    has_view_before_cart,
                    unique_products_viewed_before_cart,
                    unique_categories_viewed_before_cart,
                    unique_brands_viewed_before_cart,
                    removes_before_cart,
                    unique_products_removed_before_cart,
                    cart_events_at_first_cart_sec,
                    unique_products_carted_at_first_cart_sec,
                    has_multi_products_at_first_cart_sec,
                    avg_cart_price_at_first_cart_sec,
                    avg_viewed_price_before_cart,
                    max_viewed_price_before_cart,
                    price_ratio_cart_to_view,
                    any_cart_brand_at_first_cart_sec,
                    hour_of_day_utc,
                    day_of_week_utc,
                    user_prior_sessions,
                    user_prior_purchase_sessions,
                    target_purchased_after_cart,
                    ROW_NUMBER() OVER (
                        PARTITION BY target_purchased_after_cart
                        ORDER BY hash(user_session)
                    ) AS rn
                FROM intent_features
                WHERE split = 'test'
                  AND views_before_cart BETWEEN 2 AND 12
                  AND seconds_to_first_cart > 0
                  AND avg_cart_price_at_first_cart_sec IS NOT NULL
                  AND has_multi_products_at_first_cart_sec = 0
            )
            SELECT
                user_session, user_id, session_start, first_cart_time,
                cart_product_ids_at_first_cart_sec, cart_category_ids_at_first_cart_sec,
                seconds_to_first_cart, views_before_cart, has_view_before_cart,
                unique_products_viewed_before_cart, unique_categories_viewed_before_cart,
                unique_brands_viewed_before_cart, removes_before_cart,
                unique_products_removed_before_cart, cart_events_at_first_cart_sec,
                unique_products_carted_at_first_cart_sec, has_multi_products_at_first_cart_sec,
                avg_cart_price_at_first_cart_sec, avg_viewed_price_before_cart,
                max_viewed_price_before_cart, price_ratio_cart_to_view,
                any_cart_brand_at_first_cart_sec, hour_of_day_utc, day_of_week_utc,
                user_prior_sessions, user_prior_purchase_sessions, target_purchased_after_cart
            FROM candidates
            WHERE rn <= 50
            ORDER BY target_purchased_after_cart DESC, session_start ASC
        """).fetchall()

        replay_ids = [r[0] for r in replay_sessions_rows]
        con.execute("CREATE TEMP TABLE selected_replays (user_session VARCHAR)")
        con.executemany("INSERT INTO selected_replays VALUES (?)", [(sid,) for sid in replay_ids])

        replay_events_rows = con.execute("""
            SELECT
                e.user_session,
                CAST(e.event_time AS VARCHAR) AS event_time,
                e.event_type,
                e.product_id,
                e.category_id,
                e.category_code,
                e.brand,
                ROUND(e.price, 2) AS price,
                CASE
                    WHEN e.event_time < s.first_cart_time THEN 'before_first_cart'
                    WHEN e.event_time = s.first_cart_time AND e.event_type = 'cart' THEN 'at_first_cart_second'
                    WHEN e.event_time = s.first_cart_time THEN 'same_second_other'
                    ELSE 'after_first_cart_outcome'
                END AS event_phase
            FROM valid_events e
            JOIN selected_replays sr ON e.user_session = sr.user_session
            JOIN eligible_cart_sessions s ON e.user_session = s.user_session
            ORDER BY e.user_session, e.event_time
        """).fetchall()

        if DB_PATH.exists():
            DB_PATH.unlink()

        scon = sqlite3.connect(DB_PATH)
        try:
            cur = scon.cursor()
            cur.executescript("""
                CREATE TABLE products (
                    product_id TEXT PRIMARY KEY,
                    category_id TEXT NOT NULL,
                    category_code TEXT,
                    brand TEXT,
                    latest_price REAL NOT NULL,
                    view_count INTEGER NOT NULL,
                    cart_count INTEGER NOT NULL,
                    pos_purchase_count INTEGER NOT NULL
                );
                CREATE INDEX idx_products_purchase ON products(pos_purchase_count DESC);
                CREATE INDEX idx_products_brand ON products(brand);
                CREATE INDEX idx_products_category ON products(category_id);

                CREATE TABLE funnel_summary (
                    period TEXT PRIMARY KEY,
                    total_valid_sessions INTEGER NOT NULL,
                    sessions_with_view INTEGER NOT NULL,
                    sessions_with_cart INTEGER NOT NULL,
                    sessions_with_purchase INTEGER NOT NULL,
                    sessions_with_view_and_purchase INTEGER NOT NULL,
                    sessions_with_purchase_without_view INTEGER NOT NULL,
                    sessions_with_cart_without_purchase INTEGER NOT NULL,
                    overall_purchase_rate_pct REAL NOT NULL,
                    view_to_purchase_rate_pct REAL NOT NULL,
                    session_cart_abandonment_rate_pct REAL NOT NULL,
                    total_recorded_purchase_signed REAL NOT NULL,
                    historical_aov_signed REAL NOT NULL,
                    total_recorded_purchase_pos REAL NOT NULL,
                    historical_aov_pos REAL NOT NULL
                );

                CREATE TABLE replay_sessions (
                    user_session TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_start TEXT NOT NULL,
                    first_cart_time TEXT NOT NULL,
                    cart_product_ids_at_first_cart_sec TEXT NOT NULL,
                    cart_category_ids_at_first_cart_sec TEXT NOT NULL,
                    seconds_to_first_cart INTEGER NOT NULL,
                    views_before_cart INTEGER NOT NULL,
                    has_view_before_cart INTEGER NOT NULL,
                    unique_products_viewed_before_cart INTEGER NOT NULL,
                    unique_categories_viewed_before_cart INTEGER NOT NULL,
                    unique_brands_viewed_before_cart INTEGER NOT NULL,
                    removes_before_cart INTEGER NOT NULL,
                    unique_products_removed_before_cart INTEGER NOT NULL,
                    cart_events_at_first_cart_sec INTEGER NOT NULL,
                    unique_products_carted_at_first_cart_sec INTEGER NOT NULL,
                    has_multi_products_at_first_cart_sec INTEGER NOT NULL,
                    avg_cart_price_at_first_cart_sec REAL,
                    avg_viewed_price_before_cart REAL,
                    max_viewed_price_before_cart REAL,
                    price_ratio_cart_to_view REAL,
                    any_cart_brand_at_first_cart_sec INTEGER NOT NULL,
                    hour_of_day_utc INTEGER NOT NULL,
                    day_of_week_utc INTEGER NOT NULL,
                    user_prior_sessions INTEGER NOT NULL,
                    user_prior_purchase_sessions INTEGER NOT NULL,
                    target_purchased_after_cart INTEGER NOT NULL
                );

                CREATE TABLE replay_session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_session TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    category_id TEXT NOT NULL,
                    category_code TEXT,
                    brand TEXT,
                    price REAL NOT NULL,
                    event_phase TEXT NOT NULL,
                    FOREIGN KEY (user_session) REFERENCES replay_sessions(user_session)
                );
                CREATE INDEX idx_replay_events_session ON replay_session_events(user_session);
            """)

            cur.executemany(
                "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                products_rows,
            )

            funnel_insert = []
            for r in funnel_rows:
                period, tot, sv, sc, sp, svp, spnv, scnp, sum_s, aov_s, sum_p, aov_p = r
                funnel_insert.append((
                    period, int(tot), int(sv), int(sc), int(sp), int(svp), int(spnv), int(scnp),
                    round((sp / tot) * 100, 2) if tot else 0.0,
                    round((svp / sv) * 100, 2) if sv else 0.0,
                    round((scnp / sc) * 100, 2) if sc else 0.0,
                    float(sum_s or 0.0),
                    float(aov_s or 0.0),
                    float(sum_p or 0.0),
                    float(aov_p or 0.0),
                ))
            cur.executemany(
                "INSERT INTO funnel_summary VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                funnel_insert,
            )

            cur.executemany(
                f"INSERT INTO replay_sessions VALUES ({', '.join(['?'] * 27)})",
                replay_sessions_rows,
            )

            cur.executemany(
                """
                INSERT INTO replay_session_events (
                    user_session, event_time, event_type, product_id,
                    category_id, category_code, brand, price, event_phase
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                replay_events_rows,
            )
            scon.commit()
        finally:
            scon.close()

        all_funnel = next(r for r in funnel_insert if r[0] == "ALL")
        db_size_mb = round(DB_PATH.stat().st_size / (1024 * 1024), 2)
        summary = {
            "cleaning_and_feature_rules": [
                "Dropped rows with null/empty user_session and excluded 272 multi-user session IDs",
                "Retained all valid-session events regardless of price for behavioral funnel and purchase target",
                "Applied price > 0 strictly to price-based features, purchase baskets (recommendations), and RFM (recorded spend on positive-price purchase rows)",
                "Kept negative-price purchase records separate in funnel summary (signed vs positive-only totals/AOV) without assuming their business cause",
                "Computed pre-cart features strictly on event_time < first_cart_time; cart snapshot strictly on event_time = first_cart_time",
                "Excluded boundary sessions (2019-10-01, 2020-02-29, cross-split) and 8 same-second purchase sessions",
                "All timestamps and date aggregations executed in UTC",
            ],
            "overall_funnel_all_valid_sessions": {
                "total_valid_sessions": all_funnel[1],
                "sessions_with_view": all_funnel[2],
                "sessions_with_cart": all_funnel[3],
                "sessions_with_purchase": all_funnel[4],
                "sessions_with_view_and_purchase": all_funnel[5],
                "sessions_with_purchase_without_view": all_funnel[6],
                "sessions_with_cart_without_purchase": all_funnel[7],
                "overall_purchase_rate_pct": all_funnel[8],
                "view_to_purchase_rate_pct": all_funnel[9],
                "session_cart_abandonment_rate_pct": all_funnel[10],
                "total_recorded_purchase_signed": all_funnel[11],
                "historical_aov_signed_units": all_funnel[12],
                "total_recorded_purchase_pos_only": all_funnel[13],
                "historical_aov_pos_only_units": all_funnel[14],
            },
            "rfm_reference_date_utc": RFM_REFERENCE_DATE,
            "intent_datasets": intent_counts,
            "basket_datasets": basket_counts,
            "rfm_unique_buyers_pos_price": int(rfm_users),
            "sqlite_database": {
                "path": DB_PATH.as_posix(),
                "size_mb": db_size_mb,
                "products_count": len(products_rows),
                "funnel_periods": len(funnel_rows),
                "curated_test_replay_sessions": len(replay_sessions_rows),
                "replay_events_count": len(replay_events_rows),
            },
        }

        summary_path = PROCESSED_DIR / "dataset_prep_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        print("\n=== FINAL MASTER DATASETS & SQLITE READY ===")
        print(json.dumps(summary, indent=2))
        print(f"\nSaved summary to: {summary_path}")
    finally:
        con.close()
        shutil.rmtree(TMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    build_master_datasets()