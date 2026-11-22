# DealMind AI

E-commerce intelligence system built for the DEPI Graduation Project (`NHA-5-158`). The project focuses on session-level Purchase Intent Prediction, Market Basket Recommendations (FP-Growth), RFM Customer Segmentation, and an interactive demo storefront with analytics.

## Repository Structure

- `data/raw/` — Raw Kaggle CSVs (git-ignored, local only)
- `data/processed/` — Parquet datasets (git-ignored) + JSON audit reports (tracked)
- `data/dealmind.db` — Lightweight SQLite app database (7.2 MB, tracked)
- `scripts/01_audit_and_convert.py` — Chunked CSV-to-Parquet conversion and raw row-level audit
- `scripts/02_session_and_duplicate_audit.py` — DuckDB session-level funnel and duplicate audit
- `scripts/02b_inspect_anomalies.py` — Inspection of negative-price records and same-second first-cart events
- `scripts/03_build_master_datasets.py` — Builds leak-free intent datasets, purchase baskets, RFM table, and SQLite app DB

## Dataset & Preparation Rules

Source: **eCommerce Events History in Cosmetics Shop** (Oct 2019 – Feb 2020, 5 monthly files, 20,692,840 raw events).

Key data handling decisions (documented in `data/processed/*.json`):
- **Valid sessions:** Dropped rows with missing/empty `user_session` and excluded 272 multi-user session IDs, leaving 4,535,669 valid sessions.
- **Prices:** Retained all valid-session events regardless of price for behavioral funnel analysis and purchase targets. Applied `price > 0` strictly to price-based features, recommendation baskets, and RFM recorded spend. Negative-price purchase records are separated in the funnel summary (signed vs. positive-only totals) without assuming a business cause, and prices are treated as recorded source units without assuming a currency.
- **Leak-free intent features:** Pre-cart behavioral features use events strictly before the first cart second (`event_time < first_cart_time`). Events at `event_time = first_cart_time` are treated as a same-second snapshot. Multi-product first-cart sessions are flagged in modeling files and excluded from the 100 curated single-product test replay sessions in `data/dealmind.db`.
- **Temporal split (UTC):**
  - **Train:** Oct 2, 2019 – Dec 31, 2019 (590,754 cart sessions; 12.57% purchase after cart)
  - **Validation:** Jan 1, 2020 – Jan 31, 2020 (192,366 cart sessions; 13.12% purchase after cart)
  - **Test:** Feb 1, 2020 – Feb 28, 2020 (179,226 cart sessions; 12.39% purchase after cart)
  - Boundary sessions (first day, last day, cross-split) and 8 same-second purchase sessions are excluded.

## Team Setup (Getting the Data)

1. Clone this repository: `git clone https://github.com/nhahub/NHA-5-158.git`
2. Enter the folder: `cd NHA-5-158`
3. Download the Parquet files you need from the shared Google Drive folder (`DealMind_AI_Datasets/01_Modeling_Datasets/`) and place them inside `data/processed/`.
4. The SQLite database (`data/dealmind.db`) and audit reports (`data/processed/*.json`) are already included in this repo.