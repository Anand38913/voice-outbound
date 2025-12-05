import os
import uuid
from typing import Optional
from flask import Flask, request, jsonify, send_file, session
from dotenv import load_dotenv
import requests
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-here")

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

# Store call state in memory (use Redis/database for production)
call_states = {}

# Language configurations
LANGUAGES = {
    "en": {"name": "English", "code": "en-IN"},
    "hi": {"name": "Hindi", "code": "hi-IN"},
    "te": {"name": "Telugu", "code": "te-IN"}
}

LANGUAGE_PROMPTS = {
    "en": {
        "welcome": "Welcome to TGSPDCL Telangana Southern Power Distribution. Press 1 for English, Press 2 for Hindi, Press 3 for Telugu.",
        "greeting": "Welcome to TGSPDCL. Our customer care number is 040-23552222. Toll-free helpline is 1800-425-1912. How can I help you today?",
        "ask_more": "Do you have any other questions? Press 1 to continue, Press 2 to change language, or Press 3 to end the call.",
        "goodbye": "Thank you for calling TGSPDCL. Goodbye.",
        "no_input": "I did not receive your input. Please try again.",
        "change_language": "To change language, Press 1 for English, Press 2 for Hindi, Press 3 for Telugu."
    },
    "hi": {
        "welcome": "TGSPDCL तेलंगाना दक्षिणी विद्युत वितरण में आपका स्वागत है। अंग्रेजी के लिए 1 दबाएं, हिंदी के लिए 2 दबाएं, तेलुगु के लिए 3 दबाएं।",
        "greeting": "TGSPDCL में आपका स्वागत है। हमारा ग्राहक सेवा नंबर 040-23552222 है। टोल-फ्री हेल्पलाइन 1800-425-1912 है। मैं आज आपकी कैसे मदद कर सकता हूं?",
        "ask_more": "क्या आपके कोई अन्य प्रश्न हैं? जारी रखने के लिए 1 दबाएं, भाषा बदलने के लिए 2 दबाएं, या कॉल समाप्त करने के लिए 3 दबाएं।",
        "goodbye": "TGSPDCL को कॉल करने के लिए धन्यवाद। अलविदा।",
        "no_input": "मुझे आपका इनपुट नहीं मिला। कृपया पुनः प्रयास करें।",
        "change_language": "भाषा बदलने के लिए, अंग्रेजी के लिए 1 दबाएं, हिंदी के लिए 2 दबाएं, तेलुगु के लिए 3 दबाएं।"
    },
    "te": {
        "welcome": "TGSPDCL తెలంగాణ దక్షిణ విద్యుత్ పంపిణీకి స్వాగతం। ఇంగ్లీష్ కోసం 1 నొక్కండి, హిందీ కోసం 2 నొక్కండి, తెలుగు కోసం 3 నొక్కండి।",
        "greeting": "TGSPDCL కి స్వాగతం। మా కస్టమర్ కేర్ నంబర్ 040-23552222. టోల్-ఫ్రీ హెల్ప్‌లైన్ 1800-425-1912. నేను ఈరోజు మీకు ఎలా సహాయం చేయగలను?",
        "ask_more": "మీకు ఇంకా ఏవైనా ప్రశ్నలు ఉన్నాయా? కొనసాగించడానికి 1 నొక్కండి, భాషను మార్చడానికి 2 నొక్కండి, లేదా కాల్ ముగించడానికి 3 నొక్కండి।",
        "goodbye": "TGSPDCL కు కాల్ చేసినందుకు ధన్యవాదాలు। వీడ్కోలు।",
        "no_input": "నాకు మీ ఇన్‌పుట్ అందలేదు। దయచేసి మళ్లీ ప్రయత్నించండి।",
        "change_language": "భాషను మార్చడానికి, ఇంగ్లీష్ కోసం 1 నొక్కండి, హిందీ కోసం 2 నొక్కండి, తెలుగు కోసం 3 నొక్కండి।"
    }
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


def sarvam_stt(audio_path: str, language_code: str = "en-IN") -> str:
    """Send audio file to Sarvam STT and return the transcribed text."""
    if not (SARVAM_API_KEY and SARVAM_STT_URL):
        raise RuntimeError("Sarvam STT not configured (SARVAM_API_KEY/SARVAM_STT_URL)")

    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}"}
    
    # Prepare the request with language code
    data_payload = {
        "language_code": language_code,
        "model": "saaras:v1"
    }
    
    with open(audio_path, "rb") as fh:
        files = {"file": (os.path.basename(audio_path), fh, "audio/wav")}
        resp = requests.post(SARVAM_STT_URL, headers=headers, files=files, data=data_payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("text") or data.get("transcript") or ""


def sarvam_tts(text: str, language_code: str = "en-IN") -> str:
    """Send text to Sarvam TTS and return path to generated audio file (wav/mp3).
       This version is defensive: inspects response and chooses correct extension.
    """
    if not (SARVAM_API_KEY and SARVAM_TTS_URL):
        raise RuntimeError("Sarvam TTS not configured (SARVAM_API_KEY/SARVAM_TTS_URL)")

    # model selection (your mapping)
    if language_code == "hi-IN":
        model = "bulbul:v1"
        speaker = ""
    elif language_code == "te-IN":
        model = "sarvam-tts-te-v1"
        speaker = ""
    else:
        model = "bulbul:v1"
        speaker = ""

    print(f"[DEBUG] TTS request - lang: {language_code}, model: {model}, speaker: {speaker}, text_len={len(text)}")

    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "text": text,
        "target_language_code": language_code,
        "speaker": speaker,
        "pitch": 0,
        "pace": 1.0,
        "loudness": 1.5,
        "speech_sample_rate": 16000,
        "enable_preprocessing": True,
        "model": model
    }

    resp = None
    try:
        resp = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, timeout=60)
        # Always log status and body for debugging
        print(f"[DEBUG] Sarvam TTS status: {resp.status_code}")
        print(f"[DEBUG] Sarvam TTS body: {resp.text[:2000]}")  # truncate to avoid huge logs
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # provide richer log for debugging
        if resp is not None:
            print("[ERROR] Sarvam TTS failed:", resp.status_code, resp.text)
        raise

    # Try several common shapes:
    audio_b64 = None
    audio_mime = None

    # Case A: audios is list of base64 strings or data URIs
    audios = data.get("audios")
    if audios:
        first = audios[0]
        if isinstance(first, dict):
            # maybe {"audio": "...", "mime": "audio/wav"}
            audio_b64 = first.get("audio") or first.get("data") or first.get("base64")
            audio_mime = first.get("mime") or first.get("format")
        elif isinstance(first, str):
            # maybe "data:audio/wav;base64,AAA..."
            if first.startswith("data:"):
                # parse data URI
                header, b64 = first.split(",", 1)
                audio_b64 = b64
                # header example: data:audio/wav;base64
                if ";" in header:
                    audio_mime = header.split(":")[1].split(";")[0]
            else:
                audio_b64 = first

    # Case B: direct key 'audio' or 'audio_base64'
    if not audio_b64:
        for k in ("audio", "audio_base64", "base64_audio", "file"):
            if k in data:
                audio_b64 = data[k]
                break

    if not audio_b64:
        print("[ERROR] No audio base64 found in TTS response. Full response:")
        print(data)
        raise RuntimeError("No audio returned from TTS")

    # Determine extension
    ext = ".wav"
    if audio_mime:
        ext = mimetypes.guess_extension(audio_mime) or ext
    # If extension still None and base64 begins with MP3 magic after decode, fallback to .mp3
    audio_bytes = base64.b64decode(audio_b64)
    # Quick magic-byte detection:
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
        ext = ".mp3"
    elif audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        ext = ".wav"

    filename = f"reply_{uuid.uuid4().hex}{ext}"
    path = os.path.join(REPLIES_DIR, filename)
    with open(path, "wb") as f:
        f.write(audio_bytes)

    print(f"[DEBUG] Wrote TTS file: {path} (ext={ext})")
    return path



