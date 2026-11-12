"""Visual layer for VendorGate: theme CSS and HTML builders for the run card."""
from html import escape

ACCENT, SUCCESS, WARN, REVIEW, DANGER = "#5B8CFF", "#34D399", "#F5B544", "#FB923C", "#F87171"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&family=Instrument+Serif:ital@1&display=swap');
:root{--vg-bg:#0A0F1E;--vg-card:#10172B;--vg-card2:#151E36;--vg-border:#222D4A;--vg-text:#E6EAF2;
--vg-muted:#8A94AD;--vg-accent:#5B8CFF;--vg-ok:#34D399;--vg-warn:#F5B544;--vg-rev:#FB923C;--vg-bad:#F87171;
--vg-mono:'JetBrains Mono',ui-monospace,monospace;--vg-sans:'Manrope',system-ui,sans-serif}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp td, .stApp th {font-family:var(--vg-sans)}
.stApp h1, .stApp h2, .stApp h3 {letter-spacing:-.02em; font-weight:700}
.block-container{padding-top:2.2rem; max-width:1180px}

/* hero */
.vg-eyebrow{font-family:var(--vg-mono);font-size:.74rem;letter-spacing:.22em;text-transform:uppercase;color:var(--vg-accent);
  display:inline-flex;align-items:center;gap:.55rem;border:1px solid var(--vg-border);border-radius:999px;padding:.35rem .9rem;margin-bottom:1rem}
.vg-eyebrow i{width:6px;height:6px;border-radius:50%;background:var(--vg-accent);display:inline-block;animation:vg-blink 1.6s infinite}
.vg-hero{font-size:2.7rem;line-height:1.08;font-weight:800;letter-spacing:-.035em;color:var(--vg-text);margin:0 0 .6rem}
.vg-hero em{font-family:'Instrument Serif',serif;font-style:italic;font-weight:400;color:var(--vg-accent);letter-spacing:-.01em}
.vg-sub{color:var(--vg-muted);font-size:1.02rem;max-width:720px;margin-bottom:1.6rem}
.vg-section{font-family:var(--vg-mono);font-size:.72rem;letter-spacing:.2em;text-transform:uppercase;color:var(--vg-muted);margin:1.4rem 0 .4rem}

/* hover glow on Streamlit containers */
[data-testid="stExpander"] details{border:1px solid var(--vg-border)!important;border-radius:12px!important;background:var(--vg-card);transition:border-color .2s, box-shadow .2s}
[data-testid="stExpander"] details:hover{border-color:rgba(91,140,255,.55)!important;box-shadow:0 0 0 1px rgba(91,140,255,.15),0 0 28px rgba(91,140,255,.10)}
[data-testid="stMetric"]{background:var(--vg-card);border:1px solid var(--vg-border);border-radius:12px;padding:14px 16px;transition:all .2s}
[data-testid="stMetric"]:hover{border-color:rgba(91,140,255,.55);box-shadow:0 0 28px rgba(91,140,255,.12);transform:translateY(-2px)}
[data-testid="stMetricLabel"] p{font-family:var(--vg-mono)!important;font-size:.7rem!important;letter-spacing:.14em;text-transform:uppercase;color:var(--vg-muted)!important}
[data-testid="stFileUploaderDropzone"]{border:1px dashed var(--vg-border);transition:border-color .2s}
[data-testid="stFileUploaderDropzone"]:hover{border-color:var(--vg-accent)}
.stButton button[kind="primary"]{border-radius:999px;padding:.55rem 1.4rem;font-weight:600;transition:box-shadow .2s, transform .2s}
.stButton button[kind="primary"]:hover{box-shadow:0 0 0 4px rgba(91,140,255,.18);transform:translateY(-1px)}
.stButton button[kind="secondary"]{border-radius:999px}

