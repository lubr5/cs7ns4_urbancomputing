import time
from datetime import datetime
import requests
from firebase_admin import firestore

URL = "https://dublincityairandnoise.ie/assets/php/get-monitors.php"
COLLECTION = "open_data_readings"
POLL_SECONDS = 300

# monitor_id -> last reading_id written, so unchanged monitors are not rewritten
LAST_SEEN = {}

# air quality monitors are in the same feed, so keep only the noise ones
def isNoiseMonitor(monitor):
    return (monitor.get("monitor_type") or {}).get("category") == "noise"

# the API sends some numbers as strings (e.g. latitude), so convert safely
def toFloat(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

# one Firestore document per new reading: reading + hourly/daily average
def buildDocument(monitor):
    reading = monitor.get("latest_reading") or {}
    hourly = monitor.get("latest_hourly_average") or {}
    daily = monitor.get("latest_average") or {}

    return {
        "monitor_id": monitor.get("monitor_id"),
        "code": monitor.get("code"),
        "label": monitor.get("label"),
        "location": monitor.get("location"),
        "latitude": toFloat(monitor.get("latitude")),
        "longitude": toFloat(monitor.get("longitude")),
        "reading_id": reading.get("reading_id"),
        "recorded_at": reading.get("recorded_at"),   # as sent by DCC
        "LAeq": reading.get("laeq"),                 # dB(A)
        "LAFmax": reading.get("lafmax"),             # dB(A)
        "hourly_average": hourly.get("value"),
        "hourly_average_time": hourly.get("datetime"),
        "daily_average": daily.get("value"),
        "daily_average_date": daily.get("date"),
        "current_rating": monitor.get("current_rating"),
        "received_at": firestore.SERVER_TIMESTAMP,   # when the laptop got it
    }

# request the current state of all monitors and write the ones that changed
def poll(db):
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    monitors = [m for m in response.json() if isNoiseMonitor(m)]

    written = 0
    for monitor in monitors:
        doc = buildDocument(monitor)
        readingId = doc["reading_id"]
        if readingId is None or LAST_SEEN.get(doc["monitor_id"]) == readingId:
            continue                                  # no new reading, skip the write
        # reading_id in the document id means a repeat of the same reading overwrites itself
        db.collection(COLLECTION).document(f"{doc['code']}_{readingId}").set(doc)
        LAST_SEEN[doc["monitor_id"]] = readingId
        written += 1
    return written

# background loop, so app keeps the DCC data fresh
def pollForever(db):
    while True:
        try:
            print(f"[{datetime.now():%H:%M:%S}] {poll(db)} new reading(s) written")
        except Exception as error:                    # a failed poll should not stop the run
            print(f"[{datetime.now():%H:%M:%S}] poll failed: {error}")
        time.sleep(POLL_SECONDS)
