import json
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

MONTH_FILES = [
    "2019-Oct.csv",
    "2019-Nov.csv",
    "2019-Dec.csv",
    "2020-Jan.csv",
    "2020-Feb.csv",
]

CHUNK_SIZE = 500_000

EXPECTED_COLUMNS = [
    "event_time",
    "event_type",
    "product_id",
    "category_id",
    "category_code",
    "brand",
    "price",
    "user_id",
    "user_session",
]

PARQUET_SCHEMA = pa.schema([
    ("event_time", pa.timestamp("ns", tz="UTC")),
    ("event_type", pa.string()),
    ("product_id", pa.string()),
    ("category_id", pa.string()),
    ("category_code", pa.string()),
    ("brand", pa.string()),
    ("price", pa.float64()),
    ("user_id", pa.string()),
    ("user_session", pa.string()),
])


def convert_and_audit_raw():
    total_rows = 0
    event_counts = {}
    null_counts = {col: 0 for col in EXPECTED_COLUMNS}
    price_stats = {
        "negative": 0,
        "zero": 0,
        "negative_by_event_type": {},
        "zero_by_event_type": {},
        "min": None,
        "max": None,
    }
    monthly_summary = []

    for filename in MONTH_FILES:
        csv_path = RAW_DIR / filename
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing file: {csv_path}")

        out_path = PROCESSED_DIR / filename.replace(".csv", ".parquet")
        file_rows = 0
        min_time = None
        max_time = None
        invalid_time_rows = 0

        print(f"Converting {filename}...")

        writer = pq.ParquetWriter(out_path, PARQUET_SCHEMA, compression="snappy")

        try:
            reader = pd.read_csv(
                csv_path,
                chunksize=CHUNK_SIZE,
                dtype={
                    "event_time": "string",
                    "event_type": "string",
                    "product_id": "string",
                    "category_id": "string",
                    "category_code": "string",
                    "brand": "string",
                    "price": "float64",
                    "user_id": "string",
                    "user_session": "string",
                },
            )

            for chunk in reader:
                chunk = chunk[EXPECTED_COLUMNS]
                chunk_len = len(chunk)
                file_rows += chunk_len
                total_rows += chunk_len

                for col in EXPECTED_COLUMNS:
                    null_counts[col] += int(chunk[col].isna().sum())

                parsed_time = pd.to_datetime(
                    chunk["event_time"],
                    format="%Y-%m-%d %H:%M:%S UTC",
                    utc=True,
                    errors="coerce",
                )
                invalid_time_rows += int(parsed_time.isna().sum())
                chunk["event_time"] = parsed_time

                c_min = parsed_time.min()
                c_max = parsed_time.max()
                if pd.notna(c_min):
                    min_time = c_min if min_time is None else min(min_time, c_min)
                if pd.notna(c_max):
                    max_time = c_max if max_time is None else max(max_time, c_max)

                for ev, cnt in chunk["event_type"].value_counts(dropna=False).items():
                    key = str(ev)
                    event_counts[key] = event_counts.get(key, 0) + int(cnt)

                neg_mask = chunk["price"] < 0
                zero_mask = chunk["price"] == 0

                if neg_mask.any():
                    price_stats["negative"] += int(neg_mask.sum())
                    for ev, cnt in chunk.loc[neg_mask, "event_type"].value_counts(dropna=False).items():
                        key = str(ev)
                        price_stats["negative_by_event_type"][key] = (
                            price_stats["negative_by_event_type"].get(key, 0) + int(cnt)
                        )

                if zero_mask.any():
                    price_stats["zero"] += int(zero_mask.sum())
                    for ev, cnt in chunk.loc[zero_mask, "event_type"].value_counts(dropna=False).items():
                        key = str(ev)
                        price_stats["zero_by_event_type"][key] = (
                            price_stats["zero_by_event_type"].get(key, 0) + int(cnt)
                        )

                prices = chunk["price"].dropna()
                if len(prices) > 0:
                    c_pmin = float(prices.min())
                    c_pmax = float(prices.max())
                    price_stats["min"] = c_pmin if price_stats["min"] is None else min(price_stats["min"], c_pmin)
                    price_stats["max"] = c_pmax if price_stats["max"] is None else max(price_stats["max"], c_pmax)

                table = pa.Table.from_pandas(chunk, schema=PARQUET_SCHEMA, preserve_index=False)
                writer.write_table(table)
        finally:
            writer.close()

        size_mb = round(out_path.stat().st_size / (1024 * 1024), 2)
        monthly_summary.append({
            "file": filename,
            "rows": file_rows,
            "min_time": str(min_time),
            "max_time": str(max_time),
            "invalid_time_rows": invalid_time_rows,
            "parquet_size_mb": size_mb,
        })
        print(f"  Done: {file_rows:,} rows -> {out_path.name} ({size_mb} MB)")

    missing_values = {
        col: {
            "count": cnt,
            "pct": round((cnt / total_rows) * 100, 4) if total_rows else 0.0,
        }
        for col, cnt in null_counts.items()
    }

    report = {
        "scope": "Raw CSV-to-Parquet chunked conversion and row-level audit only (session & duplicate audits run separately).",
        "total_raw_rows": total_rows,
        "monthly_summary": monthly_summary,
        "event_type_counts": event_counts,
        "missing_values": missing_values,
        "price_audit": price_stats,
    }

    report_path = PROCESSED_DIR / "raw_audit_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n=== RAW CONVERSION & AUDIT COMPLETE ===")
    print(json.dumps(report, indent=2))
    print(f"\nSaved report to: {report_path}")


if __name__ == "__main__":
    convert_and_audit_raw()