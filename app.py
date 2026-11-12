"""VendorGate: vendor onboarding, from submission to decision.
Run locally:  streamlit run app.py"""
import datetime as dt
import json
import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from types import SimpleNamespace

from vendorgate import intake, llm, store, ui
from vendorgate import validators as V
from vendorgate.pipeline import RULE_PACKS, STAGES, draft_vendor_email, run_all, run_pipeline, to_dict

ROOT = Path(__file__).parent
st.set_page_config(page_title="VendorGate", page_icon="🛡️", layout="wide")

ICON = {"pass": "✅", "info": "ℹ️", "skip": "⏭️", "fix": "🟡", "review": "🟠", "block": "❌"}
SEVERITY_TEXT = {"pass": "Passed", "info": "Note", "skip": "Not run", "fix": "Vendor can fix",
                 "review": "Needs a person", "block": "Blocking"}
STAMP = {("Approved", ""): ("#1E7F4F", "APPROVED"),
         ("Pending", "Vendor action"): ("#B7791F", "PENDING"),
         ("Pending", "Internal review"): ("#C2410C", "PENDING"),
         ("Rejected", ""): ("#B42318", "REJECTED")}
ENTITY_TYPES = {"IN": ["Private Limited Company", "Public Limited Company", "LLP",
                       "Partnership Firm", "Sole Proprietorship"],
                "US": ["Corporation", "LLC"]}
FIELDS = {"f_legal_name": "vendor.legal_name", "f_trade_name": "vendor.trade_name",
          "f_country": "vendor.country", "f_entity_type": "vendor.entity_type",
          "f_address": "vendor.address", "f_state": "vendor.state",
          "f_email": "vendor.contact_email", "f_pan": "tax.pan", "f_gstin": "tax.gstin",
          "f_ein": "tax.ein", "f_holder": "bank.account_holder",
          "f_account": "bank.account_number", "f_ifsc": "bank.ifsc", "f_swift": "bank.swift"}

st.markdown(ui.CSS, unsafe_allow_html=True)

# Festive edition: reachable at ?theme=diwali or via the sidebar toggle
if "festive" not in st.session_state:
    st.session_state.festive = st.query_params.get("theme") == "diwali"
if st.session_state.festive:
    st.markdown(ui.FESTIVE_CSS + ui.festive_decor(), unsafe_allow_html=True)


def on_festive_change():
    if st.session_state.festive:
        st.query_params["theme"] = "diwali"
    elif "theme" in st.query_params:
        del st.query_params["theme"]


# ---------------------------------------------------------------- setup
def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, default)


GEMINI_KEY = secret("GEMINI_API_KEY")
GEMINI_MODEL = secret("GEMINI_MODEL", llm.DEFAULT_MODEL)
llm.FALLBACK_MODEL = secret("GEMINI_FALLBACK_MODEL")


@st.cache_data
def load_data():
    read = lambda f: json.loads((ROOT / "data" / f).read_text())
    return read("vendor_master.json"), read("gst_registry.json"), read("scenarios.json")


MASTER, REGISTRY, SCENARIOS = load_data()
TODAY = dt.date.today()


def get_path(sub, dotted):
    obj = sub
    for p in dotted.split("."):
        obj = (obj or {}).get(p)
    return obj


def seed_history():
    """First launch: run every demo scenario so the dashboard is never empty."""
    ids = {}
    for key, sc in SCENARIOS.items():
        stages, decision = run_all(sc["submission"], MASTER, REGISTRY, TODAY)
        ids[key] = store.save(sc["submission"], to_dict(stages, decision),
                              ids.get(sc.get("resubmission_of")), key)


if store.count() == 0:
    seed_history()

ss = st.session_state
ss.setdefault("form_ver", 0)
ss.setdefault("template_docs", [])
ss.setdefault("parent_id", None)
ss.setdefault("source", "manual")
ss.setdefault("last_run_id", None)
ss.setdefault("template", "happy_path")
ss.setdefault("removed_docs", set())


