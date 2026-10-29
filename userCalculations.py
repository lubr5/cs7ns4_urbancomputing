# Calculations for how close the user is to a DCC station, averaging over the entire City's noise monitors
# Calculations for grouping the user's noise values by time of day and location
import math
import sys
from collections import defaultdict

MIN_VALID_DBFS = -110   #ignore dbfs values below this
COLLECTION = "live_batches"
CELL_METRES = 150   # patches of locations, for putting data on a map
METRES_PER_DEGREE_LAT = 111_320
CALIBRATION_OFFSET = 82.75   # dBFS -> estimated dB(A), from calibration.py (Chancery Park, 20/10/2026)
THRESHOLD_DBA = 70   # a reading above this counts as loud

# a reading is usable if it has a real dBFS level and a location
def isValid(reading):
    level = reading.get("dBFS")
    return level is not None and level > MIN_VALID_DBFS
def hasLocation(reading):
    return reading.get("latitude") is not None and reading.get("longitude") is not None

def toLevel(reading, offset=CALIBRATION_OFFSET):
    return reading["dBFS"] + offset

# average over decibels (log scale)
def leq(levels):
    levels = list(levels)
    if not levels:
        return None
    return 10 * math.log10(sum(10 ** (level / 10) for level in levels) / len(levels))

# average leq, peak and time above a threshold
def sessionSummary(readings, offset=CALIBRATION_OFFSET, threshold=None):
    levels = [toLevel(r, offset) for r in readings if isValid(r)]
    if not levels:
        return None
    summary = {
        "readings": len(levels),
        "duration_s": round(max(float(r["seconds_elapsed"]) for r in readings if isValid(r))
                            - min(float(r["seconds_elapsed"]) for r in readings if isValid(r)), 1),
        "leq": round(leq(levels), 1),
        "min": round(min(levels), 1),
        "peak": round(max(levels), 1),
    }
    if threshold is not None:
        above = sum(1 for level in levels if level > threshold)
        summary["percent_above_threshold"] = round(100 * above / len(levels), 1)
    return summary

# get time of day from IST format
def hourOfDay(reading):
    return int(reading["IST"].split(" ")[1].split(":")[0])

# Leq for each hour of the day across all the user's sessions
def byHourOfDay(readings, offset=CALIBRATION_OFFSET):
    groups = defaultdict(list)
    for r in readings:
        if isValid(r):
            groups[hourOfDay(r)].append(toLevel(r, offset))
    return {hour: {"leq": round(leq(levels), 1), "readings": len(levels)}
            for hour, levels in sorted(groups.items())}

# get the user's location (averaged across sessions)
def cellOf(latitude, longitude):
    latStep = CELL_METRES / METRES_PER_DEGREE_LAT
    lonStep = CELL_METRES / (METRES_PER_DEGREE_LAT * math.cos(math.radians(latitude)))
    return math.floor(latitude / latStep), math.floor(longitude / lonStep), latStep, lonStep

# Leq for each location across all the user's sessions
def byLocation(readings, offset=CALIBRATION_OFFSET):
    groups = defaultdict(list)
    steps = {}
    for r in readings:
        if isValid(r) and hasLocation(r):
            row, col, latStep, lonStep = cellOf(float(r["latitude"]), float(r["longitude"]))
            groups[(row, col)].append(toLevel(r, offset))
            steps[(row, col)] = (latStep, lonStep)
    cells = []
    for (row, col), levels in groups.items():
        latStep, lonStep = steps[(row, col)]
        cells.append({
            "latitude": round((row + 0.5) * latStep, 6),
            "longitude": round((col + 0.5) * lonStep, 6),
            "leq": round(leq(levels), 1),
            "readings": len(levels),
        })
    return cells

# all of one user's readings from Firestore, calculated by their token
def fetchUserReadings(token):
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccountKey.json"))
    db = firestore.client()

    readings = []
    for doc in db.collection(COLLECTION).where(filter=FieldFilter("token", "==", token)).stream():
        readings.extend(doc.to_dict().get("readings", []))
    return sorted(readings, key=lambda r: int(r["time"]))

if __name__ == "__main__":
    # python3 userCalculations.py <token>
    data = fetchUserReadings(sys.argv[1])
    print("session:", sessionSummary(data, threshold=THRESHOLD_DBA))
    print("by hour:", byHourOfDay(data))
    print("by location:", byLocation(data))