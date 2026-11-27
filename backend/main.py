from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dealmind.db"
REPORT_PATH = (
    PROJECT_ROOT / "reports" / "cart_analysis" / "cart_behavior_summary.json"
)
REQUIRED_REPORT_SECTIONS = (
    "meta",
    "pre_cart_behavior",
    "catalog_and_brands",
    "price_band_cart_behavior",
)

BACKEND_DIR = Path(__file__).resolve().parent
MODEL_PATH = BACKEND_DIR / "models" / "model.joblib"
MODEL_UNAVAILABLE_DETAIL = "Model Pending/Unavailable"

PREDICTION_THRESHOLD_ENV = "DEALMIND_PREDICTION_THRESHOLD"
# PROVISIONAL — Role 5 baseline demo threshold selected on validation using
# best F1. It is not a final approved threshold; Role 6 may replace the baseline
# model and threshold after comparison/evaluation.
DEFAULT_PREDICTION_THRESHOLD = 0.12672868322902756


def _parse_prediction_threshold(
    raw_value: str | float, *, env_name: str = PREDICTION_THRESHOLD_ENV
) -> float:
    """Validate a configured prediction threshold at configuration time."""
    if isinstance(raw_value, bool):
        raise RuntimeError(f"{env_name} must be a finite number in [0, 1]")
    try:
        threshold = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{env_name} must be a finite number in [0, 1]") from exc
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise RuntimeError(f"{env_name} must be a finite number in [0, 1]")
    return threshold


def _load_prediction_threshold() -> float:
    """Read the provisional threshold override from the environment."""
    raw_value = os.getenv(PREDICTION_THRESHOLD_ENV)
    if raw_value is None:
        return DEFAULT_PREDICTION_THRESHOLD
    return _parse_prediction_threshold(raw_value)


PREDICTION_THRESHOLD = _load_prediction_threshold()

# Exact model input schema and order agreed with the ML role. The trained
# pipeline owns imputation and scaling; the API validates and forwards numeric
# values, converting all 20 fields to float at the model-input boundary.
FEATURE_COLUMNS = (
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
)
BINARY_FEATURE_COLUMNS = frozenset(
    {
        "has_view_before_cart",
        "has_multi_products_at_first_cart_sec",
        "any_cart_brand_at_first_cart_sec",
    }
)
REAL_FEATURE_COLUMNS = frozenset(
    {
        "avg_cart_price_at_first_cart_sec",
        "avg_viewed_price_before_cart",
        "max_viewed_price_before_cart",
        "price_ratio_cart_to_view",
    }
)
# The sklearn pipeline owns imputation; only these four fields may arrive as
# JSON null, which the API converts to NaN before building the model frame.
NULLABLE_FEATURE_COLUMNS = frozenset(
    {
        "avg_cart_price_at_first_cart_sec",
        "avg_viewed_price_before_cart",
        "max_viewed_price_before_cart",
        "price_ratio_cart_to_view",
    }
)

# Embedded, not just leading, so descriptive text cannot hide a local path.
LOCAL_PATH_PATTERNS = (
    re.compile(r"\\"),  # backslash separators, including UNC paths
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"),  # C:\... or C:/...
    re.compile(r"file://", re.IGNORECASE),
    re.compile(r"/(?:home|Users|mnt|var|tmp|etc|opt|usr|srv)/"),
)

logger = logging.getLogger(__name__)

Period = Literal["ALL", "2019-10", "2019-11", "2019-12", "2020-01", "2020-02"]

SUMMARY_FIELDS = (
    "period",
    "total_valid_sessions",
    "sessions_with_view",
    "sessions_with_cart",
    "sessions_with_purchase",
    "overall_purchase_rate_pct",
    "view_to_purchase_rate_pct",
    "session_cart_abandonment_rate_pct",
    "historical_aov_pos",
    "historical_aov_signed",
)
SUMMARY_COLUMNS_SQL = ", ".join(SUMMARY_FIELDS)