def load_submission(sub, parent_id=None, source="manual"):
    for k, path in FIELDS.items():
        ss[k] = get_path(sub, path) or ""
    ss["f_country"] = ss["f_country"] or "IN"
    if ss["f_entity_type"] not in ENTITY_TYPES[ss["f_country"]]:
        ss["f_entity_type"] = ENTITY_TYPES[ss["f_country"]][0]
    ss.template_docs = sub.get("documents", [])
    ss.parent_id, ss.source = parent_id, source
    ss.form_ver += 1
    ss.removed_docs = set()
    ss.autofill_note = None
    ss.last_run_id = None


@st.cache_data(ttl=3600, show_spinner=False)
def ifsc_cached(code):
    return V.ifsc_lookup(code)


def on_gstin_change():
    """Smart intake: a valid GSTIN fills PAN, state and (from the registry) legal name."""
    info = intake.gstin_lookup(ss.get("f_gstin"), REGISTRY)
    filled = []
    for key, field, label in [("f_legal_name", "legal_name", "legal name"), ("f_pan", "pan", "PAN"),
                              ("f_state", "state", "state")]:
        if info.get(field) and not (ss.get(key) or "").strip():
            ss[key] = info[field]
            filled.append(label)
    src = "GSTIN and GST registry" if "legal name" in filled else "GSTIN"
    ss.autofill_note = f"Filled from {src}: {', '.join(filled)}" if filled else None