def process_user_query(user_text: str, language: str = "en") -> str:
    """Process user query and provide relevant EB information."""
    user_text = (user_text or "").strip().lower()
    
    # Log the transcribed text for debugging
    print(f"[DEBUG] Language: {language}, Transcribed text: {user_text}")
    
    if not user_text:
        return LANGUAGE_PROMPTS[language]["no_input"]
    
    # Keywords mapping to responses - Enhanced Telugu keywords
    if any(word in user_text for word in ["bill", "payment", "dues", "pay", "बिल", "भुगतान", "బిల్", "బిల్లు", "చెల్లింపు", "చెల్లించ"]):
        if language == "hi":
            return f"बिल भुगतान और पूछताछ के लिए, कृपया हमारे ग्राहक सेवा {HYDERABAD_EB_INFO['customer_care']} पर संपर्क करें या {HYDERABAD_EB_INFO['website']} पर जाएं। आप हमारी वेबसाइट पर ऑनलाइन भुगतान विकल्प भी उपयोग कर सकते हैं।"
        elif language == "te":
            return f"బిల్లు చెల్లింపు మరియు విచారణ కోసం, దయచేసి మా కస్టమర్ కేర్ {HYDERABAD_EB_INFO['customer_care']} ని సంప్రదించండి లేదా {HYDERABAD_EB_INFO['website']} ని సందర్శించండి। మీరు మా వెబ్‌సైట్‌లో ఆన్‌లైన్ చెల్లింపు ఎంపికలను కూడా ఉపయోగించవచ్చు।"
        else:
            return f"For bill payment and inquiry, please contact our customer care at {HYDERABAD_EB_INFO['customer_care']} or visit {HYDERABAD_EB_INFO['website']}. You can also use online payment options available on our website."
    
    elif any(word in user_text for word in ["connection", "new", "apply", "कनेक्शन", "नया", "आवेदन", "కనెక్షన్", "కొత్త", "దరఖాస్తు", "విద్యుత్"]):
        if language == "hi":
            return f"नए बिजली कनेक्शन के लिए आवेदन करने के लिए, हमारे कार्यालय में जाएं या {HYDERABAD_EB_INFO['toll_free']} पर कॉल करें। आपको पता प्रमाण, पहचान प्रमाण और संपत्ति दस्तावेज प्रदान करने होंगे।"
        elif language == "te":
            return f"కొత్త విద్యుత్ కనెక్షన్ కోసం దరఖాస్తు చేయడానికి, మా కార్యాలయాన్ని సందర్శించండి లేదా {HYDERABAD_EB_INFO['toll_free']} కు కాల్ చేయండి। మీరు చిరునామా రుజువు, గుర్తింపు రుజువు మరియు ఆస్తి పత్రాలను అందించాలి।"
        else:
            return f"To apply for a new electricity connection, visit our office or call {HYDERABAD_EB_INFO['toll_free']}. You will need to provide address proof, identity proof, and property documents."
    
    elif any(word in user_text for word in ["solar", "rooftop", "renewable", "सौर", "छत", "సౌర", "సోలార్", "పైకప్పు"]):
        if language == "hi":
            return f"हम छत पर सौर प्रतिष्ठानों के लिए नेट मीटरिंग प्रदान करते हैं। यह आपको अपनी बिजली उत्पन्न करने और अधिशेष बिजली को ग्रिड में बेचने की अनुमति देता है। नेट मीटरिंग के लिए आवेदन करने के लिए {HYDERABAD_EB_INFO['customer_care']} पर कॉल करें।"
        elif language == "te":
            return f"మేము పైకప్పు సౌర సంస్థాపనల కోసం నెట్ మీటరింగ్‌ను అందిస్తాము। ఇది మీ స్వంత విద్యుత్‌ను ఉత్పత్తి చేయడానికి మరియు మిగులు విద్యుత్‌ను గ్రిడ్‌కు విక్రయించడానికి మిమ్మల్ని అనుమతిస్తుంది। నెట్ మీటరింగ్ కోసం దరఖాస్తు చేయడానికి {HYDERABAD_EB_INFO['customer_care']} కు కాల్ చేయండి।"
        else:
            return f"We offer net metering for rooftop solar installations. This allows you to generate your own electricity and sell surplus power to the grid. Call {HYDERABAD_EB_INFO['customer_care']} to apply for net metering."
    
    elif any(word in user_text for word in ["complaint", "grievance", "issue", "problem", "शिकायत", "समस्या", "ఫిర్యాదు", "ఫిర్యాదులు", "సమస్య", "సమస్యలు"]):
        if language == "hi":
            return f"आप {HYDERABAD_EB_INFO['toll_free']} पर कॉल करके या {HYDERABAD_EB_INFO['website']} पर जाकर शिकायत दर्ज कर सकते हैं। हम 7 दिनों के भीतर समस्याओं को हल करने का लक्ष्य रखते हैं।"
        elif language == "te":
            return f"మీరు {HYDERABAD_EB_INFO['toll_free']} కు కాల్ చేయడం ద్వారా లేదా {HYDERABAD_EB_INFO['website']} ని సందర్శించడం ద్వారా ఫిర్యాదు దాఖలు చేయవచ్చు। మేము 7 రోజులలోపు సమస్యలను పరిష్కరించడానికి లక్ష్యంగా పెట్టుకున్నాము।"
        else:
            return f"You can file a complaint by calling {HYDERABAD_EB_INFO['toll_free']} or visiting {HYDERABAD_EB_INFO['website']}. We aim to resolve issues within 7 days."
    
    elif any(word in user_text for word in ["meter", "reading", "మీటర్", "రీడింగ్", "मीटर", "रीडिंग"]):
        if language == "hi":
            return f"आप हमारी वेबसाइट पर ऑनलाइन अपना मीटर रीडिंग देख सकते हैं या मीटर रीडिंग जानकारी के लिए हमें कॉल कर सकते हैं। शहर भर में स्मार्ट मीटरिंग लागू की जा रही है।"
        elif language == "te":
            return f"మీరు మా వెబ్‌సైట్‌లో ఆన్‌లైన్‌లో మీ మీటర్ రీడింగ్‌ను తనిఖీ చేయవచ్చు లేదా మీటర్ రీడింగ్ సమాచారం కోసం మమ్మల్ని కాల్ చేయవచ్చు। నగరం అంతటా స్మార్ట్ మీటరింగ్ అమలు చేయబడుతోంది।"
        else:
            return f"You can check your meter reading online on our website or call us for meter reading information. Smart metering is being rolled out across the city."
    
    else:
        if language == "hi":
            return f"आपकी पूछताछ के लिए धन्यवाद। अधिक जानकारी के लिए, कृपया {HYDERABAD_EB_INFO['website']} पर जाएं या हमारे टोल-फ्री नंबर {HYDERABAD_EB_INFO['toll_free']} पर कॉल करें।"
        elif language == "te":
            return f"మీ విచారణకు ధన్యవాదాలు। మరింత సమాచారం కోసం, దయచేసి {HYDERABAD_EB_INFO['website']} ని సందర్శించండి లేదా మా టోల్-ఫ్రీ నంబర్ {HYDERABAD_EB_INFO['toll_free']} కు కాల్ చేయండి।"
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


