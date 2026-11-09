"""Offline tests. HTTP is mocked with fixtures saved from real public API responses
(tests/fixtures/*.json, captured by scripts/capture_fixtures.py on 9 Nov 2026)."""
import importlib.util
import json
import pathlib
import re
import sys
import unittest
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nightstop import engine, sources as S  # noqa: E402
from nightstop.render import html_report, markdown  # noqa: E402
from nightstop import tools  # noqa: E402

FX = ROOT / "tests" / "fixtures"
NOM = json.loads((FX / "nominatim_berlin_hbf.json").read_text())
OVP = json.loads((FX / "overpass_berlin_hbf_600m.json").read_text())
TABLE = json.loads((FX / "osrm_table_berlin_hbf.json").read_text())
ROUTE = json.loads((FX / "osrm_route_hbf_ber.json").read_text())


def _table_lookup():
    stays, _ = S.parse_overpass(OVP)
    byid = {s["id"]: s for s in stays}
    out = {}
    for i, sid in enumerate(TABLE["stay_ids"], 1):
        s = byid[sid]
        out["%.6f,%.6f" % (s["lng"], s["lat"])] = (TABLE["durations"][0][i], TABLE["distances"][0][i])
    return out


LOOK = _table_lookup()
S.RETRY_SLEEP = 0


