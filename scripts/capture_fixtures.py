"""Save small raw responses from the real public APIs as unit-test fixtures (run once)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from nightstop import sources as S  # noqa: E402

out = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures"
c = S.Client()
import urllib.parse  # noqa: E402
nom = c.get_json(S.NOMINATIM + "?" + urllib.parse.urlencode({"q": "Berlin Hauptbahnhof", "format": "jsonv2", "limit": 1}), source="fixture", what="geocode")
(out / "nominatim_berlin_hbf.json").write_text(json.dumps(nom, indent=1, ensure_ascii=False))
center = S.parse_nominatim(nom, "Berlin Hauptbahnhof")
ov = c.get_json(S.OVERPASS[0], data={"data": S.overpass_query(center["lat"], center["lng"], 600)}, source="fixture", what="lodging", timeout=60)
(out / "overpass_berlin_hbf_600m.json").write_text(json.dumps(ov, indent=1, ensure_ascii=False))
stays, _ = S.parse_overpass(ov)
stays = stays[:5]
coords = ";".join(S._coord(p) for p in [center] + stays)
tb = c.get_json(S.OSRM_DRIVE + "/table/v1/driving/" + coords + "?sources=0&annotations=duration,distance", source="fixture", what="table")
tb.pop("sources", None); tb.pop("destinations", None)
(out / "osrm_table_berlin_hbf.json").write_text(json.dumps({"stay_ids": [s["id"] for s in stays], **tb}, indent=1))
rt = c.get_json(S.OSRM_DRIVE + "/route/v1/driving/13.369448,52.525018;13.503000,52.366000?overview=false", source="fixture", what="route")
rt.pop("waypoints", None)
(out / "osrm_route_hbf_ber.json").write_text(json.dumps(rt, indent=1))
print("saved", len(ov.get("elements", [])), "elements;", [s["name"] for s in stays])
