"""Real keyless run against the public APIs; writes live/*.json|html|md. Run: python3 scripts/live_smoke.py"""
import json
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nightstop import engine  # noqa: E402
from nightstop.render import html_report, markdown  # noqa: E402

LIVE = ROOT / "live"
LIVE.mkdir(exist_ok=True)
JOBS = [
    ("berlin-night", engine.plan_night, ("Berlin Hauptbahnhof",), {}),
    ("berlin-stay", engine.find_stay, ("Berlin Hauptbahnhof",), {"check_in": "2026-11-10", "check_out": "2026-11-11"}),
    ("berlin-ride", engine.find_ride, ("Berlin Hauptbahnhof", "Berlin Brandenburg Airport"), {}),
    ("lisbon-night", engine.plan_night, ("Lisbon airport",), {}),
    ("lagos-night", engine.plan_night, ("Murtala Muhammed Airport",), {}),
]
only = set(sys.argv[1:])
summary = json.loads((LIVE / "summary.json").read_text()) if only and (LIVE / "summary.json").exists() else {}
for name, fn, args, kw in JOBS:
    if only and name not in only:
        continue
    t = time.monotonic()
    try:
        d = fn(*args, **kw)
        (LIVE / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2))
        (LIVE / f"{name}.md").write_text(markdown(d))
        (LIVE / f"{name}.html").write_text(html_report(d))
        summary[name] = {"ok": True, "seconds": round(time.monotonic() - t, 1), "stays": len(d.get("stays", [])),
                         "found_total": d.get("found_total"), "warnings": d.get("warnings")}
    except Exception as e:  # record failure honestly
        summary[name] = {"ok": False, "seconds": round(time.monotonic() - t, 1), "error": f"{type(e).__name__}: {e}"}
        traceback.print_exc()
    print(name, summary[name], flush=True)
    time.sleep(2)  # be polite to shared public servers
(LIVE / "summary.json").write_text(json.dumps(summary, indent=2))
