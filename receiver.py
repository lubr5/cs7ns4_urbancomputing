from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)

@app.route("/data", methods=["POST"])
def receive_data():
    batch = request.get_json()
    readings = batch if isinstance(batch, list) else [batch]

    for reading in readings:
        doc_id = str(reading.get("time"))  # nanosecond timestamp as unique ID
        db.collection("sensor_readings").document(doc_id).set(reading)

    return jsonify({"received": len(readings)}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
