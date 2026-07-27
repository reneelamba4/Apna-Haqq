import os
import re
import json
from flask import Flask, request, abort
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

app = Flask(__name__)

# In-memory sessions are wiped on every Railway restart/redeploy, dropping
# every in-progress conversation mid-flow. If REDIS_URL is set (Railway's
# standard Redis add-on env var), sessions persist there instead, with a
# TTL so abandoned conversations don't accumulate forever. Falls back to
# the plain dict when REDIS_URL isn't set (e.g. local dev) so this never
# blocks running the bot without Redis provisioned.
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24h — long enough to resume a conversation, short enough not to leak profile data indefinitely
_redis_client = None
_REDIS_URL = os.environ.get("REDIS_URL")
if _REDIS_URL:
    import redis
    _redis_client = redis.from_url(_REDIS_URL, decode_responses=True)

_memory_sessions = {}

class SessionStore:
    # Every Redis call is wrapped: a transient Redis outage must never
    # crash a WhatsApp reply with a 500 — a rural user mid-conversation
    # has no way to know "wait and retry" and would just see silence.
    # On any Redis error we fall back to the in-memory dict for that one
    # operation; if Redis recovers, the next call uses it again.
    def __getitem__(self, sender):
        if _redis_client:
            try:
                raw = _redis_client.get(f"session:{sender}")
                if raw is not None:
                    return json.loads(raw)
            except redis.exceptions.RedisError:
                pass
        return _memory_sessions[sender]

    def __setitem__(self, sender, value):
        if _redis_client:
            try:
                _redis_client.setex(f"session:{sender}", SESSION_TTL_SECONDS, json.dumps(value))
                return
            except redis.exceptions.RedisError:
                pass
        _memory_sessions[sender] = value

    def __contains__(self, sender):
        if _redis_client:
            try:
                return _redis_client.exists(f"session:{sender}") == 1
            except redis.exceptions.RedisError:
                pass
        return sender in _memory_sessions

    def get(self, sender, default=None):
        # Single round-trip, no KeyError — used instead of the
        # `if sender not in sessions: ... ; session = sessions[sender]`
        # pattern, which does two separate Redis calls and can raise if the
        # key expires (24h TTL) or gets deleted by a concurrent/duplicate
        # webhook retry in the gap between them.
        if _redis_client:
            try:
                raw = _redis_client.get(f"session:{sender}")
                if raw is not None:
                    return json.loads(raw)
            except redis.exceptions.RedisError:
                pass
            return default
        return _memory_sessions.get(sender, default)

    def __delitem__(self, sender):
        if _redis_client:
            try:
                _redis_client.delete(f"session:{sender}")
            except redis.exceptions.RedisError:
                pass
        _memory_sessions.pop(sender, None)

sessions = SessionStore()

ELIGIBILITY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemes_eligibility.json")
with open(ELIGIBILITY_PATH, encoding="utf-8") as f:
    SCHEMES = json.load(f)

# _scheme_matches() indexes every one of these fields directly (scheme["x"],
# not scheme.get("x")) for every request. Validating once at boot — and
# failing loudly here — is much better than a malformed record silently
# breaking match() for every user on the next deploy.
_REQUIRED_SCHEME_KEYS = {
    'scheme_id','title','state','min_age','max_age','gender','max_income',
    'ration_card_types','occupation','marital_status','caste_category',
    'disability_required','disability_percent_min','land_ownership_required',
    'worker_board_registration_required','bank_account_required','benefit_summary',
}
for _s in SCHEMES:
    _missing = _REQUIRED_SCHEME_KEYS - _s.keys()
    if _missing:
        raise RuntimeError(f"schemes_eligibility.json record {_s.get('scheme_id','?')!r} is missing required fields: {_missing}")

# Gujarati (gu), Bengali (bn), Tamil (ta), Telugu (te), Kannada (kn),
# Malayalam (ml), Odia (or), Assamese (as), and Punjabi (pa) translations
# below are machine-quality first drafts, not yet reviewed by native
# speakers — same caution as the original Hindi/Marathi gap. Get native
# speakers to check these before they go live. State names in the "state"
# question are kept in English on purpose: these are standardized
# administrative names used pan-India regardless of the conversation
# language, and transliterating all 36 accurately across 12 scripts is
# more failure-prone than leaving them as-is.
STATE_LIST = [
    "Andaman And Nicobar", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chandigarh", "Chhattisgarh", "Dadra And Nagar Haveli", "Delhi", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jammu And Kashmir", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]
_state_options = "\n".join(f"{i+1}. {name}" for i, name in enumerate(STATE_LIST))

# For the ~10 languages that map fairly unambiguously to one state, show
# that state's native-script name alongside its Roman entry — a user who
# picked, say, Tamil specifically because they can't read Roman script at
# all otherwise has no way to find "Tamil Nadu" in a 36-line Roman-only
# list. Hindi and English have no single obvious matching state, so they
# get no hint and fall back to the plain Roman-only list.
_STATE_NATIVE_HINT = {
    "mr": ("Maharashtra", "महाराष्ट्र"),
    "gu": ("Gujarat", "ગુજરાત"),
    "bn": ("West Bengal", "পশ্চিমবঙ্গ"),
    "ta": ("Tamil Nadu", "தமிழ் நாடு"),
    "te": ("Telangana", "తెలంగాణ"),
    "kn": ("Karnataka", "ಕರ್ನಾಟಕ"),
    "ml": ("Kerala", "കേരളം"),
    "or": ("Odisha", "ଓଡ଼ିଶା"),
    "as": ("Assam", "অসম"),
    "pa": ("Punjab", "ਪੰਜਾਬ"),
}

def _state_options_for(lang_key):
    hint = _STATE_NATIVE_HINT.get(lang_key)
    if not hint:
        return _state_options
    hint_state, hint_native = hint
    lines = []
    for i, name in enumerate(STATE_LIST):
        if name == hint_state:
            lines.append(f"{i+1}. {name} / {hint_native}")
        else:
            lines.append(f"{i+1}. {name}")
    return "\n".join(lines)

# Prepended to every FLOW question after the first (which already has its
# own "Reply:" wording) — a first-time chatbot user shouldn't have to infer
# the numbered-reply convention from a single example shown once and never
# repeated.
NUMBER_CUE = {"1":"Reply with the number:\n","2":"क्रमांकाने उत्तर द्या:\n","3":"संख्या के साथ जवाब दें:\n","4":"નંબર સાથે જવાબ આપો:\n","5":"সংখ্যা দিয়ে উত্তর দিন:\n","6":"எண்ணுடன் பதிலளிக்கவும்:\n","7":"సంఖ్యతో సమాధానం ఇవ్వండి:\n","8":"ಸಂಖ್ಯೆಯೊಂದಿಗೆ ಉತ್ತರಿಸಿ:\n","9":"നമ്പർ ഉപയോഗിച്ച് ഉത്തരം നൽകുക:\n","10":"ସଂଖ୍ୟା ସହିତ ଉତ୍ତର ଦିଅନ୍ତୁ:\n","11":"সংখ্যাৰে উত্তৰ দিয়ক:\n","12":"ਨੰਬਰ ਨਾਲ ਜਵਾਬ ਦਿਓ:\n"}

# Appended to every FLOW question after the first — the code has always
# supported typing "hi" to restart at any point, but nothing on screen told
# the user that, so a mistaken answer looked unrecoverable without it.
RESTART_HINT = {"1":"\n\n(Made a mistake? Type hi to start over.)","2":"\n\n(चूक झाली? पुन्हा सुरू करण्यासाठी hi टाइप करा.)","3":"\n\n(गलती हो गई? फिर से शुरू करने के लिए hi टाइप करें.)","4":"\n\n(ભૂલ થઈ? ફરી શરૂ કરવા માટે hi ટાઈપ કરો.)","5":"\n\n(ভুল হয়েছে? আবার শুরু করতে hi লিখুন।)","6":"\n\n(தவறு ஏற்பட்டதா? மீண்டும் தொடங்க hi எனத் தட்டச்சு செய்யவும்.)","7":"\n\n(తప్పు జరిగిందా? మళ్లీ ప్రారంభించడానికి hi అని టైప్ చేయండి.)","8":"\n\n(ತಪ್ಪಾಗಿದೆಯೇ? ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಲು hi ಎಂದು ಟೈಪ್ ಮಾಡಿ.)","9":"\n\n(തെറ്റ് പറ്റിയോ? വീണ്ടും ആരംഭിക്കാൻ hi എന്ന് ടൈപ്പ് ചെയ്യുക.)","10":"\n\n(ଭୁଲ ହେଲା? ପୁଣି ଆରମ୍ଭ କରିବାକୁ hi ଟାଇପ୍ କରନ୍ତୁ।)","11":"\n\n(ভুল হ'ল নেকি? পুনৰ আৰম্ভ কৰিবলৈ hi টাইপ কৰক।)","12":"\n\n(ਗਲਤੀ ਹੋ ਗਈ? ਦੁਬਾਰਾ ਸ਼ੁਰੂ ਕਰਨ ਲਈ hi ਟਾਈਪ ਕਰੋ.)"}

# Shown once, right after language selection (Track E #22 of the roadmap:
# the guidance-not-guarantee disclaimer must appear early in the flow, not
# only at the end with the results) — every language matches the closing
# disclaimer's wording so a user sees the same promise twice, not two
# different claims.
DISCLAIMER = {
    "1":"ℹ️ Haqq gives guidance, not a guarantee — always confirm at your nearest Aaple Sarkar / Jan Seva Kendra.",
    "2":"ℹ️ Haqq मार्गदर्शक माहिती देतो, हमी नाही — जवळच्या आपले सरकार केंद्रावर नेहमी खात्री करा.",
    "3":"ℹ️ Haqq मार्गदर्शन देता है, गारंटी नहीं — हमेशा नज़दीकी आपले सरकार केंद्र पर पुष्टि करें।",
    "4":"ℹ️ Haqq માર્ગદર્શન આપે છે, ખાતરી નથી — હંમેશા નજીકના જન સેવા કેન્દ્ર પર ખાતરી કરો.",
    "5":"ℹ️ Haqq নির্দেশিকা দেয়, গ্যারান্টি নয় — সর্বদা নিকটতম জন সেবা কেন্দ্রে নিশ্চিত করুন।",
    "6":"ℹ️ Haqq ஒரு வழிகாட்டியை மட்டுமே தருகிறது, உத்தரவாதம் அல்ல — எப்போதும் அருகிலுள்ள ஆப்லே சர்க்கார் / ஜன் சேவா கேந்திரத்தில் உறுதிப்படுத்தவும்.",
    "7":"ℹ️ Haqq మార్గదర్శకత్వం మాత్రమే ఇస్తుంది, హామీ కాదు — ఎల్లప్పుడూ సమీప ఆప్లే సర్కార్ / జన సేవా కేంద్రంలో నిర్ధారించుకోండి.",
    "8":"ℹ️ Haqq ಮಾರ್ಗದರ್ಶನ ಮಾತ್ರ ನೀಡುತ್ತದೆ, ಖಾತರಿಯಲ್ಲ — ಯಾವಾಗಲೂ ಹತ್ತಿರದ ಆಪ್ಲೆ ಸರ್ಕಾರ್ / ಜನ ಸೇವಾ ಕೇಂದ್ರದಲ್ಲಿ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.",
    "9":"ℹ️ Haqq മാർഗ്ഗനിർദ്ദേശം മാത്രമേ നൽകുന്നുള്ളൂ, ഉറപ്പല്ല — എപ്പോഴും അടുത്തുള്ള ആപ്ലെ സർക്കാർ / ജൻ സേവാ കേന്ദ്രത്തിൽ സ്ഥിരീകരിക്കുക.",
    "10":"ℹ️ Haqq କେବଳ ମାର୍ଗଦର୍ଶିକା ଦିଏ, ଗ୍ୟାରେଣ୍ଟି ନୁହେଁ — ସର୍ବଦା ନିକଟସ୍ଥ ଜନ ସେବା କେନ୍ଦ୍ରରେ ନିଶ୍ଚିତ କରନ୍ତୁ।",
    "11":"ℹ️ Haqq -এ কেৱল নিৰ্দেশনা দিয়ে, নিশ্চয়তা নহয় — সদায় ওচৰৰ জন সেৱা কেন্দ্ৰত নিশ্চিত কৰক।",
    "12":"ℹ️ Haqq ਸਿਰਫ਼ ਮਾਰਗਦਰਸ਼ਨ ਦਿੰਦਾ ਹੈ, ਗਾਰੰਟੀ ਨਹੀਂ — ਹਮੇਸ਼ਾ ਨੇੜਲੇ ਜਨ ਸੇਵਾ ਕੇਂਦਰ ਵਿੱਚ ਪੁਸ਼ਟੀ ਕਰੋ।",
}