# @app.route("/twilio/voice", methods=["GET", "POST"])
@app.route("/twilio/voice", methods=["GET", "POST"])
def twilio_voice():
    """Initial TwiML: Ask for language selection."""
    call_sid = request.values.get("CallSid")
    vr = VoiceResponse()
    
    # Initialize call state
    call_states[call_sid] = {"language": None, "interaction_count": 0}
    
    # Ask for language selection
    gather = Gather(num_digits=1, action=f"{BASE_URL}/twilio/language", method="POST", timeout=5)
    # use say() here — Twilio will TTS English prompt
    gather.say(LANGUAGE_PROMPTS["en"]["welcome"], language="en-IN")
    vr.append(gather)
    
    # If no input, repeat
    vr.redirect(f"{BASE_URL}/twilio/voice")
    
    return str(vr), 200, {"Content-Type": "application/xml"}



# @app.route("/twilio/language", methods=["POST"])
# def twilio_language():
#     """Handle language selection."""
@app.route("/twilio/language", methods=["POST"])
def twilio_language():
    """Handle language selection."""
    call_sid = request.values.get("CallSid")
    digits = request.values.get("Digits")
    
    vr = VoiceResponse()
    
    # Map digit to language
    language_map = {"1": "en", "2": "hi", "3": "te"}
    language = language_map.get(digits, "en")
    
    # Update call state
    if call_sid in call_states:
        call_states[call_sid]["language"] = language
    else:
        call_states[call_sid] = {"language": language, "interaction_count": 0}
    
    print(f"[DEBUG] Language selected: {language} for call {call_sid}")
    
    # Greet in selected language and ask for query
    lang_code = LANGUAGES[language]["code"]

    # If Telugu (unsupported by Twilio Say), generate TTS via Sarvam and Play it
    if language == "te":
        # generate audio file for greeting
        greeting_audio = sarvam_tts(LANGUAGE_PROMPTS[language]["greeting"], lang_code)
        greeting_url = f"{BASE_URL}/replies/{os.path.basename(greeting_audio)}"
        vr.play(greeting_url)
    else:
        # Use Twilio Say for supported languages (English/Hindi)
        vr.say(LANGUAGE_PROMPTS[language]["greeting"], language=lang_code)
    
    # Record user's query
    vr.record(action=f"{BASE_URL}/twilio/recording", method="POST", max_length=60, play_beep=True, timeout=5)
    
    # No input message — use say() not play()
    vr.say(LANGUAGE_PROMPTS[language]["no_input"], language=lang_code)
    vr.redirect(f"{BASE_URL}/twilio/continue")
    
    return str(vr), 200, {"Content-Type": "application/xml"}




