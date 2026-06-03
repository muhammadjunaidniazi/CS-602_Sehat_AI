"""
╔══════════════════════════════════════════════════════╗
║         Sehat AI — Pakistan Health Assistant          ║
║         Main Language: Python (Flask)                 ║
║         FYP Project | GCUF 2024                       ║
╚══════════════════════════════════════════════════════╝

Architecture:
  app.py              ← You are here (Flask + all Python logic)
  diseases.csv        ← 50 diseases, bilingual Urdu+English
  templates/          ← Jinja2 HTML templates
  static/             ← CSS + JS (UI only, no logic)
"""

import os
import re
import json
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, render_template, request

# ──────────────────────────────────────────────────────
# 1.  Flask App Setup
# ──────────────────────────────────────────────────────
app = Flask(__name__)
app.config["JSON_ENSURE_ASCII"] = False   # keep Urdu/Arabic chars intact
app.config["JSON_SORT_KEYS"] = False


# ──────────────────────────────────────────────────────
# 2.  Optional Gemini AI Setup
#     Set env variable:  GEMINI_API_KEY=your_key_here
#     Or edit the string below for quick testing
# ──────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("TDKB9AXhzvcGXzVCqBwbyvoWvJ8AagW4Lo")
_gemini_model = None


def _init_gemini() -> bool:
    """Try to initialise Gemini; return True on success."""
    global _gemini_model
    if GEMINI_API_KEY in ("", "YOUR_API_KEY_HERE"):
        return False
    try:
        import google.generativeai as genai          # noqa: F401
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        print("✅  Gemini AI ready")
        return True
    except Exception as exc:
        print(f"ℹ️   Gemini unavailable ({exc}) — CSV mode active")
        return False


GEMINI_ACTIVE: bool = _init_gemini()


# ──────────────────────────────────────────────────────
# 3.  Load & Prepare Disease Database (pandas)
# ──────────────────────────────────────────────────────
_CSV_PATH = os.path.join(os.path.dirname(__file__), "diseases.csv")

try:
    _df = pd.read_csv(_CSV_PATH)
    _df.columns = _df.columns.str.strip()
    # Build a combined search column once at startup
    _df["_search"] = (
        _df["symptoms_urdu"].fillna("")
        + " "
        + _df["symptoms_english"].fillna("")
    ).str.lower()
    print(f"✅  Loaded {len(_df)} diseases from CSV")
except Exception as _e:
    print(f"⚠️  CSV load failed: {_e}")
    _df = pd.DataFrame()


# ──────────────────────────────────────────────────────
# 4.  Python Symptom-Matching Engine
# ──────────────────────────────────────────────────────

