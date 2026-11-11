"""Run every demo scenario in the terminal: python run_cli.py [scenario_key]"""
import datetime as dt
import json
import sys
from pathlib import Path

from vendorgate.pipeline import run_pipeline, run_all, diff_runs

DATA = Path(__file__).parent / "data"
ICON = {"pass": "✅", "info": "ℹ️ ", "skip": "⏭️ ", "fix": "🟡", "review": "🟠", "block": "❌"}
TODAY = dt.date(2026, 11, 9)

master = json.loads((DATA / "vendor_master.json").read_text())
registry = json.loads((DATA / "gst_registry.json").read_text())
scenarios = json.loads((DATA / "scenarios.json").read_text())

keys = sys.argv[1:] or list(scenarios)
for key in keys:
    sc = scenarios[key]
    print(f"\n{'=' * 78}\n{sc['title']}   (expected: {sc['expect']})\n{'=' * 78}")
    for kind, obj in run_pipeline(sc["submission"], master, registry, TODAY):
        if kind == "stage":
            print(f"\n{ICON[obj.worst]} {obj.name}  [{obj.duration_ms} ms]")
            for c in obj.checks:
                print(f"     {ICON[c.severity]} {c.label}: {c.message}")
        else:
            print(f"\n→ DECISION: {obj.status}  ({obj.route})")
            for r in obj.reasons:
                print(f"     • {r}")
            print("\n--- Vendor email ---\n" + obj.vendor_email)
    if sc.get("resubmission_of"):
        old, _ = run_all(scenarios[sc["resubmission_of"]]["submission"], master, registry, TODAY)
        new, _ = run_all(sc["submission"], master, registry, TODAY)
        print("\n--- What changed since the first submission ---")
        for d in diff_runs(old, new):
            print(f"     {d['check']}: {d['before']} → {d['after']}  ({d['now']})")
