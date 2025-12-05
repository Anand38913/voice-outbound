import os
import uuid
import base64
import mimetypes
from typing import Optional
from flask import Flask, request, jsonify, send_file
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

# Store call state in memory
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
        "ask_more": "మీకు ఇంకా ఏవైనా ప్రశ్నలు ఉన్నాయా? కొనసాగించడానికి 1 నొక్కండి, భాషను మార్చడానికి 2 నొక్కండి, లేదా కాల్ ముగించడానికి 3 నొక్కండి.",
        "goodbye": "TGSPDCL కు కాల్ చేసినందుకు ధన్యవాదాలు. వీడ్కోలు.",
        "no_input": "నాకు మీ ఇన్‌పుట్ అందలేదు. దయచేసి మళ్లీ ప్రయత్నించండి.",
        "change_language": "భాషను మార్చడానికి, ఇంగ్లీష్ కోసం 1 నొక్కండి, హిందీ కోసం 2 నొక్కండి, తెలుగు కోసం 3 నొక్కండి."
    }
}

HYDERABAD_EB_INFO = {
    "board_name": "TGSPDCL - Telangana Southern Power Distribution Company Limited",
    "customer_care": "040-23552222",
    "toll_free": "1800-425-1912",
    "website": "https://tgsouthernpower.org"
}


def twilio_client() -> Optional[Client]:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        return None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def download_twilio_recording(recording_url: str) -> str:
    """Download Twilio recording and return local file path."""
    print(f"[DEBUG] Downloading recording from: {recording_url}")
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
    print(f"[DEBUG] Recording saved to: {path}")
    return path


def sarvam_stt(audio_path: str, language_code: str = "en-IN") -> str:
    """Send audio file to Sarvam STT and return the transcribed text."""
    print(f"[DEBUG STT] Starting STT for language: {language_code}, file: {audio_path}")
    
    if not (SARVAM_API_KEY and SARVAM_STT_URL):
        raise RuntimeError("Sarvam STT not configured")

    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}"}
    data_payload = {
        "language_code": language_code,
        "model": "saaras:v1"
    }
    
    with open(audio_path, "rb") as fh:
        files = {"file": (os.path.basename(audio_path), fh, "audio/wav")}
        print(f"[DEBUG STT] Sending request to: {SARVAM_STT_URL}")
        resp = requests.post(SARVAM_STT_URL, headers=headers, files=files, data=data_payload, timeout=60)
    
    print(f"[DEBUG STT] Response status: {resp.status_code}")
    print(f"[DEBUG STT] Response body: {resp.text[:500]}")
    resp.raise_for_status()
    
    data = resp.json()
    transcript = data.get("text") or data.get("transcript") or ""
    print(f"[DEBUG STT] Transcribed text: '{transcript}'")
    return transcript


