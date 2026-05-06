from flask import Flask, jsonify
import psycopg2
import os
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

def get_conn():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        port=int(os.environ.get('DB_PORT', 5432)),
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        connect_timeout=10,
        sslmode='require'
    )

@app.route('/crowd-data', methods=['GET'])
def crowd_data():
    conn = get_conn()
    cursor = conn.cursor()

    # Build 48-slot timeline (30-min increments, 12am-11:30pm)
    cursor.execute("""
        SELECT DATE_TRUNC('hour', checkin_time) +
               INTERVAL '30 min' * FLOOR(EXTRACT(MINUTE FROM checkin_time) / 30) AS slot,
               COUNT(*) as checkins
        FROM checkins
        WHERE checkin_time >= CURRENT_DATE
        GROUP BY slot
        ORDER BY slot
    """)
    rows = cursor.fetchall()
    slot_map = {row[0]: row[1] for row in rows}

    timeline = []
    for i in range(48):
        dt = datetime.combine(datetime.today().date(), datetime.min.time()) + timedelta(minutes=30*i)
        hour = dt.hour
        minute = dt.minute
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        label = f"{display_hour}:{'00' if minute == 0 else '30'} {period}"
        # Estimate occupancy as 90-min rolling window
        count = 0
        for j in range(3):  # 3 x 30-min slots = 90 min
            slot_dt = dt - timedelta(minutes=30*j)
            slot_aware = datetime.combine(datetime.today().date(), slot_dt.time())
            count += slot_map.get(slot_aware, 0)
        timeline.append({"time": label, "value": count})

    daily_peak = max((t["value"] for t in timeline), default=1)

    # Best/worst times
    sorted_slots = sorted(timeline, key=lambda x: x["value"])
    best_times = [t["time"] for t in sorted_slots[:3]]
    worst_times = [t["time"] for t in sorted_slots[-3:]]

    # Next lighter window
    now = datetime.now()
    current_slot = (now.hour * 60 + now.minute) // 30
    current_val = timeline[current_slot]["value"] if current_slot < 48 else 0
    next_lighter = "No lighter window left today"
    for i in range(current_slot + 1, 48):
        if timeline[i]["value"] < current_val * 0.75:
            next_lighter = timeline[i]["time"]
            break

    # Trend direction
    if current_slot > 0:
        prev = timeline[current_slot - 1]["value"]
        curr = timeline[current_slot]["value"]
        trend = "Rising" if curr > prev * 1.1 else "Falling" if curr < prev * 0.9 else "Steady"
    else:
        trend = "Steady"

    # Weekly heatmap (last 4 weeks)
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    hours_labels = ["6AM","8AM","10AM","12PM","2PM","4PM","6PM","8PM","10PM","11PM","12AM","2AM"]
    hour_slots = [6,8,10,12,14,16,18,20,22,23,0,2]

    cursor.execute("""
        SELECT EXTRACT(DOW FROM checkin_time) as dow,
               EXTRACT(HOUR FROM checkin_time) as hour,
               COUNT(*) as cnt
        FROM checkins
        WHERE checkin_time >= NOW() - INTERVAL '28 days'
        GROUP BY dow, hour
    """)
    heatmap_raw = cursor.fetchall()
    heatmap_map = defaultdict(int)
    for row in heatmap_raw:
        heatmap_map[(int(row[0]), int(row[1]))] += row[2]

    # Convert Sunday=0 to Monday-first
    weekly_pattern = []
    for day_idx, day_name in enumerate(days):
        dow = (day_idx + 1) % 7  # Mon=1...Sun=0
        values = [int(heatmap_map.get((dow, h), 0) / 4) for h in hour_slots]
        weekly_pattern.append({"day": day_name, "values": values})

    # Week snapshot
    day_totals = {}
    for row in weekly_pattern:
        day_totals[row["day"]] = sum(row["values"])
    busiest_day = max(day_totals, key=day_totals.get) if day_totals else "-"
    quietest_day = min(day_totals, key=day_totals.get) if day_totals else "-"

    cursor.close()
    conn.close()

    return jsonify({
        "lastUpdated": datetime.now().isoformat(),
        "estimateNote": "Each check-in is treated as a 90-minute visit estimate.",
        "selectedTime": timeline[current_slot]["time"] if current_slot < 48 else "12:00 PM",
        "selectedValue": timeline[current_slot]["value"] if current_slot < 48 else 0,
        "trendDirection": trend,
        "dailyPeak": daily_peak,
        "bestTimes": best_times,
        "worstTimes": worst_times,
        "nextLighterWindow": next_lighter,
        "timeline": timeline,
        "heatmapHours": hours_labels,
        "weeklyPattern": weekly_pattern,
        "weekSnapshot": {
            "busiestDay": busiest_day,
            "quietestDay": quietest_day,
            "peakHalfHour": worst_times[-1] if worst_times else "-",
            "bestOverallWindow": best_times[0] if best_times else "-"
        }
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
