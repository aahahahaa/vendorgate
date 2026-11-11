"""Generates all mock data. Every PAN, GSTIN and account number is fictional;
GSTINs are built with the real check-digit algorithm so format checks are meaningful."""
import json
from pathlib import Path

from vendorgate.validators import make_gstin

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
TODAY = "2026-11-09"

# ---------------------------------------------------------------- vendor master
master = [
    ("V-0011", "Bharat Steel Fabricators Private Limited", "AABCB1120D", "27", "50100118830021", "HDFC0000001"),
    ("V-0014", "Om Sai Logistics", "AXRPS4471K", "09", "30981124410", "SBIN0000300"),
    ("V-0017", "Lakshmi Packaging Industries LLP", "AAKFL2290M", "33", "012345678901", "ICIC0000001"),
    ("V-0021", "Sapthagiri Traders", "AAPFS6612R", "33", "50100234417094", "HDFC0000001"),
    ("V-0023", "Himalaya Office Supplies", "BQEPK3318L", "05", "38812290114", "SBIN0000300"),
    ("V-0026", "Deccan Electricals Private Limited", "AAECD7781P", "36", "50100661209933", "HDFC0000001"),
    ("V-0030", "Konkan Chemicals Private Limited", "AADCK5530F", "27", "112233445566", "ICIC0000001"),
    ("V-0032", "Northstar IT Services Private Limited", "AAHCN8812B", "29", "50100772019284", "HDFC0000001"),
]
vendor_master = [
    {"vendor_id": vid, "legal_name": n, "tax_id": pan, "gstin": make_gstin(sc, pan),
     "account_number": acct, "ifsc": ifsc, "status": "Active"}
    for vid, n, pan, sc, acct, ifsc in master
]

# ---------------------------------------------------------------- GST registry (mock)
registry = {v["gstin"]: {"legal_name": v["legal_name"], "status": "Active",
                          "registration_date": "2019-04-01"} for v in vendor_master}


def reg(gstin, name, status="Active", date="2021-07-15"):
    registry[gstin] = {"legal_name": name, "status": status, "registration_date": date}
    return gstin


def doc(slot, fields, detected=None, conf=0.96, file=None):
    return {"slot": slot, "detected_type": detected or slot, "fields": fields,
            "confidence": conf, "file": file or f"{slot}.pdf"}


scenarios = {}

# 1. HAPPY PATH -------------------------------------------------------------------
pan = "AAACN4821K"
g = reg(make_gstin("27", pan), "Nirmala Precision Castings Private Limited")
scenarios["happy_path"] = {
    "title": "Happy path: clean Indian company",
    "expect": "Approved",
    "submission": {
        "submission_id": "SUB-1001", "submitted_at": TODAY,
        "vendor": {"legal_name": "Nirmala Precision Castings Private Limited",
                   "trade_name": "Nirmala Castings", "entity_type": "Private Limited Company",
                   "country": "IN", "address": "Plot 42, MIDC Bhosari, Pune 411026",
                   "state": "Maharashtra", "contact_email": "accounts@nirmalacastings.in"},
        "tax": {"pan": pan, "gstin": g},
        "bank": {"account_holder": "Nirmala Precision Castings Pvt Ltd",
                 "account_number": "50100398812760", "ifsc": "HDFC0000001"},
        "documents": [
            doc("gst_certificate", {"gstin": g, "legal_name": "NIRMALA PRECISION CASTINGS PRIVATE LIMITED",
                                    "registration_date": "2021-07-15", "state": "Maharashtra"}),
            doc("pan_card", {"pan": pan, "name": "NIRMALA PRECISION CASTINGS PRIVATE LIMITED"}),
            doc("cancelled_cheque", {"account_holder": "NIRMALA PRECISION CASTINGS PVT LTD",
                                     "account_number": "50100398812760", "ifsc": "HDFC0000001",
                                     "bank_name": "HDFC Bank"}, file="cheque.jpg"),
        ],
    },
}