def sarvam_tts(text: str, language_code: str = "en-IN") -> str:
    """Send text to Sarvam TTS and return path to generated audio file."""
    print(f"[DEBUG TTS] ===== STARTING TTS =====")
    print(f"[DEBUG TTS] Language: {language_code}")
    print(f"[DEBUG TTS] Text: '{text}'")
    print(f"[DEBUG TTS] Text length: {len(text)} chars")
    
    if not (SARVAM_API_KEY and SARVAM_TTS_URL):
        raise RuntimeError("Sarvam TTS not configured")

    # Model selection based on language
    if language_code == "hi-IN":
        model = "bulbul:v1"
        speaker = ""
    elif language_code == "te-IN":
        model = "sarvam-tts-te-v1"
        speaker = ""
    else:
        model = "bulbul:v1"
        speaker = ""

    print(f"[DEBUG TTS] Using model: {model}, speaker: '{speaker}'")

    headers = {
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "Content-Type": "application/json"
    }
    
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

    print(f"[DEBUG TTS] Sending request to: {SARVAM_TTS_URL}")
    print(f"[DEBUG TTS] Payload: {payload}")

    resp = None
    try:
        resp = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, timeout=60)
        print(f"[DEBUG TTS] Response status: {resp.status_code}")
        print(f"[DEBUG TTS] Response headers: {dict(resp.headers)}")
        print(f"[DEBUG TTS] Response body (first 2000 chars): {resp.text[:2000]}")
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ERROR TTS] Request failed: {str(e)}")
        if resp is not None:
            print(f"[ERROR TTS] Status: {resp.status_code}")
            print(f"[ERROR TTS] Body: {resp.text}")
        raise

    # Extract audio from response
    audio_b64 = None
    audio_mime = None

    print(f"[DEBUG TTS] Parsing response, keys: {list(data.keys())}")

    # Try to find audio in response
    audios = data.get("audios")
    if audios:
        print(f"[DEBUG TTS] Found 'audios' key with {len(audios)} items")
        first = audios[0]
        print(f"[DEBUG TTS] First audio item type: {type(first)}")
        
        if isinstance(first, dict):
            print(f"[DEBUG TTS] First audio item keys: {list(first.keys())}")
            audio_b64 = first.get("audio") or first.get("data") or first.get("base64")
            audio_mime = first.get("mime") or first.get("format")
        elif isinstance(first, str):
            if first.startswith("data:"):
                header, b64 = first.split(",", 1)
                audio_b64 = b64
                if ";" in header:
                    audio_mime = header.split(":")[1].split(";")[0]
            else:
                audio_b64 = first

    if not audio_b64:
        for k in ("audio", "audio_base64", "base64_audio", "file"):
            if k in data:
                print(f"[DEBUG TTS] Found audio in key: {k}")
                audio_b64 = data[k]
                break

    if not audio_b64:
        print(f"[ERROR TTS] No audio base64 found in response!")
        print(f"[ERROR TTS] Full response: {data}")
        raise RuntimeError("No audio returned from TTS")

    print(f"[DEBUG TTS] Audio base64 length: {len(audio_b64)} chars")
    print(f"[DEBUG TTS] Audio MIME type: {audio_mime}")

    # Decode and determine file extension
    try:
        audio_bytes = base64.b64decode(audio_b64)
        print(f"[DEBUG TTS] Decoded audio bytes: {len(audio_bytes)} bytes")
    except Exception as e:
        print(f"[ERROR TTS] Failed to decode base64: {e}")
        raise

    ext = ".wav"
    if audio_mime:
        ext = mimetypes.guess_extension(audio_mime) or ext
    
    # Check magic bytes
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
        ext = ".mp3"
        print(f"[DEBUG TTS] Detected MP3 format from magic bytes")
    elif audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        ext = ".wav"
        print(f"[DEBUG TTS] Detected WAV format from magic bytes")

    filename = f"reply_{uuid.uuid4().hex}{ext}"
    path = os.path.join(REPLIES_DIR, filename)
    
    try:
        with open(path, "wb") as f:
            f.write(audio_bytes)
        print(f"[DEBUG TTS] Successfully wrote file: {path}")
        print(f"[DEBUG TTS] File size: {os.path.getsize(path)} bytes")
    except Exception as e:
        print(f"[ERROR TTS] Failed to write file: {e}")
        raise

    # Verify file was created
    if not os.path.exists(path):
        print(f"[ERROR TTS] File does not exist after writing: {path}")
        raise RuntimeError(f"Failed to create audio file: {path}")

    print(f"[DEBUG TTS] ===== TTS COMPLETED SUCCESSFULLY =====")
    return path