FLOW = [
    {"key":"lang","q":"👋 Namaste! I'm Haqq — I help you find government schemes you're eligible for.\n\nReply:\n1. English\n2. मराठी\n3. हिंदी\n4. ગુજરાતી\n5. বাংলা\n6. தமிழ்\n7. తెలుగు\n8. ಕನ್ನಡ\n9. മലയാളം\n10. ଓଡ଼ିଆ\n11. অসমীয়া\n12. ਪੰਜਾਬੀ"},
    {"key":"state","en":f"Which state do you live in?\n{_state_options_for('en')}","mr":f"तुम्ही कोणत्या राज्यात राहता?\n{_state_options_for('mr')}","hi":f"आप किस राज्य में रहते हैं?\n{_state_options_for('hi')}","gu":f"તમે કયા રાજ્યમાં રહો છો?\n{_state_options_for('gu')}","bn":f"আপনি কোন রাজ্যে থাকেন?\n{_state_options_for('bn')}","ta":f"நீங்கள் எந்த மாநிலத்தில் வசிக்கிறீர்கள்?\n{_state_options_for('ta')}","te":f"మీరు ఏ రాష్ట్రంలో నివసిస్తున్నారు?\n{_state_options_for('te')}","kn":f"ನೀವು ಯಾವ ರಾಜ್ಯದಲ್ಲಿ ವಾಸಿಸುತ್ತೀರಿ?\n{_state_options_for('kn')}","ml":f"നിങ്ങൾ ഏത് സംസ്ഥാനത്താണ് താമസിക്കുന്നത്?\n{_state_options_for('ml')}","or":f"ଆପଣ କେଉଁ ରାଜ୍ୟରେ ରୁହନ୍ତି?\n{_state_options_for('or')}","as":f"আপুনি কোন ৰাজ্যত থাকে?\n{_state_options_for('as')}","pa":f"ਤੁਸੀਂ ਕਿਸ ਰਾਜ ਵਿੱਚ ਰਹਿੰਦੇ ਹੋ?\n{_state_options_for('pa')}"},
    {"key":"age","en":"Age?\n1. Under 18\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","mr":"वय?\n1. 18 पेक्षा कमी\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","hi":"उम्र?\n1. 18 से कम\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","gu":"ઉંમર?\n1. 18 થી ઓછી\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","bn":"বয়স?\n1. 18 এর কম\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","ta":"வயது?\n1. 18 க்கும் குறைவு\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","te":"వయస్సు?\n1. 18 కంటే తక్కువ\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","kn":"ವಯಸ್ಸು?\n1. 18 ಕ್ಕಿಂತ ಕಡಿಮೆ\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","ml":"പ്രായം?\n1. 18 വയസ്സിന് താഴെ\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","or":"ବୟସ?\n1. 18 ରୁ କମ୍\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","as":"বয়স?\n1. 18 তকৈ কম\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+","pa":"ਉਮਰ?\n1. 18 ਤੋਂ ਘੱਟ\n2. 18-25\n3. 26-35\n4. 36-60\n5. 60+"},
    {"key":"gender","en":"Gender?\n1. Female\n2. Male\n3. Other","mr":"लिंग?\n1. महिला\n2. पुरुष\n3. इतर","hi":"लिंग?\n1. महिला\n2. पुरुष\n3. अन्य","gu":"લિંગ?\n1. મહિલા\n2. પુરુષ\n3. અન્ય","bn":"লিঙ্গ?\n1. মহিলা\n2. পুরুষ\n3. অন্যান্য","ta":"பாலினம்?\n1. பெண்\n2. ஆண்\n3. மற்றவை","te":"లింగం?\n1. స్త్రీ\n2. పురుషుడు\n3. ఇతర","kn":"ಲಿಂಗ?\n1. ಮಹಿಳೆ\n2. ಪುರುಷ\n3. ಇತರೆ","ml":"ലിംഗം?\n1. സ്ത്രീ\n2. പുരുഷൻ\n3. മറ്റുള്ളവ","or":"ଲିଙ୍ଗ?\n1. ମହିଳା\n2. ପୁରୁଷ\n3. ଅନ୍ୟ","as":"লিংগ?\n1. মহিলা\n2. পুৰুষ\n3. অন্য","pa":"ਲਿੰਗ?\n1. ਔਰਤ\n2. ਮਰਦ\n3. ਹੋਰ"},
    {"key":"income","en":"Yearly income?\n1. Below 1L\n2. 1-2.5L\n3. 2.5-5L\n4. Above 5L","mr":"वार्षिक उत्पन्न?\n1. 1 लाखापेक्षा कमी\n2. 1-2.5 लाख\n3. 2.5-5 लाख\n4. 5 लाखापेक्षा जास्त","hi":"सालाना आमदनी?\n1. 1L से कम\n2. 1-2.5L\n3. 2.5-5L\n4. 5L से ज्यादा","gu":"વાર્ષિક આવક?\n1. 1 લાખથી ઓછી\n2. 1-2.5 લાખ\n3. 2.5-5 લાખ\n4. 5 લાખથી વધુ","bn":"বার্ষিক আয়?\n1. 1 লাখের কম\n2. 1-2.5 লাখ\n3. 2.5-5 লাখ\n4. 5 লাখের বেশি","ta":"ஆண்டு வருமானம்?\n1. 1 லட்சத்திற்கும் குறைவு\n2. 1-2.5 லட்சம்\n3. 2.5-5 லட்சம்\n4. 5 லட்சத்திற்கும் மேல்","te":"వార్షిక ఆదాయం?\n1. 1 లక్షలోపు\n2. 1-2.5 లక్షలు\n3. 2.5-5 లక్షలు\n4. 5 లక్షలకు పైగా","kn":"ವಾರ್ಷಿಕ ಆದಾಯ?\n1. 1 ಲಕ್ಷಕ್ಕಿಂತ ಕಡಿಮೆ\n2. 1-2.5 ಲಕ್ಷ\n3. 2.5-5 ಲಕ್ಷ\n4. 5 ಲಕ್ಷಕ್ಕಿಂತ ಹೆಚ್ಚು","ml":"വാർഷിക വരുമാനം?\n1. 1 ലക്ഷത്തിൽ താഴെ\n2. 1-2.5 ലക്ഷം\n3. 2.5-5 ലക്ഷം\n4. 5 ലക്ഷത്തിന് മുകളിൽ","or":"ବାର୍ଷିକ ଆୟ?\n1. 1 ଲକ୍ଷରୁ କମ୍\n2. 1-2.5 ଲକ୍ଷ\n3. 2.5-5 ଲକ୍ଷ\n4. 5 ଲକ୍ଷରୁ ଅଧିକ","as":"বাৰ্ষিক আয়?\n1. 1 লাখতকৈ কম\n2. 1-2.5 লাখ\n3. 2.5-5 লাখ\n4. 5 লাখতকৈ বেছি","pa":"ਸਲਾਨਾ ਆਮਦਨ?\n1. 1 ਲੱਖ ਤੋਂ ਘੱਟ\n2. 1-2.5 ਲੱਖ\n3. 2.5-5 ਲੱਖ\n4. 5 ਲੱਖ ਤੋਂ ਵੱਧ"},
    {"key":"ration","en":"Ration card?\n1. Yellow\n2. Orange\n3. White\n4. No card","mr":"रेशन कार्ड?\n1. पिवळे\n2. नारंगी\n3. पांढरे\n4. नाही","hi":"राशन कार्ड?\n1. पीला\n2. नारंगी\n3. सफेद\n4. नहीं","gu":"રેશન કાર્ડ?\n1. પીળું\n2. નારંગી\n3. સફેદ\n4. નથી","bn":"রেশন কার্ড?\n1. হলুদ\n2. কমলা\n3. সাদা\n4. নেই","ta":"ரேஷன் கார்டு?\n1. மஞ்சள்\n2. ஆரஞ்சு\n3. வெள்ளை\n4. இல்லை","te":"రేషన్ కార్డు?\n1. పసుపు\n2. నారింజ\n3. తెలుపు\n4. లేదు","kn":"ಪಡಿತರ ಚೀಟಿ?\n1. ಹಳದಿ\n2. ಕಿತ್ತಳೆ\n3. ಬಿಳಿ\n4. ಇಲ್ಲ","ml":"റേഷൻ കാർഡ്?\n1. മഞ്ഞ\n2. ഓറഞ്ച്\n3. വെള്ള\n4. ഇല്ല","or":"ରାସନ୍ କାର୍ଡ?\n1. ହଳଦିଆ\n2. କମଳା\n3. ଧଳା\n4. ନାହିଁ","as":"ৰেচন কাৰ্ড?\n1. হালধীয়া\n2. কমলা\n3. বগা\n4. নাই","pa":"ਰਾਸ਼ਨ ਕਾਰਡ?\n1. ਪੀਲਾ\n2. ਸੰਤਰੀ\n3. ਚਿੱਟਾ\n4. ਨਹੀਂ"},
    {"key":"bank","en":"Bank account?\n1. Yes\n2. No","mr":"बँक खाते?\n1. होय\n2. नाही","hi":"बैंक खाता?\n1. हाँ\n2. नहीं","gu":"બેંક ખાતું?\n1. હા\n2. ના","bn":"ব্যাংক অ্যাকাউন্ট?\n1. হ্যাঁ\n2. না","ta":"வங்கி கணக்கு?\n1. ஆம்\n2. இல்லை","te":"బ్యాంక్ ఖాతా?\n1. అవును\n2. లేదు","kn":"ಬ್ಯಾಂಕ್ ಖಾತೆ?\n1. ಹೌದು\n2. ಇಲ್ಲ","ml":"ബാങ്ക് അക്കൗണ്ട്?\n1. ഉണ്ട്\n2. ഇല്ല","or":"ବ୍ୟାଙ୍କ ଖାତା?\n1. ହଁ\n2. ନା","as":"বেংক একাউণ্ট?\n1. হয়\n2. নাই","pa":"ਬੈਂਕ ਖਾਤਾ?\n1. ਹਾਂ\n2. ਨਹੀਂ"},
    {"key":"occupation","en":"Situation?\n1. Student\n2. Homemaker\n3. Farmer\n4. Daily wage\n5. Unemployed\n6. Self-employed\n7. Private job\n8. Govt job\n9. Construction/unorganized worker\n10. Fisherman\n11. Weaver\n12. Artisan/craftsperson\n13. Journalist\n14. Ex-serviceman","mr":"काम?\n1. विद्यार्थी\n2. गृहिणी\n3. शेतकरी\n4. रोजंदारी\n5. बेरोजगार\n6. स्वयंरोजगार\n7. खाजगी\n8. सरकारी\n9. बांधकाम/असंघटित कामगार\n10. मच्छीमार\n11. विणकर\n12. कारागीर\n13. पत्रकार\n14. माजी सैनिक","hi":"काम?\n1. विद्यार्थी\n2. गृहिणी\n3. किसान\n4. दिहाड़ी\n5. बेरोज़गार\n6. स्वरोज़गार\n7. प्राइवेट\n8. सरकारी\n9. निर्माण/असंगठित श्रमिक\n10. मछुआरा\n11. बुनकर\n12. शिल्पकार\n13. पत्रकार\n14. भूतपूर्व सैनिक","gu":"પરિસ્થિતિ?\n1. વિદ્યાર્થી\n2. ગૃહિણી\n3. ખેડૂત\n4. રોજમદાર\n5. બેરોજગાર\n6. સ્વરોજગાર\n7. ખાનગી નોકરી\n8. સરકારી નોકરી\n9. બાંધકામ/અસંગઠિત કામદાર\n10. માછીમાર\n11. વણકર\n12. કારીગર\n13. પત્રકાર\n14. ભૂતપૂર્વ સૈનિક","bn":"পরিস্থিতি?\n1. ছাত্র/ছাত্রী\n2. গৃহিণী\n3. কৃষক\n4. দিনমজুর\n5. বেকার\n6. স্বনিযুক্ত\n7. বেসরকারি চাকরি\n8. সরকারি চাকরি\n9. নির্মাণ/অসংগঠিত শ্রমিক\n10. জেলে\n11. তাঁতি\n12. কারিগর\n13. সাংবাদিক\n14. প্রাক্তন সৈনিক","ta":"நிலைமை?\n1. மாணவர்/மாணவி\n2. இல்லத்தரசி\n3. விவசாயி\n4. தினக்கூலி\n5. வேலையில்லாதவர்\n6. சுயதொழில்\n7. தனியார் வேலை\n8. அரசு வேலை\n9. கட்டுமான/முறைசாரா தொழிலாளி\n10. மீனவர்\n11. நெசவாளர்\n12. கைவினைஞர்\n13. பத்திரிகையாளர்\n14. முன்னாள் ராணுவத்தினர்","te":"పరిస్థితి?\n1. విద్యార్థి\n2. గృహిణి\n3. రైతు\n4. రోజువారీ కూలీ\n5. నిరుద్యోగి\n6. స్వయం ఉపాధి\n7. ప్రైవేట్ ఉద్యోగం\n8. ప్రభుత్వ ఉద్యోగం\n9. నిర్మాణ/అసంఘటిత కార్మికుడు\n10. మత్స్యకారుడు\n11. నేత కార్మికుడు\n12. హస్తకళాకారుడు\n13. జర్నలిస్ట్\n14. మాజీ సైనికుడు","kn":"ಪರಿಸ್ಥಿತಿ?\n1. ವಿದ್ಯಾರ್ಥಿ\n2. ಗೃಹಿಣಿ\n3. ರೈತ\n4. ದಿನಗೂಲಿ\n5. ನಿರುದ್ಯೋಗಿ\n6. ಸ್ವಯಂ ಉದ್ಯೋಗ\n7. ಖಾಸಗಿ ಕೆಲಸ\n8. ಸರ್ಕಾರಿ ಕೆಲಸ\n9. ಕಟ್ಟಡ/ಅಸಂಘಟಿತ ಕಾರ್ಮಿಕ\n10. ಮೀನುಗಾರ\n11. ನೇಕಾರ\n12. ಕುಶಲಕರ್ಮಿ\n13. ಪತ್ರಕರ್ತ\n14. ಮಾಜಿ ಸೈನಿಕ","ml":"സാഹചര്യം?\n1. വിദ്യാർത്ഥി\n2. വീട്ടമ്മ\n3. കർഷകൻ\n4. ദിവസവേതനക്കാരൻ\n5. തൊഴിലില്ലാത്തവർ\n6. സ്വയം തൊഴിൽ\n7. സ്വകാര്യ ജോലി\n8. സർക്കാർ ജോലി\n9. നിർമ്മാണ/അസംഘടിത തൊഴിലാളി\n10. മത്സ്യത്തൊഴിലാളി\n11. നെയ്ത്തുകാരൻ\n12. കരകൗശലത്തൊഴിലാളി\n13. പത്രപ്രവർത്തകൻ\n14. മുൻ സൈനികൻ","or":"ପରିସ୍ଥିତି?\n1. ଛାତ୍ର\n2. ଗୃହିଣୀ\n3. କୃଷକ\n4. ଦୈନିକ ମଜୁରି\n5. ବେକାର\n6. ସ୍ୱ-ନିଯୁକ୍ତ\n7. ବେସରକାରୀ ଚାକିରି\n8. ସରକାରୀ ଚାକିରି\n9. ନିର୍ମାଣ/ଅସଙ୍ଗଠିତ ଶ୍ରମିକ\n10. ମତ୍ସ୍ୟଜୀବୀ\n11. ବୁଣାକାର\n12. କାରିଗର\n13. ସାମ୍ବାଦିକ\n14. ପୂର୍ବତନ ସୈନିକ","as":"পৰিস্থিতি?\n1. ছাত্ৰ\n2. গৃহিণী\n3. কৃষক\n4. দৈনিক মজুৰি\n5. বেকাৰ\n6. স্ব-নিযুক্ত\n7. বেচৰকাৰী চাকৰি\n8. চৰকাৰী চাকৰি\n9. নিৰ্মাণ/অসংগঠিত শ্ৰমিক\n10. মাছমৰীয়া\n11. তাঁতী\n12. শিল্পী/কাৰিকৰ\n13. সাংবাদিক\n14. প্ৰাক্তন সৈনিক","pa":"ਸਥਿਤੀ?\n1. ਵਿਦਿਆਰਥੀ\n2. ਘਰੇਲੂ ਔਰਤ\n3. ਕਿਸਾਨ\n4. ਦਿਹਾੜੀਦਾਰ\n5. ਬੇਰੁਜ਼ਗਾਰ\n6. ਸਵੈ-ਰੁਜ਼ਗਾਰ\n7. ਪ੍ਰਾਈਵੇਟ ਨੌਕਰੀ\n8. ਸਰਕਾਰੀ ਨੌਕਰੀ\n9. ਉਸਾਰੀ/ਗੈਰ-ਸੰਗਠਿਤ ਕਾਮਾ\n10. ਮਛੇਰਾ\n11. ਜੁਲਾਹਾ\n12. ਕਾਰੀਗਰ\n13. ਪੱਤਰਕਾਰ\n14. ਸਾਬਕਾ ਫੌਜੀ"},
    {"key":"marital","en":"Marital status?\n1. Single\n2. Married\n3. Widowed\n4. Divorced","mr":"वैवाहिक?\n1. अविवाहित\n2. विवाहित\n3. विधवा\n4. घटस्फोटित","hi":"वैवाहिक?\n1. अविवाहित\n2. विवाहित\n3. विधवा\n4. तलाकशुदा","gu":"વૈવાહિક સ્થિતિ?\n1. અપરિણીત\n2. પરિણીત\n3. વિધવા\n4. છૂટાછેડા","bn":"বৈবাহিক অবস্থা?\n1. অবিবাহিত\n2. বিবাহিত\n3. বিধবা\n4. তালাকপ্রাপ্ত","ta":"திருமண நிலை?\n1. திருமணமாகாதவர்\n2. திருமணமானவர்\n3. விதவை\n4. விவாகரத்து","te":"వైవాహిక స్థితి?\n1. అవివాహిత\n2. వివాహిత\n3. వితంతువు\n4. విడాకులు","kn":"ವೈವಾಹಿಕ ಸ್ಥಿತಿ?\n1. ಅವಿವಾಹಿತ\n2. ವಿವಾಹಿತ\n3. ವಿಧವೆ\n4. ವಿಚ್ಛೇದಿತ","ml":"വൈവാഹിക നില?\n1. അവിവാഹിതൻ\n2. വിവാഹിതൻ\n3. വിധവ\n4. വിവാഹമോചിതൻ","or":"ବୈବାହିକ ସ୍ଥିତି?\n1. ଅବିବାହିତ\n2. ବିବାହିତ\n3. ବିଧବା\n4. ଛାଡ଼ପତ୍ର ପ୍ରାପ୍ତ","as":"বৈবাহিক স্থিতি?\n1. অবিবাহিত\n2. বিবাহিত\n3. বিধৱা\n4. প্ৰাক্তন পতি/পত্নী","pa":"ਵਿਆਹੁਤਾ ਸਥਿਤੀ?\n1. ਅਣਵਿਆਹਿਆ\n2. ਵਿਆਹਿਆ\n3. ਵਿਧਵਾ\n4. ਤਲਾਕਸ਼ੁਦਾ"},
    {"key":"caste","en":"Caste category?\n1. General\n2. OBC\n3. SC\n4. ST","mr":"जात प्रवर्ग?\n1. सर्वसाधारण\n2. ओबीसी\n3. एससी\n4. एसटी","hi":"जाति वर्ग?\n1. सामान्य\n2. ओबीसी\n3. एससी\n4. एसटी","gu":"જાતિ વર્ગ?\n1. સામાન્ય\n2. ઓબીસી\n3. એસસી\n4. એસટી","bn":"জাতি বিভাগ?\n1. সাধারণ\n2. ওবিসি\n3. এসসি\n4. এসটি","ta":"சாதி வகை?\n1. பொது\n2. ஓபிசி\n3. எஸ்சி\n4. எஸ்டி","te":"కుల వర్గం?\n1. జనరల్\n2. ఓబీసీ\n3. ఎస్సీ\n4. ఎస్టీ","kn":"ಜಾತಿ ವರ್ಗ?\n1. ಸಾಮಾನ್ಯ\n2. ಒಬಿಸಿ\n3. ಎಸ್‌ಸಿ\n4. ಎಸ್‌ಟಿ","ml":"ജാതി വിഭാഗം?\n1. ജനറൽ\n2. ഒബിസി\n3. എസ്‌സി\n4. എസ്ടി","or":"ଜାତି ବର୍ଗ?\n1. ସାଧାରଣ\n2. ଓବିସି\n3. ଏସସି\n4. ଏସଟି","as":"জাতি শ্ৰেণী?\n1. সাধাৰণ\n2. অ'বিচি\n3. এছচি\n4. এছটি","pa":"ਜਾਤੀ ਸ਼੍ਰੇਣੀ?\n1. ਜਨਰਲ\n2. ਓਬੀਸੀ\n3. ਐਸਸੀ\n4. ਐਸਟੀ"},
    {"key":"disability","en":"Disability status?\n1. No disability\n2. Yes, under 40%\n3. Yes, 40-59%\n4. Yes, 60-79%\n5. Yes, 80% or more","mr":"अपंगत्व?\n1. नाही\n2. होय, 40% पेक्षा कमी\n3. होय, 40-59%\n4. होय, 60-79%\n5. होय, 80% किंवा जास्त","hi":"विकलांगता?\n1. नहीं\n2. हाँ, 40% से कम\n3. हाँ, 40-59%\n4. हाँ, 60-79%\n5. हाँ, 80% या अधिक","gu":"વિકલાંગતા?\n1. ના\n2. હા, 40% થી ઓછી\n3. હા, 40-59%\n4. હા, 60-79%\n5. હા, 80% અથવા વધુ","bn":"প্রতিবন্ধকতা?\n1. না\n2. হ্যাঁ, 40% এর কম\n3. হ্যাঁ, 40-59%\n4. হ্যাঁ, 60-79%\n5. হ্যাঁ, 80% বা তার বেশি","ta":"மாற்றுத்திறனாளி?\n1. இல்லை\n2. ஆம், 40% க்கும் குறைவு\n3. ஆம், 40-59%\n4. ஆம், 60-79%\n5. ஆம், 80% அல்லது அதற்கு மேல்","te":"వికలాంగత్వం?\n1. లేదు\n2. అవును, 40% కంటే తక్కువ\n3. అవును, 40-59%\n4. అవును, 60-79%\n5. అవును, 80% లేదా అంతకంటే ఎక్కువ","kn":"ಅಂಗವೈಕಲ್ಯ?\n1. ಇಲ್ಲ\n2. ಹೌದು, 40% ಕ್ಕಿಂತ ಕಡಿಮೆ\n3. ಹೌದು, 40-59%\n4. ಹೌದು, 60-79%\n5. ಹೌದು, 80% ಅಥವಾ ಹೆಚ್ಚು","ml":"വൈകല്യം?\n1. ഇല്ല\n2. ഉണ്ട്, 40% ൽ താഴെ\n3. ഉണ്ട്, 40-59%\n4. ഉണ്ട്, 60-79%\n5. ഉണ്ട്, 80% അല്ലെങ്കിൽ കൂടുതൽ","or":"ଅକ୍ଷମତା?\n1. ନାହିଁ\n2. ହଁ, 40% ରୁ କମ୍\n3. ହଁ, 40-59%\n4. ହଁ, 60-79%\n5. ହଁ, 80% କିମ୍ବା ଅଧିକ","as":"অক্ষমতা?\n1. নাই\n2. হয়, 40% তকৈ কম\n3. হয়, 40-59%\n4. হয়, 60-79%\n5. হয়, 80% বা তাতোধিক","pa":"ਅਪੰਗਤਾ?\n1. ਨਹੀਂ\n2. ਹਾਂ, 40% ਤੋਂ ਘੱਟ\n3. ਹਾਂ, 40-59%\n4. ਹਾਂ, 60-79%\n5. ਹਾਂ, 80% ਜਾਂ ਵੱਧ"},
    {"key":"land","en":"Do you own agricultural land?\n1. Yes\n2. No","mr":"तुमच्याकडे शेतजमीन आहे का?\n1. होय\n2. नाही","hi":"क्या आपके पास खेती की ज़मीन है?\n1. हाँ\n2. नहीं","gu":"શું તમારી પાસે ખેતીની જમીન છે?\n1. હા\n2. ના","bn":"আপনার কি কৃষি জমি আছে?\n1. হ্যাঁ\n2. না","ta":"உங்களுக்கு விவசாய நிலம் உள்ளதா?\n1. ஆம்\n2. இல்லை","te":"మీకు వ్యవసాయ భూమి ఉందా?\n1. అవును\n2. లేదు","kn":"ನಿಮಗೆ ಕೃಷಿ ಭೂಮಿ ಇದೆಯೇ?\n1. ಹೌದು\n2. ಇಲ್ಲ","ml":"നിങ്ങൾക്ക് കൃഷിഭൂമി ഉണ്ടോ?\n1. ഉണ്ട്\n2. ഇല്ല","or":"ଆପଣଙ୍କର କୃଷି ଜମି ଅଛି କି?\n1. ହଁ\n2. ନା","as":"আপোনাৰ কৃষি ভূমি আছে নেকি?\n1. হয়\n2. নাই","pa":"ਕੀ ਤੁਹਾਡੇ ਕੋਲ ਖੇਤੀ ਵਾਲੀ ਜ਼ਮੀਨ ਹੈ?\n1. ਹਾਂ\n2. ਨਹੀਂ"},
    {"key":"worker_board","en":"Registered with a construction/unorganized workers' welfare board?\n1. Yes\n2. No\n3. Not sure","mr":"बांधकाम/असंघटित कामगार कल्याण मंडळात नोंदणी आहे का?\n1. होय\n2. नाही\n3. माहीत नाही","hi":"क्या आप निर्माण/असंगठित श्रमिक कल्याण बोर्ड में पंजीकृत हैं?\n1. हाँ\n2. नहीं\n3. पता नहीं","gu":"શું તમે બાંધકામ/અસંગઠિત કામદાર કલ્યાણ બોર્ડમાં નોંધાયેલા છો?\n1. હા\n2. ના\n3. ખબર નથી","bn":"আপনি কি নির্মাণ/অসংগঠিত শ্রমিক কল্যাণ বোর্ডে নিবন্ধিত?\n1. হ্যাঁ\n2. না\n3. জানি না","ta":"கட்டுமான/முறைசாரா தொழிலாளர் நல வாரியத்தில் பதிவு செய்துள்ளீர்களா?\n1. ஆம்\n2. இல்லை\n3. தெரியவில்லை","te":"మీరు నిర్మాణ/అసంఘటిత కార్మిక సంక్షేమ బోర్డులో నమోదు అయ్యారా?\n1. అవును\n2. లేదు\n3. తెలియదు","kn":"ನೀವು ಕಟ್ಟಡ/ಅಸಂಘಟಿತ ಕಾರ್ಮಿಕ ಕಲ್ಯಾಣ ಮಂಡಳಿಯಲ್ಲಿ ನೋಂದಾಯಿಸಿಕೊಂಡಿದ್ದೀರಾ?\n1. ಹೌದು\n2. ಇಲ್ಲ\n3. ಗೊತ್ತಿಲ್ಲ","ml":"നിർമ്മാണ/അസംഘടിത തൊഴിലാളി ക്ഷേമ ബോർഡിൽ രജിസ്റ്റർ ചെയ്തിട്ടുണ്ടോ?\n1. ഉണ്ട്\n2. ഇല്ല\n3. അറിയില്ല","or":"ନିର୍ମାଣ/ଅସଙ୍ଗଠିତ ଶ୍ରମିକ କଲ୍ୟାଣ ବୋର୍ଡରେ ପଞ୍ଜୀକୃତ କି?\n1. ହଁ\n2. ନା\n3. ଜଣା ନାହିଁ","as":"নিৰ্মাণ/অসংগঠিত শ্ৰমিক কল্যাণ ব'ৰ্ডত পঞ্জীয়ন আছে নেকি?\n1. হয়\n2. নাই\n3. জনা নাই","pa":"ਕੀ ਤੁਸੀਂ ਉਸਾਰੀ/ਗੈਰ-ਸੰਗਠਿਤ ਕਾਮਿਆਂ ਦੇ ਭਲਾਈ ਬੋਰਡ ਵਿੱਚ ਰਜਿਸਟਰਡ ਹੋ?\n1. ਹਾਂ\n2. ਨਹੀਂ\n3. ਪਤਾ ਨਹੀਂ"},
]

