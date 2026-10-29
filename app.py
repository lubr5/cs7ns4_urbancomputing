import atexit, hashlib, json, os, shutil, signal, subprocess, sys, threading, time, urllib.request
from datetime import datetime, timedelta, timezone
from firebase_admin import firestore
from flask import jsonify, request, send_from_directory
from google.cloud.firestore_v1.base_query import FieldFilter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))
import newPoller
import stationCalculations as stations
import userCalculations as user
from newReceiver import RECENT, TOKEN_PATTERN, app, db
LIVE_WINDOW_SECONDS = 30          # live = last 30 seconds
LIVE_MAX_AGE_SECONDS = 15         # kill phone after 15s
REFRESH_COOLDOWN_SECONDS = 60     # DCC only updates every few minutes, so more often is pointless
STATION_CACHE_SECONDS = 30        # reuse station list instead of re-reading Firestore
PORT = 8000
NGROK_DOMAIN = "swapping-oncoming-joining.ngrok-free.dev"

lastRefresh = {"at": 0.0}
stationCache = {"at": 0.0, "stations": []}

def tokenFromRequest():
    token = request.args.get("token", "")
    return token if TOKEN_PATTERN.match(token) else None

def latestStations():
    if time.time() - stationCache["at"] > STATION_CACHE_SECONDS:
        stationCache["stations"] = stations.fetchLatestStations()
        stationCache["at"] = time.time()
    return stationCache["stations"]

# station as the pages need it
def publicStation(s):
    return {
        "code": s["code"], "label": s["label"], "location": s.get("location"),
        "latitude": s["latitude"], "longitude": s["longitude"],
        "LAeq": s["LAeq"], "LAFmax": s.get("LAFmax"),
        "hourly_average": s.get("hourly_average"),
        "rating": s.get("current_rating"),
        "recorded_at": s.get("recorded_at"),
        "age_minutes": stations.ageMinutes(s),
        **({"distance_m": s["distance_m"]} if "distance_m" in s else {}),
    }

# serve pages from the static folder
@app.route("/")
def mapPage():
    return send_from_directory(app.static_folder, "map.html")

@app.route("/insights")
def insightsPage():
    return send_from_directory(app.static_folder, "insights.html")

#let user share their readings with others
@app.route("/share")
def sharePage():
    return send_from_directory(app.static_folder, "share.html")

@app.route("/health")
def health():
    return jsonify({"ok": True})
@app.route("/api/stations")
def apiStations():
    return jsonify([publicStation(s) for s in latestStations()])

# the user's live level against nearest station, 3km and city
@app.route("/api/map")
def apiMap():
    token = tokenFromRequest()
    if not token:
        return jsonify({"error": "missing or invalid token"}), 400
    allStations = latestStations()
    result = {
        "unit": "dB(A)",
        "city_level": stations.cityLevel(allStations),
        "stations": [publicStation(s) for s in allStations],
        "live": False,
        "user": None,
    }
    recent = [r for r in list(RECENT.get(token, [])) if user.isValid(r)]
    if not recent:
        return jsonify(result)
    newest = int(recent[-1]["time"])
    window = [r for r in recent if int(r["time"]) >= newest - LIVE_WINDOW_SECONDS * 10**9]
    level = user.leq(user.toLevel(r) for r in window)
    ageS = time.time() - newest / 1e9
    result["live"] = ageS <= LIVE_MAX_AGE_SECONDS and level is not None
    userInfo = {
        "level": round(level, 1),
        "readings_in_window": len(window),
        "reading_age_s": round(ageS, 1),
        "latitude": None, "longitude": None,
    }
    located = [r for r in recent if user.hasLocation(r)]
    if located:
        latitude, longitude = float(located[-1]["latitude"]), float(located[-1]["longitude"])
        ranked = stations.stationsByDistance(allStations, latitude, longitude)
        local = stations.localLevel(allStations, latitude, longitude)
        userInfo.update({
            "latitude": latitude, "longitude": longitude,
            "nearest": publicStation(ranked[0]),
            "local_level": local["level"] if local else None,
            "local_stations_used": local["stations_used"] if local else 0,
            "vs_nearest_db": round(level - ranked[0]["LAeq"], 1),
            "vs_local_db": round(level - local["level"], 1) if local else None,
            "vs_city_db": round(level - result["city_level"], 1),
        })
        result["stations"] = [publicStation(s) for s in ranked]
    result["user"] = userInfo
    return jsonify(result)