def process_user_query(user_text: str, language: str = "en") -> str:
    """Process user query and provide relevant EB information."""
    user_text = (user_text or "").strip().lower()
    
    print(f"[DEBUG QUERY] Language: {language}, Text: '{user_text}'")
    
    if not user_text:
        return LANGUAGE_PROMPTS[language]["no_input"]
    
    if any(word in user_text for word in ["bill", "payment", "dues", "pay", "बिल", "भुगतान", "బిల్", "బిల్లు", "చెల్లింపు"]):
        if language == "hi":
            return f"बिल भुगतान के लिए {HYDERABAD_EB_INFO['customer_care']} पर संपर्क करें।"
        elif language == "te":
            return f"బిల్లు చెల్లింపు కోసం {HYDERABAD_EB_INFO['customer_care']} కు కాల్ చేయండి।"
        else:
            return f"For bill payment, contact {HYDERABAD_EB_INFO['customer_care']}."
    
    elif any(word in user_text for word in ["connection", "new", "कनेक्शन", "నया", "కనెక్షన్", "కొత్త"]):
        if language == "hi":
            return f"नए कनेक्शन के लिए {HYDERABAD_EB_INFO['toll_free']} पर कॉल करें।"
        elif language == "te":
            return f"కొత్త కనెక్షన్ కోసం {HYDERABAD_EB_INFO['toll_free']} కు కాల్ చేయండి।"
        else:
            return f"For new connection, call {HYDERABAD_EB_INFO['toll_free']}."
    
    else:
        if language == "hi":
            return f"अधिक जानकारी के लिए {HYDERABAD_EB_INFO['website']} पर जाएं।"
        elif language == "te":
            return f"మరింత సమాచారం కోసం {HYDERABAD_EB_INFO['website']} ని సందర్శించండి।"
        else:
            return f"For more information, visit {HYDERABAD_EB_INFO['website']}."


@app.route("/", methods=["GET"])
def index():
    return "Hyderabad EB IVR System - Diagnostic Mode", 200


@app.route("/test-tts/<language>", methods=["GET"])
def test_tts(language):
    """Test endpoint to verify TTS is working."""
    print(f"\n[TEST] Testing TTS for language: {language}")
    
    lang_map = {"en": "en-IN", "hi": "hi-IN", "te": "te-IN"}
    lang_code = lang_map.get(language, "en-IN")
    
    test_text = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["en"])["greeting"]
    
    try:
        audio_path = sarvam_tts(test_text, lang_code)
        return send_file(audio_path, mimetype="audio/wav")
    except Exception as e:
        print(f"[TEST ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/call", methods=["POST"])
def initiate_call():
    """Create an outbound Twilio call."""
    print(f"\n[CALL] Initiating call to {YOUR_PHONE_NUMBER}")
    
    client = twilio_client()
    if client is None:
        return jsonify({"error": "Twilio not configured"}), 500

    voice_url = f"{BASE_URL}/twilio/voice"
    print(f"[CALL] Voice URL: {voice_url}")
    
    call = client.calls.create(to=YOUR_PHONE_NUMBER, from_=TWILIO_FROM, url=voice_url)
    print(f"[CALL] Call SID: {call.sid}, Status: {call.status}")
    
    return jsonify({"sid": call.sid, "status": call.status}), 201