# Bracket LOWER bounds, not midpoints. A user only tells us which bracket
# they're in (e.g. "Below 1L" spans Rs.0-100,000), never an exact figure, so
# match() has to pick one representative value per bracket to compare against
# scheme max_income thresholds. Using the midpoint (e.g. Rs.80,000 for the
# lowest bracket) was a real bug: 61 of 225 income-gated schemes in
# schemes_eligibility.json have max_income below Rs.80,000 specifically
# because they target the poorest applicants — exactly the population this
# bot serves — so anyone answering "Below 1L" silently failed all of them,
# including the pre-existing curated Sanjay Gandhi Niradhar Yojana
# (max_income Rs.21,000). Using the bracket's lower bound instead means a
# "Below 1L" answer can satisfy any income cap up to Rs.1L, which is the
# correct inclusive read given the bot explicitly bills itself as guidance
# to confirm at a Jan Seva Kendra, not a guarantee — a false "you might
# qualify" costs the user a follow-up question; a false "you don't" means
# they never hear about the scheme at all.
INCOME_MAP = {"1":0,"2":100000,"3":250000,"4":500000}
AGE_MAP = {"1":15,"2":22,"3":30,"4":45,"5":65}
RATION_MAP = {"1":"AAY","2":"BPL","3":"APL","4":None}
GENDER_MAP = {"1":"female","2":"male","3":"other"}
OCC_MAP = {"1":"student","2":"homemaker","3":"farmer","4":"daily_wage","5":"unemployed","6":"self_employed","7":"private_job","8":"govt_job","9":"construction_worker","10":"fisherman","11":"weaver","12":"artisan","13":"journalist","14":"ex_servicemen"}
MARITAL_MAP = {"1":"single","2":"married","3":"widowed","4":"divorced"}
CASTE_MAP = {"1":"general","2":"obc","3":"sc","4":"st"}
# (has_disability, percent_lower_bound) — the lower bound of the selected
# bracket is what gets compared against a scheme's disability_percent_min,
# so a scheme requiring e.g. 60% is never satisfied by someone who only
# confirmed "40-59%". This slightly under-matches on the rare scheme whose
# threshold sits strictly inside a bracket (e.g. 50%) rather than on a
# bracket boundary — a deliberate false-negative bias, since telling someone
# they qualify when they don't is worse than the reverse for this bot.
DISABILITY_MAP = {"1":(False,None),"2":(True,0),"3":(True,40),"4":(True,60),"5":(True,80)}
LAND_MAP = {"1":True,"2":False}
WORKER_BOARD_MAP = {"1":True,"2":False,"3":None}

# --- SCHEME DATA ---
# The 13 curated entries below are Maharashtra-specific corrections that
# came from real fact-checking sessions (see schemes_audit.md) — several
# of the flagship schemes they cover (Ladki Bahin, Ayushman Bharat/MJPJAY,
# PM Kisan, MGNREGA, PM Jeevan Jyoti Bima, NFSA free grain) either aren't
# in schemes_eligibility.json yet (still needs_review/plausible_unconfirmed,
# not in the "verified" extraction pass) or need caveats — eKYC renewal,
# refill subsidy terms, etc — that the generic JSON-driven engine below
# doesn't carry. Kept as hardcoded overrides, applied only for Maharashtra
# profiles. Every figure was checked against a public source as of July
# 2026 — see schemes_audit.md for sources + dates. Re-verify at least once
# a year (govt schemes revise wages/amounts every April in many cases, and
# eKYC/beneficiary lists get purged mid-year) — don't treat this as
# "verified forever."
#
# Schemes below that DO also exist in schemes_eligibility.json (Jan Dhan,
# Suraksha Bima, One Stop Centre, Sanjay Gandhi Niradhar, the NSAP/
# Shravanbal old-age pension, and both Ujjwala versions) are excluded from
# the generic engine's output for Maharashtra profiles via
# MAHARASHTRA_CURATED_SLUGS, so users don't see the same scheme twice with
# two different (and possibly conflicting) benefit descriptions.
MAHARASHTRA_CURATED_SLUGS = {"pmjdy","pmsby","osc","sgngs","nsap-ignoaps","sbssps","pmuy","pmuy2","mjpjay"}

