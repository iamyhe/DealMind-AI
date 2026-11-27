# DealMind AI — API Integration Contract

**Status:** Merged backend contract — current source of truth for the implemented API.\
**Backend:** FastAPI\
**API prefix:** `/api`\
**Database:** `data/dealmind.db` (read-only access from the API)\
**Source of truth:** `backend/main.py` and `backend/tests/`

> This document describes the **current implemented behavior only**. The ML request/response contract in section 4.6 is now implemented against the trained pipeline artifact. Frontend screen requirements remain unresolved. CORS is enabled for the three approved local demo origins only (section 6.4).

---

## 1. General conventions

- All paths below are relative to the service root. The code does not configure a host/port, so no base URL is assumed here.
- Timestamps are **strings** in UTC format `YYYY-MM-DD HH:MM:SS+00`. They are not timezone-aware JSON objects.
- Boolean-like columns are returned as **integers `0` / `1`**, not JSON booleans.
- Monetary-like values (`price`, averages) are numbers in recorded source units. **No currency is defined** in the repository.
- Percent fields are already percentages (e.g. `3.43` means **3.43%**), not fractions.
- Public session identifiers are `rs_001` … `rs_100`. These are API-layer references, not raw `user_session` values.

---

## 2. Data protection rules (mandatory)

| Rule | Enforcement in current implementation |
|---|---|
| Never expose `user_id` | `public_session()` removes it; `ReplayEventOut` does not include it. Tests assert absence in list and detail responses. |
| Never expose raw `user_session` | Removed by `public_session()`; events select an explicit allowlist excluding it. Tests assert absence in list, detail, and event objects. |
| Never expose `target_purchased_after_cart` in list or detail | Removed by `public_session()`; not declared in `ReplaySessionOut`. Tests assert absence in list and detail responses. |
| Actual outcome only via `/api/replay-sessions/{id}/outcome` | The outcome endpoint is the only path returning `actual_outcome`. Tests assert it is the only place the target appears. |
| Reveal events only via `/api/replay-sessions/{id}/outcome` | Detail uses an explicit safe-phase allowlist and excludes `event_type = "purchase"`; Outcome returns the exact complement. Tests assert the two sets are disjoint and their union covers every event ID for the session. |
| No model output invention | `/api/predict` returns only values computed by the trained pipeline in `backend/models/model.joblib`. Invalid or unavailable models produce a generic `503`; no score, label, or probability is fabricated. |
| No authentication; local-demo CORS only | The API remains public with no authentication. CORS allows only the three approved local origins (section 6.4) as a browser convenience. It is **not** authentication or API protection. |
| No local filesystem paths in report responses | The cart behavior endpoint returns the parsed report object, requiring the four documented top-level sections and allowing validated additive sections. The entire object is recursively checked, including keys, for embedded Unix/Windows/UNC/`file://` paths before it is returned. Tests assert no path-like strings and no resolved file path in the response. |

**Important:** The public refs are sequential. Without authentication, any client can enumerate `rs_001`…`rs_100` and read actual outcomes through the outcome endpoint. This is a **known risk**, documented here but not changed because authentication was explicitly out of scope.

---

## 3. Endpoint summary

| # | Method | Path | Purpose |
|---|---|---|---|
| 1 | `GET` | `/api/health` | Service liveness check |
| 2 | `GET` | `/api/summary` | Business funnel summary from `funnel_summary` |
| 3 | `GET` | `/api/replay-sessions` | Paginated replay session feature list |
| 4 | `GET` | `/api/replay-sessions/{id}` | One replay session plus related events |
| 5 | `GET` | `/api/replay-sessions/{id}/outcome` | Actual recorded outcome plus withheld reveal events for one session |
| 6 | `POST` | `/api/predict` | Score 20 features with the trained pipeline; return a Model Score and predicted class |
| 7 | `GET` | `/api/reports/cart-behavior` | Role 4 cart behavior report (read-only JSON file) |

---

## 4. Endpoint details

### 4.1 `GET /api/health`

**Parameters:** none.\
**Request body:** none.

**Success — 200**
```json
{
  "status": "ok"
}
```

**Errors:** No endpoint-specific error. Standard 500 response may apply.

| Field | Type | Meaning |
|---|---|---|
| `status` | string | Always `"ok"` when the process is running. |

---

### 4.2 `GET /api/summary`

**Data source:** `funnel_summary`.

**Query parameters**

| Name | Required | Type | Default | Allowed values |
|---|---|---|---|---|
| `period` | No | string | `ALL` | `ALL`, `2019-10`, `2019-11`, `2019-12`, `2020-01`, `2020-02` |

**Request body:** none.

**Success — 200 (default `period=ALL`, actual DB values)**
```json
{
  "period": "ALL",
  "total_valid_sessions": 4535669,
  "sessions_with_view": 4280436,
  "sessions_with_cart": 985698,
  "sessions_with_purchase": 155595,
  "overall_purchase_rate_pct": 3.43,
  "view_to_purchase_rate_pct": 2.72,
  "session_cart_abandonment_rate_pct": 87.19,
  "historical_aov_pos": 40.82,
  "historical_aov_signed": 40.79
}
```

**Success — 200 (`period=2019-10`, actual DB values)**
```json
{
  "period": "2019-10",
  "total_valid_sessions": 873936,
  "sessions_with_view": 826246,
  "sessions_with_cart": 228524,
  "sessions_with_purchase": 29741,
  "overall_purchase_rate_pct": 3.4,
  "view_to_purchase_rate_pct": 2.74,
  "session_cart_abandonment_rate_pct": 89.23,
  "historical_aov_pos": 43.38,
  "historical_aov_signed": 43.36
}
```

**Field meanings**

| Field | Type | Meaning |
|---|---|---|
| `period` | string | Month in `YYYY-MM`, or aggregate row `ALL`. |
| `total_valid_sessions` | integer | Count of valid sessions in the selected period. |
| `sessions_with_view` | integer | Sessions containing at least one `view` event. |
| `sessions_with_cart` | integer | Sessions containing at least one `cart` event. |
| `sessions_with_purchase` | integer | Sessions containing at least one `purchase` event. |
| `overall_purchase_rate_pct` | number | Sessions with purchase / total valid sessions × 100. |
| `view_to_purchase_rate_pct` | number | View-and-purchase sessions / view sessions × 100. |
| `session_cart_abandonment_rate_pct` | number | Cart-without-purchase sessions / cart sessions × 100. |
| `historical_aov_pos` | number | Positive-only recorded purchase value per purchasing session, read from the same `funnel_summary` row as `period`. Uses purchase rows with `price > 0`. |
| `historical_aov_signed` | number | Signed recorded purchase value per purchasing session, read from the same `funnel_summary` row as `period`. Includes signed (negative-price) purchase rows. |

