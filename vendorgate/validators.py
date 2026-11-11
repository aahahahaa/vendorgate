"""Format validators and lookups for Indian and US vendor identifiers."""
import re

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
SWIFT_RE = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
EIN_RE = re.compile(r"^\d{2}-\d{7}$")
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
ACCOUNT_RE = re.compile(r"^\d{9,18}$")

# 4th character of a PAN encodes the holder type
PAN_HOLDER_TYPE = {
    "C": "Company", "F": "Firm / LLP", "P": "Individual / Proprietor",
    "H": "Hindu Undivided Family", "A": "Association of Persons", "T": "Trust",
    "B": "Body of Individuals", "L": "Local Authority",
    "J": "Artificial Juridical Person", "G": "Government",
}
ENTITY_TO_PAN_CHAR = {
    "Private Limited Company": "C", "Public Limited Company": "C",
    "LLP": "F", "Partnership Firm": "F", "Sole Proprietorship": "P",
}

GST_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh",
    "23": "Madhya Pradesh", "24": "Gujarat", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "32": "Kerala", "33": "Tamil Nadu", "36": "Telangana",
    "37": "Andhra Pradesh",
}

IFSC_PREFIX_BANKS = {
    "HDFC": "HDFC Bank", "SBIN": "State Bank of India", "ICIC": "ICICI Bank",
    "UTIB": "Axis Bank", "KKBK": "Kotak Mahindra Bank", "PUNB": "Punjab National Bank",
    "BARB": "Bank of Baroda", "CNRB": "Canara Bank", "YESB": "Yes Bank",
    "IDFB": "IDFC First Bank", "INDB": "IndusInd Bank",
}


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14.upper()):
        product = CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return CHARS[(36 - total % 36) % 36]


def gstin_checksum_ok(gstin: str) -> bool:
    gstin = gstin.upper()
    return len(gstin) == 15 and gstin_check_char(gstin[:14]) == gstin[14]


def make_gstin(state_code: str, pan: str, entity_no: str = "1") -> str:
    """Build a checksum-valid GSTIN (used to generate realistic test data)."""
    body = f"{state_code}{pan}{entity_no}Z"
    return body + gstin_check_char(body)


def ifsc_lookup(ifsc: str, timeout: float = 4.0) -> dict:
    """Live lookup via Razorpay's free IFSC API, with an offline fallback."""
    ifsc = ifsc.upper()
    if requests is not None:
        try:
            r = requests.get(f"https://ifsc.razorpay.com/{ifsc}", timeout=timeout)
            if r.status_code == 200:
                d = r.json()
                return {"source": "live", "found": True, "bank": d.get("BANK"),
                        "branch": d.get("BRANCH"), "city": d.get("CITY"),
                        "state": d.get("STATE")}
            if r.status_code == 404:
                return {"source": "live", "found": False}
        except Exception:
            pass
    bank = IFSC_PREFIX_BANKS.get(ifsc[:4])
    return {"source": "offline", "found": bank is not None, "bank": bank,
            "branch": None, "city": None, "state": None}