class Fake(S.Client):
    """Records evidence like the real client but answers from fixtures."""

    def __init__(self, overpass=None, fail=(), small_first=False):
        super().__init__()
        self.overpass = overpass if overpass is not None else OVP
        self.fail = set(fail)
        self.small_first = small_first
        self.calls = []

    def get_json(self, url, *, data=None, source, what, timeout=None):
        p = urllib.parse.urlsplit(url)
        self.calls.append((p.hostname, p.path, data))
        ev = {"source": source, "host": p.hostname, "url": url, "what": what}
        self.evidence.append(ev)
        if p.hostname in self.fail:
            ev.update(ok=False, error="HTTP 504")
            raise S.SourceError("%s returned HTTP 504" % p.hostname)
        ev["ok"] = True
        if p.hostname in ("ipinfo.io", "ipapi.co"):
            if p.hostname == "ipinfo.io":
                return {"ip": "203.0.113.9", "city": "Lagos", "region": "Lagos", "country": "NG",
                        "loc": "6.4541,3.3947"}
            return {"ip": "203.0.113.9", "city": "Lagos", "region": "Lagos", "country_name": "Nigeria",
                    "latitude": 6.4541, "longitude": 3.3947}
        if p.hostname == "nominatim.openstreetmap.org":
            qs = urllib.parse.parse_qs(p.query)
            q = (qs.get("q") or [""])[0]
            ql = q.lower()
            # Structured search without q
            if not q and (qs.get("city") or qs.get("amenity")):
                amenity = (qs.get("amenity") or [""])[0].lower()
                city = (qs.get("city") or [""])[0].lower()
                if "murtala" in amenity or "lagos" in city:
                    return [{"lat": "6.577369", "lon": "3.321156", "name": "Murtala Muhammed International Airport",
                             "display_name": "Murtala Muhammed International Airport, Lagos",
                             "class": "aeroway", "type": "aerodrome", "osm_type": "way", "osm_id": 1,
                             "address": {"city": "Lagos"}, "importance": 0.7}]
                return []
            if "nowhere" in ql or ql == "xyz":
                return []
            # Road trap: "murtala muhammed" without airport → Ikoyi drive (the bug we fix)
            if "murtala" in ql and "airport" not in ql and "international" not in ql:
                return [{"lat": "6.4513703", "lon": "3.4221735", "name": "Murtala Muhammed Drive",
                         "display_name": "Murtala Muhammed Drive, Ikoyi, Lagos",
                         "class": "highway", "type": "secondary", "osm_type": "way", "osm_id": 99,
                         "address": {"suburb": "Ikoyi", "city": "Lagos"}, "importance": 0.4}]
            if "murtala" in ql and ("airport" in ql or "international" in ql):
                return [
                    {"lat": "6.4513703", "lon": "3.4221735", "name": "Murtala Muhammed Drive",
                     "display_name": "Murtala Muhammed Drive, Ikoyi, Lagos",
                     "class": "highway", "type": "secondary", "osm_type": "way", "osm_id": 99,
                     "address": {"suburb": "Ikoyi"}, "importance": 0.5},
                    {"lat": "6.577369", "lon": "3.321156", "name": "Murtala Muhammed International Airport",
                     "display_name": "Murtala Muhammed International Airport, Ikeja, Lagos",
                     "class": "aeroway", "type": "aerodrome", "osm_type": "relation", "osm_id": 2,
                     "address": {"city": "Lagos"}, "importance": 0.8},
                ]
            if "nnamdi" in ql or "azikiwe" in ql or ("abuja" in ql and "airport" in ql):
                return [{"lat": "9.006645", "lon": "7.263172", "name": "Nnamdi Azikiwe International Airport",
                         "display_name": "Nnamdi Azikiwe International Airport, Abuja",
                         "class": "aeroway", "type": "aerodrome", "osm_type": "way", "osm_id": 3,
                         "address": {"city": "Abuja"}, "importance": 0.8}]
            if "lekki" in ql:
                return [
                    {"lat": "6.4335621", "lon": "3.4491265", "name": "British International School Lagos",
                     "display_name": "British International School Lagos, Lekki Phase 1",
                     "class": "amenity", "type": "school", "osm_type": "way", "osm_id": 4,
                     "address": {"suburb": "Lekki Phase 1", "city": "Lagos"}, "importance": 0.3},
                    {"lat": "6.4474", "lon": "3.4720", "name": "Lekki Phase 1",
                     "display_name": "Lekki Phase 1, Lekki, Lagos, Nigeria",
                     "class": "place", "type": "suburb", "osm_type": "node", "osm_id": 5,
                     "address": {"suburb": "Lekki Phase 1", "city": "Lagos"}, "importance": 0.6},
                ]
            # Simulate a miss on a verbose airport query so resolve() retries a simpler form.
            if "international" in ql and "airport" in ql and "lisbon" in ql:
                return []
            if ql.strip() in {"lisbon", "lisbon airport", "lisbon, portugal"} or ql.startswith("lisbon"):
                alt = json.loads(json.dumps(NOM))
                alt[0]["name"] = "Lisbon"
                alt[0]["display_name"] = "Lisbon, Portugal"
                return alt
            return NOM
        if "overpass" in p.hostname:
            if self.small_first:
                # Thin until the 10 km step so expansion ladder is exercised.
                import re as _re
                m = _re.search(r"around:(\d+)", data["data"])
                rad = int(m.group(1)) if m else 0
                if rad < 10000:
                    return {"elements": self.overpass["elements"][:1]}

            return self.overpass
        if p.path.startswith("/table") or "/table/" in p.path:
            coords = p.path.split("/table/v1/driving/")[1].split(";")
            durs, dists = [0], [0]
            for c in coords[1:]:
                d = LOOK.get(c)
                durs.append(d[0] if d else None)
                dists.append(d[1] if d else None)
            return {"code": "Ok", "durations": [durs], "distances": [dists]}
        if "/route/" in p.path:
            return ROUTE
        raise AssertionError("unexpected URL " + url)


