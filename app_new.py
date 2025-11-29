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

# Store user language preference (in production, use a database)
user_language = {}

# Language options
LANGUAGES = {
    "1": {"code": "en", "name": "English"},
    "2": {"code": "hi", "name": "Hindi"},
    "3": {"code": "te", "name": "Telugu"}
}

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


def sarvam_tts(text: str, language: str = "en") -> str:
    """Send text to Sarvam TTS and return path to generated MP3 file."""
    if not (SARVAM_API_KEY and SARVAM_TTS_URL):
        raise RuntimeError("Sarvam TTS not configured (SARVAM_API_KEY/SARVAM_TTS_URL)")

    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}", "Content-Type": "application/json"}
    payload = {"text": text, "format": "mp3"}
    
    # Add language if supported by Sarvam API
    if language in ["en", "hi", "te"]:
        payload["language"] = language
    
    resp = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, stream=True, timeout=60)
    resp.raise_for_status()

    filename = f"reply_{uuid.uuid4().hex}.mp3"
    path = os.path.join(REPLIES_DIR, filename)
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return path


def get_language_selection_text() -> str:
    """Generate language selection prompt."""
    return "Welcome to Hyderabad Electricity Board. Press 1 for English, Press 2 for Hindi, Press 3 for Telugu."


def get_eb_info_text(language: str = "en") -> str:
    """Generate text with Hyderabad EB information in selected language."""
    info = HYDERABAD_EB_INFO
    
    if language == "hi":  # Hindi
        text = f"{info['board_name']} में आपका स्वागत है। "
        text += f"हमारा ग्राहक सेवा नंबर {info['customer_care']} है। "
        text += f"टोल-फ्री हेल्पलाइन {info['toll_free']} है। "
        text += f"हमारी वेबसाइट {info['website']} पर जाएं। "
        text += "कृपया बताएं कि आपको किस सेवा के बारे में जानकारी चाहिए।"
    elif language == "te":  # Telugu
        text = f"{info['board_name']} కు స్వాగతం। "
        text += f"మా కస్టమర్ కేర్ నంబర్ {info['customer_care']}। "
        text += f"టోల్-ఫ్రీ హెల్ప్‌లైన్ {info['toll_free']}। "
        text += f"మా వెబ్‌సైట్ {info['website']} ను సందర్శించండి। "
        text += "దయచేసి మీకు ఏ సేవ గురించి సమాచారం కావాలో చెప్పండి।"
    else:  # English (default)
        text = f"Welcome to {info['board_name']}. "
        text += f"Our customer care number is {info['customer_care']}. "
        text += f"Toll-free helpline is {info['toll_free']}. "
        text += f"Visit our website at {info['website']}. "
        text += "Please tell us which service you need information about."
    
    return text


