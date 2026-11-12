"""Smart intake: catch mistakes while the vendor is still typing.

Each hint returns (kind, message) where kind is "ok", "warn", "bad" or None (nothing to say).
These hints are guidance only; the pipeline still runs every check on submit.
"""
from . import validators as V
from .matching import name_score

FREE_EMAIL = {"gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com", "rediffmail.com"}


def gstin_lookup(gstin: str, registry: dict) -> dict:
    """What we can learn from a GSTIN alone: PAN, state, and (from the registry) legal name."""
    g = (gstin or "").strip().upper()
    if not (V.GSTIN_RE.match(g) and V.gstin_checksum_ok(g)):
        return {}
    out = {"pan": g[2:12], "state": V.GST_STATE_CODES.get(g[:2])}
    rec = registry.get(g)
    if rec:
        out["legal_name"] = rec["legal_name"].title()
        out["status"] = rec["status"]
    return out


def hint_pan(pan, entity_type):
    p = (pan or "").strip().upper()
    if not p:
        return None, ""
    if not V.PAN_RE.match(p):
        return "bad", "Should look like AAAAA9999A (5 letters, 4 digits, 1 letter)"
    want = V.ENTITY_TO_PAN_CHAR.get(entity_type)
    holder = V.PAN_HOLDER_TYPE.get(p[3], "unknown type")
    if want and want != p[3]:
        return "warn", f"4th letter '{p[3]}' means {holder}, but entity type is {entity_type}"
    return "ok", f"Valid PAN · holder type: {holder}"


def hint_gstin(gstin, pan, state, registry):
    g = (gstin or "").strip().upper()
    if not g:
        return None, ""
    if not V.GSTIN_RE.match(g):
        return "bad", "Should be 15 characters, like 27AAACN4821K1ZF"
    if not V.gstin_checksum_ok(g):
        return "bad", f"Check digit fails, likely a typo (last character should be {V.gstin_check_char(g[:14])})"
    rec = registry.get(g)
    if rec and rec["status"] != "Active":
        return "bad", f"Registration is {rec['status']}"
    notes = []
    p = (pan or "").strip().upper()
    if p and V.PAN_RE.match(p) and g[2:12] != p:
        notes.append(f"contains PAN {g[2:12]}, not {p}")
    reg_state = V.GST_STATE_CODES.get(g[:2])
    if state and reg_state and state.strip().lower() != reg_state.lower():
        notes.append(f"registered in {reg_state}, address says {state.strip()}")
    if notes:
        return "warn", "Valid GSTIN, but " + "; ".join(notes)
    where = f"registered in {reg_state}" if reg_state else "valid"
    return "ok", f"Valid GSTIN · {where}" + (" · active" if rec else "")


def hint_ifsc(ifsc, lookup_fn):
    i = (ifsc or "").strip().upper()
    if not i:
        return None, ""
    if not V.IFSC_RE.match(i):
        return "bad", "Should look like HDFC0001234 (4 letters, 0, 6 characters)"
    info = lookup_fn(i)
    if not info.get("found"):
        return "bad", "This IFSC does not exist"
    where = f" · {info['branch'].title()}, {info['city'].title()}" if info.get("branch") else ""
    return "ok", f"{info['bank']}{where}"


def hint_account(acct):
    a = (acct or "").strip()
    if not a:
        return None, ""
    if not V.ACCOUNT_RE.match(a):
        return "bad", "Should be 9 to 18 digits, no spaces"
    return "ok", f"{len(a)} digits"


def hint_email(email, entity_type):
    e = (email or "").strip()
    if not e:
        return None, ""
    if not V.EMAIL_RE.match(e):
        return "bad", "Not a valid email address"
    if e.split("@")[-1].lower() in FREE_EMAIL and entity_type and "Limited" in entity_type:
        return "warn", "Free email provider; a company domain is more trustworthy"
    return "ok", "Looks good"


def hint_holder(holder, legal_name):
    h, l = (holder or "").strip(), (legal_name or "").strip()
    if not h or not l:
        return None, ""
    s = name_score(l, h)
    if s >= 88:
        return "ok", "Matches the legal name" + ("" if h.lower() == l.lower() else " (abbreviations allowed)")
    if s >= 70:
        return "warn", f"Only partly matches the legal name ({s}% similar)"
    return "warn", f"Does not match the legal name ({s}% similar); third-party accounts need a bank letter"


def hint_ein(ein):
    e = (ein or "").strip()
    if not e:
        return None, ""
    if V.PAN_RE.match(e.upper()):
        return "bad", "This is an Indian PAN; US vendors need an EIN (12-3456789)"
    return ("ok", "Valid EIN format") if V.EIN_RE.match(e) else ("bad", "Should look like 12-3456789")


def hint_swift(swift, country):
    s = (swift or "").strip().upper()
    if not s:
        return None, ""
    if not V.SWIFT_RE.match(s):
        return "bad", "Should be 8 or 11 characters, like CHASUS33"
    if s[4:6] != country:
        return "warn", f"Bank is in {s[4:6]}, vendor is in {country}"
    return "ok", f"Valid SWIFT · bank country {s[4:6]}"