# Each entry's "text" dict is keyed by FLOW's numeric lang code (1=en,2=mr,...)
# and holds (name, benefit) tuples — translations are machine-quality first
# drafts, same caveat as FLOW's own translations. Numbers/currency figures are
# identical across languages by design; only wording is translated.
MAHARASHTRA_SCHEMES = [
    {
        # Ladki Bahin Yojana — verified July 2026: Rs.1,500/month unchanged,
        # age 21-65, income <=2.5L. IMPORTANT: state ran an eKYC drive through
        # Apr 2026 and dropped ~70 lakh beneficiaries for false income claims /
        # tax-payee status / Aadhaar mismatches. "Eligible on paper" no longer
        # guarantees payment — must flag the eKYC step.
        "match": lambda p, age, inc: p.get("gender")=="1" and 21<=age<=65 and inc<=250000,
        "link": "mahadbt.maharashtra.gov.in",
        "text": {
            "1":("Ladki Bahin Yojana","Rs.1,500/month cash. You must also complete the ANNUAL eKYC (usually Jun-Jul window) or payment stops — check status at mahadbt.maharashtra.gov.in"),
            "2":("लाडकी बहीण योजना","दरमहा ₹1,500 रोख. दरवर्षी eKYC (साधारण जून-जुलैमध्ये) पूर्ण करणे बंधनकारक आहे, नाहीतर पेमेंट थांबते — स्थिती तपासा mahadbt.maharashtra.gov.in वर"),
            "3":("लाडकी बहिन योजना","हर महीने ₹1,500 नकद. हर साल eKYC (आमतौर पर जून-जुलाई में) पूरी करना ज़रूरी है, वरना भुगतान रुक जाएगा — स्थिति जांचें mahadbt.maharashtra.gov.in पर"),
            "4":("લાડકી બહેન યોજના","દર મહિને ₹1,500 રોકડ. દર વર્ષે eKYC (સામાન્ય રીતે જૂન-જુલાઈમાં) પૂર્ણ કરવું ફરજિયાત છે, નહીં તો ચુકવણી અટકી જશે — સ્થિતિ ચકાસો mahadbt.maharashtra.gov.in પર"),
            "5":("লাডকি বহিন যোজনা","প্রতি মাসে ₹1,500 নগদ. প্রতি বছর eKYC (সাধারণত জুন-জুলাই) সম্পূর্ণ করা বাধ্যতামূলক, নাহলে পেমেন্ট বন্ধ হয়ে যাবে — অবস্থা যাচাই করুন mahadbt.maharashtra.gov.in-এ"),
            "6":("லட்கி பஹின் யோஜனா","மாதம் ₹1,500 பணமாக. ஒவ்வொரு ஆண்டும் eKYC (பொதுவாக ஜூன்-ஜூலை) முடிக்க வேண்டும், இல்லையெனில் பணம் நிற்கும் — நிலையை சரிபார்க்க mahadbt.maharashtra.gov.in"),
            "7":("లడ్కీ బహిన్ యోజన","నెలకు ₹1,500 నగదు. ప్రతి సంవత్సరం eKYC (సాధారణంగా జూన్-జూలైలో) పూర్తి చేయాలి, లేకపోతే చెల్లింపు ఆగిపోతుంది — స్థితిని తనిఖీ చేయండి mahadbt.maharashtra.gov.in లో"),
            "8":("ಲಡ್ಕಿ ಬಹಿಣ್ ಯೋಜನೆ","ತಿಂಗಳಿಗೆ ₹1,500 ನಗದು. ಪ್ರತಿ ವರ್ಷ eKYC (ಸಾಮಾನ್ಯವಾಗಿ ಜೂನ್-ಜುಲೈ) ಪೂರ್ಣಗೊಳಿಸಬೇಕು, ಇಲ್ಲದಿದ್ದರೆ ಪಾವತಿ ನಿಲ್ಲುತ್ತದೆ — mahadbt.maharashtra.gov.in ನಲ್ಲಿ ಸ್ಥಿತಿ ಪರಿಶೀಲಿಸಿ"),
            "9":("ലഡ്കി ബഹിൻ യോജന","പ്രതിമാസം ₹1,500 പണം. എല്ലാ വർഷവും eKYC (സാധാരണയായി ജൂൺ-ജൂലൈ) പൂർത്തിയാക്കണം, ഇല്ലെങ്കിൽ പേയ്‌മെന്റ് നിലയ്ക്കും — mahadbt.maharashtra.gov.in-ൽ സ്ഥിതി പരിശോധിക്കുക"),
            "10":("ଲାଡ଼କୀ ବହିନ ଯୋଜନା","ମାସିକ ₹1,500 ନଗଦ। ପ୍ରତିବର୍ଷ eKYC (ସାଧାରଣତଃ ଜୁନ-ଜୁଲାଇ) ସମ୍ପୂର୍ଣ୍ଣ କରିବା ବାଧ୍ୟତାମୂଳକ, ନହେଲେ ଦେୟ ବନ୍ଦ ହୋଇଯିବ — mahadbt.maharashtra.gov.in ରେ ସ୍ଥିତି ଯାଞ୍ଚ କରନ୍ତୁ"),
            "11":("লাডকি বহিন যোজনা","মাহেকীয়া ₹1,500 নগদ। প্ৰতিবছৰে eKYC (সাধাৰণতে জুন-জুলাইত) সম্পূৰ্ণ কৰাটো বাধ্যতামূলক, নহ'লে পৰিশোধ বন্ধ হ'ব — mahadbt.maharashtra.gov.in ত অৱস্থা পৰীক্ষা কৰক"),
            "12":("ਲਾਡਕੀ ਬਹਿਣ ਯੋਜਨਾ","ਹਰ ਮਹੀਨੇ ₹1,500 ਨਕਦ। ਹਰ ਸਾਲ eKYC (ਆਮ ਤੌਰ 'ਤੇ ਜੂਨ-ਜੁਲਾਈ) ਪੂਰਾ ਕਰਨਾ ਲਾਜ਼ਮੀ ਹੈ, ਨਹੀਂ ਤਾਂ ਭੁਗਤਾਨ ਰੁਕ ਜਾਵੇਗਾ — mahadbt.maharashtra.gov.in 'ਤੇ ਸਥਿਤੀ ਦੇਖੋ"),
        },
    },
    {
        "match": lambda p, age, inc: p.get("bank")=="2",
        "link": "pmjdy.gov.in",
        "text": {
            "1":("PM Jan Dhan Yojana","Free zero-balance account + Rs.2L accidental insurance on your RuPay card (stays active only if you use the card at least once every 90 days) + optional Rs.10,000 overdraft after 6 months"),
            "2":("पंतप्रधान जन धन योजना","मोफत झिरो-बॅलन्स खाते + तुमच्या RuPay कार्डवर ₹2 लाख अपघात विमा (कार्ड दर 90 दिवसांत किमान एकदा वापरल्यासच सक्रिय राहते) + 6 महिन्यांनंतर ऐच्छिक ₹10,000 ओव्हरड्राफ्ट"),
            "3":("पीएम जन धन योजना","मुफ्त ज़ीरो-बैलेंस खाता + आपके RuPay कार्ड पर ₹2 लाख का दुर्घटना बीमा (कार्ड हर 90 दिनों में कम से कम एक बार इस्तेमाल करने पर ही सक्रिय रहता है) + 6 महीने बाद वैकल्पिक ₹10,000 ओवरड्राफ्ट"),
            "4":("પીએમ જન ધન યોજના","મફત ઝીરો-બેલેન્સ ખાતું + તમારા RuPay કાર્ડ પર ₹2 લાખનો અકસ્માત વીમો (કાર્ડ દર 90 દિવસે ઓછામાં ઓછું એકવાર વાપરો તો જ સક્રિય રહે) + 6 મહિના પછી વૈકલ્પિક ₹10,000 ઓવરડ્રાફ્ટ"),
            "5":("পিএম জন ধন যোজনা","বিনামূল্যে জিরো-ব্যালেন্স অ্যাকাউন্ট + আপনার RuPay কার্ডে ₹2 লাখ দুর্ঘটনা বীমা (প্রতি 90 দিনে অন্তত একবার কার্ড ব্যবহার করলেই সক্রিয় থাকে) + 6 মাস পর ঐচ্ছিক ₹10,000 ওভারড্রাফ্ট"),
            "6":("பிஎம் ஜன் தன் யோஜனா","இலவச பூஜ்ஜிய-இருப்பு கணக்கு + உங்கள் RuPay அட்டையில் ₹2 லட்சம் விபத்து காப்பீடு (ஒவ்வொரு 90 நாட்களுக்கும் ஒருமுறையாவது அட்டையை பயன்படுத்தினால் மட்டுமே செயலில் இருக்கும்) + 6 மாதங்களுக்குப் பிறகு விருப்ப ₹10,000 ஓவர்டிராஃப்ட்"),
            "7":("పీఎం జన్ ధన్ యోజన","ఉచిత జీరో-బ్యాలెన్స్ ఖాతా + మీ RuPay కార్డుపై ₹2 లక్షల ప్రమాద బీమా (ప్రతి 90 రోజులకు కనీసం ఒకసారి కార్డు వాడితేనే యాక్టివ్‌గా ఉంటుంది) + 6 నెలల తర్వాత ఐచ్ఛిక ₹10,000 ఓవర్‌డ్రాఫ్ట్"),
            "8":("ಪಿಎಂ ಜನ್ ಧನ್ ಯೋಜನೆ","ಉಚಿತ ಶೂನ್ಯ-ಬ್ಯಾಲೆನ್ಸ್ ಖಾತೆ + ನಿಮ್ಮ RuPay ಕಾರ್ಡ್‌ನಲ್ಲಿ ₹2 ಲಕ್ಷ ಅಪಘಾತ ವಿಮೆ (ಪ್ರತಿ 90 ದಿನಗಳಿಗೊಮ್ಮೆ ಕಾರ್ಡ್ ಬಳಸಿದರೆ ಮಾತ್ರ ಸಕ್ರಿಯ) + 6 ತಿಂಗಳ ನಂತರ ಐಚ್ಛಿಕ ₹10,000 ಓವರ್‌ಡ್ರಾಫ್ಟ್"),
            "9":("പിഎം ജൻ ധൻ യോജന","സൗജന്യ പൂജ്യം-ബാലൻസ് അക്കൗണ്ട് + നിങ്ങളുടെ RuPay കാർഡിൽ ₹2 ലക്ഷം അപകട ഇൻഷുറൻസ് (90 ദിവസത്തിലൊരിക്കൽ കാർഡ് ഉപയോഗിച്ചാൽ മാത്രമേ സജീവമായിരിക്കൂ) + 6 മാസത്തിനുശേഷം ഓപ്ഷണൽ ₹10,000 ഓവർഡ്രാഫ്റ്റ്"),
            "10":("ପିଏମ୍ ଜନ ଧନ ଯୋଜନା","ମାଗଣା ଶୂନ୍ୟ-ବାକି ଖାତା + ଆପଣଙ୍କ RuPay କାର୍ଡରେ ₹2 ଲକ୍ଷ ଦୁର୍ଘଟଣା ବୀମା (ପ୍ରତି 90 ଦିନରେ ଅତି କମରେ ଥରେ କାର୍ଡ ବ୍ୟବହାର କଲେ ହିଁ ସକ୍ରିୟ ରହେ) + 6 ମାସ ପରେ ଇଚ୍ଛାଧୀନ ₹10,000 ଓଭରଡ୍ରାଫ୍ଟ"),
            "11":("পিএম জন ধন যোজনা","বিনামূলীয়া শূন্য-ব্যালেঞ্চ একাউণ্ট + আপোনাৰ RuPay কাৰ্ডত ₹2 লাখ দুৰ্ঘটনা বীমা (প্ৰতি 90 দিনত কমেও এবাৰ কাৰ্ড ব্যৱহাৰ কৰিলেহে সক্ৰিয় থাকে) + 6 মাহৰ পিছত ঐচ্ছিক ₹10,000 অভাৰড্ৰাফ্ট"),
            "12":("ਪੀਐਮ ਜਨ ਧਨ ਯੋਜਨਾ","ਮੁਫ਼ਤ ਜ਼ੀਰੋ-ਬੈਲੇਂਸ ਖਾਤਾ + ਤੁਹਾਡੇ RuPay ਕਾਰਡ 'ਤੇ ₹2 ਲੱਖ ਦੁਰਘਟਨਾ ਬੀਮਾ (ਹਰ 90 ਦਿਨਾਂ ਵਿੱਚ ਘੱਟੋ-ਘੱਟ ਇੱਕ ਵਾਰ ਕਾਰਡ ਵਰਤਣ 'ਤੇ ਹੀ ਸਰਗਰਮ ਰਹਿੰਦਾ) + 6 ਮਹੀਨਿਆਂ ਬਾਅਦ ਵਿਕਲਪਿਕ ₹10,000 ਓਵਰਡਰਾਫਟ"),
        },
    },
    {
        # NFSA free grain — AAY (yellow card) is 35kg per HOUSEHOLD. Free
        # (no cost) until Dec 2028.
        "match": lambda p, age, inc: p.get("ration")=="1",
        "link": "nfsa.gov.in",
        "text": {
            "1":("Free Grain Scheme (AAY)","35kg free grain/month PER HOUSEHOLD, no cost, guaranteed till Dec 2028"),
            "2":("मोफत धान्य योजना (AAY)","दरमहा 35 किलो मोफत धान्य प्रति कुटुंब, कोणताही खर्च नाही, डिसेंबर 2028 पर्यंत हमी"),
            "3":("मुफ्त अनाज योजना (AAY)","हर महीने 35 किलो मुफ्त अनाज प्रति परिवार, कोई खर्च नहीं, दिसंबर 2028 तक गारंटी"),
            "4":("મફત અનાજ યોજના (AAY)","દર મહિને 35 કિલો મફત અનાજ પ્રતિ પરિવાર, કોઈ ખર્ચ નહીં, ડિસેમ્બર 2028 સુધી ગેરંટી"),
            "5":("বিনামূল্যে শস্য প্রকল্প (AAY)","প্রতি মাসে 35 কেজি বিনামূল্যে শস্য প্রতি পরিবার, কোনো খরচ নেই, ডিসেম্বর 2028 পর্যন্ত গ্যারান্টি"),
            "6":("இலவச தானிய திட்டம் (AAY)","மாதம் 35 கிலோ இலவச தானியம் ஒரு குடும்பத்திற்கு, செலவு இல்லை, டிசம்பர் 2028 வரை உத்தரவாதம்"),
            "7":("ఉచిత ధాన్యం పథకం (AAY)","నెలకు 35 కిలోల ఉచిత ధాన్యం ఒక్కో కుటుంబానికి, ఖర్చు లేదు, డిసెంబర్ 2028 వరకు హామీ"),
            "8":("ಉಚಿತ ಧಾನ್ಯ ಯೋಜನೆ (AAY)","ತಿಂಗಳಿಗೆ 35 ಕೆಜಿ ಉಚಿತ ಧಾನ್ಯ ಪ್ರತಿ ಕುಟುಂಬಕ್ಕೆ, ಯಾವುದೇ ವೆಚ್ಚವಿಲ್ಲ, ಡಿಸೆಂಬರ್ 2028 ರವರೆಗೆ ಖಾತ್ರಿ"),
            "9":("സൗജന്യ ധാന്യ പദ്ധതി (AAY)","മാസം 35 കിലോ സൗജന്യ ധാന്യം ഓരോ കുടുംബത്തിനും, ചെലവില്ല, ഡിസംബർ 2028 വരെ ഉറപ്പ്"),
            "10":("ମାଗଣା ଶସ୍ୟ ଯୋଜନା (AAY)","ମାସିକ 35 କିଲୋ ମାଗଣା ଶସ୍ୟ ପ୍ରତି ପରିବାର, କୌଣସି ଖର୍ଚ୍ଚ ନାହିଁ, ଡିସେମ୍ବର 2028 ପର୍ଯ୍ୟନ୍ତ ଗ୍ୟାରେଣ୍ଟି"),
            "11":("বিনামূলীয়া শস্য আঁচনি (AAY)","মাহেকীয়া 35 কিলো বিনামূলীয়া শস্য প্ৰতি পৰিয়ালে, কোনো খৰচ নাই, ডিচেম্বৰ 2028 লৈকে গেৰাণ্টি"),
            "12":("ਮੁਫ਼ਤ ਅਨਾਜ ਯੋਜਨਾ (AAY)","ਹਰ ਮਹੀਨੇ 35 ਕਿਲੋ ਮੁਫ਼ਤ ਅਨਾਜ ਪ੍ਰਤੀ ਪਰਿਵਾਰ, ਕੋਈ ਖਰਚਾ ਨਹੀਂ, ਦਸੰਬਰ 2028 ਤੱਕ ਗਰੰਟੀ"),
        },
    },
    {
        # Priority/BPL (orange card) is 5kg per PERSON.
        "match": lambda p, age, inc: p.get("ration")=="2",
        "link": "nfsa.gov.in",
        "text": {
            "1":("Free Grain Scheme (Priority)","5kg free grain/month PER PERSON, no cost, guaranteed till Dec 2028"),
            "2":("मोफत धान्य योजना (प्राधान्य)","दरमहा 5 किलो मोफत धान्य प्रति व्यक्ती, कोणताही खर्च नाही, डिसेंबर 2028 पर्यंत हमी"),
            "3":("मुफ्त अनाज योजना (प्राथमिकता)","हर महीने 5 किलो मुफ्त अनाज प्रति व्यक्ति, कोई खर्च नहीं, दिसंबर 2028 तक गारंटी"),
            "4":("મફત અનાજ યોજના (પ્રાયોરિટી)","દર મહિને 5 કિલો મફત અનાજ પ્રતિ વ્યક્તિ, કોઈ ખર્ચ નહીં, ડિસેમ્બર 2028 સુધી ગેરંટી"),
            "5":("বিনামূল্যে শস্য প্রকল্প (প্রায়োরিটি)","প্রতি মাসে 5 কেজি বিনামূল্যে শস্য প্রতি ব্যক্তি, কোনো খরচ নেই, ডিসেম্বর 2028 পর্যন্ত গ্যারান্টি"),
            "6":("இலவச தானிய திட்டம் (முன்னுரிமை)","மாதம் 5 கிலோ இலவச தானியம் ஒருவருக்கு, செலவு இல்லை, டிசம்பர் 2028 வரை உத்தரவாதம்"),
            "7":("ఉచిత ధాన్యం పథకం (ప్రాధాన్యత)","నెలకు 5 కిలోల ఉచిత ధాన్యం ఒక్కొక్కరికి, ఖర్చు లేదు, డిసెంబర్ 2028 వరకు హామీ"),
            "8":("ಉಚಿತ ಧಾನ್ಯ ಯೋಜನೆ (ಆದ್ಯತೆ)","ತಿಂಗಳಿಗೆ 5 ಕೆಜಿ ಉಚಿತ ಧಾನ್ಯ ಪ್ರತಿ ವ್ಯಕ್ತಿಗೆ, ಯಾವುದೇ ವೆಚ್ಚವಿಲ್ಲ, ಡಿಸೆಂಬರ್ 2028 ರವರೆಗೆ ಖಾತ್ರಿ"),
            "9":("സൗജന്യ ധാന്യ പദ്ധതി (മുൻഗണന)","മാസം 5 കിലോ സൗജന്യ ധാന്യം ഓരോ വ്യക്തിക്കും, ചെലവില്ല, ഡിസംബർ 2028 വരെ ഉറപ്പ്"),
            "10":("ମାଗଣା ଶସ୍ୟ ଯୋଜନା (ପ୍ରାଥମିକତା)","ମାସିକ 5 କିଲୋ ମାଗଣା ଶସ୍ୟ ପ୍ରତି ବ୍ୟକ୍ତି, କୌଣସି ଖର୍ଚ୍ଚ ନାହିଁ, ଡିସେମ୍ବର 2028 ପର୍ଯ୍ୟନ୍ତ ଗ୍ୟାରେଣ୍ଟି"),
            "11":("বিনামূলীয়া শস্য আঁচনি (অগ্ৰাধিকাৰ)","মাহেকীয়া 5 কিলো বিনামূলীয়া শস্য প্ৰতি জনৰ বাবে, কোনো খৰচ নাই, ডিচেম্বৰ 2028 লৈকে গেৰাণ্টি"),
            "12":("ਮੁਫ਼ਤ ਅਨਾਜ ਯੋਜਨਾ (ਤਰਜੀਹ)","ਹਰ ਮਹੀਨੇ 5 ਕਿਲੋ ਮੁਫ਼ਤ ਅਨਾਜ ਪ੍ਰਤੀ ਵਿਅਕਤੀ, ਕੋਈ ਖਰਚਾ ਨਹੀਂ, ਦਸੰਬਰ 2028 ਤੱਕ ਗਰੰਟੀ"),
        },
    },
    {
        "match": lambda p, age, inc: 18<=age<=50 and p.get("bank")=="1",
        "link": "jansuraksha.gov.in",
        "text": {
            "1":("PM Jeevan Jyoti Bima","Rs.2L life insurance for only Rs.436/year (auto-debited from your bank account)"),
            "2":("पीएम जीवन ज्योती विमा","फक्त ₹436/वर्ष मध्ये ₹2 लाख जीवन विमा (तुमच्या बँक खात्यातून ऑटो-डेबिट होते)"),
            "3":("पीएम जीवन ज्योति बीमा","सिर्फ ₹436/साल में ₹2 लाख का जीवन बीमा (आपके बैंक खाते से ऑटो-डेबिट होता है)"),
            "4":("પીએમ જીવન જ્યોતિ વીમા","ફક્ત ₹436/વર્ષમાં ₹2 લાખનો જીવન વીમો (તમારા બેંક ખાતામાંથી ઓટો-ડેબિટ થાય છે)"),
            "5":("পিএম জীবন জ্যোতি বীমা","মাত্র ₹436/বছরে ₹2 লাখ জীবন বীমা (আপনার ব্যাংক অ্যাকাউন্ট থেকে অটো-ডেবিট হয়)"),
            "6":("பிஎம் ஜீவன் ஜோதி பீமா","வருடத்திற்கு ₹436 மட்டுமே செலுத்தி ₹2 லட்சம் ஆயுள் காப்பீடு (உங்கள் வங்கிக் கணக்கிலிருந்து தானாக பிடித்தம் ஆகும்)"),
            "7":("పీఎం జీవన్ జ్యోతి బీమా","సంవత్సరానికి కేవలం ₹436తో ₹2 లక్షల జీవిత బీమా (మీ బ్యాంక్ ఖాతా నుండి ఆటో-డెబిట్ అవుతుంది)"),
            "8":("ಪಿಎಂ ಜೀವನ ಜ್ಯೋತಿ ವಿಮೆ","ವರ್ಷಕ್ಕೆ ಕೇವಲ ₹436 ಕ್ಕೆ ₹2 ಲಕ್ಷ ಜೀವ ವಿಮೆ (ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಖಾತೆಯಿಂದ ಸ್ವಯಂ-ಡೆಬಿಟ್ ಆಗುತ್ತದೆ)"),
            "9":("പിഎം ജീവൻ ജ്യോതി ബീമ","വർഷം ₹436 മാത്രം നൽകി ₹2 ലക്ഷം ജീവിത ഇൻഷുറൻസ് (നിങ്ങളുടെ ബാങ്ക് അക്കൗണ്ടിൽ നിന്ന് ഓട്ടോ-ഡെബിറ്റ് ചെയ്യും)"),
            "10":("ପିଏମ୍ ଜୀବନ ଜ୍ୟୋତି ବୀମା","ବର୍ଷକୁ ମାତ୍ର ₹436 ରେ ₹2 ଲକ୍ଷ ଜୀବନ ବୀମା (ଆପଣଙ୍କ ବ୍ୟାଙ୍କ ଖାତାରୁ ଅଟୋ-ଡେବିଟ୍ ହୁଏ)"),
            "11":("পিএম জীৱন জ্যোতি বীমা","বছৰি মাত্ৰ ₹436 ত ₹2 লাখ জীৱন বীমা (আপোনাৰ বেংক একাউণ্টৰ পৰা অটো-ডেবিট হয়)"),
            "12":("ਪੀਐਮ ਜੀਵਨ ਜੋਤੀ ਬੀਮਾ","ਸਿਰਫ਼ ₹436/ਸਾਲ ਵਿੱਚ ₹2 ਲੱਖ ਜੀਵਨ ਬੀਮਾ (ਤੁਹਾਡੇ ਬੈਂਕ ਖਾਤੇ ਤੋਂ ਆਟੋ-ਡੈਬਿਟ ਹੁੰਦਾ ਹੈ)"),
        },
    },
    {
        "match": lambda p, age, inc: 18<=age<=70 and p.get("bank")=="1",
        "link": "jansuraksha.gov.in",
        "text": {
            "1":("PM Suraksha Bima","Rs.2L accident insurance for only Rs.20/year (auto-debited from your bank account)"),
            "2":("पीएम सुरक्षा विमा","फक्त ₹20/वर्ष मध्ये ₹2 लाख अपघात विमा (तुमच्या बँक खात्यातून ऑटो-डेबिट होते)"),
            "3":("पीएम सुरक्षा बीमा","सिर्फ ₹20/साल में ₹2 लाख का दुर्घटना बीमा (आपके बैंक खाते से ऑटो-डेबिट होता है)"),
            "4":("પીએમ સુરક્ષા વીમા","ફક્ત ₹20/વર્ષમાં ₹2 લાખનો અકસ્માત વીમો (તમારા બેંક ખાતામાંથી ઓટો-ડેબિટ થાય છે)"),
            "5":("পিএম সুরক্ষা বীমা","মাত্র ₹20/বছরে ₹2 লাখ দুর্ঘটনা বীমা (আপনার ব্যাংক অ্যাকাউন্ট থেকে অটো-ডেবিট হয়)"),
            "6":("பிஎம் சுரக்ஷா பீமா","வருடத்திற்கு ₹20 மட்டுமே செலுத்தி ₹2 லட்சம் விபத்து காப்பீடு (உங்கள் வங்கிக் கணக்கிலிருந்து தானாக பிடித்தம் ஆகும்)"),
            "7":("పీఎం సురక్ష బీమా","సంవత్సరానికి కేవలం ₹20తో ₹2 లక్షల ప్రమాద బీమా (మీ బ్యాంక్ ఖాతా నుండి ఆటో-డెబిట్ అవుతుంది)"),
            "8":("ಪಿಎಂ ಸುರಕ್ಷಾ ವಿಮೆ","ವರ್ಷಕ್ಕೆ ಕೇವಲ ₹20 ಕ್ಕೆ ₹2 ಲಕ್ಷ ಅಪಘಾತ ವಿಮೆ (ನಿಮ್ಮ ಬ್ಯಾಂಕ್ ಖಾತೆಯಿಂದ ಸ್ವಯಂ-ಡೆಬಿಟ್ ಆಗುತ್ತದೆ)"),
            "9":("പിഎം സുരക്ഷാ ബീമ","വർഷം ₹20 മാത്രം നൽകി ₹2 ലക്ഷം അപകട ഇൻഷുറൻസ് (നിങ്ങളുടെ ബാങ്ക് അക്കൗണ്ടിൽ നിന്ന് ഓട്ടോ-ഡെബിറ്റ് ചെയ്യും)"),
            "10":("ପିଏମ୍ ସୁରକ୍ଷା ବୀମା","ବର୍ଷକୁ ମାତ୍ର ₹20 ରେ ₹2 ଲକ୍ଷ ଦୁର୍ଘଟଣା ବୀମା (ଆପଣଙ୍କ ବ୍ୟାଙ୍କ ଖାତାରୁ ଅଟୋ-ଡେବିଟ୍ ହୁଏ)"),
            "11":("পিএম সুৰক্ষা বীমা","বছৰি মাত্ৰ ₹20 ত ₹2 লাখ দুৰ্ঘটনা বীমা (আপোনাৰ বেংক একাউণ্টৰ পৰা অটো-ডেবিট হয়)"),
            "12":("ਪੀਐਮ ਸੁਰੱਖਿਆ ਬੀਮਾ","ਸਿਰਫ਼ ₹20/ਸਾਲ ਵਿੱਚ ₹2 ਲੱਖ ਦੁਰਘਟਨਾ ਬੀਮਾ (ਤੁਹਾਡੇ ਬੈਂਕ ਖਾਤੇ ਤੋਂ ਆਟੋ-ਡੈਬਿਟ ਹੁੰਦਾ ਹੈ)"),
        },
    },
    {
        "match": lambda p, age, inc: p.get("occupation")=="3",
        "link": "pmkisan.gov.in",
        "text": {
            "1":("PM Kisan Samman Nidhi","Rs.6,000/year to farmers, paid in 3 installments of Rs.2,000 — requires eKYC + land record seeding to get paid"),
            "2":("पीएम किसान सन्मान निधी","शेतकऱ्यांना दरवर्षी ₹6,000, ₹2,000 च्या 3 हप्त्यांमध्ये — पेमेंटसाठी eKYC + जमीन नोंद जोडणी आवश्यक"),
            "3":("पीएम किसान सम्मान निधि","किसानों को सालाना ₹6,000, ₹2,000 की 3 किश्तों में — भुगतान के लिए eKYC + भूमि रिकॉर्ड जोड़ना ज़रूरी"),
            "4":("પીએમ કિસાન સન્માન નિધિ","ખેડૂતોને વાર્ષિક ₹6,000, ₹2,000ના 3 હપ્તામાં — ચુકવણી માટે eKYC + જમીન રેકોર્ડ જોડાણ જરૂરી"),
            "5":("পিএম কিষান সম্মান নিধি","কৃষকদের বার্ষিক ₹6,000, ₹2,000 করে 3 কিস্তিতে — পেমেন্টের জন্য eKYC + জমির রেকর্ড যুক্ত করা জরুরি"),
            "6":("பிஎம் கிசான் சம்மான் நிதி","விவசாயிகளுக்கு ஆண்டுக்கு ₹6,000, ₹2,000 வீதம் 3 தவணைகளில் — பணம் பெற eKYC + நில பதிவு இணைப்பு தேவை"),
            "7":("పీఎం కిసాన్ సమ్మాన్ నిధి","రైతులకు సంవత్సరానికి ₹6,000, ₹2,000 చొప్పున 3 వాయిదాలలో — చెల్లింపు కోసం eKYC + భూమి రికార్డు అనుసంధానం అవసరం"),
            "8":("ಪಿಎಂ ಕಿಸಾನ್ ಸಮ್ಮಾನ್ ನಿಧಿ","ರೈತರಿಗೆ ವರ್ಷಕ್ಕೆ ₹6,000, ₹2,000 ರಂತೆ 3 ಕಂತುಗಳಲ್ಲಿ — ಪಾವತಿಗೆ eKYC + ಭೂ ದಾಖಲೆ ಜೋಡಣೆ ಅಗತ್ಯ"),
            "9":("പിഎം കിസാൻ സമ്മാൻ നിധി","കർഷകർക്ക് വർഷം ₹6,000, ₹2,000 വീതം 3 ഗഡുക്കളായി — പണം ലഭിക്കാൻ eKYC + ഭൂരേഖ ചേർക്കൽ ആവശ്യമാണ്"),
            "10":("ପିଏମ୍ କିଷାନ ସମ୍ମାନ ନିଧି","କୃଷକମାନଙ୍କୁ ବାର୍ଷିକ ₹6,000, ₹2,000 ଲେଖାଏଁ 3 କିସ୍ତିରେ — ଦେୟ ପାଇଁ eKYC + ଜମି ରେକର୍ଡ ଯୋଡ଼ିବା ଆବଶ୍ୟକ"),
            "11":("পিএম কিষাণ সন্মান নিধি","কৃষকক বছৰি ₹6,000, ₹2,000 কৈ 3 কিস্তিত — পৰিশোধৰ বাবে eKYC + মাটিৰ ৰেকৰ্ড সংযোগ প্ৰয়োজন"),
            "12":("ਪੀਐਮ ਕਿਸਾਨ ਸਨਮਾਨ ਨਿਧੀ","ਕਿਸਾਨਾਂ ਨੂੰ ਸਾਲਾਨਾ ₹6,000, ₹2,000 ਦੀਆਂ 3 ਕਿਸ਼ਤਾਂ ਵਿੱਚ — ਭੁਗਤਾਨ ਲਈ eKYC + ਜ਼ਮੀਨ ਰਿਕਾਰਡ ਜੋੜਨਾ ਜ਼ਰੂਰੀ"),
        },
    },
    {
        "match": lambda p, age, inc: p.get("occupation") in ["3","4","5"],
        "link": "nrega.nic.in",
        "text": {
            "1":("MGNREGA","100 days guaranteed work/year @ Rs.312/day in Maharashtra (rate set centrally each April — check nrega.nic.in if it's been a while)"),
            "2":("मनरेगा","महाराष्ट्रात दरवर्षी 100 दिवस हमी काम @ ₹312/दिवस (दर दरवर्षी एप्रिलमध्ये केंद्राकडून ठरतो — बराच वेळ झाला असल्यास nrega.nic.in वर तपासा)"),
            "3":("मनरेगा","महाराष्ट्र में सालाना 100 दिन गारंटीड काम @ ₹312/दिन (दर हर साल अप्रैल में केंद्र सरकार तय करती है — काफी समय हो गया हो तो nrega.nic.in पर जांचें)"),
            "4":("મનરેગા","મહારાષ્ટ્રમાં વાર્ષિક 100 દિવસ ગેરંટીડ કામ @ ₹312/દિવસ (દર દર વર્ષે એપ્રિલમાં કેન્દ્ર સરકાર નક્કી કરે છે — ઘણો સમય થયો હોય તો nrega.nic.in પર તપાસો)"),
            "5":("মনরেগা","মহারাষ্ট্রে বছরে 100 দিন নিশ্চিত কাজ @ ₹312/দিন (হার প্রতি বছর এপ্রিলে কেন্দ্র সরকার ঠিক করে — অনেকদিন হয়ে থাকলে nrega.nic.in-এ যাচাই করুন)"),
            "6":("மனரேகா","மகாராஷ்டிராவில் ஆண்டுக்கு 100 நாட்கள் உத்தரவாத வேலை @ ₹312/நாள் (விகிதம் ஒவ்வொரு ஆண்டும் ஏப்ரலில் மத்திய அரசால் நிர்ணயிக்கப்படும் — நீண்ட காலமாகியிருந்தால் nrega.nic.in இல் சரிபார்க்கவும்)"),
            "7":("మనరేగా","మహారాష్ట్రలో సంవత్సరానికి 100 రోజుల హామీ పని @ ₹312/రోజు (రేటు ప్రతి సంవత్సరం ఏప్రిల్‌లో కేంద్రం నిర్ణయిస్తుంది — చాలా కాలం అయితే nrega.nic.in లో చూడండి)"),
            "8":("ಮನರೇಗಾ","ಮಹಾರಾಷ್ಟ್ರದಲ್ಲಿ ವರ್ಷಕ್ಕೆ 100 ದಿನಗಳ ಖಾತ್ರಿ ಕೆಲಸ @ ₹312/ದಿನ (ದರವನ್ನು ಪ್ರತಿ ವರ್ಷ ಏಪ್ರಿಲ್‌ನಲ್ಲಿ ಕೇಂದ್ರ ನಿಗದಿಪಡಿಸುತ್ತದೆ — ಬಹಳ ದಿನವಾಗಿದ್ದರೆ nrega.nic.in ನಲ್ಲಿ ಪರಿಶೀಲಿಸಿ)"),
            "9":("മനരേഗ","മഹാരാഷ്ട്രയിൽ വർഷം 100 ദിവസത്തെ ഉറപ്പായ ജോലി @ ₹312/ദിവസം (നിരക്ക് എല്ലാ വർഷവും ഏപ്രിലിൽ കേന്ദ്രം നിശ്ചയിക്കുന്നു — കുറേക്കാലമായെങ്കിൽ nrega.nic.in ൽ പരിശോധിക്കുക)"),
            "10":("ମନରେଗା","ମହାରାଷ୍ଟ୍ରରେ ବାର୍ଷିକ 100 ଦିନ ଗ୍ୟାରେଣ୍ଟି କାମ @ ₹312/ଦିନ (ଦର ପ୍ରତିବର୍ଷ ଏପ୍ରିଲରେ କେନ୍ଦ୍ର ସ୍ଥିର କରେ — ବହୁତ ଦିନ ହୋଇଗଲେ nrega.nic.in ରେ ଯାଞ୍ଚ କରନ୍ତୁ)"),
            "11":("মনৰেগা","মহাৰাষ্ট্ৰত বছৰি 100 দিন নিশ্চিত কাম @ ₹312/দিন (হাৰ প্ৰতিবছৰে এপ্ৰিলত কেন্দ্ৰই নিৰ্ধাৰণ কৰে — বহুদিন হ'লে nrega.nic.in ত পৰীক্ষা কৰক)"),
            "12":("ਮਨਰੇਗਾ","ਮਹਾਰਾਸ਼ਟਰ ਵਿੱਚ ਸਾਲਾਨਾ 100 ਦਿਨ ਗਰੰਟੀਸ਼ੁਦਾ ਕੰਮ @ ₹312/ਦਿਨ (ਦਰ ਹਰ ਸਾਲ ਅਪ੍ਰੈਲ ਵਿੱਚ ਕੇਂਦਰ ਵੱਲੋਂ ਤੈਅ ਕੀਤੀ ਜਾਂਦੀ — ਬਹੁਤ ਸਮਾਂ ਹੋ ਗਿਆ ਹੋਵੇ ਤਾਂ nrega.nic.in 'ਤੇ ਦੇਖੋ)"),
        },
    },
    {
        "match": lambda p, age, inc: p.get("gender")=="1",
        "link": "wcd.gov.in",
        "text": {
            "1":("One Stop Centre (call 181)","Free shelter, legal aid, medical and police help for women in distress, 24/7"),
            "2":("वन स्टॉप सेंटर (181 वर कॉल करा)","संकटात असलेल्या महिलांसाठी मोफत निवारा, कायदेशीर मदत, वैद्यकीय आणि पोलीस मदत, 24/7"),
            "3":("वन स्टॉप सेंटर (181 पर कॉल करें)","संकट में महिलाओं के लिए मुफ्त आश्रय, कानूनी सहायता, चिकित्सा और पुलिस मदद, 24/7"),
            "4":("વન સ્ટોપ સેન્ટર (181 પર કૉલ કરો)","મુશ્કેલીમાં મહિલાઓ માટે મફત આશ્રય, કાનૂની સહાય, તબીબી અને પોલીસ મદદ, 24/7"),
            "5":("ওয়ান স্টপ সেন্টার (181 নম্বরে কল করুন)","বিপদে থাকা নারীদের জন্য বিনামূল্যে আশ্রয়, আইনি সহায়তা, চিকিৎসা ও পুলিশি সাহায্য, 24/7"),
            "6":("ஒன் ஸ்டாப் சென்டர் (181 ஐ அழைக்கவும்)","நெருக்கடியில் உள்ள பெண்களுக்கு இலவச தங்குமிடம், சட்ட உதவி, மருத்துவ மற்றும் காவல் உதவி, 24/7"),
            "7":("వన్ స్టాప్ సెంటర్ (181కి కాల్ చేయండి)","సంక్షోభంలో ఉన్న మహిళలకు ఉచిత ఆశ్రయం, న్యాయ సహాయం, వైద్య మరియు పోలీసు సహాయం, 24/7"),
            "8":("ವನ್ ಸ್ಟಾಪ್ ಸೆಂಟರ್ (181 ಗೆ ಕರೆ ಮಾಡಿ)","ಸಂಕಷ್ಟದಲ್ಲಿರುವ ಮಹಿಳೆಯರಿಗೆ ಉಚಿತ ಆಶ್ರಯ, ಕಾನೂನು ನೆರವು, ವೈದ್ಯಕೀಯ ಮತ್ತು ಪೊಲೀಸ್ ಸಹಾಯ, 24/7"),
            "9":("വൺ സ്റ്റോപ്പ് സെന്റർ (181 ലേക്ക് വിളിക്കുക)","പ്രതിസന്ധിയിലുള്ള സ്ത്രീകൾക്ക് സൗജന്യ അഭയം, നിയമസഹായം, മെഡിക്കൽ, പോലീസ് സഹായം, 24/7"),
            "10":("ୱାନ ଷ୍ଟପ ସେଣ୍ଟର (181 କୁ କଲ କରନ୍ତୁ)","ସଙ୍କଟରେ ଥିବା ମହିଳାମାନଙ୍କ ପାଇଁ ମାଗଣା ଆଶ୍ରୟ, ଆଇନଗତ ସହାୟତା, ଡାକ୍ତରୀ ଏବଂ ପୋଲିସ ସାହାଯ୍ୟ, 24/7"),
            "11":("ৱান ষ্টপ চেণ্টাৰ (181 নম্বৰত কল কৰক)","সংকটত থকা মহিলাসকলৰ বাবে বিনামূলীয়া আশ্ৰয়, আইনী সহায়তা, চিকিৎসা আৰু আৰক্ষী সহায়, 24/7"),
            "12":("ਵਨ ਸਟਾਪ ਸੈਂਟਰ (181 'ਤੇ ਕਾਲ ਕਰੋ)","ਸੰਕਟ ਵਿੱਚ ਔਰਤਾਂ ਲਈ ਮੁਫ਼ਤ ਪਨਾਹ, ਕਾਨੂੰਨੀ ਸਹਾਇਤਾ, ਡਾਕਟਰੀ ਅਤੇ ਪੁਲਿਸ ਮਦਦ, 24/7"),
        },
    },
    {
        # Sanjay Gandhi Niradhar Anudan Yojana — verified July 2026. NOT just
        # widows: covers destitute/disabled/seriously ill/abandoned/divorced
        # women/transgender/unmarried women 35+, age 18-65, income <=21,000
        # or on the BPL list. Rate raised to Rs.1,500/month via DBT from Dec
        # 2024 (older sources still say Rs.600).
        "match": lambda p, age, inc: 18<=age<=65 and (p.get("marital") in ["3","4"] or p.get("occupation")=="5" or p.get("disability") in ["2","3","4","5"] or (p.get("marital")=="1" and age>=35)) and (inc<=21000 or p.get("ration") in ["1","2"]),
        "link": "sjsa.maharashtra.gov.in",
        "text": {
            "1":("Sanjay Gandhi Niradhar Yojana","Rs.1,500/month via direct bank transfer. Covers destitute, disabled, seriously ill, widowed, divorced, abandoned or unmarried (35+) people — not just widows. Apply via mahadbt.maharashtra.gov.in"),
            "2":("संजय गांधी निराधार योजना","थेट बँक हस्तांतरणाद्वारे दरमहा ₹1,500. निराधार, अपंग, गंभीर आजारी, विधवा, घटस्फोटित, त्यागलेल्या किंवा अविवाहित (35+) व्यक्तींना लागू — फक्त विधवांसाठी नाही. mahadbt.maharashtra.gov.in वर अर्ज करा"),
            "3":("संजय गांधी निराधार योजना","सीधे बैंक ट्रांसफर के ज़रिए हर महीने ₹1,500. निराधार, विकलांग, गंभीर बीमार, विधवा, तलाकशुदा, त्यागी गई या अविवाहित (35+) लोगों को लागू — सिर्फ विधवाओं के लिए नहीं. mahadbt.maharashtra.gov.in पर आवेदन करें"),
            "4":("સંજય ગાંધી નિરાધાર યોજના","સીધા બેંક ટ્રાન્સફર દ્વારા દર મહિને ₹1,500. નિરાધાર, વિકલાંગ, ગંભીર બીમાર, વિધવા, છૂટાછેડા, ત્યજાયેલા અથવા અપરિણીત (35+) લોકોને લાગુ — ફક્ત વિધવાઓ માટે નહીં. mahadbt.maharashtra.gov.in પર અરજી કરો"),
            "5":("সঞ্জয় গান্ধী নিরাধার যোজনা","সরাসরি ব্যাংক ট্রান্সফারের মাধ্যমে প্রতি মাসে ₹1,500. নিরাশ্রয়, প্রতিবন্ধী, গুরুতর অসুস্থ, বিধবা, তালাকপ্রাপ্ত, পরিত্যক্ত বা অবিবাহিত (35+) ব্যক্তিদের জন্য — শুধু বিধবাদের জন্য নয়. mahadbt.maharashtra.gov.in-এ আবেদন করুন"),
            "6":("சஞ்சய் காந்தி நிராதார் யோஜனா","நேரடி வங்கி பரிமாற்றம் மூலம் மாதம் ₹1,500. உதவியற்றவர்கள், மாற்றுத்திறனாளிகள், கடுமையான நோயாளிகள், விதவைகள், விவாகரத்தானவர்கள், கைவிடப்பட்டவர்கள் அல்லது திருமணமாகாதவர்கள் (35+) — விதவைகளுக்கு மட்டும் அல்ல. mahadbt.maharashtra.gov.in இல் விண்ணப்பிக்கவும்"),
            "7":("సంజయ్ గాంధీ నిరాధార్ యోజన","నేరుగా బ్యాంక్ బదిలీ ద్వారా నెలకు ₹1,500. నిరాధారులు, వికలాంగులు, తీవ్ర అనారోగ్యంతో ఉన్నవారు, వితంతువులు, విడాకులు తీసుకున్నవారు, వదిలేయబడినవారు లేదా అవివాహితులు (35+) — వితంతువులకు మాత్రమే కాదు. mahadbt.maharashtra.gov.in లో దరఖాస్తు చేయండి"),
            "8":("ಸಂಜಯ್ ಗಾಂಧಿ ನಿರಾಧಾರ್ ಯೋಜನೆ","ನೇರ ಬ್ಯಾಂಕ್ ವರ್ಗಾವಣೆ ಮೂಲಕ ತಿಂಗಳಿಗೆ ₹1,500. ನಿರ್ಗತಿಕರು, ಅಂಗವಿಕಲರು, ಗಂಭೀರ ಅನಾರೋಗ್ಯ ಪೀಡಿತರು, ವಿಧವೆಯರು, ವಿಚ್ಛೇದಿತರು, ಪರಿತ್ಯಕ್ತರು ಅಥವಾ ಅವಿವಾಹಿತರು (35+) — ಕೇವಲ ವಿಧವೆಯರಿಗೆ ಮಾತ್ರವಲ್ಲ. mahadbt.maharashtra.gov.in ನಲ್ಲಿ ಅರ್ಜಿ ಸಲ್ಲಿಸಿ"),
            "9":("സഞ്ജയ് ഗാന്ധി നിരാധാർ യോജന","നേരിട്ട് ബാങ്ക് ട്രാൻസ്ഫർ വഴി മാസം ₹1,500. നിരാലംബർ, വികലാംഗർ, ഗുരുതര രോഗികൾ, വിധവകൾ, വിവാഹമോചിതർ, ഉപേക്ഷിക്കപ്പെട്ടവർ അല്ലെങ്കിൽ അവിവാഹിതർ (35+) — വിധവകൾക്ക് മാത്രമല്ല. mahadbt.maharashtra.gov.in ൽ അപേക്ഷിക്കുക"),
            "10":("ସଞ୍ଜୟ ଗାନ୍ଧୀ ନିରାଧାର ଯୋଜନା","ସିଧାସଳଖ ବ୍ୟାଙ୍କ ଟ୍ରାନ୍ସଫର ମାଧ୍ୟମରେ ମାସିକ ₹1,500. ନିରାଶ୍ରୟ, ଅକ୍ଷମ, ଗମ୍ଭୀର ଅସୁସ୍ଥ, ବିଧବା, ଛାଡ଼ପତ୍ର ପ୍ରାପ୍ତ, ପରିତ୍ୟକ୍ତ କିମ୍ବା ଅବିବାହିତ (35+) ବ୍ୟକ୍ତିଙ୍କ ପାଇଁ — କେବଳ ବିଧବାଙ୍କ ପାଇଁ ନୁହେଁ। mahadbt.maharashtra.gov.in ରେ ଆବେଦନ କରନ୍ତୁ"),
            "11":("সঞ্জয় গান্ধী নিৰাধাৰ যোজনা","প্ৰত্যক্ষ বেংক স্থানান্তৰৰ জৰিয়তে মাহেকীয়া ₹1,500. নিৰাশ্ৰয়, অক্ষম, গুৰুতৰ ৰোগাক্ৰান্ত, বিধৱা, প্ৰাক্তন পতি-পত্নী, পৰিত্যক্ত বা অবিবাহিত (35+) লোকৰ বাবে — কেৱল বিধৱাৰ বাবে নহয়. mahadbt.maharashtra.gov.in ত আবেদন কৰক"),
            "12":("ਸੰਜੇ ਗਾਂਧੀ ਨਿਰਾਧਾਰ ਯੋਜਨਾ","ਸਿੱਧੇ ਬੈਂਕ ਟ੍ਰਾਂਸਫਰ ਰਾਹੀਂ ਹਰ ਮਹੀਨੇ ₹1,500. ਬੇਸਹਾਰਾ, ਅਪੰਗ, ਗੰਭੀਰ ਬਿਮਾਰ, ਵਿਧਵਾ, ਤਲਾਕਸ਼ੁਦਾ, ਤਿਆਗੀਆਂ ਜਾਂ ਅਣਵਿਆਹੀਆਂ (35+) ਲਈ — ਸਿਰਫ਼ ਵਿਧਵਾਵਾਂ ਲਈ ਨਹੀਂ. mahadbt.maharashtra.gov.in 'ਤੇ ਅਰਜ਼ੀ ਦਿਓ"),
        },
    },
    {
        "match": lambda p, age, inc: age>=60 and inc<=150000,
        "link": "nsap.nic.in",
        "text": {
            "1":("Old Age Pension","Rs.1,500/month total in Maharashtra: Rs.200 (60-79) or Rs.500 (80+) from the central scheme, topped up by the state to Rs.1,500/month via Shravan Bal Yojana"),
            "2":("वृद्धापकाळ पेंशन","महाराष्ट्रात एकूण दरमहा ₹1,500: केंद्र योजनेतून ₹200 (60-79) किंवा ₹500 (80+), श्रावण बाळ योजनेद्वारे राज्याकडून ₹1,500 पर्यंत टॉप-अप"),
            "3":("वृद्धावस्था पेंशन","महाराष्ट्र में कुल ₹1,500/माह: केंद्र योजना से ₹200 (60-79) या ₹500 (80+), श्रावण बाल योजना के ज़रिए राज्य से ₹1,500 तक टॉप-अप"),
            "4":("વૃદ્ધાવસ્થા પેન્શન","મહારાષ્ટ્રમાં કુલ ₹1,500/મહિનો: કેન્દ્ર યોજનામાંથી ₹200 (60-79) અથવા ₹500 (80+), શ્રાવણ બાળ યોજના દ્વારા રાજ્ય તરફથી ₹1,500 સુધી ટોપ-અપ"),
            "5":("বার্ধক্য পেনশন","মহারাষ্ট্রে মোট ₹1,500/মাস: কেন্দ্রীয় প্রকল্প থেকে ₹200 (60-79) বা ₹500 (80+), শ্রাবণ বাল যোজনার মাধ্যমে রাজ্য থেকে ₹1,500 পর্যন্ত টপ-আপ"),
            "6":("முதுமை ஓய்வூதியம்","மகாராஷ்டிராவில் மொத்தம் ₹1,500/மாதம்: மத்திய திட்டத்தில் இருந்து ₹200 (60-79) அல்லது ₹500 (80+), ஷ்ரவண் பால் யோஜனா மூலம் மாநிலத்தால் ₹1,500 வரை டாப்-அப்"),
            "7":("వృద్ధాప్య పింఛను","మహారాష్ట్రలో మొత్తం ₹1,500/నెల: కేంద్ర పథకం నుండి ₹200 (60-79) లేదా ₹500 (80+), శ్రావణ్ బాల్ యోజన ద్వారా రాష్ట్రం నుండి ₹1,500 వరకు టాప్-అప్"),
            "8":("ವೃದ್ಧಾಪ್ಯ ಪಿಂಚಣಿ","ಮಹಾರಾಷ್ಟ್ರದಲ್ಲಿ ಒಟ್ಟು ₹1,500/ತಿಂಗಳು: ಕೇಂದ್ರ ಯೋಜನೆಯಿಂದ ₹200 (60-79) ಅಥವಾ ₹500 (80+), ಶ್ರಾವಣ ಬಾಳ ಯೋಜನೆ ಮೂಲಕ ರಾಜ್ಯದಿಂದ ₹1,500 ವರೆಗೆ ಟಾಪ್-ಅಪ್"),
            "9":("വാർദ്ധക്യ പെൻഷൻ","മഹാരാഷ്ട്രയിൽ ആകെ ₹1,500/മാസം: കേന്ദ്ര പദ്ധതിയിൽ നിന്ന് ₹200 (60-79) അല്ലെങ്കിൽ ₹500 (80+), ശ്രാവൺ ബാൽ യോജന വഴി സംസ്ഥാനത്തിൽ നിന്ന് ₹1,500 വരെ ടോപ്പ്-അപ്പ്"),
            "10":("ବୃଦ୍ଧାବସ୍ଥା ପେନସନ","ମହାରାଷ୍ଟ୍ରରେ ମୋଟ ₹1,500/ମାସ: କେନ୍ଦ୍ର ଯୋଜନାରୁ ₹200 (60-79) କିମ୍ବା ₹500 (80+), ଶ୍ରାବଣ ବାଳ ଯୋଜନା ମାଧ୍ୟମରେ ରାଜ୍ୟ ପକ୍ଷରୁ ₹1,500 ପର୍ଯ୍ୟନ୍ତ ଟପ-ଅପ"),
            "11":("বৃদ্ধাৱস্থা পেঞ্চন","মহাৰাষ্ট্ৰত মুঠ ₹1,500/মাহ: কেন্দ্ৰীয় আঁচনিৰ পৰা ₹200 (60-79) বা ₹500 (80+), শ্ৰাৱণ বাল যোজনাৰ জৰিয়তে ৰাজ্যৰ পৰা ₹1,500 লৈকে টপ-আপ"),
            "12":("ਬੁਢਾਪਾ ਪੈਨਸ਼ਨ","ਮਹਾਰਾਸ਼ਟਰ ਵਿੱਚ ਕੁੱਲ ₹1,500/ਮਹੀਨਾ: ਕੇਂਦਰੀ ਯੋਜਨਾ ਤੋਂ ₹200 (60-79) ਜਾਂ ₹500 (80+), ਸ਼੍ਰਾਵਣ ਬਾਲ ਯੋਜਨਾ ਰਾਹੀਂ ਰਾਜ ਵੱਲੋਂ ₹1,500 ਤੱਕ ਟਾਪ-ਅੱਪ"),
        },
    },
    {
        # CORRECTED July 2026: earlier note said the refill subsidy was cut
        # from 9 to 4/year — that was wrong. Cabinet approved Rs.300/refill
        # for up to 9 refills/year for FY2025-26 (Rs.12,000cr outlay,
        # PMIndia/PIB confirmed).
        "match": lambda p, age, inc: p.get("gender")=="1" and inc<=150000 and p.get("ration") in ["1","2"],
        "link": "pmuy.gov.in",
        "text": {
            "1":("PM Ujjwala","NOT fully free — Rs.1,600 connection assistance (14.2kg cylinder) or Rs.1,150 (5kg), plus Rs.300 subsidy per refill for up to 9 refills/year. Needs Aadhaar eKYC done or the subsidy won't be paid."),
            "2":("पीएम उज्ज्वला","पूर्णपणे मोफत नाही — ₹1,600 कनेक्शन सहाय्य (14.2 किलो सिलेंडर) किंवा ₹1,150 (5 किलो), शिवाय दरवर्षी 9 रिफिलपर्यंत प्रति रिफिल ₹300 सबसिडी. आधार eKYC केलेले नसल्यास सबसिडी मिळणार नाही."),
            "3":("पीएम उज्ज्वला","पूरी तरह मुफ्त नहीं — ₹1,600 कनेक्शन सहायता (14.2 किलो सिलेंडर) या ₹1,150 (5 किलो), साथ ही सालाना 9 रिफिल तक प्रति रिफिल ₹300 सब्सिडी. आधार eKYC नहीं हुआ तो सब्सिडी नहीं मिलेगी."),
            "4":("પીએમ ઉજ્જવલા","સંપૂર્ણપણે મફત નથી — ₹1,600 કનેક્શન સહાય (14.2 કિલો સિલિન્ડર) અથવા ₹1,150 (5 કિલો), ઉપરાંત વર્ષે 9 રિફિલ સુધી પ્રતિ રિફિલ ₹300 સબસિડી. આધાર eKYC થયું ન હોય તો સબસિડી નહીં મળે."),
            "5":("পিএম উজ্জ্বলা","সম্পূর্ণ বিনামূল্যে নয় — ₹1,600 সংযোগ সহায়তা (14.2 কেজি সিলিন্ডার) বা ₹1,150 (5 কেজি), সাথে বছরে 9টি রিফিল পর্যন্ত প্রতি রিফিলে ₹300 ভর্তুকি. আধার eKYC না হলে ভর্তুকি মিলবে না."),
            "6":("பிஎம் உஜ்வலா","முழுவதுமாக இலவசம் இல்லை — ₹1,600 இணைப்பு உதவி (14.2 கிலோ சிலிண்டர்) அல்லது ₹1,150 (5 கிலோ), கூடுதலாக ஆண்டுக்கு 9 நிரப்புதல் வரை ஒவ்வொரு நிரப்புதலுக்கும் ₹300 மானியம். ஆதார் eKYC செய்யப்படாவிட்டால் மானியம் கிடைக்காது."),
            "7":("పీఎం ఉజ్వల","పూర్తిగా ఉచితం కాదు — ₹1,600 కనెక్షన్ సహాయం (14.2 కిలోల సిలిండర్) లేదా ₹1,150 (5 కిలోలు), అలాగే సంవత్సరానికి 9 రీఫిల్స్ వరకు ఒక్కో రీఫిల్‌కు ₹300 సబ్సిడీ. ఆధార్ eKYC చేయకపోతే సబ్సిడీ రాదు."),
            "8":("ಪಿಎಂ ಉಜ್ವಲಾ","ಸಂಪೂರ್ಣ ಉಚಿತವಲ್ಲ — ₹1,600 ಸಂಪರ್ಕ ನೆರವು (14.2 ಕೆಜಿ ಸಿಲಿಂಡರ್) ಅಥವಾ ₹1,150 (5 ಕೆಜಿ), ಜೊತೆಗೆ ವರ್ಷಕ್ಕೆ 9 ರೀಫಿಲ್‌ಗಳವರೆಗೆ ಪ್ರತಿ ರೀಫಿಲ್‌ಗೆ ₹300 ಸಬ್ಸಿಡಿ. ಆಧಾರ್ eKYC ಆಗದಿದ್ದರೆ ಸಬ್ಸಿಡಿ ಸಿಗುವುದಿಲ್ಲ."),
            "9":("പിഎം ഉജ്ജ്വല","പൂർണ്ണമായും സൗജന്യമല്ല — ₹1,600 കണക്ഷൻ സഹായം (14.2 കിലോ സിലിണ്ടർ) അല്ലെങ്കിൽ ₹1,150 (5 കിലോ), കൂടാതെ വർഷം 9 റീഫില്ലുകൾ വരെ ഓരോ റീഫില്ലിനും ₹300 സബ്സിഡി. ആധാർ eKYC ചെയ്തിട്ടില്ലെങ്കിൽ സബ്സിഡി ലഭിക്കില്ല."),
            "10":("ପିଏମ୍ ଉଜ୍ଜ୍ୱଳା","ସମ୍ପୂର୍ଣ୍ଣ ମାଗଣା ନୁହେଁ — ₹1,600 ସଂଯୋଗ ସହାୟତା (14.2 କିଲୋ ସିଲିଣ୍ଡର) କିମ୍ବା ₹1,150 (5 କିଲୋ), ସାଙ୍ଗକୁ ବର୍ଷକୁ 9 ରିଫିଲ ପର୍ଯ୍ୟନ୍ତ ପ୍ରତି ରିଫିଲରେ ₹300 ସବସିଡି। ଆଧାର eKYC ହୋଇନଥିଲେ ସବସିଡି ମିଳିବ ନାହିଁ।"),
            "11":("পিএম উজ্জ্বলা","সম্পূৰ্ণ বিনামূলীয়া নহয় — ₹1,600 সংযোগ সহায় (14.2 কিলো চিলিণ্ডাৰ) বা ₹1,150 (5 কিলো), লগতে বছৰি 9টা ৰিফিললৈকে প্ৰতি ৰিফিলত ₹300 ভৰ্তুকি. আধাৰ eKYC নকৰিলে ভৰ্তুকি নাপাব."),
            "12":("ਪੀਐਮ ਉੱਜਵਲਾ","ਪੂਰੀ ਤਰ੍ਹਾਂ ਮੁਫ਼ਤ ਨਹੀਂ — ₹1,600 ਕਨੈਕਸ਼ਨ ਸਹਾਇਤਾ (14.2 ਕਿਲੋ ਸਿਲੰਡਰ) ਜਾਂ ₹1,150 (5 ਕਿਲੋ), ਨਾਲ ਹੀ ਸਾਲਾਨਾ 9 ਰੀਫਿਲਾਂ ਤੱਕ ਪ੍ਰਤੀ ਰੀਫਿਲ ₹300 ਸਬਸਿਡੀ. ਆਧਾਰ eKYC ਨਾ ਹੋਣ 'ਤੇ ਸਬਸਿਡੀ ਨਹੀਂ ਮਿਲੇਗੀ."),
        },
    },
]

