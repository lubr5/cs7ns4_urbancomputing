"""
Receives Sensor Logger's HTTP Push and stores it in Firestore using the same
columns as the Assignment 2 dataset:

    time, UTC, IST, seconds_elapsed, dBFS, latitude, longitude

Sensor Logger sends microphone and location readings as separate entries.
Like the Assignment 2 merge, every MICROPHONE reading becomes one row and takes
the most recent location fix at or before it (the location is held until the
next fix arrives).

Each 1-second batch is stored as ONE Firestore document (about 600 writes for a
10-minute walk; the free plan allows 20,000 writes per day).
"""
import threading
from datetime import datetime, timedelta, timezone

import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, request

COLLECTION = "sensor_batches"
COLUMNS = ["time", "UTC", "IST", "seconds_elapsed", "dBFS", "latitude", "longitude"]

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
app = Flask(__name__)

SESSIONS = {}
LOCK = threading.Lock()

# Nanoseconds since epoch to UTC conversion (as per assignment 2)
def nanosecondsToUTC(ns):
    seconds, remainder_ns = divmod(int(ns), 10**9)
    return (datetime.fromtimestamp(seconds, tz=timezone.utc)
            + timedelta(microseconds=remainder_ns // 1000))

# Helper for IST conversion - March and October have 31 days
def lastSunday(year, month):
    day = datetime(year, month, 31, 1, tzinfo=timezone.utc)  # March and October have 31 days
    return day - timedelta(days=(day.weekday() + 1) % 7)

# UTC to IST conversion (as per assignment 2)
def UTCtoIST(utc_dt):
    start, end = lastSunday(utc_dt.year, 3), lastSunday(utc_dt.year, 10)
    return 1 if start <= utc_dt < end else 0

# Time in format dd:mm:yyyy hh:mm:ss (as per assignment 2)
def ddmmyyyyhhmmssFormat(ns):
    seconds = int(ns) // 10**9 + (1 if int(ns) % 10**9 >= 5 * 10**8 else 0)
    utc = datetime.fromtimestamp(seconds, tz=timezone.utc)
    local = utc + timedelta(hours=UTCtoIST(utc))
    fmt = "%d:%m:%Y %H:%M:%S"
    return utc.strftime(fmt), local.strftime(fmt)

# merge location & microphone data - using my columns format from assignment 2
def buildDatabaseRows(sessionId, readings):
    with LOCK:
        state = SESSIONS.setdefault(sessionId, {"t0": None, "latitude": None, "longitude": None})
        rows = []
        for r in sorted(readings, key=lambda r: int(r.get("time", 0))):
            values = r.get("values", {})
            if r.get("name") == "location": # project out the location values to match the microphone timing
                if "latitude" in values and "longitude" in values:
                    state["latitude"], state["longitude"] = values["latitude"], values["longitude"]
            elif r.get("name") == "microphone" and "dBFS" in values:
                ns = int(r["time"])
                if state["t0"] is None:
                    state["t0"] = ns          # first microphone reading = 0 seconds
                utcString, istString = ddmmyyyyhhmmssFormat(ns)

                # populate my column format 
                rows.append({
                    "time": str(ns),          # text, so no client loses digits
                    "UTC": utcString,
                    "IST": istString,
                    "seconds_elapsed": round((ns - state["t0"]) / 1e9, 3),
                    "dBFS": values["dBFS"],
                    "latitude": state["latitude"],    
                    "longitude": state["longitude"],
                })
        return rows

# Batching required to not go over Firebase rate limits
def buildBatch(body):
    if isinstance(body, dict):
        readings, meta = body.get("payload", []), body
    else:
        readings, meta = body, {}

    sessionId = meta.get("sessionId") or "unknown-session"
    rows = buildDatabaseRows(sessionId, readings)
    times = [nanosecondsToUTC(r["time"]) for r in rows]

    doc = {
        "sessionId": meta.get("sessionId"),
        "deviceId": meta.get("deviceId"),
        "messageId": meta.get("messageId"),
        "count": len(rows),
        "first_time": min(times) if times else None,   # real timestamps, for querying
        "last_time": max(times) if times else None,
        "received_at": firestore.SERVER_TIMESTAMP,     # when the laptop got it
        "readings": rows,                              # the Assignment 2 columns
    }
    message = meta.get("messageId")
    doc_id = f"{meta['sessionId']}_{int(message):06d}" if meta.get("sessionId") and message is not None else None
    return doc_id, doc

# endpoint that sensor logger posts to
@app.route("/data", methods=["POST"])
def receive_data():
    doc_id, doc = buildBatch(request.get_json(force=True))
    ref = db.collection(COLLECTION)
    (ref.document(doc_id) if doc_id else ref.document()).set(doc)
    print(f"batch {doc['messageId']}: {doc['count']} rows")
    return jsonify({"received": doc["count"]}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)