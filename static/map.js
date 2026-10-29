// Map page: Dublin-bounded OpenStreetMap with the DCC noise monitors as pins.

const STATION_REFRESH_MS = 30000;
const DUBLIN_BOUNDS = [[53.265, -6.52], [53.495, -6.04]];   //boundary box for Dublin City
// DCC's own colours, same as their website
const RATING_COLOURS = { 1: "#2e9e4f", 2: "#8bc34a", 3: "#f2c200", 4: "#f28c00", 5: "#d63a2f" };
const NO_RATING_COLOUR = "#8a94a0";
const map = L.map("map", {
  maxBounds: DUBLIN_BOUNDS,
  maxBoundsViscosity: 1.0,
  minZoom: 11,
  maxZoom: 18,
}).fitBounds([[53.30, -6.35], [53.40, -6.18]]);

// never zoom out far enough to show tiles outside the box, whatever the window size
function fitMinZoom() {
  map.setMinZoom(map.getBoundsZoom(DUBLIN_BOUNDS, true));
}
fitMinZoom();
map.on("resize", fitMinZoom);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const stationLayer = L.layerGroup().addTo(map);
const crowdLayer = L.layerGroup().addTo(map);

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
        <tr><td>Received</td><td>${formatAge(s.age_minutes)}</td></tr>
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

// ---- citizen readings shared by other users: triangles with a black border, so they are not mistaken for DCC monitors ----
const CROWD_REFRESH_MS = 20000;

// colour by level (the same bands as the Insights page), not by DCC rating
function levelColour(level) {
  if (level < 55) return "#2e9e4f";
  if (level < 65) return "#f2c200";
  if (level < 75) return "#f28c00";
  return "#d63a2f";
}

function crowdIcon(level) {
  return L.divIcon({
    className: "crowd-icon",
    html: `<svg width="26" height="24" viewBox="0 0 26 24"><polygon points="13,2 24,22 2,22"
      fill="${levelColour(level)}" stroke="#000000" stroke-width="2.5" stroke-linejoin="round"/></svg>`,
    iconSize: [26, 24],
    iconAnchor: [13, 16],
  });
}

function crowdPopup(r) {
  return `
    <div class="popup">
      <h3>Citizen reading</h3>
      <p class="sub">Shared by a user, position rounded to about 100 m</p>
      <table>
        <tr><td>Level</td><td>${escapeHtml(r.level)} dB(A) (estimated)</td></tr>
        <tr><td>Shared</td><td>${escapeHtml(formatAge(r.age_minutes))}</td></tr>
      </table>
      <p class="sub">From a phone microphone, not a calibrated measurement.</p>
    </div>`;
}

function drawCrowd(readings) {
  crowdLayer.clearLayers();
  for (const r of readings) {
    L.marker([r.latitude, r.longitude], { icon: crowdIcon(r.level), title: "Citizen reading" })
      .bindPopup(crowdPopup(r)).addTo(crowdLayer);
  }
}

async function loadCrowd() {
  try {
    const response = await fetch("/api/crowd");
    if (!response.ok) throw new Error(response.status);
    drawCrowd(await response.json());
  } catch (error) {
    console.error("could not load shared readings:", error);
  }
}

// colour key
const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  const key = "<strong>DCC rating</strong><br>" + [1, 2, 3, 4, 5]
    .map(r => `<i style="background:${ratingColour(r)}"></i>${r}`).join("<br>")
    + `<br><i style="background:${NO_RATING_COLOUR}"></i>No data`
    + `<br><svg width="12" height="11" viewBox="0 0 26 24" style="margin-right:6px"><polygon points="13,2 24,22 2,22" fill="#cfd5dc" stroke="#000" stroke-width="3"/></svg>Citizen reading`;
  div.innerHTML = `
    <div class="legend-nav">
      <button id="prev-monitor" type="button" disabled>&#9664; Prev</button>
      <span id="monitor-count">Monitor</span>
      <button id="next-monitor" type="button" disabled>Next &#9654;</button>
    </div>
    <div class="legend-key">${key}</div>`;
  L.DomEvent.disableClickPropagation(div);          // pressing a button must not move the map
  div.querySelector("#prev-monitor").addEventListener("click", () => cycleMonitor(-1));
  div.querySelector("#next-monitor").addEventListener("click", () => cycleMonitor(1));
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