EVENT_FIELDS = (
    "id",
    "event_time",
    "event_type",
    "product_id",
    "category_id",
    "category_code",
    "brand",
    "price",
    "event_phase",
)
EVENT_COLUMNS_SQL = ", ".join(EVENT_FIELDS)

# Session Details may reveal only the pre-outcome timeline. Outcome exposes the
# exact complement, so no event can disappear if a new phase appears later.
SAFE_DETAIL_EVENT_PHASES = (
    "before_first_cart",
    "at_first_cart_second",
    "same_second_other",
)
SAFE_DETAIL_EVENT_PHASES_SQL = ", ".join("?" for _ in SAFE_DETAIL_EVENT_PHASES)
DETAIL_EVENT_FILTER_SQL = (
    f"(event_phase IN ({SAFE_DETAIL_EVENT_PHASES_SQL}) AND event_type <> 'purchase')"
)
OUTCOME_EVENT_FILTER_SQL = f"NOT {DETAIL_EVENT_FILTER_SQL}"

# Explicit allowlist for replay-session queries. `user_session` is selected only
# for internal row mapping and is removed from every response by public_session().
SESSION_FIELDS = (
    "user_session",
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
)
SESSION_COLUMNS_SQL = ", ".join(SESSION_FIELDS)

EXCLUDED_SESSION_FIELDS = {
    "user_id",
    "user_session",
    "target_purchased_after_cart",
}

app = FastAPI(title="DealMind AI API", version="0.1.0")

# Local-demo browser convenience only. This is not authentication or API
# protection; it does not change server binding or allow any production origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@contextmanager
def read_db() -> Iterator[sqlite3.Connection]:
    """Open the project database strictly in read-only mode."""
    connection = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


@lru_cache(maxsize=1)
def session_refs() -> dict[str, str]:
    """Map stable public refs (rs_001...) to internal session keys."""
    with read_db() as connection:
        rows = connection.execute(
            "SELECT user_session FROM replay_sessions ORDER BY user_session"
        ).fetchall()

    return {
        f"rs_{index:03d}": row["user_session"]
        for index, row in enumerate(rows, start=1)
    }


def public_session(row: sqlite3.Row, ref: str) -> dict[str, Any]:
    """Build a response payload without identifiers or the actual label."""
    payload = dict(row)
    for field in EXCLUDED_SESSION_FIELDS:
        payload.pop(field, None)
    payload["id"] = ref
    return payload


