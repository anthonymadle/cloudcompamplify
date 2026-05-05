"""
Fetches new check-ins from the ABC Financial API and upserts into RDS.
Run this periodically (daily or hourly) to keep the database current.

Endpoint: GET /{clubId}/clubs/checkins/details
Auth:     app_id / app_key headers
Param:    checkInTimestampRange = "YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS"

Usage:
    py sync_checkins.py
"""

import os
import time
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("ABC_BASE_URL", "https://api.abcfinancial.com/rest")
CLUB_ID  = os.environ["ABC_CLUB_ID"]

HEADERS = {
    "app_id":  os.environ["ABC_APP_ID"],
    "app_key": os.environ["ABC_APP_KEY"],
    "Accept":  "application/json",
}

DB_CONFIG = {
    "host":     os.environ["DB_HOST"],
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ["DB_NAME"],
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
}

PAGE_SIZE = 100


def get_last_sync_datetime(conn) -> datetime:
    cur = conn.cursor()
    cur.execute("SELECT MAX(checkin_datetime) FROM check_ins;")
    result = cur.fetchone()[0]
    cur.close()
    return result if result else datetime.now() - timedelta(days=365)


def fetch_page(start_dt: datetime, end_dt: datetime, page: int) -> dict:
    ts_range = f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')},{end_dt.strftime('%Y-%m-%d %H:%M:%S')}"
    params = {
        "page":                  page,
        "size":                  PAGE_SIZE,
        "checkInTimestampRange": ts_range,
    }
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                f"{BASE_URL}/{CLUB_ID}/clubs/checkins/details",
                headers=HEADERS,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == 3:
                raise
            wait = attempt * 5
            print(f"\n  Connection error (attempt {attempt}/3), retrying in {wait}s: {e}")
            time.sleep(wait)


def map_checkin(raw: dict):
    """
    Map an API check-in record to DB columns.
    The check-in endpoint returns memberId but not name/gender — those fields
    are left empty. The crowd meter only needs checkin_datetime to calculate
    occupancy, so this is sufficient.
    """
    try:
        checkin_datetime = datetime.strptime(
            raw["checkInTimestamp"][:19], "%Y-%m-%d %H:%M:%S"
        )
    except (KeyError, ValueError):
        return None

    agreement_number = raw.get("member", {}).get("memberId", "")
    member_name      = ""
    gender           = ""

    return (agreement_number, member_name, checkin_datetime, gender)


def reconnect() -> psycopg2.extensions.connection:
    """Open a fresh DB connection using DB_CONFIG."""
    return psycopg2.connect(**DB_CONFIG)


def insert_checkins(conn, records: list) -> tuple:
    """Insert only records not already in the DB (by memberId + timestamp).
    Returns (inserted_count, conn) — conn may be a new object if reconnection occurred."""
    for attempt in range(1, 4):
        try:
            cur = conn.cursor()
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO check_ins (agreement_number, member_name, checkin_datetime, gender)
                SELECT v.agreement_number, v.member_name, v.checkin_datetime::timestamp, v.gender
                FROM (VALUES %s) AS v(agreement_number, member_name, checkin_datetime, gender)
                WHERE NOT EXISTS (
                    SELECT 1 FROM check_ins c
                    WHERE c.agreement_number = v.agreement_number
                      AND c.checkin_datetime = v.checkin_datetime::timestamp
                )
                """,
                records,
            )
            inserted = cur.rowcount
            conn.commit()
            cur.close()
            return inserted, conn
        except psycopg2.OperationalError as e:
            if attempt == 3:
                raise
            print(f"\n  DB connection lost (attempt {attempt}/3), reconnecting: {e}")
            time.sleep(5)
            try:
                conn.close()
            except Exception:
                pass
            conn = reconnect()


def month_chunks(start_dt: datetime, end_dt: datetime):
    """Yield (chunk_start, chunk_end) pairs one month at a time."""
    current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current < end_dt:
        # Last moment of the current month
        if current.month == 12:
            next_month = current.replace(year=current.year + 1, month=1)
        else:
            next_month = current.replace(month=current.month + 1)
        chunk_end = min(next_month - timedelta(seconds=1), end_dt)
        yield current, chunk_end
        current = next_month


def sync_range(conn, start_dt: datetime, end_dt: datetime):
    total_fetched  = 0
    total_inserted = 0

    for chunk_start, chunk_end in month_chunks(start_dt, end_dt):
        print(f"\n  [{chunk_start:%Y-%m}] ", end="", flush=True)
        page = 1

        while True:
            print(f"p{page} ", end="", flush=True)

            try:
                data = fetch_page(chunk_start, chunk_end, page)
            except requests.HTTPError as e:
                print(f"\n  API error: {e}\n  {e.response.text[:200]}")
                break

            checkins = data.get("checkins") or []
            if not checkins:
                print("done.")
                break

            records = [r for raw in checkins if (r := map_checkin(raw)) is not None]
            if records:
                inserted, conn = insert_checkins(conn, records)
            else:
                inserted = 0

            total_fetched  += len(checkins)
            total_inserted += inserted

            next_page = data.get("status", {}).get("nextPage")
            if not next_page:
                print(f"done. ({inserted} new)")
                break

            page = int(next_page)
            time.sleep(0.3)

    return total_fetched, total_inserted, conn


def main():
    import sys
    conn = psycopg2.connect(**DB_CONFIG)

    if len(sys.argv) > 1:
        start_dt = datetime.strptime(sys.argv[1], "%Y-%m-%d")
        print(f"Using custom start date: {start_dt:%Y-%m-%d}")
    else:
        last_sync = get_last_sync_datetime(conn)
        start_dt  = last_sync - timedelta(hours=1)

    end_dt = datetime.now()
    print(f"Syncing check-ins from {start_dt:%Y-%m-%d} to {end_dt:%Y-%m-%d} ...")

    total_fetched, total_inserted, conn = sync_range(conn, start_dt, end_dt)

    conn.close()
    print(f"\nSync complete — {total_fetched:,} fetched, {total_inserted:,} new rows inserted.")


if __name__ == "__main__":
    main()
