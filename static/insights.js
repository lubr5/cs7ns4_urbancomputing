// the user's own history, from /api/history.

// colour for an estimated dB(A) level
function levelColour(level) {
  if (level < 55) return "#2e9e4f";
  if (level < 65) return "#f2c200";
  if (level < 75) return "#f28c00";
  return "#d63a2f";
}

const tokenInput = document.getElementById("token");
const statusBox = document.getElementById("status");
const content = document.getElementById("content");

let hourChart = null;
let cellMap = null;
let cellLayer = null;

function savedToken() {
  try { return localStorage.getItem("noiseToken") || ""; } catch { return ""; }
}

function showStatus(message) {
  statusBox.textContent = message;
  statusBox.hidden = false;
  content.hidden = true;
}

function drawCards(history) {
  const s = history.summary;
  document.getElementById("leq").innerHTML = `${s.leq} <span class="unit">dB(A)</span>`;
  document.getElementById("peak").innerHTML = `${s.peak} <span class="unit">dB(A)</span>`;
  document.getElementById("above").innerHTML = `${s.percent_above_threshold}<span class="unit">%</span>`;
  document.getElementById("readings").textContent = s.readings.toLocaleString();
  document.getElementById("threshold-a").textContent = history.threshold;
}

function drawHourChart(history) {
  const styles = getComputedStyle(document.documentElement);
  const text = styles.getPropertyValue("--muted").trim();
  const grid = styles.getPropertyValue("--line").trim();

  const hours = Array.from({ length: 24 }, (_, h) => h);
  const levels = hours.map(h => history.by_hour[h]?.leq ?? null);       // hours with no readings stay empty
  const colours = levels.map(l => (l === null ? "transparent" : levelColour(l)));

  if (hourChart) hourChart.destroy();
  hourChart = new Chart(document.getElementById("hour-chart"), {
    data: {
      labels: hours.map(h => String(h).padStart(2, "0") + ":00"),
      datasets: [
        { type: "bar", label: "Leq (dB(A))", data: levels, backgroundColor: colours, borderRadius: 3 },
        { type: "line", label: `${history.threshold} dB(A) threshold`, data: hours.map(() => history.threshold),
          borderColor: text, borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: text } } },
      scales: {
        x: { ticks: { color: text, maxRotation: 0, autoSkip: true }, grid: { display: false } },
        y: { suggestedMin: 30, suggestedMax: 90, title: { display: true, text: "dB(A)", color: text },
             ticks: { color: text }, grid: { color: grid } },
      },
    },
  });
}

function drawCellMap(history) {
  if (!cellMap) {
    cellMap = L.map("cell-map", { minZoom: 11, maxZoom: 18 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(cellMap);
    cellLayer = L.layerGroup().addTo(cellMap);
  }
  cellLayer.clearLayers();

  const points = [];
  for (const cell of history.by_location) {
    L.circle([cell.latitude, cell.longitude], {
      radius: 75,                       // half the 150 m patch
      weight: 1,
      color: "#ffffff",
      fillColor: levelColour(cell.leq),
      fillOpacity: 0.8,
    }).bindPopup(`${cell.leq} dB(A)<br>${cell.readings.toLocaleString()} readings`).addTo(cellLayer);
    points.push([cell.latitude, cell.longitude]);
  }
  cellMap.invalidateSize();             // the map was hidden until now
  if (points.length) cellMap.fitBounds(points, { padding: [40, 40], maxZoom: 16 });
}

async function loadHistory() {
  const token = savedToken();
  if (!token) return showStatus("Enter your token above to see your recordings.");

  showStatus("Loading your recordings...");
  try {
    const response = await fetch(`/api/history?token=${encodeURIComponent(token)}`);
    if (!response.ok) throw new Error(response.status);
    const history = await response.json();
    if (!history.summary) return showStatus("No readings found for this token yet.");

    statusBox.hidden = true;
    content.hidden = false;
    drawCards(history);
    drawHourChart(history);
    drawCellMap(history);
  } catch (error) {
    console.error("could not load history:", error);
    showStatus("Could not load your recordings. Check the token and try again.");
  }
}

tokenInput.value = savedToken();
document.getElementById("save-token").addEventListener("click", () => {
  try { localStorage.setItem("noiseToken", tokenInput.value.trim()); } catch { /* private mode: not remembered */ }
  loadHistory();
});
document.getElementById("reload").addEventListener("click", loadHistory);

loadHistory();
