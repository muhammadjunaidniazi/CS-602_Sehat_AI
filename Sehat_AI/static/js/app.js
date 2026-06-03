/**
 * Sehat AI — app.js
 * UI logic only. All medical analysis runs in Python (app.py).
 * JavaScript here handles: fetch calls, DOM updates, voice input, directory.
 */

"use strict";

/* ──────────────────────────────────────
   Voice Recognition
────────────────────────────────────── */
let _recognition = null;
let _isRecording = false;

function _initRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  _recognition = new SR();
  _recognition.lang = "ur-PK";
  _recognition.continuous = false;
  _recognition.interimResults = false;

  _recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    document.getElementById("symptoms").value = text;
    _stopVoice();
    // Auto-analyse
    setTimeout(analyseSymptoms, 400);
  };
  _recognition.onerror = () => _stopVoice();
  _recognition.onend   = () => _stopVoice();
  return true;
}

function _startVoice() {
  if (!_initRecognition()) {
    alert("Voice input needs Chrome browser.\nدرست برائوزر: Chrome");
    return;
  }
  _isRecording = true;
  document.getElementById("micBtn").classList.add("recording");
  const vs = document.getElementById("voiceStatus");
  document.getElementById("voiceStatusText").textContent =
    "Listening… بولیں — speak your symptoms";
  vs.classList.remove("hidden");
  _recognition.start();
}

function _stopVoice() {
  _isRecording = false;
  const btn = document.getElementById("micBtn");
  if (btn) btn.classList.remove("recording");
  const vs = document.getElementById("voiceStatus");
  if (vs) vs.classList.add("hidden");
}

window.toggleVoice = function () {
  _isRecording ? (_recognition && _recognition.stop()) : _startVoice();
};

/* ──────────────────────────────────────
   Quick-add chips
────────────────────────────────────── */
window.addSymptom = function (word) {
  const ta = document.getElementById("symptoms");
  const cur = ta.value.trim();
  ta.value = cur ? `${cur}, ${word}` : word;
  ta.focus();
};

window.clearAll = function () {
  document.getElementById("symptoms").value = "";
  document.getElementById("resultPanel").classList.add("hidden");
  document.getElementById("loader").classList.add("hidden");
};

/* ──────────────────────────────────────
   Main Analyse Function
   Sends symptoms to Python backend.
────────────────────────────────────── */
window.analyseSymptoms = async function () {
  const symptoms = document.getElementById("symptoms").value.trim();
  if (!symptoms) {
    _shake(document.getElementById("symptoms"));
    return;
  }

  // UI: loading
  document.getElementById("analyseBtn").disabled = true;
  document.getElementById("resultPanel").classList.add("hidden");
  document.getElementById("loader").classList.remove("hidden");

  try {
    const res  = await fetch("/analyze", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ symptoms }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById("loader").classList.add("hidden");

    if (data.success) {
      _renderResult(data);
    } else {
      _showError(data.error || "Something went wrong. Please try again.");
    }
  } catch (err) {
    document.getElementById("loader").classList.add("hidden");
    _showError("Network error — check connection and try again.");
    console.error("Sehat AI fetch error:", err);
  } finally {
    document.getElementById("analyseBtn").disabled = false;
  }
};