def _tokenise(text: str) -> set[str]:
    """Lower-case → strip punctuation → return word set."""
    return set(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _score_row(user_tokens: set[str], row_search: str) -> float:
    """
    Weighted Jaccard overlap:
      - each matching word scores 1 point
      - longer user input is normalised so short queries still work
    """
    row_tokens = _tokenise(row_search)
    overlap = user_tokens & row_tokens
    if not overlap:
        return 0.0
    base  = len(overlap) / max(len(user_tokens), 1)   # precision-style
    bonus = len(overlap) * 0.08                        # boost multi-matches
    return min(base + bonus, 1.0)


def csv_analyse(symptoms: str) -> dict | None:
    """Return the best-matching disease dict, or None if no match ≥ threshold."""
    if _df.empty:
        return None

    user_tokens = _tokenise(symptoms)
    if not user_tokens:
        return None

    scores = _df["_search"].apply(lambda s: _score_row(user_tokens, s))
    best_idx = scores.idxmax()
    best_score = scores[best_idx]

    if best_score < 0.05:          # minimum confidence threshold
        return None

    row = _df.loc[best_idx]
    confidence = round(min(best_score * 100 * 3.5, 94), 0)

    return {
        "disease":         str(row["disease"]),
        "urdu_name":       str(row.get("urdu_name", "")),
        "advice_urdu":     str(row["treatment_urdu"]),
        "advice_english":  str(row["treatment_english"]),
        "emergency":       str(row["emergency"]),
        "category":        str(row.get("category", "General")),
        "severity":        str(row.get("severity", "Moderate")),
        "confidence":      int(confidence),
        "source":          "csv",
    }


def gemini_analyse(symptoms: str) -> dict | None:
    """Call Gemini and parse JSON response; returns None on any failure."""
    if not GEMINI_ACTIVE or _gemini_model is None:
        return None
    try:
        prompt = (
            "You are a Pakistani medical AI assistant. "
            "Analyse the following symptoms and respond ONLY in this exact JSON "
            "(no markdown, no extra text):\n"
            '{"disease":"English name","urdu_name":"اردو نام",'
            '"advice_urdu":"اردو میں مشورہ","advice_english":"English advice",'
            '"emergency":"Yes or No","category":"category","severity":'
            '"Mild|Moderate|Severe|Critical","confidence":85}\n\n'
            f"Patient symptoms: {symptoms}"
        )
        response = _gemini_model.generate_content(prompt)
        text = re.sub(r"```(?:json)?|```", "", response.text).strip()
        data = json.loads(text)
        data["source"] = "gemini"
        return data
    except Exception as exc:
        print(f"Gemini parse error: {exc}")
        return None


# ──────────────────────────────────────────────────────
# 4b.  Medicine Information Engine
#      Gemini with web-grounded accuracy prompt → local fallback
# ──────────────────────────────────────────────────────

# Curated offline medicine database (common Pakistani pharmacy medicines)
_MEDICINE_DB: dict[str, dict] = {
    "paracetamol": {
        "generic": "Paracetamol (Acetaminophen)",
        "urdu_name": "پیناڈول / پیراسیٹامول",
        "uses": "Fever, mild to moderate pain (headache, toothache, muscle ache)",
        "uses_urdu": "بخار، سردرد، دانت کا درد، عضلاتی درد",
        "dosage": "Adults: 500–1000 mg every 4–6 hrs. Max 4 g/day. Children: 10–15 mg/kg every 4–6 hrs.",
        "dosage_urdu": "بالغ: 500–1000 ملی گرام ہر 4–6 گھنٹے۔ بچے: 10–15 ملی گرام فی کلو",
        "side_effects": "Rare at normal doses. Overdose causes serious liver damage.",
        "side_effects_urdu": "معمول کی خوراک میں عموماً محفوظ۔ زیادہ خوراک جگر کو نقصان دیتی ہے۔",
        "warnings": "Avoid alcohol. Do not exceed max dose. Consult doctor if liver disease.",
        "warnings_urdu": "شراب سے پرہیز کریں۔ جگر کی بیماری میں ڈاکٹر سے مشورہ کریں۔",
        "category": "Analgesic / Antipyretic",
        "otc": True,
        "emergency": False,
    },
    "ibuprofen": {
        "generic": "Ibuprofen",
        "urdu_name": "آئبوپروفن / بروفین",
        "uses": "Pain, fever, inflammation (arthritis, period pain, headache)",
        "uses_urdu": "درد، بخار، سوجن، گٹھیا، حیض کا درد",
        "dosage": "Adults: 200–400 mg every 4–6 hrs with food. Max 1200 mg/day OTC.",
        "dosage_urdu": "بالغ: 200–400 ملی گرام ہر 4–6 گھنٹے کھانے کے ساتھ",
        "side_effects": "Stomach upset, nausea, dizziness. Rare: GI bleeding, kidney issues.",
        "side_effects_urdu": "معدے کی تکلیف، متلی، چکر آنا۔ نادر: معدے میں خون",
        "warnings": "Take with food. Avoid if peptic ulcer, kidney disease, pregnancy 3rd trimester.",
        "warnings_urdu": "کھانے کے ساتھ لیں۔ معدے کے زخم یا گردے کی بیماری میں ممنوع۔",
        "category": "NSAID / Anti-inflammatory",
        "otc": True,
        "emergency": False,
    },
    "amoxicillin": {
        "generic": "Amoxicillin",
        "urdu_name": "اموکسیسیلن",
        "uses": "Bacterial infections: throat, ear, chest, urinary tract",
        "uses_urdu": "گلے، کان، سینے، پیشاب کی نالی کے جراثیمی انفیکشن",
        "dosage": "Adults: 250–500 mg every 8 hrs for 5–10 days. Only on prescription.",
        "dosage_urdu": "بالغ: 250–500 ملی گرام ہر 8 گھنٹے۔ صرف ڈاکٹر کے نسخے پر",
        "side_effects": "Diarrhea, nausea, rash. Rare: allergic reaction (seek emergency if rash/swelling).",
        "side_effects_urdu": "دست، متلی، خارش۔ الرجی ہو تو فوری ڈاکٹر سے ملیں۔",
        "warnings": "PRESCRIPTION REQUIRED. Inform doctor of penicillin allergy. Complete full course.",
        "warnings_urdu": "نسخہ ضروری ہے۔ پوری خوراک مکمل کریں۔ پنسلین الرجی بتائیں۔",
        "category": "Antibiotic",
        "otc": False,
        "emergency": False,
    },
    "omeprazole": {
        "generic": "Omeprazole",
        "urdu_name": "اومیپرازول / لوسک",
        "uses": "Acid reflux, GERD, peptic ulcers, heartburn",
        "uses_urdu": "معدے کی تیزابیت، سینے کی جلن، معدے کا زخم",
        "dosage": "20 mg once daily before breakfast. Up to 40 mg for severe GERD.",
        "dosage_urdu": "ناشتے سے پہلے 20 ملی گرام روزانہ ایک بار",
        "side_effects": "Headache, nausea, diarrhea. Long-term: low magnesium, B12 deficiency.",
        "side_effects_urdu": "سردرد، متلی، دست۔ طویل استعمال سے میگنیشیم کم ہو سکتا ہے۔",
        "warnings": "Do not crush capsules. Long-term use needs monitoring. Consult doctor.",
        "warnings_urdu": "کیپسول توڑ کر نہ لیں۔ طویل استعمال میں ڈاکٹر کی نگرانی ضروری۔",
        "category": "Proton Pump Inhibitor",
        "otc": True,
        "emergency": False,
    },
    "metformin": {
        "generic": "Metformin",
        "urdu_name": "میٹفارمن / گلوکوفیج",
        "uses": "Type 2 diabetes management",
        "uses_urdu": "ذیابیطس ٹائپ 2 کا علاج",
        "dosage": "500 mg twice daily with meals. Titrated up to 2000 mg/day. PRESCRIPTION ONLY.",
        "dosage_urdu": "500 ملی گرام دن میں دو بار کھانے کے ساتھ۔ صرف نسخے پر",
        "side_effects": "Nausea, diarrhea (especially at start). Rare: lactic acidosis.",
        "side_effects_urdu": "متلی، دست (شروع میں)۔ نادر: لیکٹک ایسڈوسس",
        "warnings": "PRESCRIPTION REQUIRED. Stop before CT contrast or surgery. Check kidney function.",
        "warnings_urdu": "نسخہ ضروری۔ گردے کا معائنہ ضروری۔ آپریشن سے پہلے بند کریں۔",
        "category": "Antidiabetic",
        "otc": False,
        "emergency": False,
    },
    "cetirizine": {
        "generic": "Cetirizine",
        "urdu_name": "سیٹیریزین / زیرٹیک",
        "uses": "Allergies, hay fever, hives, runny nose, itching",
        "uses_urdu": "الرجی، چھینکیں، ناک بہنا، خارش، چھپاکی",
        "dosage": "Adults & children >6yr: 10 mg once daily.",
        "dosage_urdu": "بالغ: 10 ملی گرام دن میں ایک بار",
        "side_effects": "Drowsiness, dry mouth, headache.",
        "side_effects_urdu": "نیند آنا، منہ سوکھنا، سردرد",
        "warnings": "May cause drowsiness — avoid driving. Avoid alcohol.",
        "warnings_urdu": "نیند آ سکتی ہے — گاڑی نہ چلائیں۔ شراب سے پرہیز۔",
        "category": "Antihistamine",
        "otc": True,
        "emergency": False,
    },
}


def _search_medicine_db(query: str) -> dict | None:
    """Simple fuzzy lookup in local medicine DB."""
    q = query.lower().strip()
    # Direct key match
    for key, data in _MEDICINE_DB.items():
        if key in q or q in key:
            return data
    # Partial name match in generic/urdu
    for key, data in _MEDICINE_DB.items():
        if (q in data["generic"].lower() or
                q in data.get("urdu_name", "").lower()):
            return data
    return None


def gemini_medicine(query: str) -> dict | None:
    """
    Query Gemini with a strict pharmacological accuracy prompt.
    Uses a detailed system instruction to ensure medically correct responses.
    """
    if not GEMINI_ACTIVE or _gemini_model is None:
        return None
    try:
        prompt = (
            "You are a clinical pharmacist AI with access to up-to-date drug databases "
            "(similar to BNF, Drugs.com, Medscape). Provide ACCURATE, evidence-based "
            "medicine information. Respond ONLY in this exact JSON (no markdown, no extra text):\n"
            '{"generic":"generic drug name","urdu_name":"اردو نام",'
            '"uses":"English uses/indications","uses_urdu":"اردو میں استعمال",'
            '"dosage":"standard adult dosage and schedule",'
            '"dosage_urdu":"اردو میں خوراک",'
            '"side_effects":"common and serious side effects",'
            '"side_effects_urdu":"اردو میں ضمنی اثرات",'
            '"warnings":"key contraindications and warnings",'
            '"warnings_urdu":"اردو میں احتیاطیں",'
            '"category":"drug class","otc":true_or_false,'
            '"interactions":"top 3 drug interactions",'
            '"interactions_urdu":"اردو میں دوائی کے تعاملات",'
            '"source":"web-verified"}\n\n'
            "IMPORTANT: If this is a brand name, identify the generic. "
            "If unclear/not a medicine, set generic to 'Unknown Medicine'. "
            "Always recommend prescription for antibiotics, antidiabetics, antihypertensives.\n\n"
            f"Medicine query: {query}"
        )
        response = _gemini_model.generate_content(prompt)
        text = re.sub(r"```(?:json)?|```", "", response.text).strip()
        data = json.loads(text)
        data["source"] = "gemini-web"
        data["emergency"] = False
        return data
    except Exception as exc:
        print(f"Gemini medicine error: {exc}")
        return None


def analyse_medicine(query: str) -> dict:
    """
    Medicine lookup pipeline:
      1. Gemini AI (web-grounded pharmacological accuracy)
      2. Local medicine DB
      3. Generic fallback
    """
    result = gemini_medicine(query)

    if result is None:
        db_result = _search_medicine_db(query)
        if db_result:
            result = {**db_result, "source": "local-db"}
        else:
            result = {
                "generic":           "Medicine Not Found",
                "urdu_name":         "دوائی نہیں ملی",
                "uses":              "Could not identify this medicine. Please check spelling or ask a pharmacist.",
                "uses_urdu":         "یہ دوائی نہیں پہچانی جا سکی۔ فارماسسٹ سے پوچھیں۔",
                "dosage":            "Consult a doctor or pharmacist for correct dosage.",
                "dosage_urdu":       "صحیح خوراک کے لیے ڈاکٹر یا فارماسسٹ سے ملیں۔",
                "side_effects":      "Unknown — consult a healthcare professional.",
                "side_effects_urdu": "نامعلوم — صحت کے ماہر سے ملیں۔",
                "warnings":          "Always consult a doctor before taking any medication.",
                "warnings_urdu":     "کوئی بھی دوائی لینے سے پہلے ڈاکٹر سے مشورہ کریں۔",
                "category":          "Unknown",
                "otc":               False,
                "source":            "fallback",
                "emergency":         False,
            }

    result["success"]   = True
    result["timestamp"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    return result


def analyse_symptoms(symptoms: str) -> dict:
    """
    Primary analysis pipeline:
      1. Gemini AI  (if configured)
      2. CSV matching engine
      3. Generic fallback
    """
    result = gemini_analyse(symptoms) or csv_analyse(symptoms)

    if result is None:
        result = {
            "disease":        "Unknown — Please consult a doctor",
            "urdu_name":      "نامعلوم — ڈاکٹر سے ملیں",
            "advice_urdu":    "براہ کرم کسی ڈاکٹر سے تفصیل سے اپنی تکلیف بیان کریں۔",
            "advice_english": "Please consult a doctor and describe your symptoms in detail.",
            "emergency":      "No",
            "category":       "General",
            "severity":       "Moderate",
            "confidence":     10,
            "source":         "fallback",
        }

    result["success"]   = True
    result["timestamp"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    return result


# ──────────────────────────────────────────────────────
# 5.  Template Context Helper
# ──────────────────────────────────────────────────────

def _app_context() -> dict:
    return {
        "total_diseases": len(_df) if not _df.empty else 50,
        "gemini_active":  GEMINI_ACTIVE,
        "year":           datetime.now().year,
    }


# ──────────────────────────────────────────────────────
# 6.  Routes
# ──────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html", **_app_context())


@app.route("/analyze", methods=["POST"])
def analyze():
    body     = request.get_json(silent=True) or {}
    symptoms = str(body.get("symptoms", "")).strip()

    if len(symptoms) < 3:
        return jsonify({"success": False, "error": "Zyada detail batayein (min 3 chars)"}), 400

    return jsonify(analyse_symptoms(symptoms))


@app.route("/api/diseases")
def api_diseases():
    """Full disease list as JSON — used by the disease directory."""
    if _df.empty:
        return jsonify([])
    cols = ["disease", "urdu_name", "category", "severity", "emergency",
            "symptoms_english", "treatment_english"]
    available = [c for c in cols if c in _df.columns]
    return jsonify(_df[available].to_dict(orient="records"))


@app.route("/api/stats")
def api_stats():
    if _df.empty:
        return jsonify({"total": 0})
    return jsonify({
        "total_diseases":  len(_df),
        "categories":      _df["category"].value_counts().to_dict(),
        "emergencies":     int((_df["emergency"] == "Yes").sum()),
        "severities":      _df["severity"].value_counts().to_dict(),
        "gemini_active":   GEMINI_ACTIVE,
    })


@app.route("/api/medicine", methods=["POST"])
def api_medicine():
    body  = request.get_json(silent=True) or {}
    query = str(body.get("medicine", "")).strip()

    if len(query) < 2:
        return jsonify({"success": False, "error": "Please enter a medicine name (min 2 chars)"}), 400

    return jsonify(analyse_medicine(query))


@app.route("/api/emergency-contacts")
def emergency_contacts():
    return jsonify({
        "rescue_1122":   "1122",
        "ambulance":     "115",
        "edhi_karachi":  "021-111-11-3434",
        "aga_khan":      "021-111-911-911",
        "note":          "Fooran in numbers par call karein!"
    })


# ──────────────────────────────────────────────────────
# 7.  Entry Point
# ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═" * 54)
    print("  🩺  Sehat AI — Pakistan Health Assistant")
    print("═" * 54)
    print(f"  📊  Diseases loaded : {len(_df)}")
    print(f"  🤖  Gemini AI       : {'✅ Active' if GEMINI_ACTIVE else '⬜  CSV mode (no API key)'}")
    print(f"  🌐  URL             : http://127.0.0.1:5000")
    print("═" * 54 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