@app.route("/twilio/voice", methods=["GET", "POST"])
def twilio_voice():
    """Initial TwiML: Ask for language selection."""
    call_sid = request.values.get("CallSid")
    print(f"\n[VOICE] Call started: {call_sid}")
    
    vr = VoiceResponse()
    call_states[call_sid] = {"language": None, "interaction_count": 0}
    
    gather = Gather(num_digits=1, action=f"{BASE_URL}/twilio/language", method="POST", timeout=5)
    gather.say(LANGUAGE_PROMPTS["en"]["welcome"], language="en-IN")
    vr.append(gather)
    vr.redirect(f"{BASE_URL}/twilio/voice")
    
    print(f"[VOICE] Sent TwiML: {str(vr)}")
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/language", methods=["POST"])
def twilio_language():
    """Handle language selection."""
    call_sid = request.values.get("CallSid")
    digits = request.values.get("Digits")
    
    print(f"\n[LANGUAGE] Call: {call_sid}, Digits: {digits}")
    
    language_map = {"1": "en", "2": "hi", "3": "te"}
    language = language_map.get(digits, "en")
    
    if call_sid in call_states:
        call_states[call_sid]["language"] = language
    else:
        call_states[call_sid] = {"language": language, "interaction_count": 0}
    
    print(f"[LANGUAGE] Selected language: {language}")
    
    vr = VoiceResponse()
    lang_code = LANGUAGES[language]["code"]
    greeting_text = LANGUAGE_PROMPTS[language]["greeting"]

    print(f"[LANGUAGE] Generating greeting TTS for: {language}")
    print(f"[LANGUAGE] Greeting text: '{greeting_text}'")

    try:
        # Generate TTS audio
        greeting_audio = sarvam_tts(greeting_text, lang_code)
        greeting_url = f"{BASE_URL}/replies/{os.path.basename(greeting_audio)}"
        
        print(f"[LANGUAGE] Generated audio file: {greeting_audio}")
        print(f"[LANGUAGE] Audio URL: {greeting_url}")
        
        vr.play(greeting_url)
        print(f"[LANGUAGE] Added Play instruction to TwiML")
        
    except Exception as e:
        print(f"[LANGUAGE ERROR] TTS failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Fallback
        if language in ["en", "hi"]:
            vr.say(greeting_text, language=lang_code)
            print(f"[LANGUAGE] Using fallback Say for {language}")
        else:
            vr.say("Sorry, there was an error. Please try again.", language="en-IN")
            print(f"[LANGUAGE] Using English fallback due to error")
    
    # Record user query
    vr.record(action=f"{BASE_URL}/twilio/recording", method="POST", max_length=60, play_beep=True, timeout=5)
    
    if language in ["en", "hi"]:
        vr.say(LANGUAGE_PROMPTS[language]["no_input"], language=lang_code)
    else:
        vr.say("I did not receive input.", language="en-IN")
    
    vr.redirect(f"{BASE_URL}/twilio/continue")
    
    print(f"[LANGUAGE] Final TwiML: {str(vr)}")
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/recording", methods=["POST"])
def twilio_recording():
    """Handle recording: transcribe, process, respond."""
    call_sid = request.values.get("CallSid")
    recording_url = request.form.get("RecordingUrl") or request.values.get("RecordingUrl")
    
    print(f"\n[RECORDING] Call: {call_sid}")
    print(f"[RECORDING] URL: {recording_url}")
    
    call_state = call_states.get(call_sid, {"language": "en", "interaction_count": 0})
    language = call_state["language"]
    lang_code = LANGUAGES[language]["code"]
    
    print(f"[RECORDING] Language: {language}")
    
    vr = VoiceResponse()
    
    if not recording_url:
        print(f"[RECORDING] No recording URL provided")
        vr.say("No recording received.", language="en-IN")
        vr.redirect(f"{BASE_URL}/twilio/continue")
        return str(vr), 200, {"Content-Type": "application/xml"}

    try:
        # Download and transcribe
        audio_path = download_twilio_recording(recording_url)
        user_text = sarvam_stt(audio_path, lang_code)
        
        # Process query
        reply_text = process_user_query(user_text, language)
        print(f"[RECORDING] Reply text: '{reply_text}'")
        
        # Generate response audio
        reply_audio_path = sarvam_tts(reply_text, lang_code)
        audio_url = f"{BASE_URL}/replies/{os.path.basename(reply_audio_path)}"
        
        print(f"[RECORDING] Reply audio URL: {audio_url}")
        
        vr.play(audio_url)
        
        call_state["interaction_count"] += 1
        call_states[call_sid] = call_state
        
        vr.redirect(f"{BASE_URL}/twilio/continue")
        
        print(f"[RECORDING] Success! TwiML: {str(vr)}")
        return str(vr), 200, {"Content-Type": "application/xml"}

    except Exception as e:
        print(f"[RECORDING ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        
        vr.say("Sorry, there was an error processing your request.", language="en-IN")
        vr.redirect(f"{BASE_URL}/twilio/continue")
        return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/continue", methods=["GET", "POST"])
def twilio_continue():
    """Ask if user wants to continue."""
    call_sid = request.values.get("CallSid")
    call_state = call_states.get(call_sid, {"language": "en", "interaction_count": 0})
    language = call_state["language"]
    lang_code = LANGUAGES[language]["code"]
    
    print(f"\n[CONTINUE] Call: {call_sid}, Language: {language}")
    
    vr = VoiceResponse()
    ask_more_text = LANGUAGE_PROMPTS[language]["ask_more"]
    
    try:
        # Generate TTS for continuation prompt
        ask_more_audio = sarvam_tts(ask_more_text, lang_code)
        ask_more_url = f"{BASE_URL}/replies/{os.path.basename(ask_more_audio)}"
        
        gather = Gather(num_digits=1, action=f"{BASE_URL}/twilio/action", method="POST", timeout=5)
        gather.play(ask_more_url)
        vr.append(gather)
        
        print(f"[CONTINUE] Using TTS audio for prompt")
        
    except Exception as e:
        print(f"[CONTINUE ERROR] {str(e)}")
        
        gather = Gather(num_digits=1, action=f"{BASE_URL}/twilio/action", method="POST", timeout=5)
        if language in ["en", "hi"]:
            gather.say(ask_more_text, language=lang_code)
        else:
            gather.say("Press 1 to continue, 2 to change language, or 3 to end.", language="en-IN")
        vr.append(gather)
    
    # Default: end call
    try:
        goodbye_audio = sarvam_tts(LANGUAGE_PROMPTS[language]["goodbye"], lang_code)
        goodbye_url = f"{BASE_URL}/replies/{os.path.basename(goodbye_audio)}"
        vr.play(goodbye_url)
    except:
        if language in ["en", "hi"]:
            vr.say(LANGUAGE_PROMPTS[language]["goodbye"], language=lang_code)
        else:
            vr.say("Thank you. Goodbye.", language="en-IN")
    
    vr.hangup()
    
    return str(vr), 200, {"Content-Type": "application/xml"}


@app.route("/twilio/action", methods=["POST"])
def twilio_action():
    """Handle user's next action choice."""
    call_sid = request.values.get("CallSid")
    digits = request.values.get("Digits")
    call_state = call_states.get(call_sid, {"language": "en", "interaction_count": 0})
    language = call_state["language"]
    lang_code = LANGUAGES[language]["code"]
    
    print(f"\n[ACTION] Call: {call_sid}, Digits: {digits}, Language: {language}")
    
    vr = VoiceResponse()
    
    if digits == "1":
        # Continue
        print(f"[ACTION] User chose to continue")
        try:
            greeting_audio = sarvam_tts(LANGUAGE_PROMPTS[language]["greeting"], lang_code)
            greeting_url = f"{BASE_URL}/replies/{os.path.basename(greeting_audio)}"
            vr.play(greeting_url)
        except:
            if language in ["en", "hi"]:
                vr.say(LANGUAGE_PROMPTS[language]["greeting"], language=lang_code)
            else:
                vr.say("How can I help you?", language="en-IN")
        
        vr.record(action=f"{BASE_URL}/twilio/recording", method="POST", max_length=60, play_beep=True, timeout=5)
        vr.redirect(f"{BASE_URL}/twilio/continue")
    
    elif digits == "2":
        # Change language
        print(f"[ACTION] User chose to change language")
        gather = Gather(num_digits=1, action=f"{BASE_URL}/twilio/language", method="POST", timeout=5)
        gather.say("Press 1 for English, 2 for Hindi, 3 for Telugu.", language="en-IN")
        vr.append(gather)
        vr.redirect(f"{BASE_URL}/twilio/continue")
    
    elif digits == "3":
        # End call
        print(f"[ACTION] User chose to end call")
        try:
            goodbye_audio = sarvam_tts(LANGUAGE_PROMPTS[language]["goodbye"], lang_code)
            goodbye_url = f"{BASE_URL}/replies/{os.path.basename}}