class Parsing(unittest.TestCase):
    def test_latlng(self):
        self.assertEqual(S.parse_latlng("52.52, 13.37"), (52.52, 13.37))
        self.assertIsNone(S.parse_latlng("Berlin Hbf"))
        with self.assertRaises(ValueError):
            S.parse_latlng("95.0,13.0")

    def test_nominatim_fixture(self):
        g = S.parse_nominatim(NOM, "Berlin Hauptbahnhof")
        self.assertEqual(g["label"], "Berlin Hauptbahnhof")
        self.assertAlmostEqual(g["lat"], 52.525, places=2)
        with self.assertRaises(S.SourceError):
            S.parse_nominatim([], "x")

    def test_overpass_query_shape(self):
        q = S.overpass_query(52.5, 13.4, 3000)
        self.assertIn('"tourism"~"^(hotel|hostel|guest_house|motel|apartment|chalet)$"', q)
        self.assertIn('"amenity"="hotel"', q)
        self.assertIn("out tags center", q)
        self.assertNotIn("building", q)

    def test_rejects_residential_apartment_blocks(self):
        self.assertIsNone(S.normalize_element({"type": "way", "id": 1, "center": {"lat": 1, "lon": 2}, "tags": {"building": "apartments", "name": "Block A"}}))
        ok = S.normalize_element({"type": "node", "id": 2, "lat": 1, "lon": 2, "tags": {"tourism": "apartment", "name": "Flat 9"}})
        self.assertEqual(ok["type"], "apartment")

    def test_rejects_unnamed_disused(self):
        self.assertIsNone(S.normalize_element({"type": "node", "id": 3, "lat": 1, "lon": 2, "tags": {"tourism": "hotel"}}))
        self.assertIsNone(S.normalize_element({"type": "node", "id": 4, "lat": 1, "lon": 2, "tags": {"tourism": "hotel", "name": "Old", "disused": "yes"}}))
        self.assertEqual(S.normalize_element({"type": "way", "id": 5, "center": {"lat": 1, "lon": 2}, "tags": {"amenity": "hotel", "name": "X"}})["type"], "hotel")

    def test_fixture_parse_and_dedup(self):
        dup = {"elements": OVP["elements"] + OVP["elements"][:2]}
        stays, _ = S.parse_overpass(dup)
        ids = [s["id"] for s in stays]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(s["name"] for s in stays))
        self.assertIn("Motel One Berlin-Hauptbahnhof", [s["name"] for s in stays])

    def test_no_invented_price_or_facts(self):
        stays, _ = S.parse_overpass(OVP)
        for s in stays:
            self.assertIsNone(s["price"])
            self.assertIn("no nightly rates", s["price_note"])
            el = next(e for e in OVP["elements"] if "%s/%s" % (e["type"], e["id"]) == s["id"])
            if "stars" not in el["tags"]:
                self.assertIsNone(s["stars"])
            if "phone" not in el["tags"] and "contact:phone" not in el["tags"]:
                self.assertIsNone(s["phone"])


class Dedup(unittest.TestCase):
    def test_merges_same_hotel_mapped_twice(self):
        els = [{"type": "node", "id": 1, "lat": 38.7858, "lon": -9.1200, "tags": {"tourism": "hotel", "name": "Holiday Inn Express", "brand": "Holiday Inn Express"}},
               {"type": "way", "id": 2, "center": {"lat": 38.7859, "lon": -9.1202}, "tags": {"tourism": "hotel", "name": "Holiday Inn Express Lisbon Airport", "addr:street": "Rua X", "phone": "+351 1", "website": "https://x"}},
               {"type": "node", "id": 3, "lat": 38.80, "lon": -9.10, "tags": {"tourism": "hotel", "name": "Holiday Inn Express"}}]
        stays, _ = S.parse_overpass({"elements": els})
        self.assertEqual(len(stays), 2)  # far-away namesake kept
        main = next(s for s in stays if s["id"] == "way/2")
        self.assertEqual(main["also_mapped_as"], ["node/1"])


class Links(unittest.TestCase):
    A = {"lat": 52.525, "lng": 13.369, "label": "Berlin Hbf"}
    B = {"lat": 52.366, "lng": 13.503, "name": "BER", "city": "Berlin"}

    def q(self, url):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)

    def test_uber(self):
        u = S.uber_link(self.A, self.B)
        self.assertTrue(u.startswith("https://m.uber.com/ul/?"))
        q = self.q(u)
        self.assertEqual(q["action"], ["setPickup"])
        self.assertEqual(q["pickup[latitude]"], ["52.525000"])
        self.assertEqual(q["dropoff[longitude]"], ["13.503000"])
        self.assertEqual(q["dropoff[nickname]"], ["BER"])

    def test_lyft_maps(self):
        q = self.q(S.lyft_link(self.A, self.B))
        self.assertEqual(q["id"], ["lyft"])
        self.assertEqual(q["destination[latitude]"], ["52.366000"])
        m = S.maps_directions(self.A, self.B)
        self.assertTrue(m.startswith("https://www.google.com/maps/dir/?"))
        self.assertEqual(self.q(m)["travelmode"], ["driving"])
        self.assertEqual(self.q(m)["origin"], ["52.525000,13.369000"])

    def test_booking_airbnb(self):
        q = self.q(S.booking_link(self.B))
        self.assertEqual(q["ss"], ["BER, Berlin"])
        self.assertNotIn("checkin", q)
        q = self.q(S.booking_link(self.B, "2026-11-10", "2026-11-11"))
        self.assertEqual(q["checkin"], ["2026-11-10"])
        a = S.airbnb_link(self.B, "2026-11-10", "2026-11-11")
        self.assertTrue(a.startswith("https://www.airbnb.com/s/homes?"))
        self.assertEqual(self.q(a)["checkout"], ["2026-11-11"])
        self.assertGreater(float(self.q(a)["ne_lat"][0]), 52.366)

    def test_tel(self):
        self.assertEqual(S.tel_link("+49 30 36410050"), "tel:+493036410050")
        self.assertIsNone(S.tel_link(None))
        self.assertIsNone(S.tel_link("n/a"))