> Both AOV fields are historical dataset aggregates, **not model predictions**. They are read directly from `funnel_summary`; the API does not recompute them. Values are expressed in the **recorded source units** — **no currency is defined** in the repository, so no currency symbol is added. For `ALL`, the current DB yields `40.82` (positive-only) and `40.79` (signed); monthly values differ. Definitions are documented in `data/processed/dataset_prep_summary.json` and `scripts/03_build_master_datasets.py`.

**Errors**

| Status | When | Example |
|---|---|---|
| `422` | `period` is outside the allowed enum | `{"detail":[{"type":"literal_error","loc":["query","period"],"msg":"Input should be 'ALL', '2019-10', '2019-11', '2019-12', '2020-01' or '2020-02'","input":"1999-01","ctx":{"expected":"'ALL', '2019-10', '2019-11', '2019-12', '2020-01' or '2020-02'"}}]}` |
| `404` | Valid enum value has no row in `funnel_summary` (not currently the case) | `{"detail": "Resource not found"}` |
| `500` | Unexpected server error | `{"detail": "Internal server error"}` |

> The exact `422` `msg` text comes from FastAPI/Pydantic and may change between versions; `loc` and `type` are the stable parts.

---

### 4.3 `GET /api/replay-sessions`

**Data source:** `replay_sessions`.

**Query parameters**

| Name | Required | Type | Default | Constraints |
|---|---|---|---|---|
| `page` | No | integer | `1` | `>= 1` |
| `size` | No | integer | `20` | `1 <= size <= 100` |

**Request body:** none.

**Pagination behavior**
- Items are ordered by the public reference `rs_001`, `rs_002`, …
- `total` is the number of replay sessions currently mapped by the API (currently `100`).
- An out-of-range page returns `200` with `"items": []`, not `404`.
- There are **no filter parameters** in the current implementation. Filtering needs are unresolved.

**Success — 200 (default, one item shown; remaining 19 omitted for brevity)**
```json
{
  "items": [
    {
      "id": "rs_001",
      "session_start": "2020-02-14 20:03:53+00",
      "first_cart_time": "2020-02-14 20:09:37+00",
      "cart_product_ids_at_first_cart_sec": "5739124",
      "cart_category_ids_at_first_cart_sec": "1487580008246412266",
      "seconds_to_first_cart": 344,
      "views_before_cart": 2,
      "has_view_before_cart": 1,
      "unique_products_viewed_before_cart": 2,
      "unique_categories_viewed_before_cart": 2,
      "unique_brands_viewed_before_cart": 1,
      "removes_before_cart": 0,
      "unique_products_removed_before_cart": 0,
      "cart_events_at_first_cart_sec": 1,
      "unique_products_carted_at_first_cart_sec": 1,
      "has_multi_products_at_first_cart_sec": 0,
      "avg_cart_price_at_first_cart_sec": 4.51,
      "avg_viewed_price_before_cart": 10.35,
      "max_viewed_price_before_cart": 16.19,
      "price_ratio_cart_to_view": 0.4357,
      "any_cart_brand_at_first_cart_sec": 1,
      "hour_of_day_utc": 20,
      "day_of_week_utc": 5,
      "user_prior_sessions": 0,
      "user_prior_purchase_sessions": 0
    }
  ],
  "page": 1,
  "size": 20,
  "total": 100
}
```

**Item field meanings**

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Public session reference `rs_NNN`. Not a raw `user_session`. |
| `session_start` | string (UTC) | First recorded event time in the session. |
| `first_cart_time` | string (UTC) | Time of the first `cart` event in the session. |
| `cart_product_ids_at_first_cart_sec` | string | Comma-separated product IDs carted at `first_cart_time`; current curated rows contain one ID. |
| `cart_category_ids_at_first_cart_sec` | string | Comma-separated category IDs carted at `first_cart_time`; current curated rows contain one ID. |
| `seconds_to_first_cart` | integer | Seconds from `session_start` to `first_cart_time`. |
| `views_before_cart` | integer | `view` events strictly before `first_cart_time`. |
| `has_view_before_cart` | integer `0|1` | Whether `views_before_cart > 0`. |
| `unique_products_viewed_before_cart` | integer | Distinct viewed product IDs before first cart. |
| `unique_categories_viewed_before_cart` | integer | Distinct viewed category IDs before first cart. |
| `unique_brands_viewed_before_cart` | integer | Distinct non-null brands viewed before first cart. |
| `removes_before_cart` | integer | `remove_from_cart` events before first cart. |
| `unique_products_removed_before_cart` | integer | Distinct removed product IDs before first cart. |
| `cart_events_at_first_cart_sec` | integer | `cart` events exactly at `first_cart_time`. |
| `unique_products_carted_at_first_cart_sec` | integer | Distinct products carted at that second. |
| `has_multi_products_at_first_cart_sec` | integer `0|1` | Whether more than one product was carted at that second. Current replay rows are curated to `0`. |
| `avg_cart_price_at_first_cart_sec` | number or `null` | Average positive cart price at first-cart second. |
| `avg_viewed_price_before_cart` | number or `null` | Average positive viewed price before first cart. |
| `max_viewed_price_before_cart` | number or `null` | Maximum positive viewed price before first cart. |
| `price_ratio_cart_to_view` | number or `null` | Cart average / viewed average; `null` when denominator unavailable. |
| `any_cart_brand_at_first_cart_sec` | integer `0|1` | Whether a non-null brand existed on cart events at first-cart second. |
| `hour_of_day_utc` | integer | UTC hour of `first_cart_time` (`0`–`23`). |
| `day_of_week_utc` | integer | Weekday of `first_cart_time` generated by `EXTRACT(DOW ...)` in `scripts/03_build_master_datasets.py`: `0`=Sunday, …, `6`=Saturday. No weekday name is exposed; client-side naming is a Frontend display decision. |
| `user_prior_sessions` | integer | Cumulative prior sessions for the user before this session. |
| `user_prior_purchase_sessions` | integer | Cumulative prior purchase sessions for the user before this session. |

**Errors**

| Status | When | Example |
|---|---|---|
| `422` | Invalid `page`/`size`, e.g. `page=0`, `size=101`, or non-numeric values | `{"detail":[{"type":"greater_than_equal","loc":["query","page"],"msg":"Input should be greater than or equal to 1","input":"0","ctx":{"ge":1}}]}` |
| `500` | Unexpected server error | `{"detail": "Internal server error"}` |

---

### 4.4 `GET /api/replay-sessions/{id}`

**Data sources:** `replay_sessions`, `replay_session_events`.