// minutes for recent readings, hours or days if the data is old (for example the poller was off)
function formatAge(minutes) {
  if (minutes < 90) return `${Math.round(minutes)} min ago`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / 1440)} days ago`;
}

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

function drawUser(user, target) {
  userLayer.clearLayers();
  const here = [user.latitude, user.longitude];

  if (target) {
    L.polyline([here, [target.latitude, target.longitude]],
      { color: "#1f6feb", weight: 2, dashArray: "6 6" }).addTo(userLayer);
    L.circleMarker([target.latitude, target.longitude],          // ring round the monitor being compared
      { radius: 18, weight: 3, color: "#1f6feb", fill: false }).addTo(userLayer);
  }
  L.circleMarker(here, { radius: 9, weight: 3, color: "#ffffff", fillColor: "#1f6feb", fillOpacity: 1 })
    .bindTooltip("You", { permanent: true, direction: "top", offset: [0, -8] })
    .addTo(userLayer);

  if (firstFix) {            
    const points = [here];
    if (target) points.push([target.latitude, target.longitude]);
    map.fitBounds(points, { padding: [60, 60], maxZoom: 15 });
    firstFix = false;
  }
}
let selectedCode = null;      // null means "the nearest one"
let latestResult = null;

function chosenMonitor(result) {
  const list = result.stations;                       // sorted by distance from the user
  let index = list.findIndex(s => s.code === selectedCode);
  if (index < 0) index = 0;
  return { index, station: list[index] };
}

function updateMonitorButtons(result, chosen) {
  const count = result.stations.length;
  document.getElementById("prev-monitor").disabled = count < 2;
  document.getElementById("next-monitor").disabled = count < 2;
  document.getElementById("monitor-count").textContent = `Monitor ${chosen.index + 1} of ${count}`;
}

function cycleMonitor(step) {
  if (!latestResult || latestResult.user?.latitude == null) return;
  const count = latestResult.stations.length;
  const next = (chosenMonitor(latestResult).index + step + count) % count;
  selectedCode = latestResult.stations[next].code;
  renderLive(latestResult);                           // update card 
  const user = latestResult.user, target = latestResult.stations[next];
  map.fitBounds([[user.latitude, user.longitude], [target.latitude, target.longitude]],
    { padding: [60, 60], maxZoom: 15 });          
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

  latestResult = result;
  const chosen = chosenMonitor(result);
  drawUser(user, chosen.station);
  updateMonitorButtons(result, chosen);
  document.getElementById("d-nearest-label").textContent =
    `Compared with ${chosen.station.label}, ${chosen.station.location}` + (chosen.index === 0 ? " (nearest)" : "");
  setCard("d-nearest", formatDifference(user.level - chosen.station.LAeq),
    `${formatDistance(chosen.station.distance_m)} away: ${chosen.station.LAeq} dB(A) (15-minute average, ${formatAge(chosen.station.age_minutes)})`);

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

// ---- refresh button: ask the server to fetch new DCC readings now ----
const REFRESH_COOLDOWN_MS = 60000;      // matches the server's limit, so the button never gets a refusal
const refreshButton = document.getElementById("refresh");
const refreshNote = document.getElementById("refresh-note");
let cooldownUntil = 0;
let lastResult = "";
let lastCheck = 0;

// keeps the button label, the countdown and the "checked N s ago" note up to date
function updateRefreshControls() {
  const wait = Math.ceil((cooldownUntil - Date.now()) / 1000);
  refreshButton.disabled = wait > 0;
  refreshButton.textContent = wait > 0 ? `Refresh DCC data (${wait} s)` : "Refresh DCC data";
  if (lastResult) {
    const ago = Math.round((Date.now() - lastCheck) / 1000);
    refreshNote.textContent = `${lastResult} (checked ${ago} s ago)`;
  }
}

async function refreshDcc() {
  refreshButton.disabled = true;
  refreshNote.textContent = "Asking DCC for new readings...";
  try {
    const response = await fetch("/refresh", { method: "POST" });
    const result = await response.json();
    lastCheck = Date.now();
    if (response.status === 429) {                       // someone refreshed a moment ago
      cooldownUntil = Date.now() + result.retry_in_s * 1000;
      lastResult = "Someone just refreshed, the data is current";
    } else if (response.ok) {
      cooldownUntil = Date.now() + REFRESH_COOLDOWN_MS;
      lastResult = result.new_readings > 0
        ? `${result.new_readings} new reading${result.new_readings === 1 ? "" : "s"} from DCC`
        : "No new readings yet: DCC publishes about every 15 minutes";
      await loadStations();
    } else {
      cooldownUntil = Date.now() + 10000;
      lastResult = "Could not reach DCC, try again shortly";
    }
  } catch (error) {
    console.error("refresh failed:", error);
    cooldownUntil = Date.now() + 10000;
    lastCheck = Date.now();
    lastResult = "Cannot reach the server";
  }
  updateRefreshControls();
}

refreshButton.addEventListener("click", refreshDcc);
setInterval(updateRefreshControls, 1000);

loadStations();
setInterval(loadStations, STATION_REFRESH_MS);
loadCrowd();
setInterval(loadCrowd, CROWD_REFRESH_MS);
pollLive();
setInterval(pollLive, LIVE_REFRESH_MS);