class Engine(unittest.TestCase):
    def test_find_stay_ranked_by_osrm(self):
        d = engine.find_stay("Berlin Hauptbahnhof", client=Fake())
        routed = [s for s in d["stays"] if s["drive"]]
        self.assertGreaterEqual(len(routed), 3)
        durs = [s["drive"]["duration_s"] for s in routed]
        self.assertEqual(durs, sorted(durs))
        self.assertEqual(d["stays"][:len(routed)], routed)  # routed before unrouted
        for s in routed:  # every routed number is an OSRM fixture number
            self.assertIn((s["drive"]["duration_s"], s["drive"]["distance_m"]),
                          {(round(a), round(b)) for a, b in LOOK.values()})
        self.assertTrue(all(e.get("ok") for e in d["evidence"]))
        self.assertEqual({e["host"] for e in d["evidence"]} - S.ALLOWED_HOSTS, set())

    def test_no_currency_amounts_anywhere(self):
        d = engine.plan_night("Berlin Hauptbahnhof", client=Fake())
        text = markdown(d) + html_report(d)
        self.assertIsNone(re.search(r"[$€£]\s?\d|\d\s?(EUR|USD|GBP)\b", text))
        self.assertNotIn("review", text.lower())

    def test_expands_radius_once_and_says_so(self):
        d = engine.find_stay("Berlin Hauptbahnhof", client=Fake(small_first=True))
        self.assertEqual(d["radius_km"], 10.0)
        self.assertTrue(any("expanded" in w for w in d["warnings"]))
        self.assertGreaterEqual(len(d["stays"]), 3)

    def test_stay_type_filter(self):
        d = engine.find_stay("52.525,13.3694", stay_type="hostel", client=Fake())
        self.assertTrue(d["stays"])
        self.assertTrue(all(s["type"] == "hostel" for s in d["stays"]))
        self.assertEqual(d["center"]["source"], "coordinates (user supplied)")

    def test_plan_night_links(self):
        d = engine.plan_night("Berlin Hauptbahnhof", check_in="2026-11-10", check_out="2026-11-11", client=Fake())
        self.assertEqual(d["top_pick"]["id"], d["stays"][0]["id"])
        for s in d["stays"]:
            for k in ("open_uber", "open_lyft", "directions", "check_booking", "check_airbnb"):
                self.assertIn(k, s["links"])
            self.assertIn("checkin=2026-11-10", s["links"]["check_booking"])
        self.assertTrue(any("do" in w and "vacancy" in w for w in d["warnings"]))
        self.assertIn("cannot complete a paid checkout", d["honesty"])

    def test_osrm_down_keeps_stays_without_inventing_times(self):
        d = engine.plan_night("Berlin Hauptbahnhof", client=Fake(fail={"router.project-osrm.org", "routing.openstreetmap.de"}))
        self.assertTrue(d["stays"])
        self.assertTrue(all(s["drive"] is None and s["walk"] is None for s in d["stays"]))
        self.assertTrue(any("Driving times unavailable" in w for w in d["warnings"]))
        self.assertIn("driving time unavailable", markdown(d).lower())

    def test_overpass_fallback_mirror(self):
        c = Fake(fail={"overpass-api.de"})
        d = engine.find_stay("Berlin Hauptbahnhof", client=c)
        self.assertTrue(d["stays"])
        hosts = [h for h, _, _ in c.calls]
        self.assertIn("overpass.kumi.systems", hosts)

    def test_all_overpass_down_returns_partial(self):
        d = engine.find_stay("Berlin Hauptbahnhof", client=Fake(fail={"overpass-api.de", "overpass.kumi.systems"}))
        self.assertEqual(d["stays"], [])
        self.assertTrue(any("Lodging search failed" in w for w in d["warnings"]))
        self.assertIn("check_booking", d["area_links"])
        self.assertIn("check_airbnb", d["area_links"])

    def test_find_ride_real_numbers(self):
        d = engine.find_ride("Berlin Hauptbahnhof", "52.366,13.503", client=Fake())
        r = ROUTE["routes"][0]
        self.assertEqual(d["drive"], {"distance_m": round(r["distance"]), "duration_s": round(r["duration"]), "source": "https://router.project-osrm.org"})
        self.assertIsNone(d["walk"])  # too far to walk
        self.assertIn("m.uber.com", d["links"]["open_uber"])

    def test_ride_route_failure_returns_partial_with_links(self):
        d = engine.find_ride("Berlin Hauptbahnhof", "52.366,13.503", client=Fake(fail={"router.project-osrm.org", "routing.openstreetmap.de"}))
        self.assertIsNone(d["drive"])
        self.assertIsNone(d["walk"])
        self.assertIn("m.uber.com", d["links"]["open_uber"])
        self.assertTrue(any("No driving or walking route" in w for w in d["warnings"]))

    def test_validation(self):
        for kw in ({"check_in": "2026-11-10"}, {"check_in": "2026-11-10", "check_out": "2026-11-09"},
                   {"check_in": "tomorrow", "check_out": "2026-11-12"}, {"radius_km": 100}, {"stay_type": "castle"}):
            with self.assertRaises(ValueError):
                engine.find_stay("Berlin", client=Fake(), **kw)

    def test_geocode_miss(self):
        with self.assertRaises(S.SourceError):
            engine.find_stay("Nowhere-xyz", client=Fake())