**Path parameters**

| Name | Required | Type | Example |
|---|---|---|---|
| `id` | Yes | string | `rs_001` |

**Query parameters:** none.\
**Request body:** none.

**Detail event filtering policy**

`events` contains only rows satisfying **both**:

- `event_phase IN ("before_first_cart", "at_first_cart_second", "same_second_other")`; and
- `event_type <> "purchase"`.

This is an explicit allowlist, not a single-phase exclusion. `after_first_cart_outcome` events and any `purchase` event are withheld and returned only by the Outcome endpoint. `same_second_other` rows are included when present and non-purchase; purchase rows in that phase would be withheld. Ordering remains `ORDER BY event_time, id`.

**Success — 200 (all 3 safe events for `rs_001` shown)**
```json
{
  "session": {
    "id": "rs_001",
    "session_start": "2020-02-14 20:03:53+00",
    "first_cart_time": "2020-02-14 20:09:37+00",
    "cart_product_ids_at_first_cart_sec": "5739124",
    "cart_category_ids_at_first_cart_sec": "1487580008246412266",
    "seconds_to_first_cart": 344,
    "views_before_cart": 2,
    "has_view_before_cart": 1,
    "unique_products_viewed_before_cart": 2,
    "unique_categories_viewed_before_cart": 2,
    "unique_brands_viewed_before_cart": 1,
    "removes_before_cart": 0,
    "unique_products_removed_before_cart": 0,
    "cart_events_at_first_cart_sec": 1,
    "unique_products_carted_at_first_cart_sec": 1,
    "has_multi_products_at_first_cart_sec": 0,
    "avg_cart_price_at_first_cart_sec": 4.51,
    "avg_viewed_price_before_cart": 10.35,
    "max_viewed_price_before_cart": 16.19,
    "price_ratio_cart_to_view": 0.4357,
    "any_cart_brand_at_first_cart_sec": 1,
    "hour_of_day_utc": 20,
    "day_of_week_utc": 5,
    "user_prior_sessions": 0,
    "user_prior_purchase_sessions": 0
  },
  "events": [
    {
      "id": 1,
      "event_time": "2020-02-14 20:03:53+00",
      "event_type": "view",
      "product_id": "5651975",
      "category_id": "1487580012902088873",
      "category_code": null,
      "brand": null,
      "price": 16.19,
      "event_phase": "before_first_cart"
    },
    {
      "id": 2,
      "event_time": "2020-02-14 20:08:46+00",
      "event_type": "view",
      "product_id": "5739124",
      "category_id": "1487580008246412266",
      "category_code": null,
      "brand": "kapous",
      "price": 4.51,
      "event_phase": "before_first_cart"
    },
    {
      "id": 3,
      "event_time": "2020-02-14 20:09:37+00",
      "event_type": "cart",
      "product_id": "5739124",
      "category_id": "1487580008246412266",
      "category_code": null,
      "brand": "kapous",
      "price": 4.51,
      "event_phase": "at_first_cart_second"
    }
  ]
}
```

**`session` object:** same fields and meanings as section 4.3.\
**`events[]` field meanings**

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Internal event row ID. Safe to expose; not a personal identifier. |
| `event_time` | string (UTC) | Event timestamp. |
| `event_type` | string | In Detail: `view`, `cart`, or `remove_from_cart`. `purchase` is withheld and appears only in Outcome. |
| `product_id` | string | Product identifier as recorded in source data. |
| `category_id` | string | Category identifier as recorded in source data. |
| `category_code` | string or `null` | Often missing in the source dataset. |
| `brand` | string or `null` | Brand when recorded; may be missing. |
| `price` | number | Recorded price in source units; currency undefined. |
| `event_phase` | string | In Detail: only `before_first_cart`, `at_first_cart_second`, or `same_second_other`. `after_first_cart_outcome` is returned only by the Outcome endpoint. |

> `same_second_other` is a boundary-phase value generated by the build script when a non-cart event shares the first-cart second. It is included in Detail when present and non-purchase. No such rows exist in the current DB, but this is data state, not a permanent rule.

**Errors**

| Status | When | Example |
|---|---|---|
| `404` | Unknown `id` | `{"detail": "Resource not found"}` |
| `500` | Unexpected server error | `{"detail": "Internal server error"}` |

---

### 4.5 `GET /api/replay-sessions/{id}/outcome`

**Data sources:** `replay_sessions.target_purchased_after_cart`, `replay_session_events`.

**Path parameters**

| Name | Required | Type | Example |
|---|---|---|---|
| `id` | Yes | string | `rs_001` |

**Query parameters:** none.\
**Request body:** none.

**Outcome event policy**

`events` is the **exact complement** of the Detail event set for the same session. Detail keeps rows where `event_phase IN ("before_first_cart", "at_first_cart_second", "same_second_other")` **and** `event_type <> "purchase"`. Outcome returns every other row for that session: all `after_first_cart_outcome` events, any `purchase` event regardless of phase, and any unexpected future phase. The two sets are disjoint and their union covers all events for the session. Ordering is `ORDER BY event_time, id`.