# Ayushman Bharat/MJPJAY handled separately (not in MAHARASHTRA_SCHEMES)
# because its benefit text has a conditional extra clause for ration-card
# holders rather than a fixed string. Coverage was expanded to EVERY
# Maharashtra resident in July 2024, not just BPL/ration-card holders — so
# it always applies for Maharashtra profiles, with the extra renal cover
# appended only for ration card holders.
AYUSHMAN_TEXT = {
    "1":("Ayushman Bharat - MJPJAY","Rs.5L/year cashless treatment at empanelled hospitals (1,300+ procedures). ALL Maharashtra residents are covered as of July 2024 — you don't need a ration card or income proof for the base Rs.5L cover."," As an Orange/Yellow ration card holder you also get an extra Rs.1.5L cover for kidney/renal treatment."),
    "2":("आयुष्मान भारत - एमजेपीजेएवाय","सूचीबद्ध रुग्णालयांमध्ये वार्षिक ₹5 लाखांपर्यंत कॅशलेस उपचार (1,300+ प्रक्रिया). जुलै 2024 पासून सर्व महाराष्ट्र रहिवासी पात्र आहेत — मूळ ₹5 लाख कव्हरसाठी रेशन कार्ड किंवा उत्पन्नाचा पुरावा लागत नाही."," नारंगी/पिवळे रेशन कार्डधारकांना किडनी/मूत्रपिंड उपचारासाठी अतिरिक्त ₹1.5 लाख कव्हर मिळते."),
    "3":("आयुष्मान भारत - एमजेपीजेएवाय","सूचीबद्ध अस्पतालों में सालाना ₹5 लाख तक कैशलेस इलाज (1,300+ प्रक्रियाएं). जुलाई 2024 से सभी महाराष्ट्र निवासी कवर हैं — मूल ₹5 लाख कवर के लिए राशन कार्ड या आय प्रमाण की ज़रूरत नहीं."," ऑरेंज/येलो राशन कार्ड धारकों को किडनी/रीनल इलाज के लिए अतिरिक्त ₹1.5 लाख कवर मिलता है."),
    "4":("આયુષ્માન ભારત - એમજેપીજેએવાય","લિસ્ટેડ હોસ્પિટલોમાં વાર્ષિક ₹5 લાખ સુધીની કેશલેસ સારવાર (1,300+ પ્રક્રિયાઓ). જુલાઈ 2024થી તમામ મહારાષ્ટ્ર નિવાસીઓ કવર છે — મૂળ ₹5 લાખ કવર માટે રેશન કાર્ડ કે આવકનો પુરાવો જરૂરી નથી."," ઓરેન્જ/યલો રેશન કાર્ડ ધારકોને કિડની સારવાર માટે વધારાનું ₹1.5 લાખ કવર મળે છે."),
    "5":("আয়ুষ্মান ভারত - এমজেপিজেএভাই","তালিকাভুক্ত হাসপাতালে বার্ষিক ₹5 লাখ পর্যন্ত ক্যাশলেস চিকিৎসা (1,300+ প্রসিডিওর)। জুলাই 2024 থেকে সব মহারাষ্ট্র বাসিন্দা কভারড — মূল ₹5 লাখ কভারের জন্য রেশন কার্ড বা আয়ের প্রমাণ লাগবে না।"," অরেঞ্জ/হলুদ রেশন কার্ডধারীরা কিডনি চিকিৎসার জন্য অতিরিক্ত ₹1.5 লাখ কভার পান।"),
    "6":("ஆயுஷ்மான் பாரத் - எம்ஜேபிஜேஏவை","பட்டியலிடப்பட்ட மருத்துவமனைகளில் ஆண்டுக்கு ₹5 லட்சம் வரை காசில்லா சிகிச்சை (1,300+ செயல்முறைகள்). ஜூலை 2024 முதல் அனைத்து மகாராஷ்டிரா குடியிருப்பாளர்களும் உள்ளடக்கப்பட்டுள்ளனர் — அடிப்படை ₹5 லட்சம் கவரேஜுக்கு ரேஷன் கார்டு அல்லது வருமான ஆதாரம் தேவையில்லை."," ஆரஞ்சு/மஞ்சள் ரேஷன் கார்டு வைத்திருப்பவர்களுக்கு சிறுநீரக சிகிச்சைக்கு கூடுதலாக ₹1.5 லட்சம் கவரேஜ் கிடைக்கும்."),
    "7":("ఆయుష్మాన్ భారత్ - ఎంజేపీజేఏవై","జాబితా చేసిన ఆసుపత్రులలో వార్షికంగా ₹5 లక్షల వరకు నగదు రహిత చికిత్స (1,300+ ప్రక్రియలు). జూలై 2024 నుండి మహారాష్ట్ర నివాసులందరూ కవర్ చేయబడ్డారు — మూల ₹5 లక్షల కవర్‌కు రేషన్ కార్డు లేదా ఆదాయ రుజువు అవసరం లేదు."," ఆరెంజ్/పసుపు రేషన్ కార్డు హోల్డర్‌లకు కిడ్నీ చికిత్స కోసం అదనంగా ₹1.5 లక్షల కవర్ లభిస్తుంది."),
    "8":("ಆಯುಷ್ಮಾನ್ ಭಾರತ್ - ಎಂಜೆಪಿಜೆಎವೈ","ಪಟ್ಟಿ ಮಾಡಲಾದ ಆಸ್ಪತ್ರೆಗಳಲ್ಲಿ ವಾರ್ಷಿಕ ₹5 ಲಕ್ಷದವರೆಗೆ ನಗದುರಹಿತ ಚಿಕಿತ್ಸೆ (1,300+ ಪ್ರಕ್ರಿಯೆಗಳು). ಜುಲೈ 2024 ರಿಂದ ಎಲ್ಲಾ ಮಹಾರಾಷ್ಟ್ರ ನಿವಾಸಿಗಳು ಒಳಗೊಂಡಿದ್ದಾರೆ — ಮೂಲ ₹5 ಲಕ್ಷ ಕವರ್‌ಗೆ ಪಡಿತರ ಚೀಟಿ ಅಥವಾ ಆದಾಯ ಪುರಾವೆ ಅಗತ್ಯವಿಲ್ಲ."," ಕಿತ್ತಳೆ/ಹಳದಿ ಪಡಿತರ ಚೀಟಿದಾರರಿಗೆ ಮೂತ್ರಪಿಂಡ ಚಿಕಿತ್ಸೆಗೆ ಹೆಚ್ಚುವರಿ ₹1.5 ಲಕ್ಷ ಕವರ್ ಸಿಗುತ್ತದೆ."),
    "9":("ആയുഷ്മാൻ ഭാരത് - എംജെപിജെഎവൈ","പട്ടികപ്പെടുത്തിയ ആശുപത്രികളിൽ വാർഷികം ₹5 ലക്ഷം വരെ ക്യാഷ്‌ലെസ് ചികിത്സ (1,300+ പ്രൊസീജറുകൾ). ജൂലൈ 2024 മുതൽ എല്ലാ മഹാരാഷ്ട്ര നിവാസികളും കവർ ചെയ്യപ്പെടുന്നു — അടിസ്ഥാന ₹5 ലക്ഷം കവറിന് റേഷൻ കാർഡോ വരുമാന തെളിവോ ആവശ്യമില്ല."," ഓറഞ്ച്/മഞ്ഞ റേഷൻ കാർഡ് ഉടമകൾക്ക് വൃക്ക ചികിത്സയ്ക്ക് അധികമായി ₹1.5 ലക്ഷം കവർ ലഭിക്കും."),
    "10":("ଆୟୁଷ୍ମାନ ଭାରତ - ଏମଜେପିଜେଏଭାଇ","ତାଲିକାଭୁକ୍ତ ଡାକ୍ତରଖାନାରେ ବାର୍ଷିକ ₹5 ଲକ୍ଷ ପର୍ଯ୍ୟନ୍ତ ନଗଦବିହୀନ ଚିକିତ୍ସା (1,300+ ପ୍ରକ୍ରିୟା). ଜୁଲାଇ 2024 ଠାରୁ ସମସ୍ତ ମହାରାଷ୍ଟ୍ର ବାସିନ୍ଦା ଅନ୍ତର୍ଭୁକ୍ତ — ମୂଳ ₹5 ଲକ୍ଷ କଭର ପାଇଁ ରାସନ କାର୍ଡ କିମ୍ବା ଆୟ ପ୍ରମାଣ ଆବଶ୍ୟକ ନାହିଁ।"," କମଳା/ହଳଦିଆ ରାସନ କାର୍ଡଧାରୀ ହୋଇଥିଲେ କିଡନୀ ଚିକିତ୍ସା ପାଇଁ ଅତିରିକ୍ତ ₹1.5 ଲକ୍ଷ କଭର ମିଳେ।"),
    "11":("আয়ুষ্মান ভাৰত - এমজেপিজেএভাই","তালিকাভুক্ত চিকিৎসালয়ত বাৰ্ষিক ₹5 লাখলৈকে নগদবিহীন চিকিৎসা (1,300+ প্ৰক্ৰিয়া)। জুলাই 2024ৰ পৰা সকলো মহাৰাষ্ট্ৰ বাসিন্দা কভাৰ কৰা হৈছে — মূল ₹5 লাখ কভাৰৰ বাবে ৰেচন কাৰ্ড বা আয়ৰ প্ৰমাণৰ প্ৰয়োজন নাই।"," কমলা/হালধীয়া ৰেচন কাৰ্ডধাৰীয়ে বৃক্ক চিকিৎসাৰ বাবে অতিৰিক্ত ₹1.5 লাখ কভাৰ পাব।"),
    "12":("ਆਯੁਸ਼ਮਾਨ ਭਾਰਤ - ਐਮਜੇਪੀਜੇਏਵਾਈ","ਸੂਚੀਬੱਧ ਹਸਪਤਾਲਾਂ ਵਿੱਚ ਸਾਲਾਨਾ ₹5 ਲੱਖ ਤੱਕ ਨਕਦ ਰਹਿਤ ਇਲਾਜ (1,300+ ਪ੍ਰਕਿਰਿਆਵਾਂ). ਜੁਲਾਈ 2024 ਤੋਂ ਸਾਰੇ ਮਹਾਰਾਸ਼ਟਰ ਨਿਵਾਸੀ ਕਵਰ ਹਨ — ਮੂਲ ₹5 ਲੱਖ ਕਵਰ ਲਈ ਰਾਸ਼ਨ ਕਾਰਡ ਜਾਂ ਆਮਦਨ ਸਬੂਤ ਦੀ ਲੋੜ ਨਹੀਂ."," ਸੰਤਰੀ/ਪੀਲੇ ਰਾਸ਼ਨ ਕਾਰਡ ਧਾਰਕਾਂ ਨੂੰ ਗੁਰਦੇ ਦੇ ਇਲਾਜ ਲਈ ਵਾਧੂ ₹1.5 ਲੱਖ ਕਵਰ ਮਿਲਦਾ ਹੈ."),
}

