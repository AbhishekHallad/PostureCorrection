from flask import Flask, request, jsonify
from collections import deque
import time

app = Flask(__name__)

last_sample = None
# Keep last ~2 minutes at 1 sample per second
history = deque(maxlen=180)

@app.route("/api/data", methods=["POST"])
def receive_data():
    global last_sample, history
    data = request.get_json(force=True)
    last_sample = data

    # Add timestamped data for charts
    sample = {
      "ts": time.time(),
      "pitch": float(data.get("pitch", 0)),
      "seatedTime": int(data.get("seatedTime", 0)),
      "isSeated": int(data.get("isSeated", 0)),
      "state": data.get("state", "UNKNOWN")
    }
    history.append(sample)

    print("Received:", data)
    return "", 204  # No content

@app.route("/api/latest", methods=["GET"])
def latest():
    if last_sample is None:
        return jsonify({"message": "no data yet"})
    return jsonify(last_sample)

@app.route("/api/history", methods=["GET"])
def get_history():
    # Return history as list
    return jsonify(list(history))

@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Posture Monitor Dashboard (Cloud)</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 0;
      background: #0f172a;
      color: #e5e7eb;
    }
    header {
      padding: 16px 24px;
      background: #020617;
      border-bottom: 1px solid #1f2937;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    header h1 {
      font-size: 1.4rem;
      margin: 0;
    }
    header span {
      font-size: 0.9rem;
      color: #9ca3af;
    }
    .container {
      padding: 16px 24px 40px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }
    .card {
      background: #020617;
      border-radius: 12px;
      padding: 16px;
      border: 1px solid #1f2937;
      box-shadow: 0 10px 20px rgba(15, 23, 42, 0.6);
    }
    .card-title {
      font-size: 1rem;
      margin-bottom: 8px;
      color: #e5e7eb;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .badge {
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      border: 1px solid #374151;
      color: #9ca3af;
    }
    .value-row {
      display: flex;
      justify-content: space-between;
      margin: 4px 0;
      font-size: 0.9rem;
    }
    .label {
      color: #9ca3af;
    }
    .value {
      font-weight: 500;
    }
    .state-ok { color: #22c55e; font-weight: 600; }
    .state-warn { color: #eab308; font-weight: 600; }
    .state-bad { color: #f97373; font-weight: 600; }
    .pill {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      background: #020617;
      border: 1px solid #1f2937;
      font-size: 0.8rem;
      gap: 6px;
      color: #e5e7eb;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: #22c55e;
    }
    .dot-night { background: #0ea5e9; }
    .dot-day { background: #facc15; }
    .dot-unknown { background: #6b7280; }
    .status-text {
      font-size: 0.9rem;
      margin-top: 8px;
      color: #9ca3af;
    }
    canvas {
      width: 100%;
      max-height: 260px;
    }
    @media (max-width: 600px) {
      header, .container { padding: 12px 12px 24px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Posture & Sitting Monitor</h1>
      <span id="status">Connecting to device...</span>
    </div>
    <div id="dayNightPill" class="pill">
      <span class="dot dot-unknown"></span>
      <span id="dayNightLabel">Unknown</span>
    </div>
  </header>

  <div class="container">
    <!-- Current State -->
    <div class="card">
      <div class="card-title">
        <span>Current State</span>
        <span class="badge" id="lastUpdate">Last update: --</span>
      </div>
      <div id="stateText" class="state-ok">Waiting for data...</div>
      <div class="status-text" id="stateExplanation"></div>
    </div>

    <!-- Posture metrics -->
    <div class="card">
      <div class="card-title">
        <span>Posture</span>
        <span class="badge">Pitch & Seating</span>
      </div>
      <div class="value-row">
        <span class="label">Pitch</span>
        <span class="value" id="pitch">-- °</span>
      </div>
      <div class="value-row">
        <span class="label">Seated</span>
        <span class="value" id="isSeated">--</span>
      </div>
      <div class="value-row">
        <span class="label">Sitting Time</span>
        <span class="value" id="seatedTime">-- s</span>
      </div>
    </div>

    <!-- Environment -->
    <div class="card">
      <div class="card-title">
        <span>Environment</span>
        <span class="badge">FSR / Light</span>
      </div>
      <div class="value-row">
        <span class="label">FSR raw (seat)</span>
        <span class="value" id="fsr">--</span>
      </div>
      <div class="value-row">
        <span class="label">LDR raw (light)</span>
        <span class="value" id="ldr">--</span>
      </div>
      <div class="status-text" id="lightDesc">Day/Night will be inferred from LDR.</div>
    </div>

    <!-- Chart: Pitch over time -->
    <div class="card">
      <div class="card-title">
        <span>Pitch over Time</span>
        <span class="badge">Last ~2 minutes</span>
      </div>
      <canvas id="pitchChart"></canvas>
    </div>

    <!-- Chart: Sitting time over time -->
    <div class="card">
      <div class="card-title">
        <span>Sitting Time Trend</span>
        <span class="badge">Last ~2 minutes</span>
      </div>
      <canvas id="sitChart"></canvas>
    </div>
  </div>

  <!-- Chart.js from CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    let pitchChart, sitChart;

    function classifyDayNight(ldr) {
      // *** Adjust this threshold based on your sensor ***
      // If your LDR gives LOWER values in bright light, invert logic.
      const THRESH = 2000; // example: >2000 = bright/day, <=2000 = dark/night
      if (ldr === null || ldr === undefined) return "UNKNOWN";

      if (ldr > THRESH) return "DAY";
      return "NIGHT";
    }

    function updateDayNight(ldr) {
      const mode = classifyDayNight(ldr);
      const pill = document.getElementById("dayNightPill");
      const label = document.getElementById("dayNightLabel");

      pill.querySelector(".dot").className = "dot";
      if (mode === "DAY") {
        pill.querySelector(".dot").classList.add("dot-day");
        label.textContent = "Daytime environment";
      } else if (mode === "NIGHT") {
        pill.querySelector(".dot").classList.add("dot-night");
        label.textContent = "Night / low light";
      } else {
        pill.querySelector(".dot").classList.add("dot-unknown");
        label.textContent = "Unknown lighting";
      }
    }

    function initCharts() {
      const pitchCtx = document.getElementById("pitchChart").getContext("2d");
      const sitCtx = document.getElementById("sitChart").getContext("2d");

      pitchChart = new Chart(pitchCtx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [{
            label: 'Pitch (deg)',
            data: [],
            borderWidth: 2,
            tension: 0.3
          }]
        },
        options: {
          responsive: true,
          scales: {
            x: {
              ticks: { display: false }
            }
          }
        }
      });

      sitChart = new Chart(sitCtx, {
        type: 'line',
        data: {
          labels: [],
          datasets: [{
            label: 'Sitting time (s)',
            data: [],
            borderWidth: 2,
            tension: 0.3
          }]
        },
        options: {
          responsive: true,
          scales: {
            x: {
              ticks: { display: false }
            }
          }
        }
      });
    }

    function updateCharts(history) {
      if (!pitchChart || !sitChart) return;
      const labels = history.map(h => new Date(h.ts * 1000).toLocaleTimeString());
      const pitchData = history.map(h => h.pitch);
      const sitData = history.map(h => h.seatedTime);

      pitchChart.data.labels = labels;
      pitchChart.data.datasets[0].data = pitchData;
      pitchChart.update('none');

      sitChart.data.labels = labels;
      sitChart.data.datasets[0].data = sitData;
      sitChart.update('none');
    }

    async function refresh() {
      try {
        const [latestRes, histRes] = await Promise.all([
          fetch("/api/latest"),
          fetch("/api/history")
        ]);
        const latest = await latestRes.json();
        const history = await histRes.json();

        if (latest.message) {
          document.getElementById("status").innerText = "No data yet...";
          return;
        }

        const nowStr = new Date().toLocaleTimeString();
        document.getElementById("status").innerText = "Connected to device";
        document.getElementById("lastUpdate").innerText = "Last update: " + nowStr;

        // Numbers
        document.getElementById("pitch").innerText = latest.pitch.toFixed(2) + " °";
        document.getElementById("fsr").innerText = latest.fsr;
        document.getElementById("ldr").innerText = latest.ldr;
        document.getElementById("isSeated").innerText = latest.isSeated ? "Yes" : "No";
        document.getElementById("seatedTime").innerText = latest.seatedTime + " s";

        // Day/Night from LDR
        updateDayNight(latest.ldr);

        // State classification
        const stateEl = document.getElementById("stateText");
        const explEl = document.getElementById("stateExplanation");
        let desc = "";
        let expl = "";
        let cls = "";

        switch (latest.state) {
          case "NOT SEATED":
            desc = "You are currently not seated.";
            expl = "No sitting time is being accumulated. Posture and break alerts are idle.";
            cls = "state-ok";
            break;
          case "SEATED OK":
            desc = "You are seated with good posture.";
            expl = "Pitch is within acceptable range and sitting time is below the long-sit threshold.";
            cls = "state-ok";
            break;
          case "LONG SITTING":
            desc = "You have been sitting for a long time.";
            expl = "The device recommends taking a short standing or walking break to reduce muscle strain.";
            cls = "state-warn";
            break;
          case "BAD POSTURE":
            desc = "Your posture is poor.";
            expl = "The upper-back pitch angle is above the threshold. Straighten your back to stop the alert.";
            cls = "state-bad";
            break;
          default:
            desc = latest.state;
            expl = "";
            cls = "state-ok";
            break;
        }

        stateEl.className = cls;
        stateEl.textContent = desc;
        explEl.textContent = expl;

        // Charts
        updateCharts(history);

      } catch (e) {
        document.getElementById("status").innerText = "Error contacting server";
        console.error(e);
      }
    }

    initCharts();
    setInterval(refresh, 1000);
    refresh();
  </script>
</body>
</html>
    """

if __name__ == "__main__":
    # 0.0.0.0 so it's reachable from the internet
    app.run(host="0.0.0.0", port=5000)