**Success — 200 (`rs_001`, all 4 withheld events shown)**
```json
{
  "actual_outcome": 0,
  "events": [
    {
      "id": 4,
      "event_time": "2020-02-14 20:10:46+00",
      "event_type": "cart",
      "product_id": "5739122",
      "category_id": "1783999067156644376",
      "category_code": null,
      "brand": "kapous",
      "price": 4.51,
      "event_phase": "after_first_cart_outcome"
    },
    {
      "id": 5,
      "event_time": "2020-02-14 20:14:48+00",
      "event_type": "view",
      "product_id": "5688837",
      "category_id": "1487580012902088873",
      "category_code": null,
      "brand": null,
      "price": 27.06,
      "event_phase": "after_first_cart_outcome"
    },
    {
      "id": 6,
      "event_time": "2020-02-14 20:16:25+00",
      "event_type": "view",
      "product_id": "5700068",
      "category_id": "1487580012902088873",
      "category_code": null,
      "brand": "runail",
      "price": 23.81,
      "event_phase": "after_first_cart_outcome"
    },
    {
      "id": 7,
      "event_time": "2020-02-14 20:16:56+00",
      "event_type": "view",
      "product_id": "5688837",
      "category_id": "1487580012902088873",
      "category_code": null,
      "brand": null,
      "price": 27.06,
      "event_phase": "after_first_cart_outcome"
    }
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `actual_outcome` | integer `0|1` | Recorded dataset target: whether a purchase occurred **after** the first cart, using the leak-free rules documented in `README.md`. It is **not** a model prediction. |
| `events` | array | Events withheld from Session Details. Each item uses the same public event schema as section 4.4 and never includes `user_id`, `user_session`, or `target_purchased_after_cart`. |

> For the current DB, every withheld event has `event_phase = "after_first_cart_outcome"`. The implementation does not rely on that: a `purchase` in any phase is also withheld. `rs_002`, for example, returns 45 withheld events including 7 `purchase` events.

**Errors**

| Status | When | Example |
|---|---|---|
| `404` | Unknown `id` | `{"detail": "Resource not found"}` |
| `500` | Unexpected server error | `{"detail": "Internal server error"}` |

**Reveal flow:** Call Session Details first to render the safe timeline. Call this endpoint only when the UI intentionally reveals the outcome. It returns both the label and the events that were withheld from Details.

**Access rule:** This is the **only** endpoint allowed to return the actual target and the withheld events. Frontend must not try to derive either from list/detail responses, and must not treat `actual_outcome` as a prediction.

---

### 4.6 `POST /api/predict`

**Purpose:** score exactly one row of pre-cart features with the trained ML pipeline and return a Model Score plus a predicted class.

**Artifact and preprocessing ownership:** `backend/models/model.joblib`. The path is built as `BACKEND_DIR / "models" / "model.joblib"`, where `BACKEND_DIR` is derived from `backend/main.py`; it is **independent of the process working directory**. The artifact contains the **full** sklearn pipeline `SimpleImputer(strategy="median") -> FunctionTransformer(np.log1p) -> StandardScaler() -> LogisticRegression()`. The Backend **does not** impute, calculate medians, scale, encode, fill, drop, rename, or reorder features; all preprocessing lives inside the artifact. At the model-input boundary, the Backend builds a single-row pandas DataFrame, converts all 20 values to floating-point values, and converts JSON `null` to floating-point `NaN` for the four explicitly nullable fields.

**Provisional decision threshold:** `PREDICTION_THRESHOLD` defaults to `0.12672868322902756`, the baseline demo threshold recommended by Role 5 and selected on validation using best F1. It is documented as **PROVISIONAL — not the final approved threshold**. It can be overridden with the environment variable `DEALMIND_PREDICTION_THRESHOLD`. The value is parsed at configuration initialization and must be a finite number in `[0, 1]`; invalid values fail clearly instead of silently falling back. The score is uncalibrated and must be presented as **Model Score**; this default is not calibrated or production-approved. Role 6 may replace the baseline model and threshold after comparison/evaluation.

**Model lifecycle:** the pipeline is loaded lazily on the first `/api/predict` request and cached with `lru_cache(maxsize=1)`; it is not loaded at import time and not reloaded per request. `joblib` and `pandas` are imported lazily for the same reason. A missing artifact, missing dependency, load failure, feature-name/order mismatch, inference failure, or invalid model output yields the generic `503` below. Error logs record the exception type only, never a filesystem path or traceback.

**Query parameters:** none.

**Request body:** exactly one object with a single `features` key. Extra top-level keys are rejected.

```json
{
  "features": {
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
    "avg_viewed_price_before_cart": null,
    "max_viewed_price_before_cart": 60.0,
    "price_ratio_cart_to_view": 1.15,
    "any_cart_brand_at_first_cart_sec": 1,
    "hour_of_day_utc": 14,
    "day_of_week_utc": 3,
    "user_prior_sessions": 5,
    "user_prior_purchase_sessions": 2
  }
}
```

**Exact feature schema and order** (this is also the column order of the single row passed to the model):

| # | Feature | JSON type |
|---|---|---|
| 1 | `seconds_to_first_cart` | integer |
| 2 | `views_before_cart` | integer |
| 3 | `has_view_before_cart` | integer, binary `0`/`1` |
| 4 | `unique_products_viewed_before_cart` | integer |
| 5 | `unique_categories_viewed_before_cart` | integer |
| 6 | `unique_brands_viewed_before_cart` | integer |
| 7 | `removes_before_cart` | integer |
| 8 | `unique_products_removed_before_cart` | integer |
| 9 | `cart_events_at_first_cart_sec` | integer |
| 10 | `unique_products_carted_at_first_cart_sec` | integer |
| 11 | `has_multi_products_at_first_cart_sec` | integer, binary `0`/`1` |
| 12 | `avg_cart_price_at_first_cart_sec` | number (integer or float) or `null` |
| 13 | `avg_viewed_price_before_cart` | number (integer or float) or `null` |
| 14 | `max_viewed_price_before_cart` | number (integer or float) or `null` |
| 15 | `price_ratio_cart_to_view` | number (integer or float) or `null` |
| 16 | `any_cart_brand_at_first_cart_sec` | integer, binary `0`/`1` |
| 17 | `hour_of_day_utc` | integer |
| 18 | `day_of_week_utc` | integer |
| 19 | `user_prior_sessions` | integer |
| 20 | `user_prior_purchase_sessions` | non-negative integer count; integer or integer-valued float |

**Validation (every violation returns `422`):**

- `features` must be present; extra top-level keys are rejected.
- All 20 keys above must be present exactly once; missing or extra feature keys are rejected.
- Integer fields accept JSON integers only. Number fields accept JSON integers or floats. `user_prior_purchase_sessions` accepts a non-negative integer count as either an integer (`2`) or an integer-valued float (`2.0`); fractional, negative, non-finite, boolean, and string values are rejected. Other strings and non-numeric JSON types are rejected.
- Only `avg_viewed_price_before_cart`, `max_viewed_price_before_cart`, `price_ratio_cart_to_view`, and `avg_cart_price_at_first_cart_sec` accept JSON `null`; `null` for any other feature is rejected.
- Every numeric value must be non-negative; negative integers and negative floats are rejected.
- JSON booleans are **not** accepted as numbers, including for binary fields.
- `NaN`, `Infinity`, and `-Infinity` are rejected.
- `has_view_before_cart`, `has_multi_products_at_first_cart_sec`, and `any_cart_brand_at_first_cart_sec` must be exactly `0` or `1`.
- There is no silent filling of missing values, no string-to-number coercion, and no reordering, dropping, or renaming of features. Allowed `null` values become `NaN` only at the model-input boundary, where all 20 features are converted to floating-point values.

**Success — 200**

```json
{
  "model_score": 0.83,
  "predicted_class": 1
}
```

`model_score` is taken from the class-1 column of `predict_proba()` using `model.classes_`; class order is **not** assumed. It is the raw uncalibrated class-1 probability from the model and must be presented as **Model Score**, not a guaranteed probability and not a calibrated probability. `predicted_class` is decided by the provisional configured threshold: `1` when `model_score >= PREDICTION_THRESHOLD`, otherwise `0`; equality therefore returns class `1`. Class `1` means **purchase predicted / higher purchase likelihood**. Class `0` means **potential abandonment risk / lower purchase likelihood**, not confirmed abandonment. The model predicts purchase likelihood; it does not prove actual abandonment or user intent. Both values are checked to be finite, `model_score` must be within `[0, 1]`, and the classes must be exactly `{0, 1}`. The values shown above are illustrative; real values come from the artifact.

The pipeline receives a **single-row pandas DataFrame** whose column names and order are exactly the 20 fields listed above. Every non-null value is converted to a floating-point value and allowed `null` values are converted to `NaN` before inference. Before inference, `model.feature_names_in_` must match that list exactly; a mismatch fails safely with `503` and is never silently reordered.

**Errors**

| Status | When | Example |
|---|---|---|
| `422` | Missing `features`, missing/extra feature keys, wrong value types, `null` outside the four allowed fields, negative numbers, booleans as numbers, non-finite numbers, invalid binary values, or malformed JSON | standard FastAPI validation error body |
| `503` | Artifact missing, dependency unavailable, load failure, feature-name/order mismatch, inference failure, or invalid model output | `{"detail": "Model Pending/Unavailable"}` |
| `500` | Unexpected server error | `{"detail": "Internal server error"}` |

> The `503` detail is intentionally generic: no filesystem path, exception message, or traceback is returned. A missing artifact does not prevent the rest of the API from starting.

**Do not** use `actual_outcome` as a prediction. Frontend must treat `model_score` as a ranking signal only and must not present it as a calibrated probability.

---

### 4.7 `GET /api/reports/cart-behavior`

**Purpose:** expose Abdelrahman's merged Role 4 cart behavior report to the Frontend Dashboard.

**Data source:** `reports/cart_analysis/cart_behavior_summary.json`.

- The path is built as `PROJECT_ROOT / "reports/cart_analysis/cart_behavior_summary.json"`, where `PROJECT_ROOT` is derived from `backend/main.py`. It is **independent of the process working directory**.
- The file is opened with `encoding="utf-8"` and parsed with `json.load()` on **every request**. There is no cache, no write handle, and no recalculation.
- The response is the report object itself: the four documented top-level sections are required, and any additive top-level sections are passed through after validation. No wrapper and no file path is added. Object key order is not part of the contract; clients should rely on field names, not ordering.
- `meta.source_file` is the dataset filename `"intent_train.parquet"`, **not** a machine path. `meta.notes` are four descriptive caveats and contain no paths. No string in the current merged report contains a local filesystem path.
- Before returning, the entire parsed object is recursively validated. Keys must be strings; string keys and values must not contain embedded Unix, Windows drive, UNC, or `file://` paths; numbers must be finite; unsupported values are rejected.
- Invalid structure or unsafe content maps to the generic `500` response. Report logs record the exception type only; no local path or traceback is included in the response or report logs.

