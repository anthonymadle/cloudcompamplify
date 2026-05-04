"""
Bulk-loads Check In History.csv into the RDS PostgreSQL check_ins table.
Uses PostgreSQL COPY for fast ingestion of ~800K rows.

Usage:
    pip install psycopg2-binary python-dotenv
    python load_csv_to_rds.py

Set these env vars (or create a .env file):
    DB_HOST     - RDS endpoint (e.g. mydb.xxxx.us-east-1.rds.amazonaws.com)
    DB_PORT     - 5432
    DB_NAME     - database name
    DB_USER     - master username
    DB_PASSWORD - master password
"""

import os
import csv
import io
import psycopg2
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CSV_FILE = Path(__file__).parent / "Check In History.csv"

DB_CONFIG = {
    "host":     os.environ["DB_HOST"],
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ["DB_NAME"],
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
}


def parse_datetime(raw: str) -> str:
    """Convert M/D/YYYY H:MM to a format PostgreSQL accepts."""
    dt = datetime.strptime(raw.strip(), "%m/%d/%Y %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def build_tsv_buffer(csv_path: Path) -> tuple[io.StringIO, int]:
    """Read CSV and return a tab-separated StringIO ready for COPY."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    count = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            agreement = row.get("agreement_number", "").strip()
            name      = row.get("member_name", "").strip()
            raw_dt    = row.get("checkin_datetime", "").strip()
            gender    = row.get("gender", "").strip()

            if not raw_dt:
                continue
            try:
                dt_str = parse_datetime(raw_dt)
            except ValueError:
                print(f"  Skipping unparseable date: {raw_dt!r}")
                continue

            writer.writerow([agreement, name, dt_str, gender])
            count += 1

    buf.seek(0)
    return buf, count


def main():
    print(f"Connecting to {DB_CONFIG['host']}:{DB_CONFIG['port']} / {DB_CONFIG['dbname']} ...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    print("Running schema.sql ...")
    schema_path = Path(__file__).parent / "schema.sql"
    cur.execute(schema_path.read_text())

    print(f"Reading {CSV_FILE} ...")
    buf, total = build_tsv_buffer(CSV_FILE)
    print(f"  Parsed {total:,} rows. Starting COPY ...")

    cur.copy_expert(
        """
        COPY check_ins (agreement_number, member_name, checkin_datetime, gender)
        FROM STDIN
        WITH (FORMAT text, DELIMITER E'\\t', NULL '')
        """,
        buf,
    )

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. {total:,} rows loaded into check_ins.")


if __name__ == "__main__":
    main()