/* ──────────────────────────────────────
   Render Results into DOM
────────────────────────────────────── */
function _renderResult(d) {
  // Source badge
  const srcEl = document.getElementById("sourceTag");
  srcEl.textContent = d.source === "gemini"
    ? "🤖 Gemini AI"
    : d.source === "csv"
      ? "📋 CSV Match"
      : "⚠️ Fallback";
  srcEl.className = `source-tag tag--${d.source || "fallback"}`;

  document.getElementById("resultTime").textContent = d.timestamp || "";

  // Disease
  document.getElementById("diseaseName").textContent  = d.disease    || "–";
  document.getElementById("diseaseUrdu").textContent  = d.urdu_name  || "";

  // Category + severity tags
  const tagsRow = document.getElementById("diseaseTagsRow");
  tagsRow.innerHTML = "";
  if (d.category) {
    const ct = document.createElement("span");
    ct.className = "tag-cat";
    ct.textContent = d.category;
    tagsRow.appendChild(ct);
  }
  if (d.severity) {
    const sv = document.createElement("span");
    sv.className = `tag-sev sev-${d.severity.toLowerCase()}`;
    sv.textContent = d.severity;
    tagsRow.appendChild(sv);
  }

  // Confidence ring (circumference = 2π×30 ≈ 188.5)
  const pct     = Math.min(parseInt(d.confidence) || 0, 100);
  const offset  = 188.5 * (1 - pct / 100);
  requestAnimationFrame(() => {
    document.getElementById("ringProgress").style.strokeDashoffset = offset;
  });
  document.getElementById("confidenceNum").textContent = `${pct}%`;

  // Emergency
  const isEmrg = String(d.emergency).toLowerCase() === "yes";
  const emrgCard = document.getElementById("emergencyCard");
  emrgCard.classList.toggle("is-emrg", isEmrg);
  emrgCard.classList.toggle("no-emrg", !isEmrg);
  document.getElementById("emergencyIcon").textContent = isEmrg ? "🚨" : "✅";
  document.getElementById("emergencyText").textContent = isEmrg
    ? "URGENT — See doctor now"
    : "No immediate emergency";
  document.getElementById("emergencyText").style.color = isEmrg
    ? "var(--c-red)" : "var(--c-green)";

  const callBtn = document.getElementById("emergencyCallBtn");
  callBtn.classList.toggle("hidden", !isEmrg);

  // Advice
  document.getElementById("adviceUrdu").textContent    = d.advice_urdu    || "–";
  document.getElementById("adviceEnglish").textContent = d.advice_english || "–";

  // Show panel and scroll
  const panel = document.getElementById("resultPanel");
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ──────────────────────────────────────
   Emergency / Error Helpers
────────────────────────────────────── */
window.callEmergency = function () {
  const msg =
    "⚠️ EMERGENCY\n\n" +
    "Pakistan Emergency: 1122\n" +
    "Ambulance: 115\n" +
    "Edhi Foundation: 021-111-11-3434\n\n" +
    "Call 1122 now?";
  if (confirm(msg)) window.location.href = "tel:1122";
};

function _showError(msg) {
  alert("Error: " + msg);
}

function _shake(el) {
  el.style.animation = "none";
  el.offsetHeight;  // reflow
  el.style.animation = "shake .4s ease";
  el.focus();
}

/* ──────────────────────────────────────
   Disease Directory
   Fetches from Python /api/diseases
────────────────────────────────────── */
let _allDiseases = [];

async function _loadDirectory() {
  try {
    const res  = await fetch("/api/diseases");
    _allDiseases = await res.json();
    _renderDirectory(_allDiseases);
  } catch (_) {
    document.getElementById("dirGrid").innerHTML =
      '<p style="color:var(--c-muted);font-size:.85rem">Could not load disease directory.</p>';
  }
}

function _renderDirectory(list) {
  const grid = document.getElementById("dirGrid");
  if (!list.length) {
    grid.innerHTML = '<p style="color:var(--c-muted);font-size:.85rem">No results.</p>';
    return;
  }

  grid.innerHTML = list.map((d) => {
    const isEmrg  = String(d.emergency).toLowerCase() === "yes";
    const dotCls  = isEmrg ? "dot-yes" : "dot-no";
    const name    = d.disease   || "–";
    const cat     = d.category  || "";
    return `
      <div class="dir-tile" onclick="quickSearch('${_esc(name)}')">
        <span class="dir-tile-dot ${dotCls}" title="${isEmrg ? 'Emergency' : 'Non-emergency'}"></span>
        <div class="dir-tile-name">${_esc(name)}</div>
        <div class="dir-tile-cat">${_esc(cat)}</div>
      </div>`;
  }).join("");
}

window.filterDirectory = function () {
  const q = document.getElementById("dirFilter").value.toLowerCase().trim();
  if (!q) { _renderDirectory(_allDiseases); return; }
  const filtered = _allDiseases.filter((d) =>
    (d.disease || "").toLowerCase().includes(q) ||
    (d.category || "").toLowerCase().includes(q) ||
    (d.symptoms_english || "").toLowerCase().includes(q)
  );
  _renderDirectory(filtered);
};

// Click a directory tile → pre-fill + analyse
window.quickSearch = function (diseaseName) {
  document.getElementById("symptoms").value = diseaseName;
  window.scrollTo({ top: 0, behavior: "smooth" });
  setTimeout(analyseSymptoms, 600);
};

function _esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ──────────────────────────────────────
   Keyboard Shortcuts
────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  _loadDirectory();

  // Ctrl+Enter or Shift+Enter to analyse
  document.getElementById("symptoms").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.shiftKey) && e.key === "Enter") {
      e.preventDefault();
      analyseSymptoms();
    }
  });
});