**Parameters:** none.\
**Request body:** none.

**Response — 200: verified structure from the merged file**

| Top-level key | Type | Meaning |
|---|---|---|
| `meta` | object | Provenance and scale of the analyzed dataset: source filename, train split, session/user counts, covered UTC period, target column, overall purchase rate, buyer/non-buyer counts, and four descriptive notes. |
| `pre_cart_behavior` | object | Buyer vs non-buyer comparisons and purchase rates by pre-cart behavior buckets. |
| `catalog_and_brands` | object | Catalog concentration and purchase rates by category/product volume and rate rank, plus brand-presence buckets. |
| `price_band_cart_behavior` | object | Price terciles of the first-cart average price, thresholds, per-band behavior metrics, and cart-vs-viewed price moves. |

| Section | Nested keys and types (all verified in the merged report) |
|---|---|
| `meta` | `source_file` (string), `split` (string), `n_sessions` (int), `n_users` (int), `period_start` (string UTC), `period_end` (string UTC), `target_column` (string), `overall_purchase_rate` (number, fraction), `n_buyers` (int), `n_non_buyers` (int), `notes` (array of 4 strings). |
| `pre_cart_behavior` | `numeric_comparison` (13 rows: `feature`, `buyer_mean`, `non_buyer_mean`, `buyer_median`, `non_buyer_median`); `flag_comparison` (3 rows: `feature`, `buyer_share`, `non_buyer_share`); `purchase_rate_by_has_view` (2), `purchase_rate_by_seconds_to_first_cart` (8), `purchase_rate_by_views_before_cart` (6), `purchase_rate_by_removes_before_cart` (4), `purchase_rate_by_prior_purchase_sessions` (4), `purchase_rate_by_multi_product_cart` (2) — each row `{bucket, sessions, purchase_rate}`; `purchase_rate_by_hour_utc` (24 rows `{hour, sessions, purchase_rate}`); `purchase_rate_by_weekday_utc` (7 rows `{weekday, sessions, purchase_rate}`). |
| `catalog_and_brands` | `n_categories` (int), `n_products` (int), `top10_categories_share_of_sessions` (number), `top50_products_share_of_sessions` (number), `min_sessions_for_rate_ranking` (int); `top_categories_by_volume` (15 rows `{category_id, sessions, share, purchase_rate}`); `highest_purchase_rate_categories` (10) and `lowest_purchase_rate_categories` (10) (rows `{category_id, sessions, purchase_rate}`); `top_products_by_volume` (15 rows `{product_id, sessions, share, purchase_rate}`); `brand_presence` object with `cart_item_has_brand` (2 bucket rows) and `distinct_brands_viewed_before_cart` (4 bucket rows), each `{bucket, sessions, purchase_rate}`. |
| `price_band_cart_behavior` | `price_column` (string), `band_method` (string), `thresholds` object `{low_max, mid_max}` (numbers); `bands` (3 rows with 14 fields each: `band`, `sessions`, `purchase_rate`, `price_min`, `price_median`, `price_max`, `median_seconds_to_first_cart`, `mean_views_before_cart`, `mean_removes_before_cart`, `share_has_view`, `share_multi_product_cart`, `share_branded`, `median_prior_sessions`, `mean_prior_purchase_sessions`); `cart_vs_viewed_price` (3 rows `{move, sessions, share, purchase_rate}`). |

> All `purchase_rate`, `share`, `buyer_share`, and `non_buyer_share` values are **fractions between 0 and 1**, not percentages. `sessions` values are integer counts. Category/product IDs are raw string IDs with no names in the source data. Brand analysis is presence-based because no brand-name column exists. The JSON itself currently contains **no null values**; the NaN caveat in `meta.notes[1]` is preserved verbatim. Price-like values use recorded source units; **no currency is defined**. This is descriptive train-split analysis, **not** model predictions.

