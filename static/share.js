// Share page: share your current reading with other users, and clear everything you have shared.

const LIVE_REFRESH_MS = 3000;

const tokenInput = document.getElementById("token");
const shareButton = document.getElementById("share");
const clearButton = document.getElementById("clear");
const shareNote = document.getElementById("share-note");
const clearNote = document.getElementById("clear-note");
const sharedList = document.getElementById("shared-list");
const sharedEmpty = document.getElementById("shared-empty");

let phoneReady = false;          // live, with a GPS position: the two things a share needs

function savedToken() {
  try { return localStorage.getItem("noiseToken") || ""; } catch { return ""; }
}

function describePhone(result) {
  const user = result.user;
  if (!user) return { ready: false, state: "Not sending", sub: "Start Sensor Logger with this token." };
  if (!result.live) return { ready: false, state: "Offline", sub: `Last reading ${Math.round(user.reading_age_s)} s ago.` };
  if (user.latitude === null) return { ready: false, state: "No GPS yet", sub: "Waiting for a position." };
  return { ready: true, state: "Live", sub: "Sending data and position." };
}

async function pollPhone() {
  const token = savedToken();
  const level = document.getElementById("s-level");
  const state = document.getElementById("s-state");
  const sub = document.getElementById("s-state-sub");
  if (!token) {
    phoneReady = false;
    level.textContent = "-";
    state.textContent = "-";
    sub.textContent = "Enter your token above.";
  } else {
    try {
      const response = await fetch(`/api/map?token=${encodeURIComponent(token)}`);
      if (!response.ok) throw new Error(response.status);
      const result = await response.json();
      const phone = describePhone(result);
      phoneReady = phone.ready;
      level.innerHTML = result.user ? `${result.user.level} <span class="unit">dB(A)</span>` : "-";
      state.textContent = phone.state;
      sub.textContent = phone.sub;
    } catch (error) {
      phoneReady = false;
      state.textContent = "Offline";
      sub.textContent = "Cannot reach the server.";
    }
  }
  shareButton.disabled = !phoneReady || shareCooling();
}

// the server allows one share every 30 s per token, so the button waits as well
let cooldownUntil = 0;
function shareCooling() { return Date.now() < cooldownUntil; }

function formatAge(minutes) {
  if (minutes < 1) return "just now";
  if (minutes < 90) return `${minutes} min ago`;
  return `${Math.round(minutes / 60)} h ago`;
}

async function loadShared() {
  const token = savedToken();
  let list = [];
  if (token) {
    try {
      const response = await fetch(`/api/shared?token=${encodeURIComponent(token)}`);
      if (response.ok) list = await response.json();
    } catch (error) {
      console.error("could not load shared readings:", error);
    }
  }
  sharedList.replaceChildren(...list.map(item => {
    const li = document.createElement("li");
    li.textContent = `${item.level} dB(A), near ${item.latitude}, ${item.longitude}, ${formatAge(item.age_minutes)}`;
    return li;
  }));
  sharedEmpty.hidden = list.length > 0;
  clearButton.disabled = list.length === 0;
}

async function shareNow() {
  shareButton.disabled = true;
  shareNote.textContent = "Sharing...";
  try {
    const response = await fetch(`/api/share?token=${encodeURIComponent(savedToken())}`, { method: "POST" });
    const result = await response.json();
    if (result.shared) {
      cooldownUntil = Date.now() + 30000;
      shareNote.textContent = `Shared ${result.level} dB(A) near ${result.latitude}, ${result.longitude}. It is on the map now.`;
    } else {
      shareNote.textContent = result.error;
    }
  } catch (error) {
    shareNote.textContent = "Cannot reach the server.";
  }
  await loadShared();
  pollPhone();
}

async function clearMine() {
  if (!confirm("Remove everything you have shared from the map? This cannot be undone.")) return;
  clearButton.disabled = true;
  try {
    const response = await fetch(`/api/clear-shared?token=${encodeURIComponent(savedToken())}`, { method: "POST" });
    const result = await response.json();
    clearNote.textContent = result.cleared > 0
      ? `Removed ${result.cleared} shared reading${result.cleared === 1 ? "" : "s"}. Other people can no longer see ${result.cleared === 1 ? "it" : "them"}.`
      : "You had nothing shared.";
  } catch (error) {
    clearNote.textContent = "Cannot reach the server.";
  }
  loadShared();
}

tokenInput.value = savedToken();
document.getElementById("save-token").addEventListener("click", () => {
  try { localStorage.setItem("noiseToken", tokenInput.value.trim()); } catch { /* not remembered */ }
  shareNote.textContent = "";
  clearNote.textContent = "";
  pollPhone();
  loadShared();
});
shareButton.addEventListener("click", shareNow);
clearButton.addEventListener("click", clearMine);

pollPhone();
setInterval(pollPhone, LIVE_REFRESH_MS);
loadShared();