# 2. EDGE 1: wrong document + abbreviated bank name -> Pending, then resubmission -> Approved
pan = "AAGCS7731M"
g = reg(make_gstin("29", pan), "Shree Ganesh Enterprises Private Limited", date="2020-02-10")
base = {
    "submission_id": "SUB-1002", "submitted_at": TODAY,
    "vendor": {"legal_name": "Shree Ganesh Enterprises Private Limited",
               "trade_name": "Ganesh Hardware", "entity_type": "Private Limited Company",
               "country": "IN", "address": "14 KR Road, Basavanagudi, Bengaluru 560004",
               "state": "Karnataka", "contact_email": "shreeganesh.ent@gmail.com"},
    "tax": {"pan": pan, "gstin": g},
    "bank": {"account_holder": "Shree Ganesh Enterprises Pvt Ltd",
             "account_number": "30744218805", "ifsc": "SBIN0000300"},
}
gst_doc = doc("gst_certificate", {"gstin": g, "legal_name": "SHREE GANESH ENTERPRISES PRIVATE LIMITED",
                                  "registration_date": "2020-02-10", "state": "Karnataka"})
pan_doc = doc("pan_card", {"pan": pan, "name": "SHREE GANESH ENTERPRISES PRIVATE LIMITED"})
scenarios["edge1_wrong_document"] = {
    "title": "Edge 1: PAN card uploaded in the cheque slot",
    "expect": "Pending (Vendor action)",
    "submission": {**base, "documents": [
        gst_doc, pan_doc,
        doc("cancelled_cheque", {"pan": pan, "name": "SHREE GANESH ENTERPRISES PRIVATE LIMITED"},
            detected="pan_card", file="IMG_2041.jpg")]},
}
scenarios["edge1_resubmission"] = {
    "title": "Edge 1 (resubmitted): correct cheque, bank abbreviates the name",
    "expect": "Approved",
    "resubmission_of": "edge1_wrong_document",
    "submission": {**base, "submission_id": "SUB-1002-R1", "documents": [
        gst_doc, pan_doc,
        doc("cancelled_cheque", {"account_holder": "SHREE GANESH ENT PVT LTD",
                                 "account_number": "30744218805", "ifsc": "SBIN0000300",
                                 "bank_name": "State Bank of India"}, file="cheque_scan.jpg",
            conf=0.88)]},
}

# 3. EDGE 2: every field is well-formed, but they contradict each other -> internal review
real_pan, typed_pan = "AAECV5520H", "AAECV5502H"   # transposed digits
g = reg(make_gstin("27", real_pan), "Vasundhara Agro Foods Private Limited", date="2018-09-03")
scenarios["edge2_hidden_inconsistency"] = {
    "title": "Edge 2: valid-looking fields that contradict each other",
    "expect": "Pending (Internal review)",
    "submission": {
        "submission_id": "SUB-1003", "submitted_at": TODAY,
        "vendor": {"legal_name": "Vasundhara Agro Foods Private Limited",
                   "entity_type": "Private Limited Company", "country": "IN",
                   "address": "88 Industrial Suburb, Yeshwanthpur, Bengaluru 560022",
                   "state": "Karnataka", "contact_email": "finance@vasundharaagro.com"},
        "tax": {"pan": typed_pan, "gstin": g},
        "bank": {"account_holder": "Vasundhara Agro Foods Private Limited",
                 "account_number": "000405118823", "ifsc": "ICIC0000001"},
        "documents": [
            doc("gst_certificate", {"gstin": g, "legal_name": "VASUNDHARA AGRO FOODS PRIVATE LIMITED",
                                    "registration_date": "2018-09-03", "state": "Maharashtra"}),
            doc("pan_card", {"pan": typed_pan, "name": "VASUNDHARA AGRO FOODS PRIVATE LIMITED"}),
            doc("cancelled_cheque", {"account_holder": "VASUNDHARA AGRO FOODS PRIVATE LIMITED",
                                     "account_number": "000405118823", "ifsc": "ICIC0000001",
                                     "bank_name": "ICICI Bank"}),
        ],
    },
}

