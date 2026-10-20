# Calibration script for after I gather SensorLogger readings at a known DCC noise monitor
# Chancery Park (DCC monitor 11) is a moderately noisy monitor and closest to TCD
# This script will calculate the offset for dBFS to dB(A)
#
# C = station LAeq (dB(A)) - phone Leq (dBFS) where both measured the same noise.
# I visited Chancery Park and recorded data on my phone while polling the DCC API on 20 OCT 2025 @ 12:30-12:50
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from userCalculations import isValid, leq
TOKEN = "CALIB"
STATION_LABEL = "Noise 11"
STATION_RECORDED_AT = "2026-10-20 12:40:00"
WINDOW_MINUTES = 15
firebase_admin.initialize_app(credentials.Certificate("serviceAccountKey.json"))
db = firestore.client()
end = datetime.strptime(STATION_RECORDED_AT, "%Y-%m-%d %H:%M:%S")
start = end - timedelta(minutes=WINDOW_MINUTES)

# the station's db(A)
stationDocs = db.collection("open_data_readings").where(filter=FieldFilter("label", "==", STATION_LABEL)).stream()
stationdBA = next(d.to_dict()["LAeq"] for d in stationDocs if d.to_dict()["recorded_at"] == STATION_RECORDED_AT)

# the phone's dBFS in the same window
levels, seconds = [], set()
for doc in db.collection("live_batches").where(filter=FieldFilter("token", "==", TOKEN)).stream():
    for r in doc.to_dict()["readings"]:
        t = datetime.fromtimestamp(int(r["time"]) / 1e9)
        if isValid(r) and start <= t < end:
            levels.append(r["dBFS"])
            seconds.add(t.replace(microsecond=0))
phoneLeq = leq(levels)
C = round(stationdBA - phoneLeq, 2)
print(f"window {start:%H:%M}-{end:%H:%M}: phone covers {len(seconds)} of {WINDOW_MINUTES * 60} seconds")
print(f"station LAeq {stationdBA} dB(A), phone Leq {phoneLeq:.2f} dBFS")
print(f"C = {C} dB")