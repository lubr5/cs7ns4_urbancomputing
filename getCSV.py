import csv
import sys

import firebase_admin
from firebase_admin import credentials, firestore

COLLECTION = "sensor_batches"
COLUMNS = ["time", "UTC", "IST", "seconds_elapsed", "dBFS", "latitude", "longitude"]
TRIM_SECONDS = 5

session = sys.argv[1] if len(sys.argv) > 1 else None
out_path = sys.argv[2] if len(sys.argv) > 2 else "export.csv"

firebase_admin.initialize_app(credentials.Certificate("serviceAccountKey.json"))
db = firestore.client()

query = db.collection(COLLECTION)
if session:
    query = query.where("sessionId", "==", session)

batches = sorted((d.to_dict() for d in query.stream()), key=lambda b: b.get("firstTime") or 0)

# write firebase stored data back to a CSV
count = 0
with open(out_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(COLUMNS)
    for batch in batches:
        for row in batch.get("readings", []):
            if (row.get("seconds_elapsed") or 0) < TRIM_SECONDS: #cut out 5 seconds of recording, as per assignment 2
                continue
            if row.get("latitude") is None or row.get("longitude") is None: # cut any outlier that doesn't have location points projected correctly
                continue
            writer.writerow([row.get(c) for c in COLUMNS])
            count += 1

print(f"wrote {count} rows from {len(batches)} batches to {out_path}")