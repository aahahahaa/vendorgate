"""Gemini calls. The LLM only READS documents and WRITES emails.
It never decides a status. Every call has a fallback so the app never crashes."""
import base64
import hashlib
import json
import re
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash"

EXTRACT_PROMPT = """You are reading one document uploaded during vendor onboarding.

1. Classify it as exactly one of: gst_certificate, pan_card, cancelled_cheque, w8ben, bank_letter, other.
2. Extract the fields for that type. Use null for anything not clearly visible. Never guess.
   - gst_certificate: gstin, legal_name, trade_name, registration_date (YYYY-MM-DD), state
   - pan_card: pan, name
   - cancelled_cheque: account_holder, account_number, ifsc, bank_name
   - w8ben: name, country, ein
   - bank_letter: account_holder, account_number, swift, bank_name
3. confidence: a number from 0 to 1 for how sure you are the values were read correctly.
   Use a lower number for blurry, rotated, handwritten, cropped or partial documents.

Return only JSON: {"detected_type": "...", "confidence": 0.0, "fields": {...}, "notes": "one short sentence"}"""

EMAIL_PROMPT = """Rewrite this vendor onboarding email so a small-business owner understands it quickly.
Rules:
- Keep every requested item. Do not add, remove or soften any requirement.
- Do not invent deadlines, links, phone numbers or names.
- Plain, polite business English. Under 150 words. Numbered list for the requests.
- Return only the email text, starting with "Dear".

Email:
"""

MIME = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
        "jpeg": "image/jpeg", "webp": "image/webp"}


STATUS = {"state": "unused", "at": None}   # unused | ok | quota | busy; shared by all visitors


def _set_status(state):
    STATUS.update(state=state, at=time.time())


def quota_active():
    """True if the quota ran out since the last daily reset (midnight Pacific)."""
    if STATUS["state"] != "quota" or not STATUS["at"]:
        return False
    from datetime import datetime
    from zoneinfo import ZoneInfo
    pt = datetime.now(ZoneInfo("America/Los_Angeles"))
    last_reset = pt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return STATUS["at"] >= last_reset


FALLBACK_MODEL = None          # optional second model, set from secrets by the app
RETRY_STATUSES = {429, 500, 502, 503, 504}
FRIENDLY = {429: "rate limit reached", 500: "server error", 502: "server error",
            503: "model busy (high demand)", 504: "timed out"}


def _post_once(parts, key, model, json_mode, timeout):
    body = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    r = requests.post(API.format(model=model), json=body, timeout=timeout,
                      headers={"x-goog-api-key": key})  # header, so the key never appears in error text
    return r


def _post(parts, key, model, json_mode, timeout=60, attempts=3):
    """Retries busy/overloaded responses with backoff, then tries the fallback model once."""
    last = None
    for m in [model] + ([FALLBACK_MODEL] if FALLBACK_MODEL and FALLBACK_MODEL != model else []):
        for i in range(attempts):
            try:
                r = _post_once(parts, key, m, json_mode, timeout)
            except requests.RequestException:
                last = "network error"
                time.sleep(2 ** i)
                continue
            if r.status_code == 200:
                _set_status("ok")
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            last = f"{FRIENDLY.get(r.status_code, 'error')} ({r.status_code})"
            if r.status_code not in RETRY_STATUSES:
                raise RuntimeError(f"Gemini {last}")
            if r.status_code == 429:
                break  # quota used up: retrying only wastes requests, try the fallback model
            time.sleep(2 ** i)
    _set_status("quota" if last and "429" in last else "busy")
    if last and "429" in last:
        raise RuntimeError("Gemini quota reached for now (429); the free tier resets daily")
    raise RuntimeError(f"Gemini unavailable: {last}, retried {attempts}x")


def _clean(field, value):
    if value is None:
        return None
    value = str(value).strip()
    if field in {"pan", "gstin", "ifsc", "swift"}:
        value = value.replace(" ", "").upper()
    if field == "account_number":
        value = re.sub(r"\D", "", value)
    return value or None


_CACHE = {}  # sha256(file) + model -> successful extraction


def extract_document(data: bytes, filename: str, slot: str, key: str, model: str) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower()
    base = {"slot": slot, "file": filename}
    ck = hashlib.sha256(data).hexdigest() + model
    if ck in _CACHE:
        return {**base, **_CACHE[ck], "cached": True}
    if ext not in MIME:
        return {**base, "error": f".{ext} files are not supported; upload a PDF, PNG or JPG"}
    try:
        text = _post([{"inline_data": {"mime_type": MIME[ext],
                                       "data": base64.b64encode(data).decode()}},
                      {"text": EXTRACT_PROMPT}], key, model, json_mode=True)
        out = json.loads(re.sub(r"^```(json)?|```$", "", text.strip()).strip())
        fields = {k: _clean(k, v) for k, v in (out.get("fields") or {}).items()}
        result = {"detected_type": out.get("detected_type"),
                  "confidence": float(out.get("confidence", 0)),
                  "fields": {k: v for k, v in fields.items() if v},
                  "notes": out.get("notes", ""), "read_by": model}
        _CACHE[ck] = result
        return {**base, **result}
    except Exception as e:
        return {**base, "error": str(e)[:200]}


def polish_email(template: str, key: str, model: str) -> tuple[str, bool]:
    """Returns (email, was_polished). Falls back to the template on any failure."""
    if quota_active():
        return template, False
    try:
        text = _post([{"text": EMAIL_PROMPT + template}], key, model, json_mode=False, timeout=30)
        text = text.strip()
        return (text, True) if text.lower().startswith("dear") else (template, False)
    except Exception:
        return template, False
