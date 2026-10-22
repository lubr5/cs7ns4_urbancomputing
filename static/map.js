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
  try { localStorage.setItem("noiseToken", tokenInput.value.trim()); } catch { /* private mode: not remembered */ }
});

loadStations();
setInterval(loadStations, STATION_REFRESH_MS);