"""Run history in SQLite: the audit trail behind the dashboard."""
import datetime as dt
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "runs.db"


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY, created TEXT, vendor TEXT, country TEXT, status TEXT,
        route TEXT, parent_id TEXT, source TEXT, submission TEXT, result TEXT)""")
    return c


def count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]


def save(sub: dict, result: dict, parent_id=None, source="manual") -> str:
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] + 1
        run_id = f"RUN-{n:04d}"
        d = result["decision"]
        c.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", (
            run_id, dt.datetime.now().isoformat(timespec="seconds"),
            sub.get("vendor", {}).get("legal_name") or "Unnamed vendor",
            sub.get("vendor", {}).get("country", "IN"), d["status"], d["route"],
            parent_id, source, json.dumps(sub), json.dumps(result)))
    return run_id


def _row(r):
    d = dict(r)
    d["submission"] = json.loads(d["submission"])
    d["result"] = json.loads(d["result"])
    return d


def all_runs() -> list[dict]:
    with _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM runs ORDER BY id DESC")]


def get(run_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _row(r) if r else None


def update_email(run_id: str, email: str):
    run = get(run_id)
    if run:
        run["result"]["decision"]["vendor_email"] = email
        with _conn() as c:
            c.execute("UPDATE runs SET result = ? WHERE id = ?",
                      (json.dumps(run["result"]), run_id))


REVIEW_OUTCOMES = {"approve": ("Approved", "Approved by reviewer"),
                   "request": ("Pending", "Vendor action"),
                   "reject": ("Rejected", "Rejected by reviewer")}


def apply_review(run_id: str, review: dict, vendor_email: str):
    """Record a reviewer's decision on an internal-review case. The automated
    decision is kept alongside it so the audit trail shows both."""
    run = get(run_id)
    res = run["result"]
    d = res["decision"]
    res["auto_decision"] = {"status": d["status"], "route": d["route"], "reasons": list(d["reasons"])}
    status, route = REVIEW_OUTCOMES[review["decision"]]
    d["status"], d["route"] = status, route
    d["reasons"] = [f"Reviewer {review['by']}: {review['reason']}"] + d["reasons"]
    d["vendor_email"], d["email_polished"] = vendor_email, False
    d["internal_summary"] = f"{run['vendor']}: {status} ({route}) after manual review."
    res["review"] = review
    with _conn() as c:
        c.execute("UPDATE runs SET status = ?, route = ?, result = ? WHERE id = ?",
                  (status, route, json.dumps(res), run_id))
