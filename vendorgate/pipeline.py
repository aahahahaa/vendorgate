"""VendorGate pipeline: submission in, reasoned decision out.

Principle: AI reads, rules decide, humans own the grey zone.
Every stage returns a list of Checks. The decision is computed only from
Check severities, so every outcome can be traced back to evidence.

Severities:
  pass    - check succeeded
  info    - noteworthy, does not change the outcome
  skip    - could not run (missing upstream data)
  fix     - vendor can fix it        -> Pending (vendor action)
  review  - needs a human to judge   -> Pending (internal review)
  block   - fraud / ineligible       -> Rejected
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field, asdict

from . import validators as V
from .matching import name_score, name_verdict

SEVERITY_RANK = {"pass": 0, "skip": 1, "info": 1, "fix": 2, "review": 3, "block": 4}
FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com",
                      "outlook.com", "rediffmail.com"}
NEW_GST_DAYS = 30
DOC_NAMES = {"gst_certificate": "GST certificate", "pan_card": "PAN card",
             "cancelled_cheque": "cancelled cheque", "w8ben": "W-8BEN-E form",
             "bank_letter": "bank letter", "aadhaar": "Aadhaar card", "invoice": "invoice"}

RULE_PACKS = {
    "IN": {
        "fields": ["vendor.legal_name", "vendor.entity_type", "vendor.address",
                   "vendor.state", "vendor.contact_email", "tax.pan", "tax.gstin",
                   "bank.account_holder", "bank.account_number", "bank.ifsc"],
        "documents": {"gst_certificate": "GST registration certificate",
                      "pan_card": "PAN card",
                      "cancelled_cheque": "Cancelled cheque"},
    },
    "US": {
        "fields": ["vendor.legal_name", "vendor.entity_type", "vendor.address",
                   "vendor.state", "vendor.contact_email", "tax.ein",
                   "bank.account_holder", "bank.account_number", "bank.swift"],
        "documents": {"w8ben": "Form W-8BEN-E (tax residency)",
                      "bank_letter": "Bank confirmation letter"},
    },
}


@dataclass
class Check:
    id: str
    label: str
    severity: str
    message: str
    evidence: dict = field(default_factory=dict)
    vendor_request: str | None = None


@dataclass
class StageResult:
    key: str
    name: str
    checks: list[Check]
    duration_ms: int = 0

    @property
    def worst(self) -> str:
        if not self.checks:
            return "pass"
        return max((c.severity for c in self.checks), key=SEVERITY_RANK.get)


@dataclass
class Decision:
    status: str              # Approved | Pending | Rejected
    route: str               # who acts next
    reasons: list[str]
    vendor_requests: list[str]
    vendor_email: str | None = None
    internal_summary: str = ""


def _get(sub: dict, dotted: str):
    obj = sub
    for part in dotted.split("."):
        obj = (obj or {}).get(part)
    return obj.strip() if isinstance(obj, str) else obj


# ---------------------------------------------------------------- stages
def stage_intake(ctx):
    sub = ctx["sub"]
    country = _get(sub, "vendor.country") or "IN"
    pack = RULE_PACKS.get(country)
    ctx["country"], ctx["pack"] = country, pack
    if pack is None:
        return [Check("rule_pack", "Rule pack", "review",
                      f"No rule pack for country '{country}'. Routing to a human.",
                      {"country": country})]
    return [Check("received", "Submission received", "pass",
                  f"{_get(sub, 'vendor.legal_name') or 'Unnamed vendor'} "
                  f"· {len(sub.get('documents', []))} document(s)"),
            Check("rule_pack", "Rule pack selected", "pass",
                  f"Applying {country} rules ({len(pack['fields'])} fields, "
                  f"{len(pack['documents'])} documents)", {"country": country})]


def stage_completeness(ctx):
    if not ctx["pack"]:
        return []
    sub, pack, checks = ctx["sub"], ctx["pack"], []
    missing = [f for f in pack["fields"] if not _get(sub, f)]
    if missing:
        labels = ", ".join(f.split(".")[1].replace("_", " ") for f in missing)
        checks.append(Check("fields", "Required fields", "fix",
                            f"Missing: {labels}", {"missing": missing},
                            f"Please fill in: {labels}."))
    else:
        checks.append(Check("fields", "Required fields", "pass",
                            "All required fields present"))
    slots = {d["slot"] for d in sub.get("documents", [])}
    for slot, label in pack["documents"].items():
        if slot in slots:
            checks.append(Check(f"doc_{slot}", label, "pass", "Uploaded"))
        else:
            checks.append(Check(f"doc_{slot}", label, "fix", "Not uploaded", {},
                                f"Please upload your {label}."))
    return checks


def stage_documents(ctx):
    """Classify each upload and accept its extracted fields.

    Extraction itself is done by the extractor (LLM vision) before the
    pipeline runs; here we judge whether the result can be trusted.
    """
    checks, valid = [], {}
    labels = (ctx["pack"] or {}).get("documents", {})
    for doc in ctx["sub"].get("documents", []):
        slot, detected = doc["slot"], doc.get("detected_type")
        label = labels.get(slot, slot)
        conf = doc.get("confidence", 0)
        if doc.get("error"):
            checks.append(Check(f"read_{slot}", f"Read {label}", "review",
                                f"Could not read file: {doc['error']}",
                                {"file": doc.get("file")}))
        elif detected != slot:
            pretty = DOC_NAMES.get(detected, "an unrecognised document")
            checks.append(Check(f"read_{slot}", f"Read {label}", "fix",
                                f"File uploaded as {label} looks like a {pretty}",
                                {"expected": slot, "detected": detected,
                                 "file": doc.get("file")},
                                f"The file you uploaded as your {label} appears to be a "
                                f"{pretty}. Please upload the correct {label}."))
        elif conf < 0.7:
            checks.append(Check(f"read_{slot}", f"Read {label}", "review",
                                f"Low extraction confidence ({conf:.0%}); a person should "
                                f"verify the values", {"fields": doc.get("fields")}))
            valid[slot] = doc["fields"]
        else:
            how = (f"Read live by {doc['read_by']}" if doc.get("read_by")
                   else "Sample file, read in advance")
            checks.append(Check(f"read_{slot}", f"Read {label}", "pass",
                                f"{how}: {len(doc.get('fields', {}))} fields "
                                f"({conf:.0%} confidence)", {"fields": doc.get("fields")}))
            valid[slot] = doc["fields"]
    ctx["docs"] = valid
    return checks


def stage_format(ctx):
    sub, checks = ctx["sub"], []
    ctx["format_ok"] = set()

    def fmt(cid, label, value, ok, bad_msg, request):
        if not value:
            checks.append(Check(cid, label, "skip", "Not provided"))
        elif ok:
            checks.append(Check(cid, label, "pass", f"{value} is well-formed"))
            ctx["format_ok"].add(cid)
        else:
            checks.append(Check(cid, label, "fix", bad_msg, {"value": value}, request))

    email = _get(sub, "vendor.contact_email")
    fmt("email", "Contact email", email, bool(email and V.EMAIL_RE.match(email)),
        f"'{email}' is not a valid email", "Please provide a valid contact email.")
    acct = _get(sub, "bank.account_number")

    if ctx["country"] == "IN":
        pan, gstin, ifsc = (_get(sub, "tax.pan") or "").upper(), \
            (_get(sub, "tax.gstin") or "").upper(), (_get(sub, "bank.ifsc") or "").upper()
        fmt("pan", "PAN format", pan, bool(V.PAN_RE.match(pan)),
            f"'{pan}' is not a valid PAN (expected AAAAA9999A)",
            "Your PAN appears to be in the wrong format. Please re-check it.")
        if gstin and V.GSTIN_RE.match(gstin) and not V.gstin_checksum_ok(gstin):
            checks.append(Check("gstin", "GSTIN format", "fix",
                                f"{gstin} fails the GSTIN check digit (likely a typo)",
                                {"value": gstin,
                                 "expected_last_char": V.gstin_check_char(gstin[:14])},
                                "Your GSTIN looks mistyped. Please copy it exactly "
                                "from your GST certificate."))
        else:
            fmt("gstin", "GSTIN format", gstin, bool(V.GSTIN_RE.match(gstin)),
                f"'{gstin}' is not a valid GSTIN",
                "Your GSTIN appears to be in the wrong format. Please re-check it.")
        fmt("ifsc", "IFSC format", ifsc, bool(V.IFSC_RE.match(ifsc)),
            f"'{ifsc}' is not a valid IFSC (expected AAAA0XXXXXX)",
            "Your IFSC code appears incorrect. Please re-check it.")
        fmt("account", "Account number", acct, bool(acct and V.ACCOUNT_RE.match(acct)),
            "Account number should be 9 to 18 digits",
            "Please re-check your bank account number.")
    else:
        ein, swift = _get(sub, "tax.ein") or "", (_get(sub, "bank.swift") or "").upper()
        if ein and V.PAN_RE.match(ein.upper()):
            checks.append(Check("ein", "Tax ID format", "fix",
                                f"'{ein}' is an Indian PAN, but the vendor declared "
                                f"country {ctx['country']}", {"value": ein},
                                f"You registered as a {ctx['country']} entity, so we need "
                                f"your EIN (format 12-3456789), not an Indian PAN."))
        else:
            fmt("ein", "EIN format", ein, bool(V.EIN_RE.match(ein)),
                f"'{ein}' is not a valid EIN (expected 12-3456789)",
                "Please provide your EIN in the format 12-3456789.")
        fmt("swift", "SWIFT/BIC format", swift, bool(V.SWIFT_RE.match(swift)),
            f"'{swift}' is not a valid SWIFT/BIC", "Please re-check your SWIFT/BIC code.")
        if "swift" in ctx["format_ok"] and swift[4:6] != ctx["country"]:
            checks.append(Check("swift_country", "Bank country", "review",
                                f"Bank is in {swift[4:6]} but vendor is in "
                                f"{ctx['country']} (offshore account)",
                                {"swift_country": swift[4:6]}))
    return checks


def _name_check(cid, label, a, b, a_src, b_src, request=None):
    score = name_score(a, b)
    verdict = name_verdict(score)
    ev = {a_src: a, b_src: b, "similarity": score}
    if verdict == "match":
        exact = a.strip().lower() == b.strip().lower()
        note = "" if exact else " after normalising abbreviations/case"
        return Check(cid, label, "pass", f"Names match{note} ({score}% similar)", ev)
    return Check(cid, label, "review",
                 f"{a_src} '{a}' vs {b_src} '{b}' ({score}% similar)", ev, request)


def stage_crossref(ctx):
    sub, docs, ok, checks = ctx["sub"], ctx["docs"], ctx["format_ok"], []
    legal = _get(sub, "vendor.legal_name") or ""

    if ctx["country"] == "IN":
        pan = (_get(sub, "tax.pan") or "").upper()
        gstin = (_get(sub, "tax.gstin") or "").upper()
        if {"pan", "gstin"} <= ok:
            if gstin[2:12] == pan:
                checks.append(Check("pan_in_gstin", "PAN ↔ GSTIN", "pass",
                                    "PAN embedded in GSTIN matches submitted PAN"))
            else:
                checks.append(Check("pan_in_gstin", "PAN ↔ GSTIN", "review",
                                    f"GSTIN contains PAN {gstin[2:12]}, but submitted "
                                    f"PAN is {pan}",
                                    {"pan_in_gstin": gstin[2:12], "submitted_pan": pan},
                                    "The PAN inside your GSTIN does not match the PAN "
                                    "you submitted. Please confirm both."))
        if "gstin" in ok:
            gst_state = V.GST_STATE_CODES.get(gstin[:2], f"code {gstin[:2]}")
            addr_state = _get(sub, "vendor.state") or ""
            if gst_state.lower() == addr_state.lower():
                checks.append(Check("gst_state", "GSTIN state ↔ address", "pass",
                                    f"GSTIN registered in {gst_state}, matches address"))
            else:
                checks.append(Check("gst_state", "GSTIN state ↔ address", "review",
                                    f"GSTIN is registered in {gst_state} but billing "
                                    f"address is in {addr_state}",
                                    {"gstin_state": gst_state, "address_state": addr_state},
                                    f"Your GSTIN is registered in {gst_state}, but your "
                                    f"address is in {addr_state}. If you hold a GSTIN for "
                                    f"{addr_state}, please share it."))
        entity = _get(sub, "vendor.entity_type")
        if "pan" in ok and entity in V.ENTITY_TO_PAN_CHAR:
            want, got = V.ENTITY_TO_PAN_CHAR[entity], pan[3]
            if want == got:
                checks.append(Check("pan_entity", "PAN holder type ↔ entity", "pass",
                                    f"PAN type '{got}' ({V.PAN_HOLDER_TYPE[got]}) fits "
                                    f"{entity}"))
            else:
                checks.append(Check("pan_entity", "PAN holder type ↔ entity", "review",
                                    f"PAN type '{got}' means "
                                    f"{V.PAN_HOLDER_TYPE.get(got, 'unknown')}, but vendor "
                                    f"declared {entity}", {"pan_char": got, "entity": entity}))

        gc = docs.get("gst_certificate")
        if gc:
            if gc.get("gstin", "").upper() == gstin:
                checks.append(Check("gstin_doc", "GSTIN: form ↔ certificate", "pass",
                                    "GSTIN on certificate matches form"))
            else:
                checks.append(Check("gstin_doc", "GSTIN: form ↔ certificate", "review",
                                    f"Form says {gstin}, certificate says {gc.get('gstin')}",
                                    {"form": gstin, "certificate": gc.get("gstin")}))
            checks.append(_name_check("name_gst", "Name: form ↔ GST certificate",
                                      legal, gc.get("legal_name", ""), "Form",
                                      "GST certificate"))
        pc = docs.get("pan_card")
        if pc:
            if pc.get("pan", "").upper() == pan:
                checks.append(Check("pan_doc", "PAN: form ↔ PAN card", "pass",
                                    "PAN on card matches form"))
            else:
                checks.append(Check("pan_doc", "PAN: form ↔ PAN card", "review",
                                    f"Form says {pan}, PAN card says {pc.get('pan')}",
                                    {"form": pan, "card": pc.get("pan")}))
        bank_doc = docs.get("cancelled_cheque")
    else:
        w8 = docs.get("w8ben")
        if w8 and w8.get("ein"):
            ein = _get(sub, "tax.ein")
            sev = "pass" if w8["ein"] == ein else "review"
            checks.append(Check("ein_doc", "EIN: form ↔ W-8BEN-E", sev,
                                "EIN matches tax form" if sev == "pass"
                                else f"Form {ein} vs W-8BEN-E {w8['ein']}"))
        bank_doc = docs.get("bank_letter")

    if bank_doc:
        acct = _get(sub, "bank.account_number")
        if bank_doc.get("account_number") == acct:
            checks.append(Check("acct_doc", "Account: form ↔ bank proof", "pass",
                                "Account number on bank proof matches form"))
        else:
            checks.append(Check("acct_doc", "Account: form ↔ bank proof", "review",
                                f"Form ...{str(acct)[-4:]} vs bank proof "
                                f"...{str(bank_doc.get('account_number'))[-4:]}"))
        checks.append(_name_check(
            "name_bank", "Name: legal name ↔ bank account holder", legal,
            bank_doc.get("account_holder", ""), "Legal name", "Account holder",
            "The bank account holder name does not match your registered legal name. "
            "Please share a bank letter confirming the account belongs to your company."))
    if not checks:
        checks.append(Check("crossref", "Cross-reference", "skip",
                            "Nothing to cross-check until upstream issues are fixed"))
    return checks


def stage_external(ctx):
    sub, checks = ctx["sub"], []
    if ctx["country"] == "IN":
        if "ifsc" in ctx["format_ok"]:
            ifsc = _get(sub, "bank.ifsc").upper()
            info = V.ifsc_lookup(ifsc)
            src = "live API" if info["source"] == "live" else "offline table"
            if not info["found"]:
                checks.append(Check("ifsc_lookup", "IFSC lookup", "fix",
                                    f"{ifsc} does not exist ({src})", info,
                                    "Your IFSC code does not exist. Please re-check it."))
            else:
                where = f", {info['branch']}, {info['city']}" if info.get("branch") else ""
                checks.append(Check("ifsc_lookup", "IFSC lookup", "pass",
                                    f"{info['bank']}{where} ({src})", info))
                cheque = ctx["docs"].get("cancelled_cheque")
                if cheque and cheque.get("bank_name"):
                    s = name_score(info["bank"], cheque["bank_name"])
                    sev = "pass" if s >= 70 else "review"
                    checks.append(Check("ifsc_bank", "IFSC bank ↔ cheque bank", sev,
                                        f"IFSC belongs to {info['bank']}; cheque is from "
                                        f"{cheque['bank_name']}", {"similarity": s}))
        if "gstin" in ctx["format_ok"]:
            gstin = _get(sub, "tax.gstin").upper()
            rec = ctx["gst_registry"].get(gstin)
            if rec is None:
                checks.append(Check("gst_status", "GST registry", "info",
                                    f"{gstin} is not in the sample registry. Simulated: "
                                    f"production would confirm it on the GST portal",
                                    {"gstin": gstin}))
            elif rec["status"] != "Active":
                checks.append(Check("gst_status", "GST registry", "block",
                                    f"GST registration is {rec['status']}", rec))
            else:
                checks.append(Check("gst_status", "GST registry", "pass",
                                    f"Active since {rec['registration_date']}", rec))
                age = (ctx["today"] - dt.date.fromisoformat(rec["registration_date"])).days
                if age < NEW_GST_DAYS:
                    checks.append(Check("gst_age", "Registration age", "review",
                                        f"GST registered only {age} days ago",
                                        {"days": age}))
        checks.append(Check("penny_drop", "Bank account verification", "info",
                            "Simulated: production would run a ₹1 penny-drop via a "
                            "bank verification API"))
    else:
        checks.append(Check("tax_registry", "Tax registry", "info",
                            "Simulated: production would verify EIN via IRS TIN matching"))
    return checks


def stage_risk(ctx):
    sub, master, checks = ctx["sub"], ctx["vendor_master"], []
    acct = _get(sub, "bank.account_number")
    pan = (_get(sub, "tax.pan") or _get(sub, "tax.ein") or "").upper()
    for v in master:
        if acct and v["account_number"] == acct:
            if v["tax_id"].upper() != pan:
                checks.append(Check("dup_bank", "Bank account reuse", "block",
                                    f"Account ...{acct[-4:]} already belongs to "
                                    f"{v['vendor_id']} {v['legal_name']} (different tax ID)",
                                    {"existing_vendor": v}))
            else:
                checks.append(Check("dup_vendor", "Existing vendor", "review",
                                    f"Same bank and tax ID as {v['vendor_id']}: likely a "
                                    f"duplicate record", {"existing_vendor": v}))
        elif pan and v["tax_id"].upper() == pan:
            checks.append(Check("dup_vendor", "Existing vendor", "review",
                                f"Tax ID already on file as {v['vendor_id']} "
                                f"{v['legal_name']}", {"existing_vendor": v}))
    if not any(c.id.startswith("dup") for c in checks):
        checks.append(Check("dup", "Duplicate check", "pass",
                            f"No overlap with {len(master)} existing vendors"))
    email = _get(sub, "vendor.contact_email") or ""
    if email.split("@")[-1].lower() in FREE_EMAIL_DOMAINS:
        checks.append(Check("email_domain", "Email domain", "info",
                            f"{email.split('@')[-1]} is a free email provider"))
    return checks


STAGES = [
    ("intake", "Intake", stage_intake),
    ("completeness", "Completeness", stage_completeness),
    ("documents", "Document understanding", stage_documents),
    ("format", "Format validation", stage_format),
    ("crossref", "Cross-reference", stage_crossref),
    ("external", "External verification", stage_external),
    ("risk", "Risk & duplicates", stage_risk),
]


# ---------------------------------------------------------------- decision
def decide(stages: list[StageResult], sub: dict) -> Decision:
    checks = [c for s in stages for c in s.checks]
    blocks = [c for c in checks if c.severity == "block"]
    reviews = [c for c in checks if c.severity == "review"]
    fixes = [c for c in checks if c.severity == "fix"]
    requests = [c.vendor_request for c in fixes + reviews if c.vendor_request]
    requests = list(dict.fromkeys(requests))

    if blocks:
        status, route, why = "Rejected", "Escalated to procurement risk", blocks + reviews
        requests = []  # never tell a suspected fraudster what tripped the check
    elif reviews:
        status, route, why = "Pending", "Internal review", reviews + fixes
    elif fixes:
        status, route, why = "Pending", "Vendor action", fixes
    else:
        status, route, why = "Approved", "Ready to create in vendor master", []

    reasons = [f"{c.label}: {c.message}" for c in why] or ["All checks passed"]
    name = _get(sub, "vendor.legal_name") or "the vendor"
    summary = (f"{name}: {status} ({route}). "
               f"{len(blocks)} blocking, {len(reviews)} for review, {len(fixes)} fixable.")
    return Decision(status, route, reasons, requests, None, summary)


def draft_vendor_email(sub: dict, decision: Decision) -> str | None:
    """Template version; the LLM version rewrites this in plainer language."""
    name = _get(sub, "vendor.legal_name") or "there"
    if decision.status == "Approved":
        return (f"Dear {name},\n\nYour vendor registration is complete and approved. "
                f"You can now receive purchase orders from us.\n\nRegards,\nProcurement Team")
    if decision.status == "Rejected":
        return (f"Dear {name},\n\nThank you for your submission. We are unable to "
                f"complete your registration at this time. Our procurement team will "
                f"contact you directly.\n\nRegards,\nProcurement Team")
    if not decision.vendor_requests:
        return (f"Dear {name},\n\nThank you for your submission. It is under review by "
                f"our team and we will be in touch shortly.\n\nRegards,\nProcurement Team")
    items = "\n".join(f"  {i}. {r}" for i, r in enumerate(decision.vendor_requests, 1))
    return (f"Dear {name},\n\nThank you for registering with us. To complete your "
            f"onboarding, we need the following:\n\n{items}\n\nPlease resubmit using the "
            f"same link. Only these items will be re-checked.\n\nRegards,\nProcurement Team")


# ---------------------------------------------------------------- runner
def run_pipeline(sub: dict, vendor_master: list, gst_registry: dict, today=None):
    """Generator: yields ('stage', StageResult) as each stage finishes,
    then ('decision', Decision). The UI renders these live."""
    ctx = {"sub": sub, "vendor_master": vendor_master, "gst_registry": gst_registry,
           "today": today or dt.date.today(), "docs": {}, "format_ok": set(),
           "pack": None, "country": "IN"}
    results = []
    for key, name, fn in STAGES:
        t0 = time.perf_counter()
        try:
            checks = fn(ctx)
        except Exception as e:  # a crashed stage routes to a human, never silently passes
            checks = [Check(f"{key}_error", name, "review", f"Stage failed: {e}")]
        res = StageResult(key, name, checks, round((time.perf_counter() - t0) * 1000))
        results.append(res)
        yield "stage", res
    decision = decide(results, sub)
    decision.vendor_email = draft_vendor_email(sub, decision)
    yield "decision", decision


def run_all(sub, vendor_master, gst_registry, today=None):
    stages, decision = [], None
    for kind, obj in run_pipeline(sub, vendor_master, gst_registry, today):
        if kind == "stage":
            stages.append(obj)
        else:
            decision = obj
    return stages, decision


def diff_runs(old: list[StageResult], new: list[StageResult]) -> list[dict]:
    """What changed between a submission and its resubmission."""
    before = {c.id: c for s in old for c in s.checks}
    after = {c.id: c for s in new for c in s.checks}
    out = []
    for cid in dict.fromkeys(list(before) + list(after)):
        b, a = before.get(cid), after.get(cid)
        if (b and b.severity) != (a and a.severity):
            out.append({"check": (a or b).label,
                        "before": b.severity if b else "-",
                        "after": a.severity if a else "-",
                        "now": a.message if a else "removed"})
    return out


def to_dict(stages, decision):
    return {"stages": [{**asdict(s), "worst": s.worst} for s in stages],
            "decision": asdict(decision)}