/* run card */
.vg-card{background:var(--vg-card);border:1px solid var(--vg-border);border-radius:16px;overflow:hidden;margin:.6rem 0 1rem;transition:border-color .2s, box-shadow .2s}
.vg-card:hover{border-color:rgba(91,140,255,.45);box-shadow:0 0 36px rgba(91,140,255,.08)}
.vg-bar{display:flex;align-items:center;gap:12px;padding:12px 18px;border-bottom:1px solid var(--vg-border);font-family:var(--vg-mono);font-size:.78rem;color:var(--vg-muted)}
.vg-dots{display:flex;gap:6px}.vg-dots b{width:9px;height:9px;border-radius:50%;background:#2A3555;display:inline-block}
.vg-live{margin-left:auto;color:var(--vg-accent);letter-spacing:.14em;text-transform:uppercase;display:flex;align-items:center;gap:7px}
.vg-live i{width:7px;height:7px;border-radius:50%;background:var(--vg-accent);display:inline-block;animation:vg-blink 1s infinite}
.vg-live.done{color:var(--vg-muted)}.vg-live.done i{animation:none;background:var(--vg-muted)}

.vg-rail{position:relative;display:flex;padding:24px 10px 8px}
.vg-step{flex:1;display:flex;flex-direction:column;align-items:center;gap:9px;position:relative;z-index:1}
.vg-track,.vg-fill{position:absolute;top:36px;height:2px;border-radius:2px}
.vg-track{background:var(--vg-border)}
.vg-fill{background:var(--vg-accent);transition:width .45s ease}
.vg-node{position:relative;width:26px;height:26px;border-radius:50%;border:2px solid #34405F;background:var(--vg-card);
  display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:700;color:var(--vg-text)}
.vg-node.active{border-color:var(--vg-accent)}
.vg-node.active::before,.vg-node.active::after{content:"";position:absolute;inset:-2px;border-radius:50%;border:2px solid var(--vg-accent);animation:vg-ping 1.4s ease-out infinite}
.vg-node.active::after{animation-delay:.7s}
.vg-node.pass{border-color:var(--vg-accent);background:rgba(91,140,255,.16);color:var(--vg-accent)}
.vg-node.warn{border-color:var(--vg-warn);background:rgba(245,181,68,.14);color:var(--vg-warn)}
.vg-node.bad{border-color:var(--vg-bad);background:rgba(248,113,113,.14);color:var(--vg-bad)}
.vg-lbl{font-family:var(--vg-mono);font-size:.66rem;letter-spacing:.06em;color:var(--vg-muted);text-align:center;white-space:nowrap}

.vg-body{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:0;border-top:1px solid var(--vg-border);margin-top:14px}
.vg-col{padding:14px 18px 18px}.vg-col+.vg-col{border-left:1px solid var(--vg-border)}
.vg-h{font-family:var(--vg-mono);font-size:.68rem;letter-spacing:.18em;text-transform:uppercase;color:var(--vg-muted);margin:0 0 8px}
.vg-stage{font-family:var(--vg-mono);font-size:.64rem;letter-spacing:.16em;text-transform:uppercase;color:#5D6886;margin:12px 0 2px}
.vg-chk{display:flex;gap:10px;align-items:flex-start;padding:4px 0;font-size:.88rem;color:var(--vg-text);line-height:1.45}
.vg-chk.new{animation:vg-rise .35s ease-out both}
.vg-ic{flex:0 0 18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.66rem;font-weight:800;margin-top:1px}
.vg-ic.pass{background:rgba(91,140,255,.18);color:var(--vg-accent)}
.vg-ic.info,.vg-ic.skip{background:rgba(138,148,173,.16);color:var(--vg-muted)}
.vg-ic.fix{background:rgba(245,181,68,.18);color:var(--vg-warn)}
.vg-ic.review{background:rgba(251,146,60,.18);color:var(--vg-rev)}
.vg-ic.block{background:rgba(248,113,113,.18);color:var(--vg-bad)}
.vg-chk b{font-weight:600}.vg-chk .m{color:var(--vg-muted)}
.vg-diff{font-family:var(--vg-mono);font-size:.8rem;background:var(--vg-card2);border:1px solid var(--vg-border);border-radius:8px;padding:7px 10px;margin:6px 0 2px;line-height:1.75;display:inline-block}
.vg-diff span.k{color:var(--vg-muted);display:inline-block;min-width:96px}
.vg-diff mark{background:rgba(248,113,113,.22);color:#FFB4B4;border-radius:3px;padding:0 2px}
.vg-ev{font-family:var(--vg-mono);font-size:.74rem;color:var(--vg-muted);margin:2px 0 0}

.vg-wait{font-family:var(--vg-mono);font-size:.8rem;color:var(--vg-muted)}
.vg-stampwrap{position:relative;display:inline-block;margin:8px 0 10px}
.vg-stamp{font-family:var(--vg-mono);font-weight:500;font-size:1.55rem;letter-spacing:.2em;padding:8px 20px;border:2.5px solid;border-radius:8px;transform:rotate(-3deg)}
.vg-stamp.anim{animation:vg-land .5s cubic-bezier(.2,1.4,.4,1) both}
.vg-ripple{position:absolute;inset:0;border:2px solid;border-radius:8px;transform:rotate(-3deg);opacity:0}
.vg-ripple.anim{animation:vg-ripple .9s ease-out .35s both}
.vg-next{font-size:.88rem;color:var(--vg-muted);margin:4px 0 0}.vg-next b{color:var(--vg-text)}
.vg-counts{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.vg-pill{font-family:var(--vg-mono);font-size:.68rem;letter-spacing:.06em;border:1px solid var(--vg-border);border-radius:999px;padding:3px 9px;color:var(--vg-muted)}

.vg-hint{font-size:.78rem;margin:-.55rem 0 .7rem;display:flex;gap:6px;align-items:baseline;line-height:1.4}
.vg-hint.ok{color:#7FA6FF}.vg-hint.warn{color:var(--vg-warn)}.vg-hint.bad{color:var(--vg-bad)}
.vg-fill-note{font-family:var(--vg-mono);font-size:.72rem;color:var(--vg-accent);border:1px solid rgba(91,140,255,.35);
  background:rgba(91,140,255,.08);border-radius:8px;padding:6px 10px;margin:0 0 .8rem;animation:vg-rise .35s ease-out}
.vg-review{background:var(--vg-card);border:1px solid rgba(251,146,60,.45);border-radius:14px;padding:14px 18px;margin:.4rem 0 .8rem}
.vg-review h4{margin:0 0 4px;font-size:1rem}.vg-review p{color:var(--vg-muted);font-size:.86rem;margin:0}
.vg-reviewed{font-size:.84rem;color:var(--vg-muted);margin:10px 0 0;border-top:1px solid var(--vg-border);padding-top:10px}
.vg-reviewed b{color:var(--vg-text)}
.vg-ai{border:1px solid var(--vg-border);border-radius:12px;padding:10px 12px;font-size:.8rem;display:flex;flex-direction:column;gap:3px;margin-top:6px}
.vg-ai b{display:flex;align-items:center;gap:8px;font-weight:600;color:var(--vg-text)}
.vg-ai b i{width:8px;height:8px;border-radius:50%;display:inline-block}
.vg-ai.ok b i{background:var(--vg-ok)}.vg-ai.warn b i{background:var(--vg-warn)}.vg-ai.bad b i{background:var(--vg-bad)}
.vg-ai.bad{border-color:rgba(248,113,113,.45)}
.vg-ai span{color:var(--vg-muted);line-height:1.45}.vg-ai .m{font-family:var(--vg-mono);font-size:.68rem;opacity:.8}
@keyframes vg-ping{0%{transform:scale(1);opacity:.75}100%{transform:scale(2.5);opacity:0}}
@keyframes vg-blink{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes vg-rise{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
@keyframes vg-land{0%{transform:scale(1.9) rotate(-3deg);opacity:0}70%{transform:scale(.94) rotate(-3deg);opacity:1}100%{transform:scale(1) rotate(-3deg);opacity:1}}
@keyframes vg-ripple{0%{transform:scale(1) rotate(-3deg);opacity:.7}100%{transform:scale(1.65) rotate(-3deg);opacity:0}}
@media (max-width:760px){.vg-body{grid-template-columns:1fr}.vg-col+.vg-col{border-left:0;border-top:1px solid var(--vg-border)}
 .vg-lbl{display:none}.vg-hero{font-size:2rem}}
</style>
"""

ICON_CHAR = {"pass": "✓", "info": "i", "skip": "–", "fix": "!", "review": "?", "block": "✕"}
STAMP_STYLE = {("Approved", ""): (SUCCESS, "APPROVED"),
               ("Pending", "Vendor action"): (WARN, "PENDING"),
               ("Pending", "Internal review"): (REVIEW, "PENDING"),
               ("Rejected", ""): (DANGER, "REJECTED")}

# Checks whose evidence holds two values worth comparing character by character
DIFF_FIELDS = {
    "pan_in_gstin": (("submitted_pan", "Form PAN"), ("pan_in_gstin", "Inside GSTIN")),
    "gstin_doc": (("form", "Form"), ("certificate", "Certificate")),
    "pan_doc": (("form", "Form"), ("card", "PAN card")),
}


def hero(eyebrow, headline_html, sub):
    return (f"<div class='vg-eyebrow'><i></i>{escape(eyebrow)}</div>"
            f"<div class='vg-hero'>{headline_html}</div><div class='vg-sub'>{escape(sub)}</div>")


def section(label):
    return f"<div class='vg-section'>{escape(label)}</div>"


def node_state(worst):
    if worst in ("block",):
        return "bad"
    if worst in ("fix", "review"):
        return "warn"
    return "pass"


def rail(names, states, active=None):
    n = len(names)
    edge = f"calc(100% / {2 * n})"
    done = max([i for i, s in enumerate(states) if s] or [-1])
    frac = max(done, 0) / (n - 1) if n > 1 else 0
    steps = "".join(
        f"<div class='vg-step'><div class='vg-node{' active' if i == active else ''}"
        f"{' ' + s if s else ''}'>{ {'pass': '✓', 'warn': '!', 'bad': '✕'}.get(s, '') }</div>"
        f"<div class='vg-lbl'>{escape(nm)}</div></div>"
        for i, (nm, s) in enumerate(zip(names, states)))
    return (f"<div class='vg-rail'><div class='vg-track' style='left:{edge};right:{edge}'></div>"
            f"<div class='vg-fill' style='left:{edge};width:calc((100% - 100% / {n}) * {frac:.4f})'></div>"
            f"{steps}</div>")


def _diff(a, b):
    out_a, out_b = [], []
    for i in range(max(len(a), len(b))):
        ca, cb = (a[i] if i < len(a) else ""), (b[i] if i < len(b) else "")
        if ca != cb:
            out_a.append(f"<mark>{escape(ca) or '&nbsp;'}</mark>")
            out_b.append(f"<mark>{escape(cb) or '&nbsp;'}</mark>")
        else:
            out_a.append(escape(ca))
            out_b.append(escape(cb))
    return "".join(out_a), "".join(out_b)


def check_html(c, new=False):
    sev = c["severity"]
    ev = c.get("evidence") or {}
    extra = ""
    pair = DIFF_FIELDS.get(c["id"])
    if pair and sev != "pass" and isinstance(ev.get(pair[0][0]), str) and isinstance(ev.get(pair[1][0]), str):
        (ka, la), (kb, lb) = pair
        da, db = _diff(ev[ka], ev[kb])
        extra = (f"<div class='vg-diff'><span class='k'>{la}</span>{da}<br>"
                 f"<span class='k'>{lb}</span>{db}</div>")
    elif sev in ("fix", "review", "block"):
        simple = {k: v for k, v in ev.items() if isinstance(v, (str, int, float)) and k != "source"}
        if simple:
            extra = "<div class='vg-ev'>" + " · ".join(
                f"{escape(k.replace('_', ' '))}: {escape(str(v))}" for k, v in simple.items()) + "</div>"
    return (f"<div class='vg-chk{' new' if new else ''}'><div class='vg-ic {sev}'>{ICON_CHAR[sev]}</div>"
            f"<div><b>{escape(c['label'])}</b> <span class='m'>· {escape(c['message'])}</span>{extra}</div></div>")


def stamp(decision, animate, festive=False):
    route = decision["route"] if decision["status"] == "Pending" else ""
    color, word = STAMP_STYLE[(decision["status"], route)]
    a = " anim" if animate else ""
    party = celebration() if (festive and animate and decision["status"] == "Approved") else ""
    return (f"<div class='vg-stampwrap'>{party}<span class='vg-ripple{a}' style='border-color:{color}'></span>"
            f"<div class='vg-stamp{a}' style='color:{color};border-color:{color}'>{word}</div></div>"
            f"<p class='vg-next'>Next: <b>{escape(decision['route'])}</b></p>")


def card(run_id, rail_html, checks_html, decision_html, live=True):
    status = "<i></i>live" if live else "<i></i>done"
    return (f"<div class='vg-card'><div class='vg-bar'><span class='vg-dots'><b></b><b></b><b></b></span>"
            f"<span>vendor-intake · run #{escape(run_id)}</span>"
            f"<span class='vg-live{'' if live else ' done'}'>{status}</span></div>"
            f"{rail_html}<div class='vg-body'><div class='vg-col'><div class='vg-h'>Checks</div>{checks_html}</div>"
            f"<div class='vg-col'><div class='vg-h'>Decision</div>{decision_html}</div></div></div>")


def counts(stages):
    sev = [c["severity"] for s in stages for c in s["checks"]]
    parts = [("passed", sum(x == "pass" for x in sev)), ("vendor fixes", sev.count("fix")),
             ("for review", sev.count("review")), ("blocking", sev.count("block"))]
    return "<div class='vg-counts'>" + "".join(
        f"<span class='vg-pill'>{n} {label}</span>" for label, n in parts if n or label == "passed") + "</div>"


HINT_ICON = {"ok": "✓", "warn": "!", "bad": "✕"}


def hint(kind, msg):
    if not kind:
        return ""
    return f"<div class='vg-hint {kind}'><span>{HINT_ICON[kind]}</span><span>{escape(msg)}</span></div>"


def reviewed_note(review, auto):
    verb = {"approve": "approved", "request": "sent back to the vendor", "reject": "rejected"}[review["decision"]]
    return (f"<div class='vg-reviewed'>Reviewed by <b>{escape(review['by'])}</b> · {verb}<br>"
            f"“{escape(review['reason'])}”<br>Automated result was {escape(auto['status'])} "
            f"({escape(auto['route'])})</div>")


# ================================================================ festive edition (Diwali)
import math as _m

FESTIVE_GOLD, FESTIVE_COLORS = "#FFC93C", ["#FFC93C", "#FF7A59", "#F5E1A4", "#E86FA8", "#7FD1FF"]

FESTIVE_CSS_TEMPLATE = """
<style>
:root{--vg-accent:#FFC93C;--vg-card:#1E1233;--vg-card2:#271843;--vg-border:#3D2A57;--vg-muted:#B9A98A;--vg-text:#F3E9D2}
.stApp{background:radial-gradient(1100px 520px at 50% -8%,#2D1650 0%,#140B24 62%) fixed}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background:#1A0F2E}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{background:#1E1233!important;border-color:#3D2A57!important}
input,textarea{background:transparent!important}
.stButton button[kind="primary"],[data-testid="stFormSubmitButton"] button{background:#FFC93C!important;color:#3A2400!important;border:none!important}
.stButton button[kind="primary"]:hover{box-shadow:0 0 0 4px rgba(255,201,60,.22)!important}
.block-container{padding-bottom:110px}
.vg-hero em{color:#FFC93C}
.vg-eyebrow{border-color:#5A4220}
.vg-node.pass{border-color:#FFC93C;background:rgba(255,201,60,.14);color:#FFC93C}
.vg-node.active,.vg-node.active::before,.vg-node.active::after{border-color:#FFC93C}
.vg-fill{background:#FFC93C}
.vg-ic.pass{background:rgba(255,201,60,.16);color:#FFC93C}
.vg-hint.ok{color:#FFD873}
.vg-fill-note{color:#FFC93C;border-color:rgba(255,201,60,.4);background:rgba(255,201,60,.08)}
.vg-live,.vg-live i{color:#FFC93C}.vg-live i{background:#FFC93C}
.vg-card:hover,[data-testid="stExpander"] details:hover,[data-testid="stMetric"]:hover{border-color:rgba(255,201,60,.55)!important;box-shadow:0 0 30px rgba(255,201,60,.12)!important}
.vg-stamp{outline:3px dotted #FF922B;outline-offset:6px}

/* decorations: fixed, behind nothing clickable */
.fx{position:fixed;pointer-events:none;z-index:999990}
.fx-toran{top:0;left:0;right:0;height:46px}
.fx-string{position:absolute;left:-2%;right:-2%;top:-30px;height:58px;border-bottom:1.5px solid #8C6A2F;border-radius:0 0 50% 50%}
.fx-bulb{position:absolute;width:8px;height:8px;border-radius:50%;animation:fx-tw 1.6s ease-in-out infinite}
.fx-mari{width:64px;height:64px;border-radius:50%;animation:fx-spin 40s linear infinite;
  background:radial-gradient(circle,#7A3E00 0 13%,transparent 14%),
  radial-gradient(circle,transparent 0 13%,#FFC93C 14% 34%,transparent 35%),
  repeating-conic-gradient(#E8590C 0 9deg,#FF922B 9deg 18deg);
  -webkit-mask:radial-gradient(circle,#000 62%,transparent 63%),repeating-conic-gradient(#000 0 9deg,transparent 9deg 18deg);
  mask:radial-gradient(circle,#000 62%,transparent 63%),repeating-conic-gradient(#000 0 9deg,transparent 9deg 18deg)}
.fx-diyas{bottom:10px;left:0;right:0;display:flex;justify-content:space-around;padding:0 4%}
.fx-diya{display:flex;flex-direction:column;align-items:center}
.fx-flame{width:9px;height:16px;background:#FFC93C;border-radius:50% 50% 50% 50%/62% 62% 38% 38%;transform-origin:bottom;
  animation:fx-flame 2.7s ease-in-out infinite;box-shadow:0 -2px 12px rgba(255,201,60,.55)}
.fx-lamp{width:38px;height:15px;background:#C2410C;border-radius:0 0 50% 50%/0 0 100% 100%;border-top:2px solid #FFC93C;margin-top:1px}
.fx-ray{position:absolute;width:0;height:0}
.fx-spark{position:absolute;left:0;top:-2px;width:4px;height:4px;border-radius:50%;opacity:0}
.vg-celebrate{position:absolute;inset:0;pointer-events:none}
@keyframes fx-tw{0%,100%{opacity:.25}50%{opacity:1}}
@keyframes fx-spin{to{transform:rotate(360deg)}}
@keyframes fx-flame{0%,100%{opacity:.25;transform:scaleY(.6)}50%{opacity:1;transform:scaleY(1)}}
__SPARK_KEYFRAMES__
@media (prefers-reduced-motion:reduce){.fx *,.vg-celebrate *{animation:none!important}.fx-bg,.vg-celebrate{display:none}}
@media (max-width:760px){.fx-mari{width:44px;height:44px}.fx-diya:nth-child(n+6){display:none}}
</style>
"""


SPARK_DIST = (45, 55, 65, 75, 90)


def _spark_keyframes():
    out = []
    for d in SPARK_DIST:
        out.append(f".fx-bg .fx-spark.d{d}{{animation:fx-loop{d} 20s ease-out infinite both}}"
                   f".vg-celebrate .fx-spark.d{d}{{animation:fx-once{d} 1.3s ease-out both}}"
                   f"@keyframes fx-loop{d}{{0%{{opacity:0;transform:translateX(0)}}.4%{{opacity:1;transform:translateX(0)}}"
                   f"6%{{opacity:0;transform:translateX({d}px)}}100%{{opacity:0;transform:translateX({d}px)}}}}"
                   f"@keyframes fx-once{d}{{0%{{opacity:0;transform:translateX(0)}}8%{{opacity:1}}"
                   f"100%{{opacity:0;transform:translateX({d}px)}}}}")
    return "\n".join(out)


def _sparks(x, y, n, spread, delay, unit="px", seed=0):
    """Each spark sits on a rotated ray and flies outward along it (no CSS variables needed)."""
    out = []
    for i in range(n):
        target = spread * (0.65 + 0.35 * ((i * 7 + seed) % 5) / 4)
        d = min(SPARK_DIST, key=lambda v: abs(v - target))
        out.append(f"<span class='fx-ray' style='left:{x}{unit};top:{y}{unit};transform:rotate({i / n * 360:.0f}deg)'>"
                   f"<i class='fx-spark d{d}' style='background:{FESTIVE_COLORS[(i + seed) % len(FESTIVE_COLORS)]};"
                   f"animation-delay:{delay}s'></i></span>")
    return "".join(out)


def festive_decor():
    bulb_colors = ["#FFC93C", "#FF7A59", "#F5E1A4", "#E86FA8"]
    bulbs = "".join(
        f"<span class='fx-bulb' style='left:{i / 23 * 100:.1f}%;top:{6 + 22 * _m.sin(i / 23 * _m.pi):.0f}px;"
        f"background:{bulb_colors[i % 4]};animation-delay:{(i % 2) * .8}s'></span>" for i in range(24))
    diyas = "".join(f"<div class='fx-diya'><div class='fx-flame' style='animation-delay:{i * .3:.1f}s'></div>"
                    f"<div class='fx-lamp'></div></div>" for i in range(9))
    spots = [(22, 26), (76, 20), (58, 44), (34, 40)]
    bursts = "".join(_sparks(x, y, 22, 70, k * 5 + 1, "%", seed=k) for k, (x, y) in enumerate(spots))
    return (f"<div class='fx fx-toran'><div class='fx-string'></div>{bulbs}</div>"
            f"<div class='fx fx-mari' style='top:-16px;left:-16px'></div>"
            f"<div class='fx fx-mari' style='top:-16px;right:-16px;animation-direction:reverse'></div>"
            f"<div class='fx fx-bg' style='inset:0'>{bursts}</div>"
            f"<div class='fx fx-diyas'>{diyas}</div>")


def celebration():
    """Three bursts around the stamp, played once when a vendor is approved."""
    return ("<span class='vg-celebrate'>" + _sparks(50, 50, 24, 90, .35, "%", 0)
            + _sparks(15, 30, 18, 70, .6, "%", 2) + _sparks(85, 30, 18, 70, .85, "%", 4) + "</span>")


FESTIVE_CSS = FESTIVE_CSS_TEMPLATE.replace("__SPARK_KEYFRAMES__", _spark_keyframes())
