import os
import uuid
from typing import Optional
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
import requests
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

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
YOUR_PHONE_NUMBER = os.environ.get("YOUR_PHONE_NUMBER", "+917995465001")

REPLIES_DIR = os.path.join(os.getcwd(), "replies")
os.makedirs(REPLIES_DIR, exist_ok=True)

# Hyderabad Electricity Board Information
HYDERABAD_EB_INFO = {
    "board_name": "TGSPDCL - Telangana Southern Power Distribution Company Limited",
    "customer_care": "040-23552222",
    "toll_free": "1800-425-1912",
    "website": "https://tgsouthernpower.org",
    "services": [
        "New electricity connection",
        "Bill payment and inquiry",
        "Meter reading",
        "Load enhancement request",
        "Disconnect and reconnect",
        "Net metering for rooftop solar",
        "Consumer grievances",
        "Subsidy schemes information"
    ],
    "schemes": [
        "PM Saubhagya: Free household electrification",
        "UJALA: Efficient LED distribution program",
        "PM-KUSUM: Solar pump set scheme",
        "Rooftop Solar with net-metering facility",
        "Agricultural tariff with seasonal rates",
        "BPL subsidy schemes"
    ]
}


def twilio_client() -> Optional[Client]:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        return None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def download_twilio_recording(recording_url: str) -> str:
    """Download Twilio recording and return local file path (wav)."""
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
    """Send audio file to Sarvam STT and return the transcribed text."""
    if not (SARVAM_API_KEY and SARVAM_STT_URL):
        raise RuntimeError("Sarvam STT not configured (SARVAM_API_KEY/SARVAM_STT_URL)")

    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}"}
    with open(audio_path, "rb") as fh:
        files = {"file": (os.path.basename(audio_path), fh, "audio/wav")}
        resp = requests.post(SARVAM_STT_URL, headers=headers, files=files, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("text") or data.get("transcript") or ""


def sarvam_tts(text: str) -> str:
    """Send text to Sarvam TTS and return path to generated MP3 file."""
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


def get_eb_info_text() -> str:
    """Generate text with Hyderabad EB information."""
    info = HYDERABAD_EB_INFO
    text = f"Welcome to {info['board_name']}. "
    text += f"Our customer care number is {info['customer_care']}. "
    text += f"Toll-free helpline is {info['toll_free']}. "
    text += f"Visit our website at {info['website']}. "
    text += "We provide services including: "
    text += ", ".join(info['services'][:4]) + ". "
    text += "Available schemes include: "
    text += ", ".join(info['schemes'][:3]) + ". "
    text += "Please tell us which service you need information about."
    return text


def process_user_query(user_text: str) -> str:
    """Process user query and provide relevant EB information."""
    user_text = (user_text or "").strip().lower()
    
    if not user_text:
        return "I did not catch that. Please repeat your question about our services or schemes."
    
    # Keywords mapping to responses
    if any(word in user_text for word in ["bill", "payment", "dues"]):
        return f"For bill payment and inquiry, please contact our customer care at {HYDERABAD_EB_INFO['customer_care']} or visit {HYDERABAD_EB_INFO['website']}. You can also use online payment options available on our website."
    
    elif any(word in user_text for word in ["connection", "new", "apply"]):
        return f"To apply for a new electricity connection, visit our office or call {HYDERABAD_EB_INFO['toll_free']}. You will need to provide address proof, identity proof, and property documents."
    
    elif any(word in user_text for word in ["solar", "rooftop", "renewable"]):
        return f"We offer net metering for rooftop solar installations. This allows you to generate your own electricity and sell surplus power to the grid. Call {HYDERABAD_EB_INFO['customer_care']} to apply for net metering."
    
    elif any(word in user_text for word in ["subsidy", "free", "scheme", "saubhagya"]):
        schemes = "; ".join(HYDERABAD_EB_INFO['schemes'])
        return f"We offer various schemes: {schemes}. Contact our office for eligibility and application details."
    
    elif any(word in user_text for word in ["complaint", "grievance", "issue", "problem"]):
        return f"You can file a complaint by calling {HYDERABAD_EB_INFO['toll_free']} or visiting {HYDERABAD_EB_INFO['website']}. We aim to resolve issues within 7 days."
    
    elif any(word in user_text for word in ["meter", "reading", "consumption"]):
        return "You can check your meter reading online on our website or call us for meter reading information. Smart metering is being rolled out across the city."
    
    else:
        return f"Thank you for your inquiry. For more information, please visit {HYDERABAD_EB_INFO['website']} or call our toll-free number {HYDERABAD_EB_INFO['toll_free']}."


@app.route("/", methods=["GET"])
def index():
    return "Hyderabad Electricity Board IVR System", 200


@app.route("/call", methods=["POST"])
def initiate_call():
    """Create an outbound Twilio call to your number."""
    client = twilio_client()
    if client is None:
        return jsonify({"error": "Twilio credentials not configured"}), 500

    voice_url = f"{BASE_URL}/twilio/voice"
    call = client.calls.create(to=YOUR_PHONE_NUMBER, from_=TWILIO_FROM, url=voice_url)
    return jsonify({"sid": call.sid, "status": call.status, "message": f"Calling {YOUR_PHONE_NUMBER}"}), 201


@app.route("/twilio/voice", methods=["GET", "POST"])
def twilio_voice():
    """Initial TwiML: greet and ask about Hyderabad EB, then record response."""
    vr = VoiceResponse()
    
    # Generate greeting with EB info
    greeting = get_eb_info_text()
    vr.say(greeting)
    
    # Record user's response
    vr.record(action="/twilio/recording", method="POST", max_length=60, play_beep=True)
    vr.say("No response received. Thank you for calling.")
    vr.hangup()
    
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/recording", methods=["POST"])
def twilio_recording():
    """Handle recording: transcribe, process, generate response, and callback."""
    recording_url = request.form.get("RecordingUrl") or request.values.get("RecordingUrl")
    if not recording_url:
        vr = VoiceResponse()
        vr.say("No recording received. Thank you for calling.")
        vr.hangup()
        return str(vr), 200, {"Content-Type": "application/xml"}

    try:
        # Download and transcribe
        audio_path = download_twilio_recording(recording_url)
        user_text = sarvam_stt(audio_path)

        # Process query and generate response
        reply_text = process_user_query(user_text)

        # Generate audio response
        reply_audio_path = sarvam_tts(reply_text)
        filename = os.path.basename(reply_audio_path)
        audio_url = f"{BASE_URL}/replies/{filename}"

        # Return TwiML to play response and ask for more info
        vr = VoiceResponse()
        vr.play(audio_url)
        vr.say("For more information, please visit our website or call the toll-free number provided.")
        vr.say("Thank you for using Hyderabad Electricity Board services. Goodbye.")
        vr.hangup()
        
        return str(vr), 200, {"Content-Type": "application/xml"}

    except Exception as e:
        print(f"Error: {str(e)}")
        vr = VoiceResponse()
        vr.say("Sorry, an error occurred. Thank you for calling.")
        vr.hangup()
        return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/replies/<path:filename>")
def serve_reply(filename: str):
    """Serve generated audio files."""
    path = os.path.join(REPLIES_DIR, filename)
    if not os.path.exists(path):
        return ("Not found", 404)
    return send_file(path, conditional=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
