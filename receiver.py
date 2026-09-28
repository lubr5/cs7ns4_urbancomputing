from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
first_payload_seen = False


@app.route("/data", methods=["POST"])
def receive_data():
    global first_payload_seen
    body = request.get_json(force=True)

    if not first_payload_seen:
        print("FIRST PAYLOAD RECEIVED:")
        print(body)
        first_payload_seen = True

    # Accept either a bare list or an object wrapping a "payload" list
    if isinstance(body, dict):
        readings = body.get("payload", [body])
    else:
        readings = body

    batch = db.batch()
    count = 0
    for reading in readings:
        name = reading.get("name", "unknown")
        time_ns = reading.get("time")
        doc_id = f"{name}_{time_ns}"
        batch.set(db.collection("sensor_readings").document(doc_id), reading)
        count += 1
    batch.commit()

    return jsonify({"received": count}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)