/* CSS shake animation injected once */
const _style = document.createElement("style");
_style.textContent = `@keyframes shake{
  0%,100%{transform:translateX(0)}
  20%{transform:translateX(-6px)}
  40%{transform:translateX(6px)}
  60%{transform:translateX(-4px)}
  80%{transform:translateX(4px)}
}`;
document.head.appendChild(_style);

/* ──────────────────────────────────────
   Medicine Lookup
   Sends medicine name to Python /api/medicine
────────────────────────────────────── */

window.quickMed = function (name) {
  document.getElementById("medicineInput").value = name;
  lookupMedicine();
};

window.lookupMedicine = async function () {
  const input = document.getElementById("medicineInput");
  const query = input.value.trim();

  if (query.length < 2) {
    input.classList.add("input-error");
    setTimeout(() => input.classList.remove("input-error"), 800);
    input.focus();
    return;
  }

  // UI state
  document.getElementById("medBtn").disabled = true;
  document.getElementById("medResultPanel").classList.add("hidden");
  document.getElementById("medLoader").classList.remove("hidden");

  try {
    const res = await fetch("/api/medicine", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ medicine: query }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById("medLoader").classList.add("hidden");

    if (data.success) {
      _renderMedicine(data);
    } else {
      alert("Error: " + (data.error || "Medicine lookup failed."));
    }
  } catch (err) {
    document.getElementById("medLoader").classList.add("hidden");
    alert("Network error — check connection and try again.");
    console.error("Medicine fetch error:", err);
  } finally {
    document.getElementById("medBtn").disabled = false;
  }
};

function _renderMedicine(d) {
  // Header
  document.getElementById("medGenericName").textContent = d.generic    || "—";
  document.getElementById("medUrduName").textContent    = d.urdu_name  || "";
  document.getElementById("medTime").textContent        = d.timestamp  || "";

  // Source tag
  const srcEl = document.getElementById("medSourceTag");
  if (d.source === "gemini-web") {
    srcEl.textContent = "🌐 Gemini AI";
    srcEl.className   = "source-tag tag--gemini";
  } else if (d.source === "local-db") {
    srcEl.textContent = "📋 Local DB";
    srcEl.className   = "source-tag tag--csv";
  } else {
    srcEl.textContent = "⚠️ Fallback";
    srcEl.className   = "source-tag tag--fallback";
  }

  // Category tags
  const tagsRow = document.getElementById("medTagsRow");
  tagsRow.innerHTML = "";
  if (d.category) {
    const ct = document.createElement("span");
    ct.className   = "tag-cat";
    ct.textContent = d.category;
    tagsRow.appendChild(ct);
  }
  if (d.otc === true || d.otc === false) {
    const rx = document.createElement("span");
    rx.className   = d.otc ? "tag-otc" : "tag-rx";
    rx.textContent = d.otc ? "OTC" : "Rx Only";
    tagsRow.appendChild(rx);
  }

  // Content cards
  document.getElementById("medUses").textContent           = d.uses           || "—";
  document.getElementById("medUsesUrdu").textContent       = d.uses_urdu      || "";
  document.getElementById("medDosage").textContent         = d.dosage         || "—";
  document.getElementById("medDosageUrdu").textContent     = d.dosage_urdu    || "";
  document.getElementById("medSideEffects").textContent    = d.side_effects   || "—";
  document.getElementById("medSideEffectsUrdu").textContent= d.side_effects_urdu || "";
  document.getElementById("medWarnings").textContent       = d.warnings       || "—";
  document.getElementById("medWarningsUrdu").textContent   = d.warnings_urdu  || "";

  // Drug interactions (Gemini-only field)
  const interactCard = document.getElementById("medInteractCard");
  if (d.interactions) {
    interactCard.style.display = "";
    document.getElementById("medInteract").textContent     = d.interactions      || "—";
    document.getElementById("medInteractUrdu").textContent = d.interactions_urdu || "";
  } else {
    interactCard.style.display = "none";
  }

  // Rx / OTC notice
  const rxNotice = document.getElementById("medRxNotice");
  if (d.otc === false) {
    rxNotice.innerHTML =
      '<span class="rx-alert">⚠️ PRESCRIPTION REQUIRED — نسخہ ضروری ہے۔ ' +
      'Do not take without a doctor\'s prescription.</span>';
  } else if (d.otc === true) {
    rxNotice.innerHTML =
      '<span class="otc-ok">✅ Available Over-the-Counter — بغیر نسخے دستیاب</span>';
  } else {
    rxNotice.innerHTML = "";
  }

  // Show and scroll
  const panel = document.getElementById("medResultPanel");
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}