**Success — 200 (values copied from the merged report; arrays truncated to their first item except `purchase_rate_by_has_view`, which is complete)**

```json
{
  "meta": {
    "source_file": "intent_train.parquet",
    "split": "train",
    "n_sessions": 590754,
    "n_users": 264008,
    "period_start": "2019-10-02 00:00:03+00:00",
    "period_end": "2019-12-31 23:54:22+00:00",
    "target_column": "target_purchased_after_cart",
    "overall_purchase_rate": 0.1257,
    "n_buyers": 74260,
    "n_non_buyers": 516494,
    "notes": [
      "Descriptive analysis only; train split only.",
      "avg_viewed_price/max_viewed_price/price_ratio are NaN when there was no view before cart (structural).",
      "No brand name column exists; brand analysis is presence-based.",
      "Category/product ids are raw ids (no names in the data)."
    ]
  },
  "pre_cart_behavior": {
    "numeric_comparison": [
      {"feature": "seconds_to_first_cart", "buyer_mean": 2735.6548, "non_buyer_mean": 1828.8358, "buyer_median": 25.0, "non_buyer_median": 13.0}
    ],
    "flag_comparison": [
      {"feature": "has_view_before_cart", "buyer_share": 0.5682, "non_buyer_share": 0.6118}
    ],
    "purchase_rate_by_has_view": [
      {"bucket": "no view", "sessions": 232583, "purchase_rate": 0.1379},
      {"bucket": "has view", "sessions": 358171, "purchase_rate": 0.1178}
    ],
    "purchase_rate_by_seconds_to_first_cart": [
      {"bucket": "0s", "sessions": 211460, "purchase_rate": 0.1321}
    ],
    "purchase_rate_by_views_before_cart": [
      {"bucket": "0", "sessions": 232583, "purchase_rate": 0.1379}
    ],
    "purchase_rate_by_removes_before_cart": [
      {"bucket": "0", "sessions": 535369, "purchase_rate": 0.1187}
    ],
    "purchase_rate_by_prior_purchase_sessions": [
      {"bucket": "0", "sessions": 477623, "purchase_rate": 0.1189}
    ],
    "purchase_rate_by_multi_product_cart": [
      {"bucket": "single product", "sessions": 590067, "purchase_rate": 0.1257}
    ],
    "purchase_rate_by_hour_utc": [
      {"hour": 0, "sessions": 6800, "purchase_rate": 0.0716}
    ],
    "purchase_rate_by_weekday_utc": [
      {"weekday": "Sun", "sessions": 86833, "purchase_rate": 0.111}
    ]
  },
  "catalog_and_brands": {
    "n_categories": 463,
    "n_products": 38101,
    "top10_categories_share_of_sessions": 0.2966,
    "top50_products_share_of_sessions": 0.1007,
    "min_sessions_for_rate_ranking": 500,
    "top_categories_by_volume": [
      {"category_id": "1487580005092295511", "sessions": 28094, "share": 0.0476, "purchase_rate": 0.1363}
    ],
    "highest_purchase_rate_categories": [
      {"category_id": "1487580009177546772", "sessions": 928, "purchase_rate": 0.2414}
    ],
    "lowest_purchase_rate_categories": [
      {"category_id": "1871018959927509750", "sessions": 525, "purchase_rate": 0.0305}
    ],
    "top_products_by_volume": [
      {"product_id": "5809910", "sessions": 8334, "share": 0.0141, "purchase_rate": 0.137}
    ],
    "brand_presence": {
      "cart_item_has_brand": [
        {"bucket": "no brand", "sessions": 242364, "purchase_rate": 0.1233}
      ],
      "distinct_brands_viewed_before_cart": [
        {"bucket": "0", "sessions": 357992, "purchase_rate": 0.1278}
      ]
    }
  },
  "price_band_cart_behavior": {
    "price_column": "avg_cart_price_at_first_cart_sec",
    "band_method": "terciles of avg cart price (equal-size bands)",
    "thresholds": {"low_max": 2.94, "mid_max": 5.95},
    "bands": [
      {"band": "Low", "sessions": 196790, "purchase_rate": 0.1123, "price_min": 0.05, "price_median": 1.59, "price_max": 2.94, "median_seconds_to_first_cart": 13.0, "mean_views_before_cart": 1.1819, "mean_removes_before_cart": 0.8351, "share_has_view": 0.5729, "share_multi_product_cart": 0.0016, "share_branded": 0.6062, "median_prior_sessions": 3.0, "mean_prior_purchase_sessions": 0.3643}
    ],
    "cart_vs_viewed_price": [
      {"move": "cheaper than viewed", "sessions": 75687, "share": 0.2116, "purchase_rate": 0.1413}
    ]
  }
}
```

**Errors**

| Status | When | Example |
|---|---|---|
| `404` | Report file is missing at the resolved path | `{"detail": "Resource not found"}` |
| `500` | Malformed JSON, unreadable/non-file path, encoding failure, missing or non-object required section, or unsafe/invalid content found by recursive validation | `{"detail": "Internal server error"}` |

Exception details are logged server-side only; the client never receives a filesystem path or traceback. Report-specific logs record the exception type, not the resolved file path. No Role 3 or Role 6 placeholder is included in this endpoint.

---

## 5. Current error response reference

| Status | Body | Source |
|---|---|---|
| `404` | `{"detail": "Resource not found"}` | Custom `StarletteHTTPException` handler |
| `422` | FastAPI validation body (`detail` array with `loc`, `msg`, `type`, `input`) | FastAPI request validation; custom handler sanitizes non-finite rejected inputs |
| `500` | `{"detail": "Internal server error"}` | Custom unhandled-exception handler |
| `503` | `{"detail": "Model Pending/Unavailable"}` | `/api/predict` model unavailable or unusable |

Internal exception details and stack traces are logged server-side only and never returned to clients.

---

## 6. Information required from the Frontend Engineer

All items below are **unresolved**. The API will not be changed until they are answered.

### 6.1 Required fields per screen

| Screen / use case | Question |
|---|---|
| Dashboard | Which of the 8 summary fields are displayed? Is `period` fixed to `ALL` or user-selectable? |
| Replay list | Which of the 25 session fields are actually rendered? Are all current fields required, or can the response be reduced later? |
| Replay detail | Which session fields and which event fields are needed? The endpoint now returns only the safe pre-outcome timeline defined in section 4.4. |
| Outcome reveal | When should `/outcome` be called? It returns `actual_outcome` plus the complement events withheld from Detail; confirm the reveal UX. |
| Prediction UI | How should the uncalibrated Model Score be displayed, and what should the UI show when the model returns `503`? |
| Cart behavior report | Which of the four report sections should the Dashboard render, and should the train-only caveat in `meta.notes` be shown in the UI? |

