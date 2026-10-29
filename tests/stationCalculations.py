# Calculations for how close the user is to a DCC station, averaging over the entire City's noise monitors
import math
import sys
from datetime import datetime, timezone
from userCalculations import leq

COLLECTION = "open_data_readings"
EARTH_RADIUS_METRES = 6_371_000
FETCH_LIMIT = 100    # newest documents for every monitor
RADIUS_METRES = 3000      # stations further than this do not count towards local level
POWER = 2                  # inverse-distance weight is 1 / distance^POWER

# newest reading for each monitor in Firestore
def fetchLatestStations():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("serviceAccountKey.json"))
    db = firestore.client()

    latest = {}
    newest = db.collection(COLLECTION).order_by("received_at", direction=firestore.Query.DESCENDING).limit(FETCH_LIMIT)
    for doc in newest.stream(): # newest first, so the first one seen per monitor wins
        station = doc.to_dict()
        if station.get("LAeq") is not None and station.get("latitude") is not None:
            latest.setdefault(station["code"], station)
    return list(latest.values())


# minutes since laptop received the reading
def ageMinutes(station, now=None):
    now = now or datetime.now(timezone.utc)
    return round((now - station["received_at"]).total_seconds() / 60, 1)

# distance in metres between two latitude/longitude points
def haversine(latitude1, longitude1, latitide2, longitude2):
    p1, p2 = math.radians(latitude1), math.radians(latitide2)
    dLatatitude, dLongitude = p2 - p1, math.radians(longitude2 - longitude1)
    a = math.sin(dLatatitude / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dLongitude / 2) ** 2
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(a))

# every station with its distance from the user, nearest first
def stationsByDistance(stations, latitude, longitude):
    ranked = [dict(s, distance_m=round(haversine(latitude, longitude, s["latitude"], s["longitude"])))
              for s in stations]
    return sorted(ranked, key=lambda s: s["distance_m"])
def nearestStation(stations, latitude, longitude):
    ranked = stationsByDistance(stations, latitude, longitude)
    return ranked[0] if ranked else None

# one figure for the whole city
def cityLevel(stations):
    level = leq(s["LAeq"] for s in stations)
    return None if level is None else round(level, 1)

# level around the user
def localLevel(stations, latitude, longitude, radius=RADIUS_METRES, power=POWER):
    weightedEnergy, totalWeight, used = 0.0, 0.0, 0
    for s in stationsByDistance(stations, latitude, longitude):
        if s["distance_m"] > radius:
            break
        weight = 1 / max(s["distance_m"], 1) ** power
        weightedEnergy += weight * 10 ** (s["LAeq"] / 10)
        totalWeight += weight
        used += 1
    if not used:
        return None
    return {"level": round(10 * math.log10(weightedEnergy / totalWeight), 1), "stations_used": used}

if __name__ == "__main__":
    # python3 stationCalculations.py <latitude> <longitude>
    latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    stations = fetchLatestStations()
    print(f"{len(stations)} stations")
    for s in stationsByDistance(stations, latitude, longitude):
        print(f"  {s['label']:<28} {s['distance_m']:>6} m  {s['LAeq']:>5} dB(A)  {ageMinutes(s)} min old")
    print("nearest:", nearestStation(stations, latitude, longitude)["label"])
    print("city level:", cityLevel(stations))
    print("local level:", localLevel(stations, latitude, longitude))