def process_user_query(user_text: str, language: str = "en") -> str:
    """Process user query and provide relevant EB information in selected language."""
    user_text = (user_text or "").strip().lower()
    info = HYDERABAD_EB_INFO
    
    if not user_text:
        if language == "hi":
            return "मैंने वह नहीं सुना। कृपया अपना प्रश्न दोहराएं।"
        elif language == "te":
            return "నేను అర్థం చేసుకోలేదు। దయచేసి మీ ప్రశ్నను మళ్లీ చెప్పండి।"
        else:
            return "I did not catch that. Please repeat your question."
    
    # Keywords mapping to responses
    if any(word in user_text for word in ["bill", "payment", "dues", "बिल", "भुगतान", "బిల్", "చెల్లింపు"]):
        if language == "hi":
            return f"बिल भुगतान और पूछताछ के लिए, कृपया {info['customer_care']} पर संपर्क करें या {info['website']} पर जाएं।"
        elif language == "te":
            return f"బిల్లు చెల్లింపు మరియు విచారణ కోసం, దయచేసి {info['customer_care']} కు సంప్రదించండి లేదా {info['website']} ను సందర్శించండి।"
        else:
            return f"For bill payment and inquiry, contact {info['customer_care']} or visit {info['website']}."
    
    elif any(word in user_text for word in ["connection", "new", "apply", "कनेक्शन", "नया", "కనెక్షన్", "కొత్త"]):
        if language == "hi":
            return f"नए बिजली कनेक्शन के लिए, {info['toll_free']} पर कॉल करें। आपको पता प्रमाण, पहचान प्रमाण और संपत्ति दस्तावेज़ की आवश्यकता होगी।"
        elif language == "te":
            return f"కొత్త విద్యుత్ కనెక్షన్ కోసం, {info['toll_free']} కు కాల్ చేయండి। మీకు చిరునామా రుజువు, గుర్తింపు రుజువు మరియు ఆస్తి పత్రాలు అవసరం।"
        else:
            return f"For new electricity connection, call {info['toll_free']}. You'll need address proof, ID proof, and property documents."
    
    elif any(word in user_text for word in ["solar", "rooftop", "renewable", "सौर", "छत", "సౌర", "పైకప్పు"]):
        if language == "hi":
            return f"हम छत पर सौर स्थापना के लिए नेट मीटरिंग प्रदान करते हैं। {info['customer_care']} पर कॉल करें।"
        elif language == "te":
            return f"మేము రూఫ్‌టాప్ సోలార్ ఇన్‌స్టాలేషన్‌ల కోసం నెట్ మీటరింగ్ అందిస్తాము। {info['customer_care']} కు కాల్ చేయండి।"
        else:
            return f"We offer net metering for rooftop solar. Call {info['customer_care']} to apply."
    
    elif any(word in user_text for word in ["complaint", "grievance", "issue", "problem", "शिकायत", "समस्या", "ఫిర్యాదు", "సమస్య"]):
        if language == "hi":
            return f"शिकायत दर्ज करने के लिए {info['toll_free']} पर कॉल करें या {info['website']} पर जाएं।"
        elif language == "te":
            return f"ఫిర్యాదు నమోదు చేయడానికి {info['toll_free']} కు కాల్ చేయండి లేదా {info['website']} ను సందర్శించండి।"
        else:
            return f"To file a complaint, call {info['toll_free']} or visit {info['website']}."
    
    else:
        if language == "hi":
            return f"अधिक जानकारी के लिए, {info['website']} पर जाएं या {info['toll_free']} पर कॉल करें।"
        elif language == "te":
            return f"మరింత సమాచారం కోసం, {info['website']} ను సందర్శించండి లేదా {info['toll_free']} కు కాల్ చేయండి।"
        else:
            return f"For more information, visit {info['website']} or call {info['toll_free']}."


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
    """Initial TwiML: Ask for language selection."""
    vr = VoiceResponse()
    call_sid = request.values.get("CallSid")
    
    # Ask for language selection using Twilio Say
    gather = vr.gather(num_digits=1, action=f"/twilio/language?CallSid={call_sid}", method="POST", timeout=5)
    gather.say(get_language_selection_text(), language="en-IN")
    
    # If no input, default to English
    vr.redirect(f"/twilio/language?CallSid={call_sid}&Digits=1")
    
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/language", methods=["POST"])
def twilio_language():
    """Handle language selection and provide EB info."""
    call_sid = request.values.get("CallSid")
    digits = request.values.get("Digits", "1")  # Default to English
    
    # Map digit to language
    language_map = {"1": "en", "2": "hi", "3": "te"}
    language = language_map.get(digits, "en")
    
    # Store language preference for this call
    user_language[call_sid] = language
    
    vr = VoiceResponse()
    
    try:
        # Provide EB information in selected language using Sarvam TTS
        greeting = get_eb_info_text(language)
        greeting_audio_path = sarvam_tts(greeting, language)
        greeting_filename = os.path.basename(greeting_audio_path)
        greeting_url = f"{BASE_URL}/replies/{greeting_filename}"
        
        vr.play(greeting_url)
        
        # Record user's query
        vr.record(action=f"/twilio/recording?CallSid={call_sid}", method="POST", max_length=60, play_beep=True)
        
        # No response message
        if language == "hi":
            no_response = "कोई प्रतिक्रिया नहीं मिली। कॉल करने के लिए धन्यवाद।"
        elif language == "te":
            no_response = "ప్రతిస్పందన రాలేదు। కాల్ చేసినందుకు ధన్యవాదాలు।"
        else:
            no_response = "No response received. Thank you for calling."
        
        no_response_audio_path = sarvam_tts(no_response, language)
        no_response_filename = os.path.basename(no_response_audio_path)
        no_response_url = f"{BASE_URL}/replies/{no_response_filename}"
        vr.play(no_response_url)
        
    except Exception as e:
        print(f"Error in language handler: {str(e)}")
        vr.say("Thank you for calling.", language="en-IN")
    
    vr.hangup()
    
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/recording", methods=["POST"])
def twilio_recording():
    """Handle recording: transcribe, process, generate response, and callback."""
    recording_url = request.form.get("RecordingUrl") or request.values.get("RecordingUrl")
    call_sid = request.values.get("CallSid")
    
    # Get language preference for this call
    language = user_language.get(call_sid, "en")
    
    if not recording_url:
        vr = VoiceResponse()
        if language == "hi":
            vr.say("कोई रिकॉर्डिंग नहीं मिली। कॉल करने के लिए धन्यवाद।", language="hi-IN")
        elif language == "te":
            vr.say("రికార్డింగ్ రాలేదు। కాల్ చేసినందుకు ధన్యవాదాలు।", language="te-IN")
        else:
            vr.say("No recording received. Thank you for calling.", language="en-IN")
        vr.hangup()
        return str(vr), 200, {"Content-Type": "application/xml"}

    try:
        # Download and transcribe
        audio_path = download_twilio_recording(recording_url)
        user_text = sarvam_stt(audio_path)

        # Process query and generate response in selected language
        reply_text = process_user_query(user_text, language)

        # Generate audio response in selected language
        reply_audio_path = sarvam_tts(reply_text, language)
        filename = os.path.basename(reply_audio_path)
        audio_url = f"{BASE_URL}/replies/{filename}"

        # Return TwiML to play response
        vr = VoiceResponse()
        vr.play(audio_url)
        
        # Closing message in selected language
        if language == "hi":
            vr.say("हैदराबाद इलेक्ट्रिसिटी बोर्ड सेवाओं का उपयोग करने के लिए धन्यवाद। अलविदा।", language="hi-IN")
        elif language == "te":
            vr.say("హైదరాబాద్ ఎలక్ట్రిసిటీ బోర్డ్ సేవలను ఉపయోగించినందుకు ధన్యవాదాలు। వీడ్కోలు।", language="te-IN")
        else:
            vr.say("Thank you for using Hyderabad Electricity Board services. Goodbye.", language="en-IN")
        
        vr.hangup()
        
        # Clean up language preference
        if call_sid in user_language:
            del user_language[call_sid]
        
        return str(vr), 200, {"Content-Type": "application/xml"}

    except Exception as e:
        print(f"Error: {str(e)}")
        vr = VoiceResponse()
        if language == "hi":
            vr.say("क्षमा करें, एक त्रुटि हुई। कॉल करने के लिए धन्यवाद।", language="hi-IN")
        elif language == "te":
            vr.say("క్షమించండి, లోపం సంభవించింది। కాల్ చేసినందుకు ధన్యవాదాలు।", language="te-IN")
        else:
            vr.say("Sorry, an error occurred. Thank you for calling.", language="en-IN")
        vr.hangup()
        
        # Clean up language preference
        if call_sid in user_language:
            del user_language[call_sid]
        
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
