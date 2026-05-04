import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DATA_DIR = PROJECT_ROOT / "src" / "data"
SRC_DATA_DIR.mkdir(parents=True, exist_ok=True)

CHECKIN_COL_CANDIDATES = [
    "Check In Date/Time",
    "Check In Datetime",
    "checkin_datetime",
    "check_in_datetime",
]

WINDOW_MINUTES = 90
SLOT_MINUTES = 30


def load_data():
    print("Connecting to RDS ...")
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df = pd.read_sql(
            "SELECT agreement_number, member_name, checkin_datetime, gender FROM check_ins",
            conn,
        )
    conn.close()
    print(f"Loaded {len(df):,} rows from RDS.")
    return df


def find_checkin_column(df: pd.DataFrame) -> str:
    for col in CHECKIN_COL_CANDIDATES:
        if col in df.columns:
            return col

    raise ValueError(
        "Could not find a check-in datetime column. "
        f"Found columns: {list(df.columns)}"
    )


def floor_to_half_hour(ts: pd.Timestamp) -> pd.Timestamp:
    minute = 0 if ts.minute < 30 else 30
    return ts.replace(minute=minute, second=0, microsecond=0)


def build_half_hour_occupancy(df: pd.DataFrame, dt_col: str) -> pd.DataFrame:
    df = df[[dt_col]].copy()
    df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
    df = df.dropna(subset=[dt_col]).sort_values(dt_col).reset_index(drop=True)

    if df.empty:
        raise ValueError("No valid check-in datetimes found after parsing.")

    start = floor_to_half_hour(df[dt_col].min())
    end = floor_to_half_hour(df[dt_col].max()) + pd.Timedelta(minutes=SLOT_MINUTES)

    slots = pd.date_range(start=start, end=end, freq=f"{SLOT_MINUTES}min")
    slot_df = pd.DataFrame({"slot": slots})

    starts = df[dt_col].apply(floor_to_half_hour)
    ends = df[dt_col] + pd.Timedelta(minutes=WINDOW_MINUTES)

    slot_index = {ts: i for i, ts in enumerate(slots)}
    occ = np.zeros(len(slots), dtype=np.int32)

    for s, e in zip(starts, ends):
        current = s
        while current < e:
            idx = slot_index.get(current)
            if idx is not None:
                occ[idx] += 1
            current += pd.Timedelta(minutes=SLOT_MINUTES)

    slot_df["occupancy"] = occ
    slot_df["date"] = slot_df["slot"].dt.date
    slot_df["time"] = slot_df["slot"].dt.strftime("%I:%M %p").str.lstrip("0")
    slot_df["hour"] = slot_df["slot"].dt.hour
    slot_df["minute"] = slot_df["slot"].dt.minute
    slot_df["weekday"] = slot_df["slot"].dt.day_name()

    return slot_df


def build_timeline(slot_df: pd.DataFrame):
    grouped = (
        slot_df.groupby(["hour", "minute", "time"], as_index=False)["occupancy"]
        .mean()
        .sort_values(["hour", "minute"])
    )
    grouped["value"] = grouped["occupancy"].round().astype(int)
    return grouped[["time", "value"]].to_dict(orient="records")


def build_weekly_pattern(slot_df: pd.DataFrame):
    target_hours = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
    heatmap_hours = ["12A", "2A", "4A", "6A", "8A", "10A", "12P", "2P", "4P", "6P", "8P", "10P"]

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday_short = {
        "Monday": "Mon",
        "Tuesday": "Tue",
        "Wednesday": "Wed",
        "Thursday": "Thu",
        "Friday": "Fri",
        "Saturday": "Sat",
        "Sunday": "Sun",
    }

    base = (
        slot_df[slot_df["minute"] == 0]
        .groupby(["weekday", "hour"], as_index=False)["occupancy"]
        .mean()
    )

    rows = []
    for day in weekday_order:
        vals = []
        day_df = base[base["weekday"] == day]
        for hr in target_hours:
            row = day_df[day_df["hour"] == hr]
            vals.append(int(round(row["occupancy"].iloc[0])) if not row.empty else 0)
        rows.append({"day": weekday_short[day], "values": vals})

    return heatmap_hours, rows


def build_best_and_worst_times(timeline):
    sorted_low = sorted(timeline, key=lambda x: x["value"])[:3]
    sorted_high = sorted(timeline, key=lambda x: x["value"], reverse=True)[:3]

    order = {item["time"]: i for i, item in enumerate(timeline)}
    best_times = [x["time"] for x in sorted(sorted_low, key=lambda x: order[x["time"]])]
    worst_times = [x["time"] for x in sorted(sorted_high, key=lambda x: order[x["time"]])]

    return best_times, worst_times


def build_week_snapshot(slot_df: pd.DataFrame):
    daily_peak_by_date = slot_df.groupby("date", as_index=False)["occupancy"].max()
    daily_peak_by_date["date"] = pd.to_datetime(daily_peak_by_date["date"])
    daily_peak_by_date["weekday"] = daily_peak_by_date["date"].dt.day_name()

    avg_by_weekday = (
        daily_peak_by_date.groupby("weekday", as_index=False)["occupancy"]
        .mean()
    )

    busiest_day = avg_by_weekday.sort_values("occupancy", ascending=False).iloc[0]["weekday"]
    quietest_day = avg_by_weekday.sort_values("occupancy", ascending=True).iloc[0]["weekday"]

    avg_by_time = (
        slot_df.groupby("time", as_index=False)["occupancy"]
        .mean()
    )
    peak_half_hour = avg_by_time.sort_values("occupancy", ascending=False).iloc[0]["time"]
    best_overall_window = avg_by_time.sort_values("occupancy", ascending=True).iloc[0]["time"]

    return {
        "busiestDay": busiest_day,
        "quietestDay": quietest_day,
        "peakHalfHour": peak_half_hour,
        "bestOverallWindow": best_overall_window,
    }