### 6.2 Expected response fields
- Confirm whether exact key sets must remain fixed, or whether extra non-sensitive fields are acceptable.
- Confirm whether integers `0|1` should be rendered as booleans in the UI, with conversion done client-side only.
- Confirm whether `day_of_week_utc` should be rendered as weekday names or displayed as the raw integer.
- Confirm display formatting for UTC timestamp strings and for numeric `price` values (currency is undefined in the dataset).

### 6.3 Pagination and filtering
- Confirm default `page=1`, `size=20`, and maximum `size=100` are acceptable.
- Confirm whether any filtering/sorting is needed (e.g. by target, time range, brand, category). **No filters exist today.**
- Confirm whether sequential `rs_NNN` refs are acceptable for URLs, or whether opaque refs are required.

### 6.4 CORS

CORS is enabled **for local demo only** with an explicit origin allowlist:

| Setting | Value |
|---|---|
| `allow_origins` | `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:4173` |
| `allow_credentials` | `False` |
| `allow_methods` | `GET`, `POST` |
| `allow_headers` | `Content-Type` |

- No wildcard origins (`*`) and no production origins are configured.
- `localhost` and `127.0.0.1` are distinct browser origins; both local dev origins are listed intentionally.
- CORS is a browser convenience, **not authentication or API protection**. Non-browser clients can still call the API directly.
- This setting does **not** change server binding. Run locally on `127.0.0.1`; do not use `0.0.0.0`.
- Production origins remain unresolved and require a separate approved decision before deployment.

---

## 7. Confirmed ML–Backend decisions

The previously open ML items are now confirmed and implemented in section 4.6.

| # | Decision | Confirmed behavior |
|---|---|---|
| 1 | Input features, order, and JSON names | The exact 20 fields and order in section 4.6, under a single `features` object. |
| 2 | Feature types and nullability | Integers, non-negative numbers, and three binary `0`/`1` integers; `user_prior_purchase_sessions` accepts integer or integer-valued float counts. `null` accepted only for the four price/ratio fields and converted to `NaN` internally. Strings, booleans, negative numbers, and non-finite numbers are rejected. |
| 3 | Preprocessing ownership | Entirely inside the artifact: `SimpleImputer(strategy="median") -> FunctionTransformer(np.log1p) -> StandardScaler() -> LogisticRegression()`. The Backend does not preprocess; it builds the DataFrame, converts all 20 values to float, and converts allowed `null` to `NaN`. |
| 4 | Target label | Binary class `1` means purchase after first cart; classes are read from `model.classes_`. Decision class `1` means purchase predicted / higher purchase likelihood; class `0` means potential abandonment risk, not confirmed abandonment. |
| 5 | Output format | `{"model_score": <number>, "predicted_class": 0|1}`. |
| 6 | Score meaning | `model_score` is the raw uncalibrated class-1 `predict_proba()` value: a Model Score, not a guaranteed or calibrated probability. |
| 7 | Input style | Raw named feature values only; no public session reference is accepted. Inference input is a single-row DataFrame matched exactly to `model.feature_names_in_`. |
| 8 | Artifact and loading | `backend/models/model.joblib`, loaded lazily and cached; path derived from the backend source file, not the process working directory. |
| 9 | Model version in responses | Not required; none is returned. |
| 10 | Invalid values and out-of-range features | Strict `422` validation; no filling, coercion, reordering, or dropping. Model/artifact failures return generic `503`. |
| 11 | Prediction threshold | `DEALMIND_PREDICTION_THRESHOLD`, default `0.12672868322902756`, finite `[0, 1]`, **PROVISIONAL — Role 5 baseline demo threshold selected on validation using best F1 and not the final approved threshold**; Role 6 may replace the baseline model and threshold after comparison/evaluation. `predicted_class = 1` when `model_score >= threshold`. |

If the artifact is not yet delivered, `/api/predict` returns `{"detail": "Model Pending/Unavailable"}` with `503`; all other endpoints remain available.

---

## 8. Verification against implementation and tests

The examples and rules above were compared with:

- `backend/main.py`: response models, SQL column allowlists, `public_session()`, exception handlers, `FEATURE_COLUMNS`, strict Pydantic validation, the cached model loader, and prediction output checks.
- `backend/tests/test_api.py`: exact field sets, pagination, `422`/`404` cases, protection assertions, prediction `422`/`503` cases, safe-phase Detail filtering, complement Outcome events, partition invariants, `rs_001`/`rs_002` regressions, and conditional `same_second_other` policy.
- `backend/tests/test_readonly.py`: `PRAGMA query_only == 1` and no SQLite sidecar files.
- `README.md` and `data/processed/dataset_prep_summary.json`: dataset rules, valid-session counts, and summary values.
- `scripts/02_session_and_duplicate_audit.py` and `scripts/03_build_master_datasets.py`: rate formulas, `day_of_week_utc` generation, event-phase labels, and replay-row curation rules.
- Direct read-only `TestClient` checks of success bodies and validation/error bodies; DB size and mtime were unchanged and no SQLite sidecar files were created.

### Mismatches found
Initial verification found **four documentation-only mismatches**, all corrected in this file:

1. `overall_purchase_rate_pct` described purchase events instead of purchase sessions.
2. The summary `422` example abbreviated `msg` and omitted `ctx`.
3. The pagination `422` example used `input: 0` and an abbreviated `msg`; the actual response uses string input `"0"` and the full message.
4. `day_of_week_utc` was marked unresolved although the build script defines `EXTRACT(DOW ...)` and DB values confirm `0`=Sunday … `6`=Saturday.

No production-code or test mismatch remains: success examples, status codes, protected fields, and corrected error bodies match the current implementation, tests, and read-only responses.

### Reveal isolation verification

- Detail now uses the explicit safe-phase allowlist plus `event_type <> "purchase"`; Outcome uses `NOT (...)` of the same predicate and returns the exact complement.
- `OutcomeOut` requires `actual_outcome` and `events`; `events` items reference `ReplayEventOut`.
- Full suite executed with the repository virtualenv: **34 passed, 1 warning**.
- All seven API routes remain registered; no routes were added or removed.
- OpenAPI `200` schema for `/api/replay-sessions/{id}/outcome` is `$ref: #/components/schemas/OutcomeOut` with required `actual_outcome` and `events`.
- DB size `7544832` bytes and `mtime_ns` `1795618575314826500` are unchanged from the pre-change baseline; no SQLite sidecars, `__pycache__`, `.pytest_cache`, or `.pyc` artifacts were created.
- Backend files are in a mixed staged/unstaged state; staged entries remain intact, unstaged changes exist in four files, and the ML artifact remains untracked.