def match_maharashtra_curated(p, age, inc, lang):
    r = []
    for scheme in MAHARASHTRA_SCHEMES:
        if scheme["match"](p, age, inc):
            name, benefit = scheme["text"].get(lang, scheme["text"]["1"])
            r.append((name, benefit, scheme["link"]))
    name, base, extra = AYUSHMAN_TEXT.get(lang, AYUSHMAN_TEXT["1"])
    benefit = base + (extra if p.get("ration") in ["1","2"] else "")
    r.append((name, benefit, "pmjay.gov.in / jeevandayee.gov.in"))
    return r


def _profile_criteria(p):
    """Map raw FLOW answer codes onto the values used in schemes_eligibility.json."""
    state_idx = p.get("state")
    state = STATE_LIST[int(state_idx)-1] if state_idx and state_idx.isdigit() and 1<=int(state_idx)<=len(STATE_LIST) else None
    has_disability, disability_pct = DISABILITY_MAP.get(p.get("disability"), (False,None))
    return {
        "state": state,
        "age": AGE_MAP.get(p.get("age","2"),22),
        "income": INCOME_MAP.get(p.get("income","2"),175000),
        "gender": GENDER_MAP.get(p.get("gender")),
        "ration": RATION_MAP.get(p.get("ration")),
        "bank": p.get("bank")=="1",
        "occupation": OCC_MAP.get(p.get("occupation")),
        "marital": MARITAL_MAP.get(p.get("marital")),
        "caste": CASTE_MAP.get(p.get("caste")),
        "has_disability": has_disability,
        "disability_pct": disability_pct,
        "land": LAND_MAP.get(p.get("land")),
        "worker_board": WORKER_BOARD_MAP.get(p.get("worker_board")),
    }


