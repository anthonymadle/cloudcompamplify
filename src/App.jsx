import { useMemo, useState } from "react";
import crowdData from "./data/crowdData.json";

function heatClass(value) {
  if (value < 40) return "heat heat-1";
  if (value < 80) return "heat heat-2";
  if (value < 130) return "heat heat-3";
  if (value < 180) return "heat heat-4";
  if (value < 240) return "heat heat-5";
  return "heat heat-6";
}

function toneClass(status) {
  if (status === "Low") {
    return {
      badge: "status-badge low",
      fill: "meter-fill low",
      glow: "meter-glow low"
    };
  }
  if (status === "Moderate") {
    return {
      badge: "status-badge moderate",
      fill: "meter-fill moderate",
      glow: "meter-glow moderate"
    };
  }
  return {
    badge: "status-badge busy",
    fill: "meter-fill busy",
    glow: "meter-glow busy"
  };
}

function weekdayShort(name) {
  return {
    Monday: "Mon",
    Tuesday: "Tue",
    Wednesday: "Wed",
    Thursday: "Thu",
    Friday: "Fri",
    Saturday: "Sat",
    Sunday: "Sun"
  }[name] || name || "-";
}

export default function App() {
  const safeData = {
    lastUpdated: crowdData?.lastUpdated || "",
    estimateNote:
      crowdData?.estimateNote ||
      "Each check-in is treated as a 90-minute visit estimate.",
    selectedTime: crowdData?.selectedTime || "12:00 PM",
    selectedValue: crowdData?.selectedValue ?? 0,
    trendDirection: crowdData?.trendDirection || "Steady",
    dailyPeak: crowdData?.dailyPeak ?? 1,
    bestTimes: Array.isArray(crowdData?.bestTimes) ? crowdData.bestTimes : [],
    worstTimes: Array.isArray(crowdData?.worstTimes) ? crowdData.worstTimes : [],
    nextLighterWindow: crowdData?.nextLighterWindow || "No lighter window left today",
    timeline: Array.isArray(crowdData?.timeline) ? crowdData.timeline : [],
    heatmapHours: Array.isArray(crowdData?.heatmapHours) ? crowdData.heatmapHours : [],
    weeklyPattern: Array.isArray(crowdData?.weeklyPattern) ? crowdData.weeklyPattern : [],
    weekSnapshot: crowdData?.weekSnapshot || {
      busiestDay: "-",
      quietestDay: "-",
      peakHalfHour: "-",
      bestOverallWindow: "-"
    }
  };

  const initialIndex = Math.max(
    0,
    safeData.timeline.findIndex((item) => item.time === safeData.selectedTime)
  );

  const [selectedIndex, setSelectedIndex] = useState(initialIndex);

  if (safeData.timeline.length === 0) {
    return (
      <div className="app-shell">
        <div className="page">
          <section className="panel" style={{ marginTop: "40px" }}>
            <div className="section-label">Data error</div>
            <h2>No timeline data found</h2>
            <p className="card-copy">
              Run <code>py build_crowd_data.py</code> again and refresh.
            </p>
          </section>
        </div>
      </div>
    );
  }

  const selected = safeData.timeline[selectedIndex] || safeData.timeline[0];
  const dailyPeak = safeData.dailyPeak || 1;
  const percentOfPeak = Math.round((selected.value / dailyPeak) * 100);
  const crowdStatus =
    percentOfPeak < 35 ? "Low" : percentOfPeak < 70 ? "Moderate" : "Busy";

  const tone = toneClass(crowdStatus);
  const peakBarHeight = 260;

  return (
    <div className="app-shell">
      <div className="ambient ambient-a"></div>
      <div className="ambient ambient-b"></div>

      <div className="page">
        <section className="hero">
          <div className="hero-top">
            <div className="brand">
              <div className="logo-wrap">
                <img src="/sfLogo.png" alt="Signature Fitness logo" className="logo" />
              </div>

              <div>
                <div className="eyebrow">24-HOUR LIVE CROWD METER</div>
                <h1>Signature Fitness</h1>
                <p className="hero-sub">
                  Check gym traffic live, slide through the day, and time your workout better.
                </p>
              </div>
            </div>

            <div className="hero-chips">
              <div className="meta-pill muted">{safeData.estimateNote}</div>
            </div>
          </div>

          <div className="hero-grid">
            <div className="hero-main">
              <div className="section-label">Current estimated occupancy</div>

              <div className="occupancy-row">
                <div className="occupancy-number">{selected.value}</div>
                <div className={tone.badge}>{crowdStatus}</div>
              </div>

              <div className="sub-stats">
                <div className="sub-stat">
                  <span className="sub-stat-label">Selected time</span>
                  <span className="sub-stat-value">{selected.time}</span>
                </div>
                <div className="sub-stat">
                  <span className="sub-stat-label">Trend</span>
                  <span className="sub-stat-value">{safeData.trendDirection}</span>
                </div>
                <div className="sub-stat">
                  <span className="sub-stat-label">Daily peak</span>
                  <span className="sub-stat-value">{dailyPeak}</span>
                </div>
              </div>

              <div className="meter-block">
                <div className="meter-header">
                  <span>Crowd meter</span>
                  <span>{percentOfPeak}% of full-day peak</span>
                </div>

                <div className="meter-track xl">
                  <div className={tone.glow}></div>
                  <div
                    className={tone.fill}
                    style={{ width: `${percentOfPeak}%` }}
                  ></div>
                </div>

                <div className="meter-scale">
                  <span>Light</span>
                  <span>Average</span>
                  <span>Peak</span>
                </div>
              </div>
            </div>

            <div className="side-stack">
              <div className="glass-card">
                <div className="section-label">Best times left today</div>
                <div className="pill-row">
                  {safeData.bestTimes.map((time) => (
                    <div key={time} className="time-pill good">
                      {time}
                    </div>
                  ))}
                </div>
              </div>

              <div className="glass-card">
                <div className="section-label">Peak times today</div>
                <div className="pill-row">
                  {safeData.worstTimes.map((time) => (
                    <div key={time} className="time-pill bad">
                      {time}
                    </div>
                  ))}
                </div>
              </div>

              <div className="glass-card">
                <div className="section-label">Smart timing</div>
                <div className="callout-big">{safeData.nextLighterWindow}</div>
                <p className="card-copy">
                  Next noticeably lighter window based on the real traffic pattern.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="panel planner-panel">
          <div className="panel-head">
            <div>
              <div className="section-label">Plan your workout</div>
              <h2>24-hour occupancy slider</h2>
            </div>
            <div className="panel-note">Half-hour increments</div>
          </div>

          <div className="planner-summary">
            <div className="planner-card strong">
              <span className="planner-label">At {selected.time}</span>
              <span className="planner-number">{selected.value}</span>
              <span className="planner-copy">estimated active people</span>
            </div>

            <div className="planner-card">
              <span className="planner-label">Crowd level</span>
              <span className="planner-number small">{crowdStatus}</span>
              <span className="planner-copy">{percentOfPeak}% of the day’s peak</span>
            </div>

            <div className="planner-card">
              <span className="planner-label">Best overall window</span>
              <span className="planner-number small">{safeData.weekSnapshot.bestOverallWindow}</span>
              <span className="planner-copy">Quietest half-hour in the full pattern</span>
            </div>
          </div>

          <div className="slider-wrap">
            <input
              type="range"
              min="0"
              max={safeData.timeline.length - 1}
              value={selectedIndex}
              onChange={(e) => setSelectedIndex(Number(e.target.value))}
              className="time-slider"
            />

            <div className="slider-labels">
              <span>12 AM</span>
              <span>6 AM</span>
              <span>12 PM</span>
              <span>6 PM</span>
              <span>11:30 PM</span>
            </div>
          </div>

          <div className="bars-wrap">
            {safeData.timeline.map((item, index) => {
              const active = index === selectedIndex;
              return (
                <div key={item.time} className="mini-bar-col">
                  <div
                    className={`mini-bar ${active ? "active" : ""}`}
                    style={{ height: `${(item.value / dailyPeak) * peakBarHeight}px` }}
                    title={`${item.time}: ${item.value}`}
                  ></div>
                </div>
              );
            })}
          </div>

          <div className="current-time-tag">{selected.time}</div>
        </section>

        <section className="bottom-grid">
          <div className="panel heatmap-panel full-width-panel">
            <div className="panel-head">
              <div>
                <div className="section-label">Weekly planning</div>
                <h2>Peak-time map</h2>
              </div>
              <div className="panel-note">Typical estimated occupancy</div>
            </div>

            <div className="heatmap-wrap">
              <div className="heatmap-header">
                <div></div>
                {safeData.heatmapHours.map((hour) => (
                  <div key={hour} className="heatmap-hour">
                    {hour}
                  </div>
                ))}
              </div>

              {safeData.weeklyPattern.map((row) => (
                <div key={row.day} className="heatmap-row">
                  <div className="day-label">{row.day}</div>
                  {row.values.map((value, index) => (
                    <div key={index} className={heatClass(value)}>
                      {value}
                    </div>
                  ))}
                </div>
              ))}
            </div>

            <div className="stats-strip">
              <div className="stats-chip">
                <span className="stats-chip-label">Busiest day</span>
                <span className="stats-chip-value">{weekdayShort(safeData.weekSnapshot.busiestDay)}</span>
              </div>
              <div className="stats-chip">
                <span className="stats-chip-label">Quietest day</span>
                <span className="stats-chip-value">{weekdayShort(safeData.weekSnapshot.quietestDay)}</span>
              </div>
              <div className="stats-chip">
                <span className="stats-chip-label">Busiest half-hour</span>
                <span className="stats-chip-value">{safeData.weekSnapshot.peakHalfHour}</span>
              </div>
              <div className="stats-chip">
                <span className="stats-chip-label">Quietest overall window</span>
                <span className="stats-chip-value">{safeData.weekSnapshot.bestOverallWindow}</span>
              </div>
            </div>

            <div className="quote-panel quote-panel-wide">
              <p>“Show up. The rest follows.”</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}