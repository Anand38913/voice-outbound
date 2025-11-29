import os
import uuid
from typing import Optional
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
import requests
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Say, Record, Play

load_dotenv()

app = Flask(__name__)

# Configuration
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.environ.get("TWILIO_FROM")

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")
SARVAM_STT_URL = os.environ.get("SARVAM_STT_URL")
SARVAM_TTS_URL = os.environ.get("SARVAM_TTS_URL")

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")

REPLIES_DIR = os.path.join(os.getcwd(), "replies")
os.makedirs(REPLIES_DIR, exist_ok=True)


def twilio_client() -> Optional[Client]:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        return None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def download_twilio_recording(recording_url: str) -> str:
    """Download Twilio recording and return local file path (wav)."""
    # Twilio recording URL typically needs authentication; append .wav
    url_wav = recording_url
    if not url_wav.endswith(".wav") and not url_wav.endswith(".mp3"):
        url_wav = recording_url + ".wav"

    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None
    resp = requests.get(url_wav, auth=auth, stream=True, timeout=30)
    resp.raise_for_status()

    filename = f"recording_{uuid.uuid4().hex}.wav"
    path = os.path.join(REPLIES_DIR, filename)
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return path


def sarvam_stt(audio_path: str) -> str:
    """Send audio file to Sarvam STT and return the transcribed text.

    NOTE: This uses a generic multipart POST (`files={'file': ...}`) and
    Authorization: Bearer <API_KEY>. Update this to match Sarvam's actual API.
    """
    if not (SARVAM_API_KEY and SARVAM_STT_URL):
        raise RuntimeError("Sarvam STT not configured (SARVAM_API_KEY/SARVAM_STT_URL)")

    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}"}
    with open(audio_path, "rb") as fh:
        files = {"file": (os.path.basename(audio_path), fh, "audio/wav")}
        resp = requests.post(SARVAM_STT_URL, headers=headers, files=files, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    # Expecting {'text': '...'} or similar
    return data.get("text") or data.get("transcript") or ""


def sarvam_tts(text: str) -> str:
    """Send text to Sarvam TTS and return path to generated MP3 file.

    NOTE: This assumes TTS endpoint returns binary audio (audio/mpeg) in response.
    Update the payload/headers to match Sarvam's actual API.
    """
    if not (SARVAM_API_KEY and SARVAM_TTS_URL):
        raise RuntimeError("Sarvam TTS not configured (SARVAM_API_KEY/SARVAM_TTS_URL)")

    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}", "Content-Type": "application/json"}
    payload = {"text": text, "format": "mp3"}
    resp = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, stream=True, timeout=60)
    resp.raise_for_status()

    filename = f"reply_{uuid.uuid4().hex}.mp3"
    path = os.path.join(REPLIES_DIR, filename)
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return path


def simple_logic(text: str) -> str:
    """Very simple response logic. Replace with your application logic."""
    text = (text or "").strip().lower()
    if not text:
        return "I didn't catch that. Could you please repeat?"
    if "hello" in text or "hi" in text:
        return "Hello! How can I help you today?"
    if "name" in text:
        return "I'm your support assistant. How can I help?"
    # default echo
    return f"You said: {text}"


@app.route("/call", methods=["POST"])
def initiate_call():
    """Create an outbound Twilio call that will request our `/twilio/voice` endpoint."""
    data = request.get_json() or request.form or request.values
    to = data.get("to")
    if not to:
        return jsonify({"error": "Missing 'to' parameter (E.164 number)"}), 400

    client = twilio_client()
    if client is None:
        return jsonify({"error": "Twilio credentials not configured"}), 500

    # Twilio needs a publicly reachable URL. BASE_URL should point to your Render app.
    voice_url = f"{BASE_URL}/twilio/voice"

    call = client.calls.create(to=to, from_=TWILIO_FROM, url=voice_url)
    return jsonify({"sid": call.sid, "status": call.status}), 201


@app.route("/twilio/voice", methods=["GET", "POST"])
def twilio_voice():
    """Initial TwiML for the call: greet and record user's speech."""
    vr = VoiceResponse()
    vr.say("Welcome. Please say something after the beep. We will record your message.")
    vr.record(action="/twilio/recording", method="POST", max_length=30, play_beep=True)
    vr.say("No recording received. Goodbye.")
    vr.hangup()
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/recording", methods=["POST"])
def twilio_recording():
    """Handler Twilio calls after a recording completes.

    Twilio POST fields include `RecordingUrl` (and RecordingSid, etc.).
    We download the recording, send to Sarvam STT, get text, respond using Sarvam TTS,
    and return TwiML to play the generated audio. Then we record again to continue.
    """
    recording_url = request.form.get("RecordingUrl") or request.values.get("RecordingUrl")
    if not recording_url:
        return jsonify({"error": "No RecordingUrl in request"}), 400

    try:
        # download recording
        audio_path = download_twilio_recording(recording_url)

        # STT
        text = sarvam_stt(audio_path)

        # logic
        reply_text = simple_logic(text)

        # TTS
        reply_audio_path = sarvam_tts(reply_text)

        # serve audio at a public URL
        filename = os.path.basename(reply_audio_path)
        audio_url = f"{BASE_URL}/replies/{filename}"

        # Return TwiML to play the audio and then record again (loop)
        vr = VoiceResponse()
        vr.play(audio_url)
        # record again to allow multi-turn conversation
        vr.record(action="/twilio/recording", method="POST", max_length=30, play_beep=True)
        vr.say("Goodbye.")
        vr.hangup()
        return str(vr), 200, {"Content-Type": "application/xml"}

    except Exception as e:
        # On error, return TwiML apologizing and hang up
        vr = VoiceResponse()
        vr.say("Sorry, an error occurred. Goodbye.")
        vr.hangup()
        return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/replies/<path:filename>")
def serve_reply(filename: str):
    path = os.path.join(REPLIES_DIR, filename)
    if not os.path.exists(path):
        return ("Not found", 404)
    # Twilio supports mp3 and wav
    return send_file(path, conditional=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
