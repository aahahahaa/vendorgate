"""Business-name normalisation and fuzzy matching.

Banks truncate and abbreviate names ("SHREE GANESH ENT PVT LTD"), so exact
matching rejects legitimate vendors. We normalise first, then fuzzy-match.
"""
import re

try:
    from rapidfuzz import fuzz

    def _ratio(a, b):
        return fuzz.token_sort_ratio(a, b)
except ImportError:  # pragma: no cover
    from difflib import SequenceMatcher

    def _ratio(a, b):
        return 100 * SequenceMatcher(None, " ".join(sorted(a.split())),
                                     " ".join(sorted(b.split()))).ratio()

ABBREVIATIONS = {
    "pvt": "private", "pte": "private", "ltd": "limited", "ent": "enterprises",
    "ents": "enterprises", "co": "company", "corp": "corporation",
    "intl": "international", "mfg": "manufacturing", "inds": "industries",
    "ind": "industries", "tech": "technologies", "techs": "technologies",
    "svcs": "services", "bros": "brothers", "inc": "incorporated",
}
STOPWORDS = {"the", "m", "s", "ms"}  # "M/s." prefix

PASS_THRESHOLD = 88
REVIEW_THRESHOLD = 70


def normalize(name: str) -> list[str]:
    name = (name or "").lower().replace("&", " and ")
    name = re.sub(r"^m/s\.?\s*", "", name)
    tokens = re.sub(r"[^a-z0-9 ]", " ", name).split()
    return [ABBREVIATIONS.get(t, t) for t in tokens if t not in STOPWORDS]


def name_score(a: str, b: str) -> int:
    ta, tb = normalize(a), normalize(b)
    # Expand truncated tokens ("enterpri" -> "enterprises") against the other name
    tb = [next((x for x in ta if len(t) >= 3 and x.startswith(t)), t) for t in tb]
    ta = [next((x for x in tb if len(t) >= 3 and x.startswith(t)), t) for t in ta]
    return round(_ratio(" ".join(ta), " ".join(tb)))


def name_verdict(score: int) -> str:
    if score >= PASS_THRESHOLD:
        return "match"
    if score >= REVIEW_THRESHOLD:
        return "partial"
    return "mismatch"