# A handful of records are institutional/entity-level grants (e.g. an
# "award for institutions engaged in..." or a rural-development fund paid
# to a Gram Panchayat) that were kept in the database for completeness but
# flagged during extraction as not something an individual can apply for.
# With every eligibility field left null (there's no "are you an
# institution" question), these matched 100% of users in their state —
# telling real people they qualify for a scheme aimed at organizations.
_NOT_INDIVIDUAL_FLAGS = {
    "not_individual_welfare_scheme", "institutional_award", "institutional_or_individual_award",
    "entity_level_scheme_not_individual", "business_entity_scheme_not_individual",
    "benefit_is_institutional_not_individual", "group_based_scheme_not_individual_cash_benefit",
    "institution_level_scheme_not_individual", "not_individual_benefit",
}

def _scheme_matches(scheme, up):
    if _NOT_INDIVIDUAL_FLAGS.intersection(scheme.get("extraction_flags") or ()):
        return False
    # Ambiguous-state records (state_guess was null at extraction time)
    # are excluded from matching entirely rather than guessed at — see
    # the schema-design notes for why.
    if scheme["state"] is None:
        return False
    if scheme["state"] != "central" and scheme["state"] != up["state"]:
        return False
    if scheme["min_age"] is not None and up["age"] < scheme["min_age"]:
        return False
    if scheme["max_age"] is not None and up["age"] > scheme["max_age"]:
        return False
    if scheme["gender"] is not None and up["gender"] is not None and scheme["gender"] != up["gender"]:
        return False
    if scheme["max_income"] is not None and up["income"] > scheme["max_income"]:
        return False
    if scheme["ration_card_types"] and up["ration"] not in scheme["ration_card_types"]:
        return False
    if scheme["occupation"] and up["occupation"] not in scheme["occupation"]:
        return False
    if scheme["marital_status"] and up["marital"] not in scheme["marital_status"]:
        return False
    if scheme["caste_category"] and up["caste"] not in scheme["caste_category"]:
        return False
    if scheme["disability_required"]:
        if not up["has_disability"]:
            return False
        if scheme["disability_percent_min"] is not None:
            if up["disability_pct"] is None or up["disability_pct"] < scheme["disability_percent_min"]:
                return False
    if scheme["land_ownership_required"] and up["land"] is not True:
        return False
    if scheme["worker_board_registration_required"] and up["worker_board"] is not True:
        return False
    if scheme["bank_account_required"] and not up["bank"]:
        return False
    return True


def match(p):
    age = AGE_MAP.get(p.get("age","2"),22)
    inc = INCOME_MAP.get(p.get("income","2"),175000)
    lang = p.get("lang","1")
    up = _profile_criteria(p)

    r = []
    if up["state"] == "Maharashtra":
        r.extend(match_maharashtra_curated(p, age, inc, lang))

    exclude = MAHARASHTRA_CURATED_SLUGS if up["state"] == "Maharashtra" else set()
    for scheme in SCHEMES:
        if scheme["scheme_id"] in exclude:
            continue
        if not _scheme_matches(scheme, up):
            continue
        benefit = scheme["benefit_summary"] or ""
        if scheme.get("caveats"):
            benefit += f"\n⚠ {scheme['caveats']}"
        source = scheme["sources"][0] if scheme.get("sources") else ""
        r.append((scheme["title"], benefit, source))

    return r


# Max valid numbered option per FLOW step — body.isdigit() alone lets an
# out-of-range reply (e.g. "99" to a 3-option gender question) through
# silently, where every *_MAP.get() falls back to None/a default and the
# criterion is quietly dropped rather than rejected. Enforced below so a
# mistyped reply gets a re-prompt instead of an unconstrained match.
STEP_MAX_OPTION = {
    "lang": 12, "state": 36, "age": 5, "gender": 3, "income": 4,
    "ration": 4, "bank": 2, "occupation": 14, "marital": 4,
    "caste": 4, "disability": 5, "land": 2, "worker_board": 3,
}

# Per-language, not one all-languages-concatenated string — by the time
# either of these can fire (any question after the first), the user has
# already picked a language, so showing all 12 scripts run together is
# unnecessary noise right when they're already confused by a rejected reply.
OUT_OF_RANGE_MSG = {"1":"Please pick a valid option number.","2":"कृपया वैध पर्याय क्रमांक निवडा.","3":"कृपया एक मान्य विकल्प संख्या चुनें.","4":"કૃપા કરી માન્ય વિકલ્પ નંબર પસંદ કરો.","5":"অনুগ্রহ করে একটি বৈধ বিকল্প সংখ্যা বেছে নিন।","6":"தயவுசெய்து சரியான விருப்பத் தொகையைத் தேர்ந்தெடுக்கவும்.","7":"దయచేసి సరైన ఎంపిక సంఖ్యను ఎంచుకోండి.","8":"ದಯವಿಟ್ಟು ಮಾನ್ಯ ಆಯ್ಕೆ ಸಂಖ್ಯೆಯನ್ನು ಆರಿಸಿ.","9":"ദയവായി സാധുവായ ഓപ്ഷൻ നമ്പർ തിരഞ്ഞെടുക്കുക.","10":"ଦୟାକରି ଏକ ବୈଧ ବିକଳ୍ପ ସଂଖ୍ୟା ବାଛନ୍ତୁ।","11":"অনুগ্ৰহ কৰি এটা বৈধ বিকল্প সংখ্যা বাছক।","12":"ਕਿਰਪਾ ਕਰਕੇ ਇੱਕ ਵੈਧ ਵਿਕਲਪ ਨੰਬਰ ਚੁਣੋ."}

NOT_A_NUMBER_MSG = {"1":"Please reply with just the number.","2":"कृपया फक्त क्रमांक टाइप करा.","3":"कृपया सिर्फ नंबर लिखें.","4":"કૃપા કરી ફક્ત નંબર લખો.","5":"অনুগ্রহ করে শুধু সংখ্যাটি লিখুন।","6":"தயவுசெய்து எண்ணை மட்டும் பதிலளிக்கவும்.","7":"దయచేసి సంఖ్యను మాత్రమే పంపండి.","8":"ದಯವಿಟ್ಟು ಸಂಖ್ಯೆಯನ್ನು ಮಾತ್ರ ಕಳುಹಿಸಿ.","9":"ദയവായി നമ്പർ മാത്രം അയക്കുക.","10":"ଦୟାକରି କେବଳ ସଂଖ୍ୟା ପଠାନ୍ତୁ।","11":"অনুগ্ৰহ কৰি কেৱল সংখ্যাটো পঠিয়াওক।","12":"ਕਿਰਪਾ ਕਰਕੇ ਸਿਰਫ਼ ਨੰਬਰ ਭੇਜੋ."}

# Only used at the very first question (idx==0), before any language has
# been chosen — the one place showing every script at once is justified.
NOT_A_NUMBER_MSG_UNKNOWN_LANG = "Please reply with a number / कृपया नंबर पाठवा / कृपया नंबर भेजें / કૃપા કરી નંબર મોકલો / অনুগ্রহ করে একটি সংখ্যা পাঠান / தயவுசெய்து ஒரு எண்ணை அனுப்பவும் / దయచేసి ఒక సంఖ్యను పంపండి / ದಯವಿಟ್ಟು ಒಂದು ಸಂಖ್ಯೆಯನ್ನು ಕಳುಹಿಸಿ / ദയവായി ഒരു നമ്പർ അയക്കുക / ଦୟାକରି ଏକ ସଂଖ୍ୟା ପଠାନ୍ତୁ / অনুগ্ৰহ কৰি এটা সংখ্যা পঠিয়াওক / ਕਿਰਪਾ ਕਰਕੇ ਇੱਕ ਨੰਬਰ ਭੇਜੋ"

def q(step, lang):
    if "q" in step: return step["q"]
    key = {"2":"mr","3":"hi","4":"gu","5":"bn","6":"ta","7":"te","8":"kn","9":"ml","10":"or","11":"as","12":"pa"}.get(lang,"en")
    return step.get(key,"")

# A matched-schemes count in the double digits routinely produces a
# 10,000-40,000 character message — WhatsApp's freeform-message limit is
# 1,024 characters and Twilio's own hard cap is 1,600 (error 21617) — so
# sending the full list in one msg.body() call was silently guaranteed to
# fail for virtually every real user. Results are paginated instead: each
# page stays under a total-message target, and any reply while schemes
# remain just requests the next page (session["pending"] holds the rest).
#
# The entries budget is deliberately smaller than the total target: the
# footer (RESULTS_CLOSING or CONTINUE_MSG, appended AFTER the entry loop)
# isn't counted while accumulating entries, so its worst-case length must
# be reserved upfront or a page could still slip past the total target.
RESULTS_TOTAL_TARGET = 950  # keep real margin under WhatsApp's 1,024-char hard limit
_FOOTER_RESERVE = 160       # >= the longest RESULTS_CLOSING/CONTINUE_MSG string in any language
RESULTS_CHAR_BUDGET = RESULTS_TOTAL_TARGET - _FOOTER_RESERVE

# "May be eligible", not "you qualify" -- the matching is deliberately
# over-inclusive (INCOME_MAP uses each bracket's lower bound on purpose,
# false positives are cheaper than false negatives here), and the
# disclaimer shown right after language selection plus RESULTS_CLOSING
# right after this list both already say "guidance, not a guarantee" --
# this header shouldn't be the one place in the conversation that states
# eligibility as settled fact.
RESULTS_HEADER = {"1":"You may be eligible for {n} schemes — check the details below:\n\n","2":"तुम्ही {n} योजनांसाठी पात्र असू शकता — खालील तपशील पहा:\n\n","3":"आप {n} योजनाओं के लिए पात्र हो सकते हैं — नीचे विवरण देखें:\n\n","4":"તમે {n} યોજનાઓ માટે પાત્ર હોઈ શકો છો — નીચે વિગતો જુઓ:\n\n","5":"আপনি {n}টি প্রকল্পের জন্য যোগ্য হতে পারেন — নিচের বিবরণ দেখুন:\n\n","6":"நீங்கள் {n} திட்டங்களுக்கு தகுதியுடையவராக இருக்கலாம் — கீழே உள்ள விவரங்களைப் பார்க்கவும்:\n\n","7":"మీరు {n} పథకాలకు అర్హులు కావచ్చు — దిగువ వివరాలను చూడండి:\n\n","8":"ನೀವು {n} ಯೋಜನೆಗಳಿಗೆ ಅರ್ಹರಾಗಿರಬಹುದು — ಕೆಳಗಿನ ವಿವರಗಳನ್ನು ನೋಡಿ:\n\n","9":"നിങ്ങൾ {n} പദ്ധതികൾക്ക് അർഹരായിരിക്കാം — താഴെയുള്ള വിവരങ്ങൾ കാണുക:\n\n","10":"ଆପଣ {n} ଯୋଜନା ପାଇଁ ଯୋଗ୍ୟ ହୋଇପାରନ୍ତି — ନିମ୍ନରେ ବିବରଣୀ ଦେଖନ୍ତୁ:\n\n","11":"আপুনি {n}টা আঁচনিৰ বাবে যোগ্য হ'ব পাৰে — তলৰ বিৱৰণ চাওক:\n\n","12":"ਤੁਸੀਂ {n} ਯੋਜਨਾਵਾਂ ਲਈ ਯੋਗ ਹੋ ਸਕਦੇ ਹੋ — ਹੇਠਾਂ ਵੇਰਵੇ ਵੇਖੋ:\n\n"}

