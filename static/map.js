// Map page: Dublin-bounded OpenStreetMap with the DCC noise monitors as pins.

const STATION_REFRESH_MS = 30000;
const DUBLIN_BOUNDS = [[53.20, -6.50], [53.50, -6.00]];   //boundary box for Dublin City
// DCC's own colours, same as their website
const RATING_COLOURS = { 1: "#2e9e4f", 2: "#8bc34a", 3: "#f2c200", 4: "#f28c00", 5: "#d63a2f" };
const NO_RATING_COLOUR = "#8a94a0";
const map = L.map("map", {
  maxBounds: DUBLIN_BOUNDS,
  maxBoundsViscosity: 1.0,
  minZoom: 11,
  maxZoom: 18,
}).fitBounds([[53.30, -6.35], [53.40, -6.18]]);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const stationLayer = L.layerGroup().addTo(map);

function ratingColour(rating) {
  return RATING_COLOURS[rating] || NO_RATING_COLOUR;
}
// station text
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function stationPopup(s) {
  return `
    <div class="popup">
      <h3>${escapeHtml(s.label)}</h3>
      <p class="sub">${escapeHtml(s.location)}</p>
      <table>
        <tr><td>LAeq</td><td>${escapeHtml(s.LAeq)} dB(A)</td></tr>
        <tr><td>Peak (LAFmax)</td><td>${escapeHtml(s.LAFmax)} dB(A)</td></tr>
        <tr><td>Hourly average</td><td>${escapeHtml(s.hourly_average)} dB(A)</td></tr>
        <tr><td>DCC rating</td><td>${escapeHtml(s.rating)}</td></tr>
        <tr><td>Received</td><td>${escapeHtml(s.age_minutes)} min ago</td></tr>
      </table>
    </div>`;
}

function drawStations(stations) {
  stationLayer.clearLayers();
  for (const s of stations) {
    L.circleMarker([s.latitude, s.longitude], {
      radius: 11,
      weight: 2,
      color: "#ffffff",
      fillColor: ratingColour(s.rating),
      fillOpacity: 0.95,
    }).bindPopup(stationPopup(s)).addTo(stationLayer);
  }
}

async function loadStations() {
  try {
    const response = await fetch("/api/stations");
    if (!response.ok) throw new Error(response.status);
    drawStations(await response.json());
  } catch (error) {
    console.error("could not load stations:", error);
  }
}

// colour key
const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML = "<strong>DCC rating</strong><br>" + [1, 2, 3, 4, 5]
    .map(r => `<i style="background:${ratingColour(r)}"></i>${r}`).join("<br>");
  return div;
};
legend.addTo(map);

// token box for different users
const tokenInput = document.getElementById("token");
function savedToken() {
  try { return localStorage.getItem("noiseToken") || ""; } catch { return ""; }
}
tokenInput.value = savedToken();
document.getElementById("save-token").addEventListener("click", () => {
  try { localStorage.setItem("noiseToken", tokenInput.value.trim()); } catch { /* not remembered */ }
  firstFix = true;                      // zoom to the new user's position
  pollLive();
});

//  live comparison: the user's phone  /api/map 
const LIVE_REFRESH_MS = 3000;
const userLayer = L.layerGroup().addTo(map);
let firstFix = true;

const statusBox = document.getElementById("live-status");

function formatDistance(metres) {
  return metres < 1000 ? `${Math.round(metres)} m` : `${(metres / 1000).toFixed(1)} km`;
}

// "+11.2 dB" in orange when louder, "-4.1 dB" in green when quieter
function formatDifference(db) {
  const sign = db > 0 ? "+" : db < 0 ? "−" : "";
  return `<span class="${db > 0 ? "up" : "down"}">${sign}${Math.abs(db).toFixed(1)} dB</span>`;
}

function setCard(id, value, sub) {
  document.getElementById(id).innerHTML = value;
  document.getElementById(`${id}-sub`).textContent = sub;
}

function clearCards(message) {
  setCard("d-level", "-", "Estimated dB(A) from your phone");
  setCard("d-nearest", "-", message);
  setCard("d-local", "-", "");
  setCard("d-city", "-", "");
  userLayer.clearLayers();
}

function setStatus(kind, text) {
  statusBox.className = `chip ${kind}`;
  statusBox.textContent = text;
  document.getElementById("dashboard").classList.toggle("stale", kind === "offline");  
}

function drawUser(user) {
  userLayer.clearLayers();
  const here = [user.latitude, user.longitude];

  if (user.nearest) {
    L.polyline([here, [user.nearest.latitude, user.nearest.longitude]],
      { color: "#1f6feb", weight: 2, dashArray: "6 6" }).addTo(userLayer);
  }
  L.circleMarker(here, { radius: 9, weight: 3, color: "#ffffff", fillColor: "#1f6feb", fillOpacity: 1 })
    .bindTooltip("You", { permanent: true, direction: "top", offset: [0, -8] })
    .addTo(userLayer);

  if (firstFix) {            
    const points = [here];
    if (user.nearest) points.push([user.nearest.latitude, user.nearest.longitude]);
    map.fitBounds(points, { padding: [60, 60], maxZoom: 15 });
    firstFix = false;
  }
}

function renderLive(result) {
  const user = result.user;
  if (!user) {
    clearCards("Waiting for your phone to send data.");
    return setStatus("waiting", "Waiting for your phone. Start Sensor Logger with this token.");
  }

  const age = Math.round(user.reading_age_s);
  setStatus(result.live ? "live" : "offline",
    result.live ? "Live" : `Phone offline: last reading ${age} s ago`);

  setCard("d-level", `${user.level} <span class="unit">dB(A)</span>`, "Estimated from your phone's microphone");

  if (user.latitude === null) {
    setCard("d-nearest", "-", "Waiting for your phone's GPS fix.");
    setCard("d-local", "-", "");
    setCard("d-city", `${formatDifference(user.level - result.city_level)}`,
      `${result.city_level} dB(A) across ${result.stations.length} monitors`);
    return;
  }

  drawUser(user);
  const near = user.nearest;
  setCard("d-nearest", formatDifference(user.vs_nearest_db),
    `${near.label}, ${formatDistance(near.distance_m)} away: ${near.LAeq} dB(A), 15-minute average from ${near.age_minutes} min ago`);

  if (user.local_level === null) {
    setCard("d-local", "-", "No monitors within 3 km.");
  } else {
    setCard("d-local", formatDifference(user.vs_local_db),
      `${user.local_level} dB(A) from ${user.local_stations_used} monitors within 3 km`);
  }
  setCard("d-city", formatDifference(user.vs_city_db),
    `${result.city_level} dB(A) across ${result.stations.length} monitors`);
}

async function pollLive() {
  const token = savedToken();
  if (!token) {
    clearCards("");
    return setStatus("waiting", "Enter your token to compare your noise with the city.");
  }
  try {
    const response = await fetch(`/api/map?token=${encodeURIComponent(token)}`);
    if (response.status === 400) {
      clearCards("");
      return setStatus("offline", "That token is not valid. Use 4 to 32 letters or digits.");
    }
    if (!response.ok) throw new Error(response.status);
    renderLive(await response.json());
  } catch (error) {
    console.error("could not load live data:", error);
    setStatus("offline", "Cannot reach the server.");
  }
}

loadStations();
setInterval(loadStations, STATION_REFRESH_MS);
pollLive();
setInterval(pollLive, LIVE_REFRESH_MS);