# 4. EDGE 3: bank account already belongs to another vendor -> Rejected
pan = "AAJFK3390Q"
g = reg(make_gstin("33", pan), "Kaveri Industrial Supplies", date="2026-10-28")
scenarios["edge3_shared_bank_account"] = {
    "title": "Edge 3: bank account already used by another vendor",
    "expect": "Rejected",
    "submission": {
        "submission_id": "SUB-1004", "submitted_at": TODAY,
        "vendor": {"legal_name": "Kaveri Industrial Supplies", "entity_type": "Partnership Firm",
                   "country": "IN", "address": "21 Ambattur Industrial Estate, Chennai 600058",
                   "state": "Tamil Nadu", "contact_email": "kaverisupplies@gmail.com"},
        "tax": {"pan": pan, "gstin": g},
        "bank": {"account_holder": "Kaveri Industrial Supplies",
                 "account_number": "50100234417094", "ifsc": "HDFC0000001"},
        "documents": [
            doc("gst_certificate", {"gstin": g, "legal_name": "KAVERI INDUSTRIAL SUPPLIES",
                                    "registration_date": "2026-10-28", "state": "Tamil Nadu"}),
            doc("pan_card", {"pan": pan, "name": "KAVERI INDUSTRIAL SUPPLIES"}),
            doc("cancelled_cheque", {"account_holder": "KAVERI INDUSTRIAL SUPPLIES",
                                     "account_number": "50100234417094", "ifsc": "HDFC0000001",
                                     "bank_name": "HDFC Bank"}),
        ],
    },
}

# 5. EDGE 4: foreign vendor gives an Indian PAN, W-8BEN missing -> different rule pack
scenarios["edge4_foreign_vendor"] = {
    "title": "Edge 4: US vendor submits an Indian tax ID",
    "expect": "Pending (Vendor action)",
    "submission": {
        "submission_id": "SUB-1005", "submitted_at": TODAY,
        "vendor": {"legal_name": "Northwind Analytics Inc.", "entity_type": "Corporation",
                   "country": "US", "address": "500 Market St, Wilmington, DE 19801",
                   "state": "Delaware", "contact_email": "ap@northwind-analytics.com"},
        "tax": {"ein": "AAFCN9921J"},
        "bank": {"account_holder": "Northwind Analytics Inc.",
                 "account_number": "483920117", "swift": "CHASUS33"},
        "documents": [
            doc("bank_letter", {"account_holder": "Northwind Analytics Inc.",
                                "account_number": "483920117", "swift": "CHASUS33",
                                "bank_name": "JPMorgan Chase Bank"}),
        ],
    },
}

# 6. BONUS: cancelled GST -> Rejected
pan = "AAFCR6614E"
g = reg(make_gstin("07", pan), "Rajdhani Print Solutions Private Limited", "Cancelled", "2017-08-01")
scenarios["bonus_cancelled_gst"] = {
    "title": "Bonus: GST registration cancelled",
    "expect": "Rejected",
    "submission": {
        "submission_id": "SUB-1006", "submitted_at": TODAY,
        "vendor": {"legal_name": "Rajdhani Print Solutions Private Limited",
                   "entity_type": "Private Limited Company", "country": "IN",
                   "address": "B-17 Okhla Phase II, New Delhi 110020", "state": "Delhi",
                   "contact_email": "billing@rajdhaniprint.in"},
        "tax": {"pan": pan, "gstin": g},
        "bank": {"account_holder": "Rajdhani Print Solutions Pvt Ltd",
                 "account_number": "50100551230981", "ifsc": "HDFC0000001"},
        "documents": [
            doc("gst_certificate", {"gstin": g, "legal_name": "RAJDHANI PRINT SOLUTIONS PRIVATE LIMITED"}),
            doc("pan_card", {"pan": pan, "name": "RAJDHANI PRINT SOLUTIONS PRIVATE LIMITED"}),
            doc("cancelled_cheque", {"account_holder": "RAJDHANI PRINT SOLUTIONS PVT LTD",
                                     "account_number": "50100551230981", "ifsc": "HDFC0000001",
                                     "bank_name": "HDFC Bank"}),
        ],
    },
}

(DATA / "vendor_master.json").write_text(json.dumps(vendor_master, indent=2))
(DATA / "gst_registry.json").write_text(json.dumps(registry, indent=2))
(DATA / "scenarios.json").write_text(json.dumps(scenarios, indent=2))
print(f"{len(vendor_master)} vendors, {len(registry)} GST records, {len(scenarios)} scenarios")