@app.route("/twilio/recording", methods=["POST"])
def twilio_recording():
    """Handle recording: transcribe, process, generate response, and ask for continuation."""
    call_sid = request.values.get("CallSid")
    recording_url = request.form.get("RecordingUrl") or request.values.get("RecordingUrl")
    
    # Get call state
    call_state = call_states.get(call_sid, {"language": "en", "interaction_count": 0})
    language = call_state["language"]
    lang_code = LANGUAGES[language]["code"]
    
    vr = VoiceResponse()
    
    if not recording_url:
        vr.play(LANGUAGE_PROMPTS[language]["no_input"], language=lang_code)
        vr.redirect(f"{BASE_URL}/twilio/continue")
        return str(vr), 200, {"Content-Type": "application/xml"}

    try:
        # Download and transcribe with language code
        audio_path = download_twilio_recording(recording_url)
        user_text = sarvam_stt(audio_path, lang_code)

        # Process query and generate response
        reply_text = process_user_query(user_text, language)

        # Generate audio response
        reply_audio_path = sarvam_tts(reply_text, lang_code)
        filename = os.path.basename(reply_audio_path)
        audio_url = f"{BASE_URL}/replies/{filename}"

        # Play response
        vr.play(audio_url)
        
        # Update interaction count
        call_state["interaction_count"] += 1
        call_states[call_sid] = call_state
        
        # Ask if user wants to continue
        vr.redirect(f"{BASE_URL}/twilio/continue")
        
        return str(vr), 200, {"Content-Type": "application/xml"}

    except Exception as e:
        print(f"Error: {str(e)}")
        vr.play(LANGUAGE_PROMPTS[language]["no_input"], language=lang_code)
        vr.redirect(f"{BASE_URL}/twilio/continue")
        return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/continue", methods=["GET", "POST"])
