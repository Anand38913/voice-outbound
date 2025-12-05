import os
import base64
import uuid
from flask import Flask, request, jsonify, send_file
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
import requests

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

# -----------------------------------------------------
# 1. GENERATE TELUGU TTS & RETURN WAV (PLAYABLE ON TWILIO)
# -----------------------------------------------------
@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text", "")
    voice = data.get("voice", "bulbul:v2")  # Telugu Native

    sarvam_url = "https://api.sarvam.ai/text-to-speech"

    headers = {
        "Content-Type": "application/json",
        "API-Key": SARVAM_API_KEY
    }

    payload = {
        "input": text,
        "voice": voice,
        "output_format": "wav",          # REQUIRED for Twilio
        "sample_rate": 8000              # REQUIRED for Twilio
    }

    res = requests.post(sarvam_url, json=payload, headers=headers)

    if res.status_code != 200:
        return jsonify({"error": res.text}), 500

    audio_base64 = res.json().get("audio_base64")
    audio_bytes = base64.b64decode(audio_base64)

    file_name = f"audio_{uuid.uuid4()}.wav"
    file_path = f"/tmp/{file_name}"

    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    return jsonify({"url": f"/audio/{file_name}"})


# -----------------------------------------------------
# 2. SERVE WAV FILES TO TWILIO
# -----------------------------------------------------
@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_file(f"/tmp/{filename}", mimetype="audio/wav")


# -----------------------------------------------------
# 3. TWILIO INBOUND CALL — PLAYS TELUGU
# -----------------------------------------------------
@app.route("/voice", methods=["POST"])
def voice():
    vr = VoiceResponse()
    vr.play("https://your-render-domain.onrender.com/audio/sample.wav")
    return str(vr)


# -----------------------------------------------------
# 4. MAKE A TEST OUTGOING CALL FROM RENDER
# -----------------------------------------------------
@app.route("/call", methods=["GET"])
def make_call():
    to_number = request.args.get("to")

    client = Client(TWILIO_SID, TWILIO_AUTH)

    call = client.calls.create(
        to=to_number,
        from_=TWILIO_NUMBER,
        url="https://your-render-domain.onrender.com/outbound-xml"
    )

    return jsonify({"status": "call started", "sid": call.sid})


# -----------------------------------------------------
# 5. XML FOR OUTBOUND CALL
# -----------------------------------------------------
@app.route("/outbound-xml", methods=["POST"])
def outbound_xml():
    text = "నమస్కారం. ఇది ఒక పరీక్ష కాల్. ట్విలియో ద్వారా తెలుగు మాట్లాడుతున్నాం."

    # Request TTS
    wav = requests.post(
        "https://your-render-domain.onrender.com/tts",
        json={"text": text}
    ).json()["url"]

    vr = VoiceResponse()
    vr.play(f"https://your-render-domain.onrender.com{wav}")
    return str(vr)


@app.route("/")
def home():
    return "Sarvam + Twilio Voice Bot Running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
