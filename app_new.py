import os
import uuid
import base64
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
import requests

load_dotenv()
app = Flask(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

RENDER_DOMAIN = os.getenv("RENDER_DOMAIN")   # https://xxx.onrender.com

# -----------------------------------------------------
# 1. GENERATE TELUGU TTS (WAV 8kHz)
# -----------------------------------------------------
@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text")
    voice = data.get("voice", "bulbul:v2")  # Telugu Native Voice

    sarvam_url = "https://api.sarvam.ai/text-to-speech"

    payload = {
        "input": text,
        "voice": voice,
        "output_format": "wav",
        "sample_rate": 8000   # REQUIRED for Twilio
    }

    headers = {
        "Content-Type": "application/json",
        "API-Key": SARVAM_API_KEY
    }

    res = requests.post(sarvam_url, json=payload, headers=headers)

    if res.status_code != 200:
        return jsonify({"error": res.text}), 500

    audio_b64 = res.json().get("audio_base64")
    audio_bytes = base64.b64decode(audio_b64)

    filename = f"{uuid.uuid4()}.wav"
    filepath = f"/tmp/{filename}"

    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    # Return public audio URL
    return jsonify({"url": f"{RENDER_DOMAIN}/audio/{filename}"})


# -----------------------------------------------------
# 2. SERVE AUDIO FILE TO TWILIO
# -----------------------------------------------------
@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_file(f"/tmp/{filename}", mimetype="audio/wav")


# -----------------------------------------------------
# 3. INCOMING CALL HANDLER (TELUGU RESPONSE)
# -----------------------------------------------------
@app.route("/voice", methods=["POST"])
def voice_incoming():
    text = "నమస్కారం. ఇది ఒక తెలుగు పరీక్ష కాల్."

    tts_res = requests.post(
        f"{RENDER_DOMAIN}/tts",
        json={"text": text}
    ).json()

    audio_url = tts_res["url"]

    vr = VoiceResponse()
    vr.play(audio_url)

    return str(vr)


# -----------------------------------------------------
# 4. OUTGOING CALL TRIGGER
# -----------------------------------------------------
@app.route("/call", methods=["GET"])
def call_user():
    to_number = request.args.get("to")

    client = Client(TWILIO_SID, TWILIO_AUTH)

    call = client.calls.create(
        to=to_number,
        from_=TWILIO_NUMBER,
        url=f"{RENDER_DOMAIN}/outbound"
    )

    return jsonify({"status": "calling", "call_sid": call.sid})


# -----------------------------------------------------
# 5. OUTBOUND CALL XML (TELUGU)
# -----------------------------------------------------
@app.route("/outbound", methods=["POST"])
def outbound():
    text = "హలో. ఇది ట్విలియో ద్వారా మాట్లాడుతున్న తెలుగు వాయిస్ మెసేజ్."

    tts_res = requests.post(
        f"{RENDER_DOMAIN}/tts",
        json={"text": text}
    ).json()

    audio_url = tts_res["url"]

    vr = VoiceResponse()
    vr.play(audio_url)

    return str(vr)


@app.route("/")
def home():
    return "Twilio + Sarvam Telugu Voice Bot Running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