# the user's own data across their sessions
@app.route("/api/history")
def apiHistory():
    token = tokenFromRequest()
    if not token:
        return jsonify({"error": "missing or invalid token"}), 400
    readings = user.fetchUserReadings(token)
    return jsonify({
        "unit": "dB(A)",
        "threshold": user.THRESHOLD_DBA,
        "summary": user.sessionSummary(readings, threshold=user.THRESHOLD_DBA),
        "by_hour": user.byHourOfDay(readings),
        "by_location": user.byLocation(readings),
    })

# the refresh button: one DCC poll now
@app.route("/refresh", methods=["POST"])
def refresh():
    wait = REFRESH_COOLDOWN_SECONDS - (time.time() - lastRefresh["at"])
    if wait > 0:
        return jsonify({"refreshed": False, "retry_in_s": round(wait)}), 429
    lastRefresh["at"] = time.time()
    try:
        written = newPoller.poll(db)
    except Exception as error:
        return jsonify({"refreshed": False, "error": str(error)}), 502
    stationCache["at"] = 0.0    
    return jsonify({"refreshed": True, "new_readings": written})

# sers can share a reading
CROWD_COLLECTION = "crowd_readings"
CROWD_LIFETIME_HOURS = 1         # a shared reading disappears from the map after 1 hour
CROWD_CACHE_SECONDS = 15
SHARE_COOLDOWN_SECONDS = 30       # cooldown period for sharing
LAT_STEP, LON_STEP = 0.001, 0.0015    # about 100 m each way
MAP_BOUNDS = (53.265, -6.52, 53.495, -6.04)    # the same box as the map
OWNER = "urban-computing-assignment-4"

lastShare = {}
crowdCache = {"at": 0.0, "readings": []}

# nobody reading the public data can tell whose a reading is
def ownerHash(token):
    return hashlib.sha256((OWNER + token).encode()).hexdigest()[:32]

def snapToGrid(value, step):
    return round(round(value / step) * step, 6)

# a shared reading
def publicCrowd(reading):
    age = (datetime.now(timezone.utc) - reading["shared_at"]).total_seconds() / 60
    return {"latitude": reading["latitude"], "longitude": reading["longitude"],
            "level": reading["level"], "age_minutes": round(age)}

def recentCrowd():
    if time.time() - crowdCache["at"] > CROWD_CACHE_SECONDS:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=CROWD_LIFETIME_HOURS)
        docs = db.collection(CROWD_COLLECTION).where(filter=FieldFilter("shared_at", ">=", cutoff)).stream()
        crowdCache["readings"] = [d.to_dict() for d in docs]
        crowdCache["at"] = time.time()
    return crowdCache["readings"]

@app.route("/api/crowd")
def apiCrowd():
    return jsonify([publicCrowd(r) for r in recentCrowd()])

# the readings this token has shared 
@app.route("/api/shared")
def apiShared():
    token = tokenFromRequest()
    if not token:
        return jsonify({"error": "missing or invalid token"}), 400
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CROWD_LIFETIME_HOURS)
    docs = db.collection(CROWD_COLLECTION).where(filter=FieldFilter("owner", "==", ownerHash(token))).stream()
    mine = [d.to_dict() for d in docs]
    mine = [r for r in mine if r.get("shared_at") and r["shared_at"] >= cutoff]
    mine.sort(key=lambda r: r["shared_at"], reverse=True)
    return jsonify([publicCrowd(r) for r in mine])