MORE_HEADER = {"1":"More schemes:\n\n","2":"आणखी योजना:\n\n","3":"और योजनाएं:\n\n","4":"વધુ યોજનાઓ:\n\n","5":"আরও প্রকল্প:\n\n","6":"மேலும் திட்டங்கள்:\n\n","7":"మరిన్ని పథకాలు:\n\n","8":"ಇನ್ನಷ್ಟು ಯೋಜನೆಗಳು:\n\n","9":"കൂടുതൽ പദ്ധതികൾ:\n\n","10":"ଆହୁରି ଯୋଜନା:\n\n","11":"অধিক আঁচনি:\n\n","12":"ਹੋਰ ਯੋਜਨਾਵਾਂ:\n\n"}

# "0" specifically -- not "1" -- because every scheme list on screen also
# starts numbering at 1 (as does every FLOW question's menu), so "reply 1"
# right under a list item literally named "1. <scheme>" reads as "pick
# scheme 1" to a user pattern-matching digits against the nearest list,
# not as a distinct "show more" command. "0" never appears as a valid
# choice anywhere else in the bot.
CONTINUE_MSG = {"1":"Reply 0 for {n} more schemes, or hi to restart.","2":"आणखी {n} योजनांसाठी 0 पाठवा, किंवा पुन्हा सुरू करण्यासाठी hi पाठवा.","3":"और {n} योजनाओं के लिए 0 भेजें, या फिर से शुरू करने के लिए hi भेजें.","4":"વધુ {n} યોજનાઓ માટે 0 મોકલો, અથવા ફરી શરૂ કરવા માટે hi મોકલો.","5":"আরও {n}টি প্রকল্পের জন্য 0 পাঠান, অথবা আবার শুরু করতে hi পাঠান।","6":"மேலும் {n} திட்டங்களுக்கு 0 எனப் பதிலளிக்கவும், அல்லது மீண்டும் தொடங்க hi எனப் பதிலளிக்கவும்.","7":"మరో {n} పథకాల కోసం 0 పంపండి, లేదా మళ్లీ ప్రారంభించడానికి hi పంపండి.","8":"ಇನ್ನೂ {n} ಯೋಜನೆಗಳಿಗಾಗಿ 0 ಕಳುಹಿಸಿ, ಅಥವಾ ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಲು hi ಕಳುಹಿಸಿ.","9":"ഇനിയും {n} പദ്ധതികൾക്കായി 0 അയക്കുക, അല്ലെങ്കിൽ വീണ്ടും ആരംഭിക്കാൻ hi അയക്കുക.","10":"ଆଉ {n} ଯୋଜନା ପାଇଁ 0 ପଠାନ୍ତୁ, କିମ୍ବା ପୁଣି ଆରମ୍ଭ କରିବାକୁ hi ପଠାନ୍ତୁ।","11":"আৰু {n}টা আঁচনিৰ বাবে 0 পঠিয়াওক, বা পুনৰ আৰম্ভ কৰিবলৈ hi পঠিয়াওক।","12":"ਹੋਰ {n} ਯੋਜਨਾਵਾਂ ਲਈ 0 ਭੇਜੋ, ਜਾਂ ਦੁਬਾਰਾ ਸ਼ੁਰੂ ਕਰਨ ਲਈ hi ਭੇਜੋ."}

RESULTS_CLOSING = {"1":"This is a guide, not a guarantee — always confirm at your nearest Aaple Sarkar / Jan Seva Kendra. Reply hi to start again.","2":"ही फक्त मार्गदर्शक माहिती आहे, हमी नाही — जवळच्या आपले सरकार केंद्रावर खात्री करा. पुन्हा hi पाठवा.","3":"यह सिर्फ एक गाइड है, गारंटी नहीं — नज़दीकी आपले सरकार केंद्र पर पुष्टि करें। दोबारा hi भेजें.","4":"આ માર્ગદર્શન છે, ખાતરી નથી — નજીકના જન સેવા કેન્દ્ર પર ખાતરી કરો. ફરી hi મોકલો.","5":"এটি একটি নির্দেশিকা, গ্যারান্টি নয় — নিকটতম জন সেবা কেন্দ্রে নিশ্চিত করুন। আবার hi পাঠান।","6":"இது ஒரு வழிகாட்டி மட்டுமே, உத்தரவாதம் அல்ல — அருகிலுள்ள ஆப்லே சர்க்கார் / ஜன் சேவா கேந்திரத்தில் உறுதிப்படுத்தவும். மீண்டும் தொடங்க hi எனப் பதிலளிக்கவும்.","7":"ఇది ఒక మార్గదర్శిని మాత్రమే, హామీ కాదు — సమీప ఆప్లే సర్కార్ / జన సేవా కేంద్రంలో నిర్ధారించుకోండి. మళ్లీ ప్రారంభించడానికి hi అని పంపండి.","8":"ಇದು ಮಾರ್ಗದರ್ಶಿ ಮಾತ್ರ, ಖಾತರಿಯಲ್ಲ — ಹತ್ತಿರದ ಆಪ್ಲೆ ಸರ್ಕಾರ್ / ಜನ ಸೇವಾ ಕೇಂದ್ರದಲ್ಲಿ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ. ಮತ್ತೆ ಪ್ರಾರಂಭಿಸಲು hi ಎಂದು ಕಳುಹಿಸಿ.","9":"ഇത് ഒരു മാർഗ്ഗനിർദ്ദേശം മാത്രമാണ്, ഉറപ്പല്ല — അടുത്തുള്ള ആപ്ലെ സർക്കാർ / ജൻ സേവാ കേന്ദ്രത്തിൽ സ്ഥിരീകരിക്കുക. വീണ്ടും ആരംഭിക്കാൻ hi എന്ന് അയക്കുക.","10":"ଏହା ଏକ ମାର୍ଗଦର୍ଶିକା, ଗ୍ୟାରେଣ୍ଟି ନୁହେଁ — ନିକଟସ୍ଥ ଜନ ସେବା କେନ୍ଦ୍ରରେ ନିଶ୍ଚିତ କରନ୍ତୁ। ପୁଣି ଆରମ୍ଭ କରିବାକୁ hi ପଠାନ୍ତୁ।","11":"এইটো এটা নিৰ্দেশনা মাত্ৰ, নিশ্চয়তা নহয় — ওচৰৰ জন সেৱা কেন্দ্ৰত নিশ্চিত কৰক। পুনৰ আৰম্ভ কৰিবলৈ hi পঠিয়াওক।","12":"ਇਹ ਸਿਰਫ਼ ਇੱਕ ਮਾਰਗਦਰਸ਼ਨ ਹੈ, ਗਾਰੰਟੀ ਨਹੀਂ — ਨੇੜਲੇ ਜਨ ਸੇਵਾ ਕੇਂਦਰ ਵਿੱਚ ਪੁਸ਼ਟੀ ਕਰੋ। ਦੁਬਾਰਾ ਸ਼ੁਰੂ ਕਰਨ ਲਈ hi ਭੇਜੋ।"}

# Some scheme records carry long, detailed caveats (sourcing/reasoning
# documentation appended during data verification) that alone can exceed
# WhatsApp's 1,024-char limit — one record ran to 1,824 characters by
# itself. Capping each entry's benefit+caveat text is a hard backstop so a
# single verbose record can never consume a whole page (or exceed the
# platform limit outright), independent of how long any future edit makes it.
MAX_ENTRY_BENEFIT_LEN = 450
_CAVEAT_MARKER = "\n⚠ "

def _truncate_benefit(benefit):
    """Shorten an over-length benefit+caveat string. The caveat (marked
    with the ⚠ prefix in match()) is the risk-disclosure half -- eKYC
    requirements, income caps, "genuinely uncertain", "do not confuse with
    X" warnings -- and matters more to not misleading a user than the
    narrative summary preceding it. Naively truncating from the tail always
    cut the caveat first (it's always last), sometimes leaving only an
    unconditional-sounding benefit sentence visible. Shorten the summary
    instead, and only fall back to trimming the caveat itself if it alone
    exceeds the budget."""
    if _CAVEAT_MARKER not in benefit:
        return benefit[:MAX_ENTRY_BENEFIT_LEN].rstrip() + "..."
    summary, caveat = benefit.split(_CAVEAT_MARKER, 1)
    caveat_block = _CAVEAT_MARKER + caveat
    if len(caveat_block) >= MAX_ENTRY_BENEFIT_LEN:
        return caveat_block[:MAX_ENTRY_BENEFIT_LEN].rstrip() + "..."
    available = MAX_ENTRY_BENEFIT_LEN - len(caveat_block) - 3
    return summary[:max(0, available)].rstrip() + "..." + caveat_block

def format_results_page(matched, start_idx, lang):
    """Build one page of results starting at matched[start_idx], staying
    under RESULTS_CHAR_BUDGET. Returns (message_text, next_idx, done)."""
    if start_idx == 0:
        out = RESULTS_HEADER.get(lang, RESULTS_HEADER["1"]).format(n=len(matched))
    else:
        out = MORE_HEADER.get(lang, MORE_HEADER["1"])

    i = start_idx
    n = len(matched)
    while i < n:
        name, benefit, link = matched[i]
        if len(benefit) > MAX_ENTRY_BENEFIT_LEN:
            benefit = _truncate_benefit(benefit)
        entry = f"{i+1}. {name}\n{benefit}\n{link}\n\n"
        # Always include at least one scheme per page (even one that alone
        # exceeds budget) so a single very long entry can't stall pagination.
        if i > start_idx and len(out) + len(entry) > RESULTS_CHAR_BUDGET:
            break
        out += entry
        i += 1

    if i >= n:
        out += RESULTS_CLOSING.get(lang, RESULTS_CLOSING["1"])
        return out, i, True
    out += CONTINUE_MSG.get(lang, CONTINUE_MSG["1"]).format(n=n - i)
    return out, i, False

app.config['MAX_CONTENT_LENGTH'] = 64 * 1024  # WhatsApp messages are short; reject oversized POST bodies outright

_TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
_twilio_validator = RequestValidator(_TWILIO_AUTH_TOKEN) if _TWILIO_AUTH_TOKEN else None

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    # Without this, "From"/"Body" are trusted unconditionally — anyone who
    # finds the webhook URL could POST an arbitrary From to hijack another
    # user's in-progress session, bypassing Twilio/WhatsApp entirely. Only
    # enforced when TWILIO_AUTH_TOKEN is configured (e.g. on Railway), so
    # local dev without Twilio credentials still works.
    if _twilio_validator is not None:
        signature = request.headers.get("X-Twilio-Signature", "")
        if not _twilio_validator.validate(request.url, request.form, signature):
            abort(403)

    sender = request.form.get("From","")
    body = request.form.get("Body","").strip()
    resp = MessagingResponse()
    msg = resp.message()

    if body.lower() in ["hi","hello","start","restart","haqq",""]:
        sessions[sender] = {"step":0,"profile":{}}
        msg.body(FLOW[0]["q"])
        return str(resp)

    session = sessions.get(sender)
    if session is None:
        sessions[sender] = {"step":0,"profile":{}}
        msg.body(FLOW[0]["q"])
        return str(resp)

    if "pending" in session:
        pending = session["pending"]
        page_text, next_idx, done = format_results_page(pending["matched"], pending["next_idx"], pending["lang"])
        if done:
            del sessions[sender]
        else:
            session["pending"]["next_idx"] = next_idx
            sessions[sender] = session
        msg.body(page_text)
        return str(resp)

    idx = session["step"]
    profile = session["profile"]
    lang = profile.get("lang","1")

    # A bounded ASCII-only pattern, not body.isdigit() — isdigit() accepts
    # Unicode characters (e.g. superscript "²", circled "①") that int()
    # cannot parse, and imposes no length cap, so a "digit-like" reply could
    # otherwise raise an uncaught ValueError deep in int(body) below.
    if not re.fullmatch(r"[0-9]{1,3}", body):
        if idx == 0:
            msg.body(NOT_A_NUMBER_MSG_UNKNOWN_LANG)  # no language chosen yet — show all scripts
        else:
            msg.body(NOT_A_NUMBER_MSG.get(lang, NOT_A_NUMBER_MSG["1"]))
        return str(resp)

    step_key = FLOW[idx]["key"]
    max_option = STEP_MAX_OPTION.get(step_key)
    if max_option is not None and not (1 <= int(body) <= max_option):
        msg.body(OUT_OF_RANGE_MSG.get(lang, OUT_OF_RANGE_MSG["1"]))
        return str(resp)

    profile[step_key] = body
    session["profile"] = profile
    session["step"] = idx + 1
    sessions[sender] = session  # write back — the Redis-backed store returns a fresh copy per read, not a live reference
    lang = profile.get("lang", lang)  # re-derive after writing — on the language-selection turn itself, `lang` above was still the stale pre-answer default and would otherwise render the disclaimer/next question in the wrong language

    if session["step"] >= len(FLOW):
        matched = match(profile)
        if not matched:
            # Framed as "not found in Haqq's list" rather than "nothing is
            # available" -- coverage is necessarily incomplete (several
            # flagship central schemes aren't in schemes_eligibility.json
            # yet, and records with an unresolved state are excluded from
            # matching entirely), so a flat "no schemes matched" overstates
            # how complete a negative result actually is.
            no = {"1":"We didn't find a match in Haqq's current list — that doesn't mean nothing is available. Please also check with your nearest Jan Seva Kendra.","2":"Haqq च्या सध्याच्या यादीत जुळणारी कोणतीही योजना सापडली नाही — याचा अर्थ काहीच उपलब्ध नाही असे नाही. कृपया जवळच्या जन सेवा केंद्रातही चौकशी करा.","3":"Haqq की मौजूदा सूची में कोई योजना नहीं मिली — इसका मतलब यह नहीं कि कुछ भी उपलब्ध नहीं है। कृपया नज़दीकी जन सेवा केंद्र पर भी पूछताछ करें।","4":"Haqq ની હાલની યાદીમાં કોઈ યોજના મળી નથી — તેનો અર્થ એ નથી કે કંઈ ઉપલબ્ધ નથી. કૃપા કરી નજીકના જન સેવા કેન્દ્રમાં પણ તપાસ કરો.","5":"Haqq-এর বর্তমান তালিকায় কোনো প্রকল্প মেলেনি — এর মানে এই নয় যে কিছুই নেই। অনুগ্রহ করে নিকটতম জন সেবা কেন্দ্রেও খোঁজ নিন।","6":"Haqq இன் தற்போதைய பட்டியலில் எந்தத் திட்டமும் பொருந்தவில்லை — எதுவும் இல்லை என்று அர்த்தமல்ல. தயவுசெய்து அருகிலுள்ள ஜன் சேவா கேந்திரத்திலும் விசாரிக்கவும்.","7":"Haqq ప్రస్తుత జాబితాలో ఏ పథకం సరిపోలలేదు — ఏమీ లేదని కాదు. దయచేసి సమీప జన సేవా కేంద్రంలో కూడా విచారించండి.","8":"Haqq ನ ಪ್ರಸ್ತುತ ಪಟ್ಟಿಯಲ್ಲಿ ಯಾವುದೇ ಯೋಜನೆ ಹೊಂದಿಕೆಯಾಗಿಲ್ಲ — ಏನೂ ಲಭ್ಯವಿಲ್ಲ ಎಂದು ಅರ್ಥವಲ್ಲ. ದಯವಿಟ್ಟು ಹತ್ತಿರದ ಜನ ಸೇವಾ ಕೇಂದ್ರದಲ್ಲಿಯೂ ವಿಚಾರಿಸಿ.","9":"Haqq ന്റെ നിലവിലെ ലിസ്റ്റിൽ ഒരു പദ്ധതിയും യോജിച്ചില്ല — ഒന്നും ലഭ്യമല്ല എന്നല്ല ഇതിനർത്ഥം. ദയവായി അടുത്തുള്ള ജൻ സേവാ കേന്ദ്രത്തിലും അന്വേഷിക്കുക.","10":"Haqq ର ବର୍ତ୍ତମାନର ତାଲିକାରେ କୌଣସି ଯୋଜନା ମେଳ ଖାଇଲା ନାହିଁ — ଏହାର ଅର୍ଥ ନୁହେଁ ଯେ କିଛି ଉପଲବ୍ଧ ନାହିଁ। ଦୟାକରି ନିକଟସ୍ଥ ଜନ ସେବା କେନ୍ଦ୍ରରେ ମଧ୍ୟ ଖୋଜ କରନ୍ତୁ।","11":"Haqq ৰ বৰ্তমান তালিকাত কোনো আঁচনি মিলা নাই — ইয়াৰ অৰ্থ এই নহয় যে একো উপলব্ধ নাই। অনুগ্ৰহ কৰি ওচৰৰ জন সেৱা কেন্দ্ৰতো বিচাৰি চাওক।","12":"Haqq ਦੀ ਮੌਜੂਦਾ ਸੂਚੀ ਵਿੱਚ ਕੋਈ ਯੋਜਨਾ ਮੇਲ ਨਹੀਂ ਖਾਂਦੀ — ਇਸਦਾ ਮਤਲਬ ਇਹ ਨਹੀਂ ਕਿ ਕੁਝ ਵੀ ਉਪਲਬਧ ਨਹੀਂ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਨੇੜਲੇ ਜਨ ਸੇਵਾ ਕੇਂਦਰ ਵਿੱਚ ਵੀ ਪੁੱਛਗਿੱਛ ਕਰੋ।"}
            msg.body(no.get(lang,no["1"]))
            del sessions[sender]
        else:
            page_text, next_idx, done = format_results_page(matched, 0, lang)
            if done:
                del sessions[sender]
            else:
                sessions[sender] = {"pending": {"matched": matched, "next_idx": next_idx, "lang": lang}}
            msg.body(page_text)
    else:
        next_q = q(FLOW[session["step"]], lang)
        # Only the very first (language) question has its own built-in
        # "Reply:" instruction and, being first, nothing to restart from —
        # every question after that gets the same cue + restart reminder
        # applied once here, rather than duplicated across 12 x 12 raw
        # FLOW strings.
        next_q = NUMBER_CUE.get(lang, NUMBER_CUE["1"]) + next_q + RESTART_HINT.get(lang, RESTART_HINT["1"])
        if idx == 0:
            # Two separate WhatsApp bubbles, not one long concatenated
            # message — a first-time user gets a short disclaimer to read
            # on its own before being confronted with the 36-state list.
            msg.body(DISCLAIMER.get(lang, DISCLAIMER["1"]))
            resp.message().body(next_q)
        else:
            msg.body(next_q)

    return str(resp)

if __name__ == "__main__":
   app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