def twilio_continue():
    """Ask if user wants to continue, change language, or end call."""
    call_sid = request.values.get("CallSid")
    call_state = call_states.get(call_sid, {"language": "en", "interaction_count": 0})
    language = call_state["language"]
    lang_code = LANGUAGES[language]["code"]
    
    vr = VoiceResponse()
    
    # Ask for next action
    gather = Gather(num_digits=1, action=f"{BASE_URL}/twilio/action", method="POST", timeout=5)
    gather.say(LANGUAGE_PROMPTS[language]["ask_more"], language=lang_code)
    vr.append(gather)
    
    # If no input, end call
    vr.play(LANGUAGE_PROMPTS[language]["goodbye"], language=lang_code)
    
    vr.hangup()
    
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/action", methods=["POST"])
def twilio_action():
    """Handle user's choice to continue, change language, or end call."""
    call_sid = request.values.get("CallSid")
    digits = request.values.get("Digits")
    call_state = call_states.get(call_sid, {"language": "en", "interaction_count": 0})
    language = call_state["language"]
    lang_code = LANGUAGES[language]["code"]
    
    vr = VoiceResponse()
    
    if digits == "1":
        # Continue with another question
        vr.play(LANGUAGE_PROMPTS[language]["greeting"], language=lang_code)
        vr.record(action=f"{BASE_URL}/twilio/recording", method="POST", max_length=60, play_beep=True, timeout=5)
        vr.redirect(f"{BASE_URL}/twilio/continue")
    
    elif digits == "2":
        # Change language
        gather = Gather(num_digits=1, action=f"{BASE_URL}/twilio/language", method="POST", timeout=5)
        gather.play(LANGUAGE_PROMPTS[language]["change_language"], language=lang_code)
        vr.append(gather)
        vr.redirect(f"{BASE_URL}/twilio/continue")
    
    elif digits == "3":
        # End call
        vr.play(LANGUAGE_PROMPTS[language]["goodbye"], language=lang_code)
        vr.hangup()
        # Clean up call state
        if call_sid in call_states:
            del call_states[call_sid]
    
    else:
        # Invalid input, ask again
        vr.redirect(f"{BASE_URL}/twilio/continue")
    
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