# share the last 30 seconds of this token's phone data
@app.route("/api/share", methods=["POST"])
def apiShare():
    token = tokenFromRequest()
    if not token:
        return jsonify({"shared": False, "error": "Enter a valid token first."}), 400
    wait = SHARE_COOLDOWN_SECONDS - (time.time() - lastShare.get(token, 0))
    if wait > 0:
        return jsonify({"shared": False, "error": f"You just shared. Try again in {round(wait)} s."}), 429

    recent = [r for r in list(RECENT.get(token, [])) if user.isValid(r)]
    if not recent or time.time() - int(recent[-1]["time"]) / 1e9 > LIVE_MAX_AGE_SECONDS:
        return jsonify({"shared": False, "error": "Your phone is not sending data right now."}), 409
    located = [r for r in recent if user.hasLocation(r)]
    if not located:
        return jsonify({"shared": False, "error": "Waiting for your phone's GPS position."}), 409
    latitude, longitude = float(located[-1]["latitude"]), float(located[-1]["longitude"])
    south, west, north, east = MAP_BOUNDS
    if not (south <= latitude <= north and west <= longitude <= east):
        return jsonify({"shared": False, "error": "You are outside the area this map covers."}), 422

    newest = int(recent[-1]["time"])
    window = [r for r in recent if int(r["time"]) >= newest - LIVE_WINDOW_SECONDS * 10**9]
    level = round(user.leq(user.toLevel(r) for r in window), 1)
    reading = {
        "owner": ownerHash(token),
        "latitude": snapToGrid(latitude, LAT_STEP),
        "longitude": snapToGrid(longitude, LON_STEP),
        "level": level,
        "shared_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection(CROWD_COLLECTION).add(reading)
    lastShare[token] = time.time()
    crowdCache["at"] = 0.0
    return jsonify({"shared": True, "latitude": reading["latitude"], "longitude": reading["longitude"], "level": level})

# "delete every reading this token has shared
@app.route("/api/clear-shared", methods=["POST"])
def apiClearShared():
    token = tokenFromRequest()
    if not token:
        return jsonify({"error": "missing or invalid token"}), 400
    docs = list(db.collection(CROWD_COLLECTION).where(filter=FieldFilter("owner", "==", ownerHash(token))).stream())
    for start in range(0, len(docs), 400):                 # Firestore allows 500 deletes per batch
        batch = db.batch()
        for doc in docs[start:start + 400]:
            batch.delete(doc.reference)
        batch.commit()
    crowdCache["at"] = 0.0
    return jsonify({"cleared": len(docs)})

# start the ngrok tunnel, stopped when the app stops
def startTunnel():
    if shutil.which("ngrok") is None:
        return print("ngrok is not installed, serving on this computer only", flush=True)
    tunnel = subprocess.Popen(["ngrok", "http", f"--url={NGROK_DOMAIN}", str(PORT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atexit.register(tunnel.terminate)
    time.sleep(3)                                   # ngrok takes a moment to connect
    if tunnel.poll() is not None:
        return print("ngrok stopped straight away. Is another ngrok tunnel already running, or the authtoken missing?", flush=True)
    try:                                            # ngrok reports its public address on a local port
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3) as response:
            print("Public address:", json.load(response)["tunnels"][0]["public_url"], flush=True)
    except Exception:
        print("ngrok is running at", f"https://{NGROK_DOMAIN}", flush=True)

if __name__ == "__main__":
    threading.Thread(target=newPoller.pollForever, args=(db,), daemon=True).start()
    for stopSignal in (signal.SIGTERM, signal.SIGHUP):    # closing the terminal or `kill` should also stop ngrok
        signal.signal(stopSignal, lambda *args: sys.exit(0))
    if "--no-tunnel" not in sys.argv:               # python3 app.py --no-tunnel to skip ngrok
        threading.Thread(target=startTunnel, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)