def build_daily_checkin_stats(df: pd.DataFrame, dt_col: str):
    temp = df[[dt_col]].copy()
    temp[dt_col] = pd.to_datetime(temp[dt_col], errors="coerce")
    temp = temp.dropna(subset=[dt_col])

    if temp.empty:
        return {
            "avgDailyCheckins": 0,
            "maxDailyCheckins": 0,
            "busiestCheckinDay": "-"
        }

    temp["date"] = temp[dt_col].dt.date
    daily_counts = temp.groupby("date").size().reset_index(name="checkins")

    avg_daily_checkins = int(round(daily_counts["checkins"].mean()))
    max_daily_checkins = int(daily_counts["checkins"].max())

    peak_row = daily_counts.sort_values("checkins", ascending=False).iloc[0]
    peak_day_ts = pd.to_datetime(peak_row["date"])
    busiest_checkin_day = f"{peak_day_ts.strftime('%b')} {peak_day_ts.day}, {peak_day_ts.year}"

    return {
        "avgDailyCheckins": avg_daily_checkins,
        "maxDailyCheckins": max_daily_checkins,
        "busiestCheckinDay": busiest_checkin_day,
    }


def build_selected_now(timeline):
    now = pd.Timestamp.now()
    hour = now.hour
    minute = 0 if now.minute < 30 else 30
    label = pd.Timestamp(year=2000, month=1, day=1, hour=hour, minute=minute).strftime("%I:%M %p").lstrip("0")

    lookup = {x["time"]: x["value"] for x in timeline}
    if label not in lookup:
        label = timeline[0]["time"]

    return label, lookup[label]


def build_next_lighter_window(timeline, current_idx, current_value):
    for i in range(current_idx + 1, len(timeline)):
        if timeline[i]["value"] <= current_value - 18:
            return timeline[i]["time"]
    return "No lighter window left today"


def build_status(value, daily_peak):
    percent_of_peak = int(round((value / daily_peak) * 100))
    if percent_of_peak < 35:
        return "Low", percent_of_peak
    if percent_of_peak < 70:
        return "Moderate", percent_of_peak
    return "Busy", percent_of_peak


def build_trend_direction(timeline, current_idx):
    current_value = timeline[current_idx]["value"]
    previous_value = timeline[max(0, current_idx - 1)]["value"]

    if current_value > previous_value + 3:
        return "Rising"
    if current_value < previous_value - 3:
        return "Cooling Off"
    return "Steady"


def main():
    print(f"Project root: {PROJECT_ROOT}")

    df = load_data()
    dt_col = find_checkin_column(df)
    print(f"Using datetime column: {dt_col}")

    slot_df = build_half_hour_occupancy(df, dt_col)
    timeline = build_timeline(slot_df)
    heatmap_hours, weekly_pattern = build_weekly_pattern(slot_df)
    best_times, worst_times = build_best_and_worst_times(timeline)
    week_snapshot = build_week_snapshot(slot_df)
    daily_checkin_stats = build_daily_checkin_stats(df, dt_col)

    daily_peak = max(x["value"] for x in timeline)

    selected_time, selected_value = build_selected_now(timeline)
    current_idx = next(i for i, x in enumerate(timeline) if x["time"] == selected_time)

    crowd_status, percent_of_peak = build_status(selected_value, daily_peak)
    trend_direction = build_trend_direction(timeline, current_idx)
    next_lighter_window = build_next_lighter_window(timeline, current_idx, selected_value)

    payload = {
        "lastUpdated": "",
        "estimateNote": "Each check-in is treated as a 90-minute visit estimate.",
        "selectedTime": selected_time,
        "selectedValue": selected_value,
        "crowdStatus": crowd_status,
        "trendDirection": trend_direction,
        "dailyPeak": daily_peak,
        "percentOfPeak": percent_of_peak,
        "bestTimes": best_times,
        "worstTimes": worst_times,
        "nextLighterWindow": next_lighter_window,
        "timeline": timeline,
        "heatmapHours": heatmap_hours,
        "weeklyPattern": weekly_pattern,
        "weekSnapshot": week_snapshot,
        "dailyCheckinStats": daily_checkin_stats
    }

    out_file = SRC_DATA_DIR / "crowdData.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Built: {out_file}")
    print(f"Selected time: {selected_time}")
    print(f"Selected value: {selected_value}")
    print(f"Daily peak: {daily_peak}")
    print(f"Avg daily check-ins: {daily_checkin_stats['avgDailyCheckins']}")
    print(f"Max daily check-ins: {daily_checkin_stats['maxDailyCheckins']}")
    print(f"Busiest check-in day: {daily_checkin_stats['busiestCheckinDay']}")
    print(f"Busiest day: {week_snapshot['busiestDay']}")
    print(f"Quietest day: {week_snapshot['quietestDay']}")
    print(f"Peak half-hour: {week_snapshot['peakHalfHour']}")
    print(f"Best overall window: {week_snapshot['bestOverallWindow']}")


if __name__ == "__main__":
    main()