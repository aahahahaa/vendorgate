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

from vendorgate import llm, store
from vendorgate.pipeline import RULE_PACKS, STAGES, run_all, run_pipeline, to_dict

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

st.markdown("""<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.stamp {display:inline-block; padding:.35rem 1.1rem; border:3px solid; border-radius:6px;
        font-weight:800; font-size:1.7rem; letter-spacing:.12em; transform:rotate(-3deg);
        margin:.4rem 0 .6rem 0;}
.route {font-size:1.05rem; margin-bottom:.4rem;}
.chk {margin:.15rem 0;}
.ev {color:#5B6676; font-size:.85rem; margin:0 0 .35rem 1.7rem;}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------- setup
def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, default)


GEMINI_KEY = secret("GEMINI_API_KEY")
GEMINI_MODEL = secret("GEMINI_MODEL", llm.DEFAULT_MODEL)


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
    ss.last_run_id = None


def on_country_change():
    ss["f_entity_type"] = ENTITY_TYPES[ss["f_country"]][0]


def on_template_change():
    key = ss.template
    load_submission(SCENARIOS[key]["submission"] if key != "blank" else {}, None,
                    key if key != "blank" else "manual")


if "f_legal_name" not in ss:
    on_template_change()


# ---------------------------------------------------------------- rendering helpers
def render_checks(checks):
    for c in checks:
        st.markdown(f"<div class='chk'>{ICON[c['severity']]} <b>{c['label']}</b>: "
                    f"{c['message']}</div>", unsafe_allow_html=True)
        ev = {k: v for k, v in (c.get("evidence") or {}).items()
              if isinstance(v, (str, int, float)) and k not in ("source",)}
        if ev and c["severity"] in ("fix", "review", "block"):
            st.markdown("<div class='ev'>" + " &nbsp;|&nbsp; ".join(
                f"{k.replace('_', ' ')}: <code>{v}</code>" for k, v in ev.items()) + "</div>",
                unsafe_allow_html=True)


def render_decision(run):
    d = run["result"]["decision"]
    sub_route = d["route"] if d["status"] == "Pending" else ""
    color, word = STAMP[(d["status"], sub_route)]
    st.markdown(f"<div class='stamp' style='color:{color};border-color:{color}'>{word}</div>"
                f"<div class='route'>Next: <b>{d['route']}</b></div>", unsafe_allow_html=True)
    st.caption(d["internal_summary"])

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("**Why**")
        for r in d["reasons"]:
            st.markdown(f"- {r}")
        if run.get("parent_id"):
            parent = store.get(run["parent_id"])
            if parent:
                st.markdown(f"**What changed since {run['parent_id']}**")
                for ch in diff(parent["result"]["stages"], run["result"]["stages"]):
                    st.markdown(f"- {ch['check']}: {ICON.get(ch['before'], '–')} → "
                                f"{ICON.get(ch['after'], '–')}")
    with right:
        tag = " (AI-polished, please review)" if d.get("email_polished") else ""
        st.markdown(f"**Email to vendor**{tag}")
        st.text_area("Email to vendor", d.get("vendor_email") or "", height=260,
                     key=f"email_{run['id']}", label_visibility="collapsed")

    if d["status"] == "Pending":
        b1, b2, _ = st.columns([1.3, 1.6, 2])
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


def stage_icon(worst):
    return "✅" if worst in ("info", "pass") else ICON[worst]


def render_stages_static(stages):
    for s in stages:
        with st.expander(f"{stage_icon(s['worst'])} {s['name']}  ({s['duration_ms']} ms)",
                         expanded=s["worst"] in ("fix", "review", "block")):
            render_checks(s["checks"])


# ---------------------------------------------------------------- live run
def live_run(sub, uploads, pacing):
    st.subheader("Live run")
    n_total = len(STAGES) + 2 + (1 if uploads else 0)
    bar = st.progress(0.0, text="Starting")
    step = 0

    if uploads:
        with st.status("Reading uploaded documents with AI", expanded=True) as box:
            for slot, up in uploads:
                st.write(f"Reading **{up.name}** as {RULE_PACKS[sub['vendor']['country']]['documents'][slot]}")
                if not GEMINI_KEY:
                    doc = {"slot": slot, "file": up.name,
                           "error": "AI reading is not configured (no GEMINI_API_KEY)"}
                else:
                    doc = llm.extract_document(up.getvalue(), up.name, slot, GEMINI_KEY, GEMINI_MODEL)
                sub["documents"] = [d for d in sub["documents"] if d["slot"] != slot] + [doc]
                if doc.get("error"):
                    st.write(f"🟠 Could not read: {doc['error']}")
                else:
                    st.write(f"Looks like a **{doc['detected_type']}** "
                             f"({doc['confidence']:.0%} confidence): {doc.get('notes', '')}")
                    st.json(doc["fields"], expanded=False)
            box.update(label="Read uploaded documents with AI", state="complete", expanded=False)
        step += 1
        bar.progress(step / n_total, text="Documents read")

    stages = []
    decision = None
    for kind, obj in run_pipeline(sub, MASTER, REGISTRY, TODAY):
        if kind == "stage":
            sd = {**asdict(obj), "worst": obj.worst}
            stages.append(sd)
            with st.status(f"{obj.name}", expanded=True) as box:
                time.sleep(pacing)
                render_checks(sd["checks"])
                box.update(label=f"{stage_icon(obj.worst)} {obj.name}  ({obj.duration_ms} ms)",
                           state="error" if obj.worst == "block" else "complete",
                           expanded=obj.worst in ("fix", "review", "block"))
            step += 1
            bar.progress(step / n_total, text=obj.name)
        else:
            decision = asdict(obj)

    with st.status("Decision engine", expanded=False) as box:
        time.sleep(pacing)
        st.write(f"{decision['status']} → {decision['route']}")
        box.update(label=f"Decision: {decision['status']} ({decision['route']})", state="complete")
    step += 1
    bar.progress(step / n_total, text="Decision made")

    decision["email_polished"] = False
    with st.status("Drafting vendor email", expanded=False) as box:
        if GEMINI_KEY and decision["status"] == "Pending" and decision["vendor_requests"]:
            decision["vendor_email"], decision["email_polished"] = llm.polish_email(
                decision["vendor_email"], GEMINI_KEY, GEMINI_MODEL)
        box.update(label="Vendor email drafted" + (" with AI" if decision["email_polished"] else
                                                    " from template"), state="complete")
    bar.progress(1.0, text="Done")

    result = {"stages": stages, "decision": decision}
    run_id = store.save(sub, result, ss.parent_id, ss.source)
    ss.last_run_id = run_id
    st.divider()
    render_decision(store.get(run_id))


# ---------------------------------------------------------------- pages
def page_new_run():
    st.title("New vendor submission")
    st.write("Pick a prepared scenario or start blank. Every field can be edited before running.")

    c1, c2 = st.columns([2, 1])
    options = ["blank"] + list(SCENARIOS)
    c1.selectbox("Start from", options, key="template", on_change=on_template_change,
                 format_func=lambda k: "Blank form" if k == "blank" else SCENARIOS[k]["title"])
    if ss.parent_id:
        c2.info(f"Resubmission of {ss.parent_id}")

    country = ss.get("f_country", "IN")
    col_a, col_b, col_c = st.columns(3, gap="large")
    with col_a:
        st.markdown("**Company**")
        st.text_input("Legal name", key="f_legal_name")
        st.text_input("Trade name (optional)", key="f_trade_name")
        st.selectbox("Country", ["IN", "US"], key="f_country", on_change=on_country_change,
                     format_func=lambda c: {"IN": "India", "US": "United States"}[c])
        st.selectbox("Entity type", ENTITY_TYPES[country], key="f_entity_type")
        st.text_input("Registered address", key="f_address")
        st.text_input("State", key="f_state")
        st.text_input("Contact email", key="f_email")
    with col_b:
        st.markdown("**Tax registration**")
        if country == "IN":
            st.text_input("PAN", key="f_pan", help="10 characters, e.g. AAACN4821K")
            st.text_input("GSTIN", key="f_gstin", help="15 characters, e.g. 27AAACN4821K1ZF")
        else:
            st.text_input("EIN", key="f_ein", help="Format 12-3456789")
    with col_c:
        st.markdown("**Bank account**")
        st.text_input("Account holder name", key="f_holder")
        st.text_input("Account number", key="f_account")
        if country == "IN":
            st.text_input("IFSC", key="f_ifsc")
        else:
            st.text_input("SWIFT / BIC", key="f_swift")

    st.markdown("**Documents**")
    pack_docs = RULE_PACKS[country]["documents"]
    template_docs = {d["slot"]: d for d in ss.template_docs
                     if d["slot"] in pack_docs and d["slot"] not in ss.removed_docs}
    if template_docs:
        st.caption("This scenario comes with sample documents that were read in advance, so the "
                   "demo is quick and repeatable. Upload your own file to have AI read it live, "
                   "or remove a sample to see what happens when a document is missing.")
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
        st.subheader(f"Result of {run['id']}")
        render_stages_static(run["result"]["stages"])
        st.divider()
        render_decision(run)


def page_dashboard():
    st.title("Dashboard")
    runs = store.all_runs()
    statuses = [r["status"] for r in runs]
    m = st.columns(5)
    m[0].metric("Runs", len(runs))
    m[1].metric("Approved", statuses.count("Approved"))
    m[2].metric("Waiting on vendor", sum(r["route"] == "Vendor action" for r in runs))
    m[3].metric("Waiting on our team", sum(r["route"] == "Internal review" for r in runs))
    m[4].metric("Rejected", statuses.count("Rejected"))

    flt = st.segmented_control("Show", ["All", "Approved", "Pending", "Rejected"], default="All")
    shown = [r for r in runs if flt in (None, "All") or r["status"] == flt]

    def flags(r, sev):
        return sum(c["severity"] == sev for s in r["result"]["stages"] for c in s["checks"])

    table = [{"Run": r["id"], "When": r["created"].replace("T", " "), "Vendor": r["vendor"],
              "Country": r["country"], "Status": r["status"], "Next step": r["route"],
              "Blocking": flags(r, "block"), "For review": flags(r, "review"),
              "Vendor fixes": flags(r, "fix"), "Resubmission of": r["parent_id"] or ""}
             for r in shown]
    if not table:
        st.info("No runs match this filter. Start one from New submission.")
        return
    st.dataframe(table, hide_index=True, width="stretch")

    pick = st.selectbox("Open a run", [r["id"] for r in shown],
                        format_func=lambda i: f"{i}: " + next(r["vendor"] for r in shown if r["id"] == i))
    run = store.get(pick)
    st.subheader(f"{run['id']}: {run['vendor']}")
    render_decision(run)
    st.markdown("**Audit trail**")
    render_stages_static(run["result"]["stages"])
    with st.expander("Raw submission"):
        st.json(run["submission"], expanded=False)


def page_how():
    st.title("How VendorGate decides")
    st.markdown("""
**AI reads, rules decide, people own the grey zone.**
The AI model only reads documents and drafts emails. Every status comes from written rules,
so every decision can be traced back to evidence.

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
    st.toggle("Demo pacing", value=True, key="pacing_on",
              help="Adds a short pause per stage so viewers can follow the run")
    ss["pacing"] = 0.4 if ss.get("pacing_on", True) else 0.0
    st.caption(f"AI document reading: {'connected (' + GEMINI_MODEL + ')' if GEMINI_KEY else 'not configured'}")

{"New submission": page_new_run, "Dashboard": page_dashboard, "How it decides": page_how}[page]()
