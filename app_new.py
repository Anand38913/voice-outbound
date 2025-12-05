import os
import uuid
import base64
import mimetypes
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
import requests
from twilio.twiml.voice_response import VoiceResponse

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "secret")

# -----------------------------
# ENV VARS
# -----------------------------
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_TTS_URL = os.getenv("SARVAM_TTS_URL")
SARVAM_STT_URL = os.getenv("SARVAM_STT_URL")

REPLIES_DIR = "replies"
os.makedirs(REPLIES_DIR, exist_ok=True)

# -----------------------------
# LANGUAGE MAP
# -----------------------------
LANG_MAP = {
    "1": "en-IN",
    "2": "hi-IN",
    "3": "te-IN"
}

WELCOME = {
    "en-IN": "Welcome to TGSPDCL Telangana power board. Press 1 for English, 2 for Hindi, 3 for Telugu.",
    "hi-IN": "TGSPDCL में आपका स्वागत है। अंग्रेजी के लिए 1 दबाएं, हिंदी के लिए 2 दबाएं, तेलुगु के लिए 3 दबाएं।",
    "te-IN": "TGSPDCL విద్యుత్ శాఖకు స్వాగతం. ఇంగ్లీష్ కోసం 1, హిందీ కోసం 2, తెలుగు కోసం 3 నొక్కండి."
}

# -----------------------------
# FIXED SARVAM TTS (WORKING TELUGU)
# -----------------------------
def sarvam_tts(text: str, lang: str = "en-IN") -> str:
    """Generate speech from Sarvam TTS and return path to MP3."""

    if lang == "te-IN":
        model = "sarvam-tts-te-v1"     # This works best for Telugu
    elif lang == "hi-IN":
        model = "bulbul:v2"
    else:
        model = "bulbul:v2"

    payload = {
        "text": text,
        "model": model,
        "target_language_code": lang,
        "pitch": 0,
        "pace": 1.0,
        "loudness": 1.2
    }

    headers = {
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "Content-Type": "application/json"
    }

    r = requests.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=40)
    r.raise_for_status()
    data = r.json()

    # Extract Base64 audio
    audio_b64 = None

    if "audios" in data:
        audio_b64 = data["audios"][0]

    if not audio_b64:
        raise Exception("No audio returned by Sarvam")

    # Remove data URL prefix if present
    if audio_b64.startswith("data:"):
        audio_b64 = audio_b64.split(",", 1)[1]

    audio_bytes = base64.b64decode(audio_b64)

    # Always save as mp3 because Twilio supports it
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(REPLIES_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    return filepath


# -----------------------------
# TWILIO ENTRYPOINT
# -----------------------------
@app.route("/twilio/voice", methods=["POST"])
def twilio_voice():
    resp = VoiceResponse()

    msg = WELCOME["en-IN"]
    audio_path = sarvam_tts(msg, "en-IN")

    resp.play(f"/reply/{os.path.basename(audio_path)}")
    resp.gather(numDigits=1, action="/select-language", timeout=6)

    return str(resp)


# -----------------------------
# LANGUAGE SELECTION
# -----------------------------
@app.route("/select-language", methods=["POST"])
def select_language():
    digit = request.values.get("Digits", "1")
    lang = LANG_MAP.get(digit, "en-IN")

    resp = VoiceResponse()

    message = WELCOME[lang]
    audio_path = sarvam_tts(message, lang)

    resp.play(f"/reply/{os.path.basename(audio_path)}")

    return str(resp)


# -----------------------------
# FILE SERVING FOR TWILIO
# -----------------------------
@app.route("/reply/<filename>")
def reply_file(filename):
    return send_file(os.path.join(REPLIES_DIR, filename), mimetype="audio/mpeg")


@app.route("/")
def home():
    return "TGSPDCL IVR is Running on Render", 200