def reset_time_ist():
    """Free-tier daily quota resets at midnight Pacific time; show it in IST."""
    from zoneinfo import ZoneInfo
    pt = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    nxt = (pt + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%-I:%M %p IST")


def ai_status_html():
    if not GEMINI_KEY:
        kind, title, body = "warn", "AI reading not configured", "Prepared scenarios still run every check."
    else:
        state, at = llm.STATUS["state"], llm.STATUS["at"]
        ago = f" · {int((time.time() - at) // 60)} min ago" if at else ""
        if state == "quota" and not llm.quota_active():
            state = "unused"
        if state == "quota":
            kind, title = "bad", "AI reading paused"
            body = (f"Today’s free Gemini quota is used up{ago}. It resets around {reset_time_ist()}. "
                    "Prepared scenarios and every other check still work.")
        elif state == "busy":
            kind, title = "warn", "AI reading busy"
            body = f"Gemini was overloaded on the last try{ago}. Uploads retry automatically."
        elif state == "ok":
            kind, title, body = "ok", "AI reading available", f"Last document read{ago}."
        else:
            kind, title, body = "ok", "AI reading ready", "Free tier: a limited number of reads per day."
    return (f"<div class='vg-ai {kind}'><b><i></i>{title}</b><span>{body}</span>"
            f"<span class='m'>{GEMINI_MODEL}</span></div>")


def show_hint(h):
    kind, msg = h
    if kind:
        st.markdown(ui.hint(kind, msg), unsafe_allow_html=True)


def on_country_change():
    ss["f_entity_type"] = ENTITY_TYPES[ss["f_country"]][0]


def on_template_change():
    key = ss.template
    load_submission(SCENARIOS[key]["submission"] if key != "blank" else {}, None,
                    key if key != "blank" else "manual")


if "f_legal_name" not in ss:
    on_template_change()


# ---------------------------------------------------------------- rendering helpers
SHORT = {"intake": "Intake", "completeness": "Complete", "documents": "Docs", "format": "Format",
         "crossref": "Cross-ref", "external": "Verify", "risk": "Risk"}


def checks_block(stages, new_key=None):
    out = []
    for s in stages:
        out.append(f"<div class='vg-stage'>{SHORT.get(s['key'], s['name'])}</div>")
        out += [ui.check_html(c, new=(s["key"] == new_key)) for c in s["checks"]]
    return "".join(out)


def static_card(run, animate=False):
    stages, d = run["result"]["stages"], run["result"]["decision"]
    names = [SHORT.get(s["key"], s["name"]) for s in stages]
    rail = ui.rail(names, [ui.node_state(s["worst"]) for s in stages])
    animate = animate or ss.pop("celebrate", None) == run["id"]
    dec = ui.stamp(d, animate, ss.festive) + ui.counts(stages)
    if run["result"].get("review"):
        dec += ui.reviewed_note(run["result"]["review"], run["result"]["auto_decision"])
    st.markdown(ui.card(run["id"], rail, checks_block(stages), dec, live=False), unsafe_allow_html=True)


REVIEW_LABELS = {"approve": "Approve", "request": "Ask vendor for more", "reject": "Reject"}


def reviewer_panel(run):
    st.markdown("<div class='vg-review'><h4>Your decision is needed</h4><p>The checks found "
                "contradictions that a rule can’t settle. Review the evidence above, then decide. "
                "Your name and reason are saved to the audit trail.</p></div>", unsafe_allow_html=True)
    with st.form(key=f"review_{run['id']}"):
        c1, c2 = st.columns([1, 2])
        by = c1.text_input("Reviewer name", placeholder="Priya (Procurement)")
        choice = c2.radio("Decision", list(REVIEW_LABELS), horizontal=True,
                          format_func=REVIEW_LABELS.get)
        reason = st.text_area("Reason", height=90,
                              placeholder="Called the vendor: they have a second GSTIN for Karnataka "
                                          "and will share it.",
                              help="If you ask the vendor for more, this text goes into their email")
        submitted = st.form_submit_button("Record decision", type="primary")
    if submitted:
        if not by.strip():
            st.error("Enter your name so the decision can be traced")
            return
        if len(reason.strip()) < 15:
            st.error("Write a reason of at least 15 characters so the decision can be audited")
            return
        status = {"approve": "Approved", "request": "Pending", "reject": "Rejected"}[choice]
        email = draft_vendor_email(run["submission"], SimpleNamespace(
            status=status, vendor_requests=[reason.strip()] if choice == "request" else []))
        store.apply_review(run["id"], {"by": by.strip(), "decision": choice, "reason": reason.strip(),
                                       "at": dt.datetime.now().isoformat(timespec="seconds")}, email)
        if choice == "approve":
            ss.celebrate = run["id"]
        st.rerun()


def render_decision(run):
    d = run["result"]["decision"]
    if d["route"] == "Internal review" and not run["result"].get("review"):
        reviewer_panel(run)
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown(ui.section("Why"), unsafe_allow_html=True)
        for r in d["reasons"]:
            st.markdown(f"- {r}")
        if run.get("parent_id"):
            parent = store.get(run["parent_id"])
            if parent:
                st.markdown(ui.section(f"What changed since {run['parent_id']}"), unsafe_allow_html=True)
                for ch in diff(parent["result"]["stages"], run["result"]["stages"]):
                    st.markdown(f"- {ch['check']}: {ICON.get(ch['before'], '–')} → "
                                f"{ICON.get(ch['after'], '–')}")
    with right:
        tag = " · AI-polished, review before sending" if d.get("email_polished") else ""
        st.markdown(ui.section("Email to vendor" + tag), unsafe_allow_html=True)
        st.text_area("Email to vendor", d.get("vendor_email") or "", height=250,
                     key=f"email_{run['id']}_{d['status']}_{d['route']}", label_visibility="collapsed")

    if d["status"] == "Pending":
        b1, b2, _ = st.columns([1.3, 1.8, 1.8])
        b1.button("Edit and resubmit", key=f"resub_{run['id']}", on_click=load_submission,
                  args=(run["submission"], run["id"], run["source"]),
                  help="Load this submission into the form as the vendor's next attempt")
        follow_up = next((k for k, s in SCENARIOS.items()
                          if s.get("resubmission_of") == run["source"]), None)
        if follow_up:
            b2.button("Load vendor's corrected resubmission", key=f"demo_{run['id']}",
                      on_click=load_submission,
                      args=(SCENARIOS[follow_up]["submission"], run["id"], follow_up))


def diff(old_stages, new_stages):
    before = {c["id"]: c for s in old_stages for c in s["checks"]}
    after = {c["id"]: c for s in new_stages for c in s["checks"]}
    out = []
    for cid in dict.fromkeys(list(before) + list(after)):
        b, a = before.get(cid), after.get(cid)
        if (b or {}).get("severity") != (a or {}).get("severity"):
            out.append({"check": (a or b)["label"], "before": (b or {}).get("severity"),
                        "after": (a or {}).get("severity")})
    return out


def render_stages_static(stages):
    for s in stages:
        icon = "✅" if s["worst"] in ("info", "pass", "skip") else ICON[s["worst"]]
        with st.expander(f"{icon} {s['name']}  ({s['duration_ms']} ms)"):
            st.markdown("".join(ui.check_html(c) for c in s["checks"]), unsafe_allow_html=True)


# ---------------------------------------------------------------- live run
def live_run(sub, uploads, pacing):
    run_id = f"RUN-{store.count() + 1:04d}"
    names = (["AI read"] if uploads else []) + [SHORT[k] for k, _, _ in STAGES]
    states = [None] * len(names)
    offset = 1 if uploads else 0
    stages, ai_lines = [], []
    box = st.empty()

    def draw(active=None, new_key=None, decision_html=None, live=True):
        ai = ""
        if ai_lines:
            ai = "<div class='vg-stage'>AI read</div>" + "".join(ai_lines)
        body = ai + checks_block(stages, new_key)
        box.markdown(ui.card(run_id, ui.rail(names, states, active), body or
                             "<div class='vg-wait'>Starting…</div>",
                             decision_html or "<div class='vg-wait'>Running checks…</div>", live),
                     unsafe_allow_html=True)

    draw(active=0)
    if uploads:
        worst = "pass"
        for slot, up in uploads:
            label = RULE_PACKS[sub["vendor"]["country"]]["documents"][slot]
            ai_lines.append(ui.check_html({"id": "ai", "severity": "info", "label": f"Reading {up.name}",
                                           "message": f"as {label}…"}, new=True))
            draw(active=0)
            if not GEMINI_KEY:
                doc = {"slot": slot, "file": up.name, "error": "AI reading is not configured"}
            else:
                doc = llm.extract_document(up.getvalue(), up.name, slot, GEMINI_KEY, GEMINI_MODEL)
            sub["documents"] = [d for d in sub["documents"] if d["slot"] != slot] + [doc]
            if doc.get("error"):
                worst = "warn"
                line = {"id": "ai", "severity": "review", "label": up.name,
                        "message": f"could not be read: {doc['error']}"}
            else:
                kind = doc["detected_type"].replace("_", " ") if doc.get("detected_type") else "unknown"
                line = {"id": "ai", "severity": "pass", "label": up.name,
                        "message": f"looks like a {kind} ({doc['confidence']:.0%} confidence), "
                                   f"{len(doc['fields'])} fields read"}
            ai_lines[-1] = ui.check_html(line, new=True)
            draw(active=0)
        states[0] = worst

    decision = None
    gen = run_pipeline(sub, MASTER, REGISTRY, TODAY)
    i = 0
    while True:
        draw(active=offset + i if offset + i < len(names) else None)
        time.sleep(pacing)
        kind, obj = next(gen)
        if kind == "decision":
            decision = asdict(obj)
            break
        sd = {**asdict(obj), "worst": obj.worst}
        stages.append(sd)
        states[offset + i] = ui.node_state(obj.worst)
        draw(active=None, new_key=sd["key"])
        i += 1

    decision["email_polished"] = False
    draw(decision_html="<div class='vg-wait'>Deciding and drafting the vendor email…</div>")
    if GEMINI_KEY and decision["status"] == "Pending" and decision["vendor_requests"]:
        decision["vendor_email"], decision["email_polished"] = llm.polish_email(
            decision["vendor_email"], GEMINI_KEY, GEMINI_MODEL)

    result = {"stages": stages, "decision": decision}
    saved_id = store.save(sub, result, ss.parent_id, ss.source)
    ss.last_run_id = saved_id
    draw(decision_html=ui.stamp(decision, animate=True, festive=ss.festive) + ui.counts(stages), live=False)
    render_decision(store.get(saved_id))


# ---------------------------------------------------------------- pages
def page_new_run():
    st.markdown(ui.hero("शुभ दीपावली · festive edition" if ss.festive else "Vendor onboarding",
                        "Vendors, verified <em>before</em> you pay.",
                        "Pick a prepared scenario or start blank. Every field can be edited, and "
                        "uploaded documents are read live by AI."), unsafe_allow_html=True)

    c1, c2 = st.columns([2, 1])
    options = ["blank"] + list(SCENARIOS)
    c1.selectbox("Start from", options, key="template", on_change=on_template_change,
                 format_func=lambda k: "Blank form" if k == "blank" else SCENARIOS[k]["title"])
    if ss.parent_id:
        c2.info(f"Resubmission of {ss.parent_id}")

    country = ss.get("f_country", "IN")
    col_a, col_b, col_c = st.columns(3, gap="large")
    with col_a:
        st.markdown(ui.section("Company"), unsafe_allow_html=True)
        st.text_input("Legal name", key="f_legal_name")
        st.text_input("Trade name (optional)", key="f_trade_name")
        st.selectbox("Country", ["IN", "US"], key="f_country", on_change=on_country_change,
                     format_func=lambda c: {"IN": "India", "US": "United States"}[c])
        st.selectbox("Entity type", ENTITY_TYPES[country], key="f_entity_type")
        st.text_input("Registered address", key="f_address")
        st.text_input("State", key="f_state")
        st.text_input("Contact email", key="f_email")
        show_hint(intake.hint_email(ss.get("f_email"), ss.get("f_entity_type")))
    with col_b:
        st.markdown(ui.section("Tax registration"), unsafe_allow_html=True)
        if country == "IN":
            st.text_input("GSTIN", key="f_gstin", on_change=on_gstin_change,
                          help="Enter this first: PAN, state and legal name fill in automatically")
            show_hint(intake.hint_gstin(ss.get("f_gstin"), ss.get("f_pan"), ss.get("f_state"), REGISTRY))
            if ss.get("autofill_note"):
                st.markdown(f"<div class='vg-fill-note'>✦ {ss.autofill_note}</div>", unsafe_allow_html=True)
            st.text_input("PAN", key="f_pan", help="10 characters, e.g. AAACN4821K")
            show_hint(intake.hint_pan(ss.get("f_pan"), ss.get("f_entity_type")))
        else:
            st.text_input("EIN", key="f_ein", help="Format 12-3456789")
            show_hint(intake.hint_ein(ss.get("f_ein")))
    with col_c:
        st.markdown(ui.section("Bank account"), unsafe_allow_html=True)
        st.text_input("Account holder name", key="f_holder")
        show_hint(intake.hint_holder(ss.get("f_holder"), ss.get("f_legal_name")))
        st.text_input("Account number", key="f_account")
        show_hint(intake.hint_account(ss.get("f_account")))
        if country == "IN":
            st.text_input("IFSC", key="f_ifsc")
            show_hint(intake.hint_ifsc(ss.get("f_ifsc"), ifsc_cached))
        else:
            st.text_input("SWIFT / BIC", key="f_swift")
            show_hint(intake.hint_swift(ss.get("f_swift"), country))

    st.markdown(ui.section("Documents"), unsafe_allow_html=True)
    pack_docs = RULE_PACKS[country]["documents"]
    template_docs = {d["slot"]: d for d in ss.template_docs
                     if d["slot"] in pack_docs and d["slot"] not in ss.removed_docs}
    if template_docs:
        st.caption("This scenario comes with sample documents that were read in advance, so the "
                   "demo is quick and repeatable. Upload your own file to have AI read it live, "
                   "or remove a sample to see what happens when a document is missing.")
    if llm.quota_active():
        st.markdown(ui.hint("warn", f"AI reading is paused until about {reset_time_ist()} (free daily "
                                    "quota used up). Uploaded files can’t be read right now; the "
                                    "attached samples work as normal."), unsafe_allow_html=True)
    uploads = []
    doc_cols = st.columns(len(pack_docs), gap="large")
    for col, (slot, label) in zip(doc_cols, pack_docs.items()):
        with col:
            up = st.file_uploader(label, type=["pdf", "png", "jpg", "jpeg"],
                                  key=f"up_{slot}_{ss.form_ver}")
            if up:
                uploads.append((slot, up))
                st.caption("Will be read by AI during the run")
            elif slot in template_docs:
                st.caption(f"📎 Sample attached: {template_docs[slot]['file']}")
                st.button("Remove sample", key=f"rm_{slot}_{ss.form_ver}",
                          on_click=lambda s=slot: ss.removed_docs.add(s))
            else:
                st.caption("⚠️ Nothing attached")
                if any(d["slot"] == slot for d in ss.template_docs):
                    st.button("Restore sample", key=f"rs_{slot}_{ss.form_ver}",
                              on_click=lambda s=slot: ss.removed_docs.discard(s))

    st.write("")
    run_clicked = st.button("Run onboarding checks", type="primary")

    if run_clicked:
        sub = {"submission_id": f"SUB-{uuid.uuid4().hex[:6].upper()}",
               "submitted_at": TODAY.isoformat(), "vendor": {}, "tax": {}, "bank": {},
               "documents": list(template_docs.values())}
        keep = {"IN": {"f_pan", "f_gstin", "f_ifsc"}, "US": {"f_ein", "f_swift"}}
        drop = keep["US" if country == "IN" else "IN"]
        for k, path in FIELDS.items():
            val = (ss.get(k) or "").strip()
            if val and k not in drop:
                group, field = path.split(".")
                sub[group][field] = val
        live_run(sub, uploads, ss.get("pacing", 0.4))
    elif ss.last_run_id:
        run = store.get(ss.last_run_id)
        static_card(run)
        render_decision(run)


def page_dashboard():
    st.markdown(ui.hero("Audit trail", "Every decision, <em>with</em> its evidence.",
                        "Each run is stored with what was checked, what was found and why it "
                        "ended where it did."), unsafe_allow_html=True)
    runs = store.all_runs()
    statuses = [r["status"] for r in runs]
    m = st.columns(5)
    m[0].metric("Runs", len(runs))
    m[1].metric("Approved", statuses.count("Approved"))
    m[2].metric("Waiting on vendor", sum(r["route"] == "Vendor action" for r in runs))
    m[3].metric("Waiting on our team", sum(r["route"] == "Internal review" for r in runs))
    m[4].metric("Rejected", statuses.count("Rejected"))

    flt = st.segmented_control("Show", ["All", "Needs review", "Approved", "Pending", "Rejected"],
                               default="All")
    shown = [r for r in runs if flt in (None, "All") or r["status"] == flt
             or (flt == "Needs review" and r["route"] == "Internal review")]

    def flags(r, sev):
        return sum(c["severity"] == sev for s in r["result"]["stages"] for c in s["checks"])

    table = [{"Run": r["id"], "When": r["created"].replace("T", " "), "Vendor": r["vendor"],
              "Country": r["country"], "Status": r["status"], "Next step": r["route"],
              "Blocking": flags(r, "block"), "For review": flags(r, "review"),
              "Vendor fixes": flags(r, "fix"), "Resubmission of": r["parent_id"] or "",
              "Reviewed by": (r["result"].get("review") or {}).get("by", "")}
             for r in shown]
    if not table:
        st.info("No runs match this filter. Start one from New submission.")
        return
    st.dataframe(table, hide_index=True, width="stretch")

    pick = st.selectbox("Open a run", [r["id"] for r in shown],
                        format_func=lambda i: f"{i}: " + next(r["vendor"] for r in shown if r["id"] == i))
    run = store.get(pick)
    static_card(run)
    render_decision(run)
    st.markdown(ui.section("Stage details"), unsafe_allow_html=True)
    render_stages_static(run["result"]["stages"])
    with st.expander("Raw submission"):
        st.json(run["submission"], expanded=False)


def page_how():
    st.markdown(ui.hero("How it decides", "AI reads, rules <em>decide</em>.",
                        "People own the grey zone."), unsafe_allow_html=True)
    st.markdown("""
The AI model only reads documents and drafts emails. Every status comes from written rules,
so every decision can be traced back to evidence.

**Built to make onboarding simpler**

- **Smart intake:** type a GSTIN and the PAN, state and legal name fill in automatically. Every field checks itself as you type (GSTIN check digit, live IFSC bank lookup, name match), so mistakes are caught before submitting, not after a review cycle.
- **Reviewer decisions:** cases the rules can’t settle go to a person, who approves, asks the vendor for more, or rejects with a written reason. The automated result and the human decision are both kept in the audit trail.

**The pipeline**

1. **Intake**: picks the rule set for the vendor's country (India or US).
2. **Completeness**: required fields and documents for that country.
3. **Document understanding**: AI identifies each upload and reads its fields. A PAN card uploaded as a cheque is caught here.
4. **Format validation**: PAN, GSTIN (including its check digit), IFSC, EIN, SWIFT.
5. **Cross-reference**: PAN inside GSTIN, GSTIN state vs address, PAN holder type vs entity type, form vs every document, legal name vs bank account holder.
6. **External verification**: live IFSC lookup; GST registry status and age.
7. **Risk and duplicates**: bank account or tax ID already belonging to another vendor.

**How each check affects the outcome**

| Result | Meaning | Outcome |
|---|---|---|
| ✅ Passed | Check succeeded | — |
| 🟡 Vendor can fix | Missing or mistyped information | Pending: vendor gets an exact list |
| 🟠 Needs a person | Information contradicts itself | Pending: internal review |
| ❌ Blocking | Fraud signal or ineligible | Rejected: vendor is not told which check failed |

A vendor is rejected only for fraud signals or ineligibility. Rejecting a genuine vendor over a typo
costs the business, so anything fixable stays pending.

**Assumptions**

- Indian vendors are GST-registered; non-registered vendors are out of scope.
- The GST registry and bank penny-drop are simulated. The IFSC lookup is live (Razorpay's public API).
- The vendor master is the company's existing list of approved vendors.
- Name matching ignores case and common abbreviations (Pvt, Ltd, Ent). 88+ is a match, 70–87 goes to a person, below 70 is flagged.
- All PANs, GSTINs and account numbers are fictional. GSTINs use the real check-digit algorithm.
""")


# ---------------------------------------------------------------- navigation
with st.sidebar:
    st.markdown("### 🛡️ VendorGate")
    st.caption("Vendor onboarding, from submission to decision")
    page = st.radio("Go to", ["New submission", "Dashboard", "How it decides"],
                    label_visibility="collapsed")
    st.divider()
    st.toggle("Festive edition 🪔", key="festive", on_change=on_festive_change,
              help="Diwali theme: same checks and rules, dressed for the season")
    st.toggle("Demo pacing", value=True, key="pacing_on",
              help="Adds a short pause per stage so viewers can follow the run")
    ss["pacing"] = 0.4 if ss.get("pacing_on", True) else 0.0
    st.markdown(ai_status_html(), unsafe_allow_html=True)

{"New submission": page_new_run, "Dashboard": page_dashboard, "How it decides": page_how}[page]()
