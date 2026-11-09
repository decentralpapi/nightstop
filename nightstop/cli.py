"""CLI: python3 run.py stay|ride|night ... [--json] [--html out.html]"""
import argparse
import json
import sys

from . import engine
from .render import html_report, markdown
from .sources import SourceError


def main(argv=None):
    p = argparse.ArgumentParser(prog="nightstop", description="Last-minute ride + room finder (OpenStreetMap + OSRM). Never books or pays.")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("stay", help="find places to sleep near a location")
    s.add_argument("location")
    r = sp.add_parser("ride", help="route + Uber/Lyft/maps links from pickup to dropoff")
    r.add_argument("pickup")
    r.add_argument("dropoff")
    n = sp.add_parser("night", help="stranded mode: stays near you ranked by driving time")
    n.add_argument("origin")
    n.add_argument("--area", help="optional area to sleep in")
    for q in (s, n):
        q.add_argument("--radius-km", type=float)
        q.add_argument("--type", dest="stay_type")
        q.add_argument("--check-in")
        q.add_argument("--check-out")
        q.add_argument("--limit", type=int)
    for q in (s, r, n):
        q.add_argument("--json", metavar="FILE", help="write raw JSON result")
        q.add_argument("--html", metavar="FILE", help="write the light HTML report")
        q.add_argument("--view", choices=["full", "list", "detail"], default="full", help="HTML layout")
    a = p.parse_args(argv)
    common = {k: getattr(a, k, None) for k in ("radius_km", "stay_type", "check_in", "check_out", "limit")}
    try:
        if a.cmd == "stay":
            data = engine.find_stay(a.location, **common)
        elif a.cmd == "ride":
            data = engine.find_ride(a.pickup, a.dropoff)
        else:
            data = engine.plan_night(a.origin, area=a.area, **common)
    except (ValueError, SourceError) as e:
        print("Error: %s" % e, file=sys.stderr)
        return 2
    print(markdown(data))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    if a.html:
        with open(a.html, "w", encoding="utf-8") as f:
            f.write(html_report(data, a.view))
        print("\nHTML report: %s" % a.html)
    return 0
