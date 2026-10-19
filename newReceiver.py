#NGROK URL: https://swapping-oncoming-joining.ngrok-free.dev

import re
import threading
from datetime import datetime, timedelta, timezone

import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, request

COLLECTION = "live_batches" # differentiate from existing firebase collection
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9]{4,32}$")

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
app = Flask(__name__)

SESSIONS = {}
LOCK = threading.Lock()

# Nanoseconds since epoch to UTC conversion
def nanosecondsToUTC(ns):
    seconds, remainder_ns = divmod(int(ns), 10**9)
    return (datetime.fromtimestamp(seconds, tz=timezone.utc)
            + timedelta(microseconds=remainder_ns // 1000))

# Helper for IST conversion
def lastSunday(year, month):
    day = datetime(year, month, 31, 1, tzinfo=timezone.utc)
    return day - timedelta(days=(day.weekday() + 1) % 7)

# UTC offset for Irish summer time: 1 between the last Sundays of March and October
def UTCtoIST(utc_dt):
    start, end = lastSunday(utc_dt.year, 3), lastSunday(utc_dt.year, 10)
    return 1 if start <= utc_dt < end else 0

# Time in format dd:mm:yyyy hh:mm:ss
def ddmmyyyyhhmmssFormat(ns):
    seconds = int(ns) // 10**9 + (1 if int(ns) % 10**9 >= 5 * 10**8 else 0)
    utc = datetime.fromtimestamp(seconds, tz=timezone.utc)
    local = utc + timedelta(hours=UTCtoIST(utc))
    fmt = "%d:%m:%Y %H:%M:%S"
    return utc.strftime(fmt), local.strftime(fmt)

# merge location & microphone data, one row per microphone reading
def buildDatabaseRows(sessionId, readings):
    with LOCK:
        state = SESSIONS.setdefault(sessionId, {"t0": None, "latitude": None, "longitude": None})
        rows = []
        for r in sorted(readings, key=lambda r: int(r.get("time", 0))):
            values = r.get("values", {})
            if r.get("name") == "location":
                if "latitude" in values and "longitude" in values:
                    state["latitude"], state["longitude"] = values["latitude"], values["longitude"]
            elif r.get("name") == "microphone" and "dBFS" in values:
                ns = int(r["time"])
                if state["t0"] is None:
                    state["t0"] = ns
                utcString, istString = ddmmyyyyhhmmssFormat(ns)
                rows.append({
                    "time": str(ns),
                    "UTC": utcString,
                    "IST": istString,
                    "seconds_elapsed": round((ns - state["t0"]) / 1e9, 3),
                    "dBFS": values["dBFS"],
                    "latitude": state["latitude"],
                    "longitude": state["longitude"],
                })
        return rows

def buildBatch(body, token):
    if isinstance(body, dict):
        readings, meta = body.get("payload", []), body
    else:
        readings, meta = body, {}

    sessionId = meta.get("sessionId") or "unknown-session"
    rows = buildDatabaseRows(sessionId, readings)
    times = [nanosecondsToUTC(r["time"]) for r in rows]

    doc = {
        "token": token,                                # pairs phone with a browser session
        "sessionId": meta.get("sessionId"),
        "deviceId": meta.get("deviceId"),
        "messageId": meta.get("messageId"),
        "count": len(rows),
        "first_time": min(times) if times else None,
        "last_time": max(times) if times else None,
        "received_at": firestore.SERVER_TIMESTAMP,
        "readings": rows,
    }
    message = meta.get("messageId")
    doc_id = f"{token}_{meta['sessionId']}_{int(message):06d}" if meta.get("sessionId") and message is not None else None
    return doc_id, doc

# endpoint that sensor logger posts to
@app.route("/data", methods=["POST"])
def receive_data():
    token = request.args.get("token", "")
    if not TOKEN_PATTERN.match(token):
        return jsonify({"error": "missing or invalid token"}), 400

    doc_id, doc = buildBatch(request.get_json(force=True), token)
    ref = db.collection(COLLECTION)
    (ref.document(doc_id) if doc_id else ref.document()).set(doc)
    print(f"[{token}] batch {doc['messageId']}: {doc['count']} rows")
    return jsonify({"received": doc["count"]}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

#NGROK URL: https://swapping-oncoming-joining.ngrok-free.dev