def _validate_report_content(value: Any) -> None:
    """Reject unsafe or non-JSON content anywhere in the report tree."""
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in LOCAL_PATH_PATTERNS):
            raise ValueError("local filesystem path in report content")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("non-string key in report content")
            _validate_report_content(key)
            _validate_report_content(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_report_content(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite number in report content")
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValueError("unsupported value in report content")


def read_cart_behavior_report() -> dict[str, Any]:
    """Load, validate, and return the merged cart behavior report on each request.

    The path is derived from PROJECT_ROOT (based on this file), not the process
    working directory. All top-level sections from the file are returned; the
    four documented ones are required. Content is recursively validated before
    it can reach a client.
    """
    try:
        with REPORT_PATH.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
        _validate_report_content(report)
    except FileNotFoundError as exc:
        logger.warning("Cart behavior report is unavailable")
        raise HTTPException(status_code=404, detail="Resource not found") from exc
    except (OSError, ValueError) as exc:
        # Log only the exception type: server logs should not carry local paths.
        logger.error("Unable to use cart behavior report (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    if not isinstance(report, dict) or not all(
        isinstance(report.get(section), dict) for section in REQUIRED_REPORT_SECTIONS
    ):
        logger.error("Cart behavior report has an unexpected structure")
        raise HTTPException(status_code=500, detail="Internal server error")

    return dict(report)


class HealthOut(BaseModel):
    status: str


class SummaryOut(BaseModel):
    period: str
    total_valid_sessions: int
    sessions_with_view: int
    sessions_with_cart: int
    sessions_with_purchase: int
    overall_purchase_rate_pct: float
    view_to_purchase_rate_pct: float
    session_cart_abandonment_rate_pct: float
    historical_aov_pos: float
    historical_aov_signed: float


class ReplaySessionOut(BaseModel):
    id: str
    session_start: str
    first_cart_time: str
    cart_product_ids_at_first_cart_sec: str
    cart_category_ids_at_first_cart_sec: str
    seconds_to_first_cart: int
    views_before_cart: int
    has_view_before_cart: int
    unique_products_viewed_before_cart: int
    unique_categories_viewed_before_cart: int
    unique_brands_viewed_before_cart: int
    removes_before_cart: int
    unique_products_removed_before_cart: int
    cart_events_at_first_cart_sec: int
    unique_products_carted_at_first_cart_sec: int
    has_multi_products_at_first_cart_sec: int
    avg_cart_price_at_first_cart_sec: float | None = None
    avg_viewed_price_before_cart: float | None = None
    max_viewed_price_before_cart: float | None = None
    price_ratio_cart_to_view: float | None = None
    any_cart_brand_at_first_cart_sec: int
    hour_of_day_utc: int
    day_of_week_utc: int
    user_prior_sessions: int
    user_prior_purchase_sessions: int


class ReplayEventOut(BaseModel):
    id: int
    event_time: str
    event_type: str
    product_id: str
    category_id: str
    category_code: str | None = None
    brand: str | None = None
    price: float
    event_phase: str


class ReplaySessionListOut(BaseModel):
    items: list[ReplaySessionOut]
    page: int
    size: int
    total: int


class ReplaySessionDetailOut(BaseModel):
    session: ReplaySessionOut
    events: list[ReplayEventOut]


class OutcomeOut(BaseModel):
    actual_outcome: int
    events: list[ReplayEventOut]


class FeatureValues(BaseModel):
    """Strict, closed schema for the 20 model inputs. No filling or coercion."""

    model_config = ConfigDict(extra="forbid")

    seconds_to_first_cart: StrictInt
    views_before_cart: StrictInt
    has_view_before_cart: StrictInt
    unique_products_viewed_before_cart: StrictInt
    unique_categories_viewed_before_cart: StrictInt
    unique_brands_viewed_before_cart: StrictInt
    removes_before_cart: StrictInt
    unique_products_removed_before_cart: StrictInt
    cart_events_at_first_cart_sec: StrictInt
    unique_products_carted_at_first_cart_sec: StrictInt
    has_multi_products_at_first_cart_sec: StrictInt
    avg_cart_price_at_first_cart_sec: StrictInt | StrictFloat | None
    avg_viewed_price_before_cart: StrictInt | StrictFloat | None
    max_viewed_price_before_cart: StrictInt | StrictFloat | None
    price_ratio_cart_to_view: StrictInt | StrictFloat | None
    any_cart_brand_at_first_cart_sec: StrictInt
    hour_of_day_utc: StrictInt
    day_of_week_utc: StrictInt
    user_prior_sessions: StrictInt
    user_prior_purchase_sessions: StrictInt | StrictFloat

    @field_validator(*sorted(REAL_FEATURE_COLUMNS))
    @classmethod
    def _finite_number(cls, value: int | float | None) -> int | float | None:
        if value is None:
            return value
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("feature value must be finite")
        return value

    @field_validator(*sorted(FEATURE_COLUMNS))
    @classmethod
    def _non_negative(cls, value: int | float | None) -> int | float | None:
        if value is None:
            return value
        if isinstance(value, bool) or value < 0:
            raise ValueError("feature value must be non-negative")
        return value

    @field_validator("user_prior_purchase_sessions")
    @classmethod
    def _integer_valued_count(cls, value: int | float) -> int:
        if isinstance(value, bool):
            raise ValueError("count must not be a boolean")
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("count must be finite")
            if not value.is_integer():
                raise ValueError("count must be an integer value")
            return int(value)
        return value

    @field_validator(*sorted(BINARY_FEATURE_COLUMNS))
    @classmethod
    def _binary_value(cls, value: int) -> int:
        if isinstance(value, bool) or value not in (0, 1):
            raise ValueError("binary feature must be 0 or 1")
        return value


class PredictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    features: FeatureValues


class PredictOut(BaseModel):
    model_score: float
    predicted_class: int


def _model_unavailable(exc: BaseException | None = None) -> HTTPException:
    if exc is not None:
        logger.error("Prediction failed (%s)", type(exc).__name__)
    return HTTPException(status_code=503, detail=MODEL_UNAVAILABLE_DETAIL)


def _import_joblib() -> Any:
    """Import joblib lazily so the rest of the API works without ML extras."""
    try:
        import joblib
    except Exception as exc:
        logger.error("Prediction dependency unavailable (%s)", type(exc).__name__)
        raise _model_unavailable(exc) from exc
    return joblib


def _import_pandas() -> Any:
    """Import pandas lazily so non-prediction endpoints need no ML extras."""
    try:
        import pandas
    except Exception as exc:
        logger.error("Prediction dependency unavailable (%s)", type(exc).__name__)
        raise _model_unavailable(exc) from exc
    return pandas


@lru_cache(maxsize=1)
def load_model() -> Any:
    """Load and cache the full pipeline once, on first prediction request."""
    if not MODEL_PATH.is_file():
        logger.warning("Prediction model artifact is unavailable")
        raise _model_unavailable()

    try:
        joblib = _import_joblib()
        return joblib.load(MODEL_PATH)
    except HTTPException:
        raise
    except Exception as exc:
        raise _model_unavailable(exc) from exc


def _validate_model_feature_contract(model: Any) -> None:
    """Refuse a model whose feature names or order differ from the contract."""
    try:
        expected = list(model.feature_names_in_)
    except Exception as exc:
        raise _model_unavailable(exc) from exc
    if expected != list(FEATURE_COLUMNS):
        raise _model_unavailable()


def _build_model_frame(features: FeatureValues) -> Any:
    """Build the single-row DataFrame expected by the trained pipeline."""
    try:
        pandas = _import_pandas()
    except HTTPException:
        raise
    except Exception as exc:
        raise _model_unavailable(exc) from exc
    columns = list(FEATURE_COLUMNS)
    try:
        values = [
            float("nan") if getattr(features, name) is None else float(getattr(features, name))
            for name in columns
        ]
        frame = pandas.DataFrame([values], columns=columns)
        if list(frame.columns) != columns:
            raise ValueError("unexpected model frame columns")
    except HTTPException:
        raise
    except Exception as exc:
        raise _model_unavailable(exc) from exc
    return frame


def _predict_with_model(model: Any, features: FeatureValues) -> dict[str, Any]:
    """Score one row with the pipeline and validate the returned output."""
    _validate_model_feature_contract(model)
    frame = _build_model_frame(features)
    try:
        probabilities = model.predict_proba(frame)
        class_values = list(model.classes_)
    except Exception as exc:
        raise _model_unavailable(exc) from exc

    try:
        rows = [list(values) for values in probabilities]
        if len(rows) != 1:
            raise ValueError("unexpected number of prediction rows")
        scores = [float(value) for value in rows[0]]
        classes = [int(value) for value in class_values]
    except Exception as exc:
        raise _model_unavailable(exc) from exc

    if len(classes) != 2 or set(classes) != {0, 1}:
        raise _model_unavailable()
    if len(scores) != len(classes):
        raise _model_unavailable()
    if not all(math.isfinite(score) and 0.0 <= score <= 1.0 for score in scores):
        raise _model_unavailable()

    model_score = scores[classes.index(1)]
    # Class 1 means purchase predicted / higher purchase likelihood; class 0
    # means potential abandonment risk, not confirmed abandonment.
    predicted_class = 1 if model_score >= PREDICTION_THRESHOLD else 0

    if predicted_class not in (0, 1) or not math.isfinite(model_score):
        raise _model_unavailable()
    if not 0.0 <= model_score <= 1.0:
        raise _model_unavailable()

    return {"model_score": model_score, "predicted_class": predicted_class}


def _json_safe_error_value(value: Any) -> Any:
    """Keep non-finite rejected inputs from breaking JSON error responses."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe_error_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_error_value(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = _json_safe_error_value(exc.errors())
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = "Resource not found" if exc.status_code == 404 else exc.detail
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health", response_model=HealthOut)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary", response_model=SummaryOut)
def summary(period: Period = "ALL") -> dict[str, Any]:
    with read_db() as connection:
        row = connection.execute(
            f"SELECT {SUMMARY_COLUMNS_SQL} FROM funnel_summary WHERE period = ?",
            (period,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return dict(row)


@app.get("/api/reports/cart-behavior")
def cart_behavior_report() -> dict[str, Any]:
    """Return the actual Role 4 cart behavior report for the Dashboard."""
    return read_cart_behavior_report()


@app.get("/api/replay-sessions", response_model=ReplaySessionListOut)
def replay_sessions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    ref_to_session = session_refs()
    total = len(ref_to_session)
    start = (page - 1) * size
    selected = [
        (f"rs_{index:03d}", ref_to_session[f"rs_{index:03d}"])
        for index in range(start + 1, min(start + size, total) + 1)
    ]
    selected_sessions = [session for _, session in selected]

    rows_by_session: dict[str, sqlite3.Row] = {}
    if selected_sessions:
        placeholders = ", ".join("?" for _ in selected_sessions)
        with read_db() as connection:
            rows = connection.execute(
                f"SELECT {SESSION_COLUMNS_SQL} FROM replay_sessions "
                f"WHERE user_session IN ({placeholders})",
                selected_sessions,
            ).fetchall()
        rows_by_session = {row["user_session"]: row for row in rows}

    items = [
        public_session(rows_by_session[session], ref)
        for ref, session in selected
        if session in rows_by_session
    ]
    return {"items": items, "page": page, "size": size, "total": total}


@app.get("/api/replay-sessions/{id}/outcome", response_model=OutcomeOut)
def replay_session_outcome(id: str) -> dict[str, Any]:
    ref_to_session = session_refs()
    user_session = ref_to_session.get(id)
    if user_session is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    with read_db() as connection:
        row = connection.execute(
            "SELECT target_purchased_after_cart FROM replay_sessions WHERE user_session = ?",
            (user_session,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Resource not found")

        event_rows = connection.execute(
            f"SELECT {EVENT_COLUMNS_SQL} FROM replay_session_events "
            f"WHERE user_session = ? AND {OUTCOME_EVENT_FILTER_SQL} "
            "ORDER BY event_time, id",
            (user_session, *SAFE_DETAIL_EVENT_PHASES),
        ).fetchall()

    return {
        "actual_outcome": int(row["target_purchased_after_cart"]),
        "events": [dict(event) for event in event_rows],
    }


@app.get("/api/replay-sessions/{id}", response_model=ReplaySessionDetailOut)
def replay_session_detail(id: str) -> dict[str, Any]:
    ref_to_session = session_refs()
    user_session = ref_to_session.get(id)
    if user_session is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    with read_db() as connection:
        session_row = connection.execute(
            f"SELECT {SESSION_COLUMNS_SQL} FROM replay_sessions WHERE user_session = ?",
            (user_session,),
        ).fetchone()
        event_rows = connection.execute(
            f"SELECT {EVENT_COLUMNS_SQL} FROM replay_session_events "
            f"WHERE user_session = ? AND {DETAIL_EVENT_FILTER_SQL} "
            "ORDER BY event_time, id",
            (user_session, *SAFE_DETAIL_EVENT_PHASES),
        ).fetchall()

    if session_row is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    return {
        "session": public_session(session_row, id),
        "events": [dict(row) for row in event_rows],
    }


@app.post(
    "/api/predict",
    response_model=PredictOut,
    responses={
        422: {
            "description": "Invalid feature payload; no features were filled or coerced.",
        },
        503: {
            "description": "The trained model artifact is unavailable or unusable.",
            "content": {
                "application/json": {
                    "example": {"detail": MODEL_UNAVAILABLE_DETAIL}
                }
            },
        },
    },
)
def predict(payload: PredictIn) -> dict[str, Any]:
    """Score one row using the full pipeline stored in model.joblib."""
    model = load_model()
    return _predict_with_model(model, payload.features)