class ToolsAndPlugin(unittest.TestCase):
    def test_handlers_return_json_errors(self):
        out = json.loads(tools.find_stay({"location": ""}))
        self.assertIn("error", out)
        self.assertIsNone(out["data"])
        out = json.loads(tools.find_ride("not a dict"))
        self.assertIn("error", out)
        out = json.loads(tools.find_ride({"pickup": "", "dropoff": "x"}))
        self.assertIn("Missing required: pickup", out["error"])
        out = json.loads(tools.plan_night({}))
        self.assertIn("Missing required: origin", out["error"])

    def test_handler_success_uses_engine(self):
        orig = S.Client
        S.Client = Fake
        try:
            out = json.loads(tools.plan_night({"origin": "Berlin Hauptbahnhof", "stay_type": "any", "unknown": 1}))
        finally:
            S.Client = orig
        self.assertIn("formatted_output", out)
        self.assertIn("reply_markdown", out)
        self.assertEqual(out["reply_markdown"], out["formatted_output"])
        self.assertIn("presentation_hint", out)
        self.assertIn("Never paste raw URLs", out["presentation_hint"])
        self.assertEqual(out["data"]["kind"], "night")
        md = out["reply_markdown"]
        for label in ("[Book on Booking.com](", "[Get an Uber](", "[Lyft](", "[Directions](", "[Airbnb nearby]("):
            self.assertIn(label, md)
        # Must not instruct the model via raw URL dumps as the only form — short labels present
        self.assertIn("cannot complete a paid checkout", md.lower())

    def test_register(self):
        spec = importlib.util.spec_from_file_location("nightstop_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["nightstop_plugin"] = mod
        spec.loader.exec_module(mod)

        class Ctx:
            def __init__(self):
                self.tools = []

            def register_tool(self, **kw):
                self.tools.append(kw)
        ctx = Ctx()
        mod.register(ctx)
        self.assertEqual([t["name"] for t in ctx.tools], ["find_stay", "find_ride", "plan_night"])
        self.assertTrue(all(t["toolset"] == "nightstop" and callable(t["handler"]) for t in ctx.tools))
        for t in ctx.tools:
            self.assertEqual(t["schema"]["name"], t["name"])

    def test_manifest_discloses_hosts(self):
        y = (ROOT / "plugin.yaml").read_text()
        for h in sorted(S.ALLOWED_HOSTS):
            self.assertIn(h, y)
        for t in ("find_stay", "find_ride", "plan_night"):
            self.assertIn("  - " + t, y)
        self.assertNotIn("requires_hermes", y)

    def test_desktop_surface(self):
        js = (ROOT / "desktop" / "plugin.js").read_text()
        imports = set(re.findall(r"^import .* from '([^']+)'", js, re.M))
        self.assertEqual(imports, {"@hermes/plugin-sdk", "react"})
        for bad in ("eval(", "new Function", "import(", "localStorage", "document.querySelector", "innerHTML"):
            self.assertNotIn(bad, js)
        for bad in ("'Send'", "'Swap'", "'Approve'", "Connect wallet", "Add to cart"):
            self.assertNotIn(bad, js)
        self.assertIn("id: 'nightstop'", js)
        self.assertIn("path: '/nightstop'", js)

    def test_html_static_no_remote_assets(self):
        d = engine.plan_night("Berlin Hauptbahnhof", client=Fake())
        page = html_report(d)
        self.assertNotRegex(page, r"<(script|img|link|iframe)\b")
        self.assertIn("© OpenStreetMap contributors", page)
        for label in ("Get a ride", "See rooms", "Open Lyft", "Open maps", "Check Airbnb"):
            self.assertIn(label, page)

    def test_client_allowlist(self):
        with self.assertRaises(S.SourceError):
            S.Client().get_json("https://www.booking.com/x", source="t", what="t")


class MarkdownAndRobustness(unittest.TestCase):
    def test_geocode_queries_keep_airport_words(self):
        qs = S.geocode_queries("Lisbon International Airport", keep_airport_words=True)
        self.assertEqual(qs[0], "Lisbon International Airport")
        self.assertTrue(any("airport" in q.lower() for q in qs))
        # Soft strip without keep_airport_words may drop airport for non-airport path
        soft = S.geocode_queries("Alfama, Lisbon", keep_airport_words=False)
        self.assertEqual(soft[0], "Alfama, Lisbon")

    def test_geocode_retry_on_verbose_airport(self):
        # Alias table maps Lisbon airport → LIS bundled coords (robust path).
        place = S.resolve(Fake(), "Lisbon International Airport", "origin")
        self.assertIn("Lisbon", place["label"])
        self.assertEqual(place.get("iata"), "LIS")
        self.assertEqual(place["confidence"], "high")

    def test_reply_markdown_short_labels_on_ride(self):
        d = engine.find_ride("Berlin Hauptbahnhof", "52.366,13.503", client=Fake())
        md = markdown(d)
        self.assertIn("[Get an Uber](", md)
        self.assertIn("[Lyft](", md)
        self.assertIn("[Directions](", md)
        self.assertNotIn("[Open Uber](", md)
        self.assertNotIn("[Check Booking](", md)

    def test_schemas_mention_short_links(self):
        from nightstop import schemas
        for sch in (schemas.FIND_STAY, schemas.FIND_RIDE, schemas.PLAN_NIGHT):
            self.assertIn("reply_markdown", sch["description"])
            self.assertIn("never paste raw urls", sch["description"].lower())
            self.assertIn("[Book on Booking.com]", sch["description"])

    def test_version_bumped(self):
        self.assertEqual(S.VERSION, "0.1.2")
        y = (ROOT / "plugin.yaml").read_text()
        self.assertIn("version: 0.1.2", y)
        self.assertIn("ipinfo.io", y)
        self.assertIn("ipapi.co", y)





class AirportAndLocation(unittest.TestCase):
    def test_murtala_prefers_aerodrome_not_ikoyi_road(self):
        # Even when Nominatim also returns the Ikoyi road, scoring + alias must win.
        place = S.resolve(Fake(), "murtala muhammed airport", "dropoff")
        # Alias table short-circuits to LOS — never the Ikoyi road.
        self.assertEqual(place.get("iata"), "LOS")
        self.assertAlmostEqual(place["lat"], 6.577369, places=3)
        self.assertNotIn("Ikoyi", place.get("display_name", ""))
        self.assertIn("Murtala", place["resolved_as"])

    def test_score_rejects_highway_when_airport_wanted(self):
        road = {"class": "highway", "type": "secondary", "name": "Murtala Muhammed Drive", "importance": 0.9}
        aero = {"class": "aeroway", "type": "aerodrome", "name": "Murtala Muhammed International Airport", "importance": 0.5}
        self.assertLess(S.score_nominatim(road, want_airport=True), -500)
        self.assertGreater(S.score_nominatim(aero, want_airport=True), 80)

    def test_abv_alias_and_nominatim(self):
        place = S.resolve(Fake(), "Nnamdi Azikiwe Airport", "location")
        self.assertEqual(place.get("iata"), "ABV")
        self.assertAlmostEqual(place["lat"], 9.006645, places=3)

    def test_lekki_prefers_suburb_over_school(self):
        place = S.resolve(Fake(), "Lekki Phase 1, Lagos", "pickup")
        self.assertEqual(place["label"], "Lekki Phase 1")
        # Bundled place table beats OSM's school/ferry false friends.
        self.assertEqual(place.get("source"), "bundled place table")
        self.assertAlmostEqual(place["lat"], 6.4474, places=3)

    def test_maps_url_and_coords(self):
        self.assertEqual(S.parse_maps_url("https://www.google.com/maps/@6.4474,3.4720,17z"), (6.4474, 3.4720))
        self.assertEqual(S.parse_maps_url("https://maps.google.com/?q=9.006,7.263"), (9.006, 7.263))
        p = S.resolve(Fake(), "6.4474, 3.4720", "pickup")
        self.assertEqual(p["source"], "coordinates (user supplied)")
        p2 = S.resolve(Fake(), "https://www.google.com/maps/place/X/@6.45,3.40,14z", "pickup")
        self.assertEqual(p2["source"], "Google Maps link")

    def test_find_ride_lekki_to_los(self):
        d = engine.find_ride("Lekki Phase 1, Lagos", "Murtala Muhammed Airport", client=Fake())
        self.assertEqual(d["dropoff"].get("iata"), "LOS")
        self.assertIn("Murtala", d["dropoff"]["resolved_as"])
        self.assertIn("m.uber.com", d["links"]["open_uber"])

    def test_current_location_one_shot_not_cached(self):
        # No module-level cache before/after.
        self.assertFalse(hasattr(S, "_LAST_IP_LOCATION"))
        self.assertFalse(hasattr(S, "_IP_CACHE"))
        c1 = Fake()
        a = S.resolve(c1, "my location", "pickup")
        self.assertTrue(a.get("ip_approx"))
        self.assertEqual(a["confidence"], "low")
        self.assertIn("not stored", a.get("location_privacy", "").lower())
        # Evidence must not contain the raw IP string from the fixture.
        blob = json.dumps(c1.evidence)
        self.assertNotIn("203.0.113.9", blob)
        # Second call with a fresh client is independent (no reuse).
        c2 = Fake()
        b = S.resolve(c2, "here", "origin")
        self.assertTrue(b.get("ip_approx"))
        self.assertIsNot(a, b)
        self.assertFalse(hasattr(S, "_LAST_IP_LOCATION"))
        # Engine surfaces location_privacy and does not persist anywhere.
        d = engine.find_ride(pickup="my location", dropoff="52.366,13.503", client=Fake())
        self.assertIn("location_privacy", d)
        self.assertIn("Used once", d["location_privacy"])
        self.assertTrue(any("approximate" in w.lower() or "IP" in w for w in d["warnings"]))
        # Nothing written under plugin paths
        for name in ("plugin_data", "ctx.state", ".nightstop_cache"):
            self.assertFalse((ROOT / name).exists())

    def test_use_current_location_tool_arg(self):
        orig = S.Client
        S.Client = Fake
        try:
            out = json.loads(tools.find_ride({"use_current_location": True, "dropoff": "52.366,13.503"}))
        finally:
            S.Client = orig
        self.assertIn("data", out)
        self.assertTrue(out["data"]["pickup"].get("ip_approx"))
        self.assertIn("location_privacy", out["data"])

    def test_schemas_mention_airports_and_location(self):
        from nightstop import schemas
        self.assertIn("airport", schemas.FIND_RIDE["description"].lower())
        self.assertIn("find_stay", schemas.FIND_RIDE["description"])
        self.assertIn("use_current_location", schemas.FIND_STAY["parameters"]["properties"])
        self.assertIn("my location", schemas.FIND_STAY["parameters"]["properties"]["location"]["description"])



if __name__ == "__main__":
    unittest.main()
