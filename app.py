import os
import sys
import threading
import time
from flask import jsonify, request, send_from_directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))
import newPoller
import stationCalculations as stations
import userCalculations as user
from newReceiver import RECENT, TOKEN_PATTERN, app, db
LIVE_WINDOW_SECONDS = 30          # live = last 30 seconds
LIVE_MAX_AGE_SECONDS = 15         # kill phone after 15s
REFRESH_COOLDOWN_SECONDS = 60     # DCC only updates every few minutes, so more often is pointless
STATION_CACHE_SECONDS = 30        # reuse station list instead of re-reading Firestore

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

if __name__ == "__main__":
    threading.Thread(target=newPoller.pollForever, args=(db,), daemon=True).start()
    app.run(host="0.0.0.0", port=8000, threaded=True)