### CORS verification

- `CORSMiddleware` is registered with exactly `http://localhost:5173`, `http://127.0.0.1:5173`, and `http://localhost:4173`; `allow_credentials=False`, `allow_methods=["GET", "POST"]`, `allow_headers=["Content-Type"]`.
- Tests cover allowed-origin GET responses, GET/POST preflights, three disallowed origins, absence of wildcard origin and credentials headers, and unchanged endpoint behavior including `422` from `/api/predict`.
- Full suite executed with the repository virtualenv: **50 passed, 1 warning**.
- No server was started; DB size/mtime are unchanged and no SQLite sidecars or caches were created.
- Four files currently have unstaged changes from their pre-change baselines; staged entries remain intact.

### AOV verification

- `SUMMARY_FIELDS` and `SummaryOut` now include `historical_aov_pos` and `historical_aov_signed`; the same `period`-based `SELECT` reads both columns from `funnel_summary`. No value is hard-coded and no AOV is recomputed.
- Tests read the actual DB row for `ALL` and all five months, assert exact equality with the API response, assert period-dependent values differ, and assert the original eight fields remain present and unchanged.
- Tests also confirm pagination, Session Replay, CORS, and `/api/predict` (`422`) are unaffected, and that `PRAGMA query_only` is still enabled.
- Full suite executed with the repository virtualenv at that stage: **61 passed, 1 warning**.
- The cart behavior report endpoint documented in section 4.7 was added later; see the verification below.

### Cart behavior report verification

- Actual merged report path: `reports/cart_analysis/cart_behavior_summary.json`. `meta.source_file = "intent_train.parquet"` and all four `meta.notes` entries were inspected; none contains a filesystem path. A scan of all 122 string values found no drive letters, UNC paths, Unix home paths, `file://` URLs, or backslashes.
- `GET /api/reports/cart-behavior` returns the parsed report object with no wrapper, no cache, and no path field. The four documented top-level sections are required; additive sections are passed through after recursive validation. Missing file maps to the generic `404`; malformed JSON, unreadable path, unsafe content, or unexpected structure maps to the generic `500`.
- Recursive validation rejects embedded local paths in string keys and values, including Unix, Windows drive, UNC, and `file://` forms; ordinary descriptive text with slashes remains valid. Report logs emit an error record with the exception type only, never the resolved path or a traceback.
- Tests cover full equality with the source JSON, exact nested key sets and array lengths, representative values read from the report, additive pass-through, dynamic loading from a temp copy, CWD independence, missing file, malformed JSON, three unexpected structures, embedded-path regressions, directory read failure, `caplog` assertions, endpoint-specific CORS, read-only guards, and unchanged existing endpoints.
- Global autouse fixture now checks only the database; report hash/size/mtime checks are scoped to report tests, so the original endpoint tests do not require the merged report file.
- Full suite executed with the repository virtualenv: **82 passed, 1 warning**.
- Report SHA256 `03e588e98d12765447dd0f4fa37f9b4ae3fe6556004e7b13aac450a602af603a`, size `20596`, and `mtime_ns` `1795630743456359600` unchanged. DB size `7544832`, `mtime_ns` `1795618575314826500`, and SHA256 `aa4f5076ce40c8893de604cfc999c8b8fb00335359213d814c7018cea0ab1052` unchanged. No sidecars, `__pycache__`, `.pytest_cache`, or `.pyc` artifacts were created.
- No Role 3 or Role 6 report was assumed or implemented.

### Prediction integration verification

- `POST /api/predict` implements the confirmed 20-feature contract; the `501` placeholder was removed. All seven routes remain registered and no other endpoint behavior changed.
- Input validation is strict and closed: missing/extra keys, wrong types, `null` outside the four allowed fields, negative numbers, JSON booleans, non-finite numbers, and non-binary binary values all return `422`. A `RequestValidationError` handler keeps non-finite rejected inputs from breaking FastAPI's JSON error serializer.
- The four nullable price/ratio fields accept JSON `null` and are converted to `float("nan")` only at the model-input boundary; the Backend does not impute, calculate medians, or otherwise preprocess.
- Inference input is a single-row pandas DataFrame. `model.feature_names_in_` must match the agreed 20 fields in the exact order; a mismatch or missing attribute returns generic `503` and is never silently reordered.
- Model loading is lazy and cached (`lru_cache(maxsize=1)`); a counting fake loader confirmed one load across two requests. `joblib` and `pandas` are imported lazily, and the artifact path is derived from `backend/main.py`, not the process working directory.
- Tests use in-memory fake estimators/joblib/pandas only: nullable fields, non-nullable null rejection, every missing feature, extra keys, negative values, infinity/non-finite values, binary `0`/`1`, booleans, decimal values, `user_prior_purchase_sessions` integer-valued float validation, all-float DataFrame conversion, DataFrame columns/order, threshold default/override/boundary and invalid configuration, feature-contract mismatches, missing feature names, missing `pandas`, missing artifact, load failure, `predict_proba` failure, reversed `classes_`, invalid outputs, safe generic errors, no reload, class-1 score extraction, and existing-endpoint regressions. No real or fake model artifact was created or required by the unit suite.
- Loading/inference errors and invalid outputs return `{"detail": "Model Pending/Unavailable"}` with `503`; no paths, exception text, or tracebacks are exposed to clients.
- Full suite executed with the repository virtualenv: **263 passed, 1 warning**.
- Runtime requirements remain pinned to the ML-confirmed versions: `scikit-learn==1.6.1`, `joblib==1.4.2`, `numpy==2.2.5`, and `pandas==2.2.3`; dev requirements and existing backend dependencies are unchanged. The project virtualenv was not modified.
- No server was started. DB size `7544832`, `mtime_ns` `1795618575314826500`, and SHA256 `aa4f5076ce40c8893de604cfc999c8b8fb00335359213d814c7018cea0ab1052` are unchanged. Report size `20596`, `mtime_ns` `1795630743456359600`, and SHA256 `03e588e98d12765447dd0f4fa37f9b4ae3fe6556004e7b13aac450a602af603a` are unchanged. No sidecars, `__pycache__`, `.pytest_cache`, or `.pyc` artifacts were created.

### Explicitly unresolved — not mismatches
- Frontend-required fields; production CORS origins (the three local demo origins are already configured).
- Filtering/sorting requirements.
- Whether Frontend renders `day_of_week_utc` as weekday names (the mapping itself is documented above).
- Model version identifier in responses (not required by the confirmed contract).
- Currency/unit definition for price-like fields.

This contract is an accurate snapshot of the current API. Only Frontend presentation and local deployment details remain unresolved; the ML–Backend prediction contract is confirmed and implemented.
