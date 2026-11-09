"""Keyless public data adapters (stdlib urllib) plus deep-link builders.

Contacted hosts (all disclosed in plugin.yaml):
  nominatim.openstreetmap.org   geocoding (max 1 request/second)
  overpass-api.de               nearby lodging from OpenStreetMap
  overpass.kumi.systems         Overpass fallback mirror
  router.project-osrm.org       driving distance/duration (OSRM demo)
  routing.openstreetmap.de      walking distance/duration (FOSSGIS OSRM foot)

Deep links (Uber, Lyft, Google Maps, Booking.com, Airbnb, OpenStreetMap) are
built as strings and returned. They are never fetched by this plugin.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "0.1.1"
USER_AGENT = f"Nightstop/{VERSION} (Hermes plugin; https://hermes-agent.nousresearch.com)"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
OSRM_DRIVE = "https://router.project-osrm.org"
OSRM_FOOT = "https://routing.openstreetmap.de/routed-foot"
ALLOWED_HOSTS = {
    "nominatim.openstreetmap.org", "overpass-api.de", "overpass.kumi.systems",
    "router.project-osrm.org", "routing.openstreetmap.de",
}

STAY_TYPES = ("hotel", "hostel", "guest_house", "motel", "apartment", "chalet")
TYPE_LABEL = {"hotel": "Hotel", "hostel": "Hostel", "guest_house": "Guest house", "motel": "Motel",
              "apartment": "Apartment", "chalet": "Chalet"}
RETRY_SLEEP = 4  # seconds before retrying an overloaded Overpass
PRICE_NOTE = "Price on Booking / Airbnb — OpenStreetMap has no nightly rates"


class SourceError(Exception):
    """A public source failed or returned something unusable."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceError("Redirect refused")


_NOMINATIM_LOCK = threading.Lock()
_NOMINATIM_LAST = [0.0]


class Client:
    """Bounded HTTP client. Records every request in ``evidence``."""

    def __init__(self, timeout: float = 30, budget: float = 200):
        self.timeout = timeout
        self.deadline = time.monotonic() + budget
        self.evidence: list[dict] = []
        self.opener = urllib.request.build_opener(NoRedirect)

    def get_json(self, url: str, *, data: dict | None = None, source: str, what: str, timeout: float | None = None):
        p = urllib.parse.urlsplit(url)
        if p.scheme != "https" or p.hostname not in ALLOWED_HOSTS or p.username or p.password:
            raise SourceError("Host not allowlisted: %s" % p.hostname)
        remaining = self.deadline - time.monotonic()
        if remaining <= 1:
            raise SourceError("Time budget exhausted before contacting %s" % p.hostname)
        if p.hostname == "nominatim.openstreetmap.org":
            with _NOMINATIM_LOCK:  # usage policy: max 1 request per second
                wait = 1.05 - (time.monotonic() - _NOMINATIM_LAST[0])
                if wait > 0:
                    time.sleep(wait)
                _NOMINATIM_LAST[0] = time.monotonic()
        ev = {"source": source, "host": p.hostname, "url": url if data is None else url, "what": what}
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=min(timeout or self.timeout, remaining)) as r:
                raw = r.read(8_000_001)
            if len(raw) > 8_000_000:
                raise SourceError("Response over 8 MB from %s" % p.hostname)
            out = json.loads(raw)
            ev["ok"] = True
            return out
        except urllib.error.HTTPError as e:
            ev.update(ok=False, error="HTTP %s" % e.code)
            raise SourceError("%s returned HTTP %s" % (p.hostname, e.code)) from None
        except SourceError as e:
            ev.update(ok=False, error=str(e))
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            ev.update(ok=False, error="network: %s" % type(reason).__name__)
            raise SourceError("%s unreachable (%s)" % (p.hostname, type(reason).__name__)) from None
        except ValueError:
            ev.update(ok=False, error="invalid JSON")
            raise SourceError("%s returned invalid JSON" % p.hostname) from None
        finally:
            self.evidence.append(ev)


# ---------------------------------------------------------------- geocoding
_LATLNG = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def parse_latlng(text):
    """Return (lat, lng) for 'lat,lng' strings, else None."""
    if not isinstance(text, str):
        return None
    m = _LATLNG.match(text)
    if not m:
        return None
    lat, lng = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("Coordinates out of range: %s" % text.strip())
    return lat, lng


def parse_nominatim(results, query):
    if not isinstance(results, list) or not results:
        raise SourceError("Nominatim found no place for %r" % query)
    top = results[0]
    try:
        lat, lng = float(top["lat"]), float(top["lon"])
    except (KeyError, TypeError, ValueError):
        raise SourceError("Nominatim result missing coordinates") from None
    name = top.get("name") or (top.get("display_name") or query).split(",")[0]
    addr = top.get("address") or {}
    city = next((addr[k] for k in ("city", "town", "village", "municipality", "county", "state") if addr.get(k)), None)
    return {"lat": lat, "lng": lng, "label": name, "display_name": top.get("display_name") or name, "city": city,
            "source": "nominatim", "osm": "%s/%s" % (top.get("osm_type"), top.get("osm_id"))}


_GEOCODE_FILLER = re.compile(
    r"\b(international|intl\.?|airport|aeroporto|aeropuerto|a[eé]roport|"
    r"terminal\s*\d*|arrivals?|departures?|the|near|around|just\s+landed\s+at)\b",
    re.I,
)


def geocode_queries(text):
    """Yield the original query, then progressively simpler Nominatim variants."""
    seen, out = set(), []
    def add(q):
        q = re.sub(r"\s+", " ", (q or "").strip(" ,.-"))
        key = q.lower()
        if q and len(q) >= 2 and key not in seen:
            seen.add(key)
            out.append(q)
    add(text)
    simplified = _GEOCODE_FILLER.sub(" ", text)
    add(simplified)
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if parts:
        add(parts[0])
        add(_GEOCODE_FILLER.sub(" ", parts[0]))
        if len(parts) >= 2:
            add(parts[-1])
            add("%s, %s" % (parts[0], parts[-1]))
            add("%s, %s" % (_GEOCODE_FILLER.sub(" ", parts[0]).strip(" ,.-") or parts[0], parts[-1]))
    # Drop trailing country/region noise when still long
    tokens = text.split()
    if len(tokens) > 2:
        add(" ".join(tokens[:2]))
        add(tokens[0])
    return out


def resolve(client, text, role="location"):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("%s is required (address, place name or 'lat,lng')" % role)
    text = text.strip()
    if len(text) > 200:
        raise ValueError("%s is too long" % role)
    ll = parse_latlng(text)
    if ll:
        return {"lat": ll[0], "lng": ll[1], "label": "%.5f, %.5f" % ll, "display_name": text,
                "source": "coordinates (user supplied)"}
    tried, last = [], None
    for q in geocode_queries(text):
        tried.append(q)
        url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1, "addressdetails": 1})
        try:
            place = parse_nominatim(
                client.get_json(url, source="Nominatim (OpenStreetMap)",
                                what="geocode %s: %s" % (role, q), timeout=20),
                q,
            )
            if q != text:
                place["query_simplified_from"] = text
                place["query_used"] = q
            return place
        except SourceError as e:
            last = e
            continue
    raise SourceError(
        "Nominatim found no place for %r (tried: %s)%s"
        % (text, ", ".join(repr(t) for t in tried), ("; last: %s" % last) if last else "")
    )


# ---------------------------------------------------------------- lodging
def overpass_query(lat, lng, radius_m):
    r = int(radius_m)
    types = "|".join(STAY_TYPES)
    return ("[out:json][timeout:25][maxsize:33554432];("  # small declared budget = admitted sooner on a busy server
            f'nwr(around:{r},{lat:.6f},{lng:.6f})["tourism"~"^({types})$"];'
            f'nwr(around:{r},{lat:.6f},{lng:.6f})["amenity"="hotel"];'
            ");out tags center 200;")


_BAD_STATE = ("disused", "abandoned", "demolished", "razed", "construction", "proposed")


def normalize_element(el):
    """OSM element -> stay dict, or None if it is not a bookable stay."""
    if not isinstance(el, dict):
        return None
    tags = el.get("tags") or {}
    kind = tags.get("tourism")
    if kind not in STAY_TYPES:
        kind = "hotel" if tags.get("amenity") == "hotel" else None
    if not kind:  # e.g. building=apartments alone = residential block, not a stay
        return None
    if any(tags.get(k) in ("yes",) for k in _BAD_STATE) or tags.get("opening_hours") == "closed":
        return None
    name = (tags.get("name") or tags.get("name:en") or "").strip()
    if not name:
        return None
    lat = el.get("lat", (el.get("center") or {}).get("lat"))
    lng = el.get("lon", (el.get("center") or {}).get("lon"))
    if lat is None or lng is None:
        return None
    addr = " ".join(x for x in [tags.get("addr:street"), tags.get("addr:housenumber")] if x)
    city = " ".join(x for x in [tags.get("addr:postcode"), tags.get("addr:city")] if x)
    stay = {
        "id": "%s/%s" % (el.get("type"), el.get("id")),
        "name": name,
        "type": kind,
        "type_label": TYPE_LABEL[kind],
        "lat": float(lat), "lng": float(lng),
        "address": ", ".join(x for x in [addr, city] if x) or None,
        "city": tags.get("addr:city"),
        "operator": tags.get("operator"),
        "brand": tags.get("brand"),
        "stars": tags.get("stars"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "website": tags.get("website") or tags.get("contact:website") or tags.get("url"),
        "opening_hours": tags.get("opening_hours"),
        "rooms": tags.get("rooms"),
        "beds": tags.get("beds"),
        "wheelchair": tags.get("wheelchair"),
        "internet_access": tags.get("internet_access"),
        "price": None,
        "price_note": PRICE_NOTE,
        "osm_url": "https://www.openstreetmap.org/%s/%s" % (el.get("type"), el.get("id")),
    }
    return stay


def _norm_name(n):
    return re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()


def merge_duplicates(stays, within_m=150):
    """OSM sometimes maps one hotel twice (node + building). Merge entries whose
    normalised name is equal or a prefix of the other and that sit within ~150 m.
    Keeps the entry with more tagged facts. Returns (stays, merged_count)."""
    def facts(s):
        return sum(1 for k in ("address", "phone", "website", "stars", "operator", "brand", "opening_hours") if s.get(k))
    kept, merged = [], 0
    for s in sorted(stays, key=facts, reverse=True):
        n = _norm_name(s["name"])
        dup = next((k for k in kept if haversine_m(k, s) <= within_m and
                    (n == _norm_name(k["name"]) or n.startswith(_norm_name(k["name"]) + " ") or _norm_name(k["name"]).startswith(n + " "))), None)
        if dup:
            merged += 1
            dup.setdefault("also_mapped_as", []).append(s["id"])
        else:
            kept.append(s)
    return kept, merged


def parse_overpass(payload):
    els = (payload or {}).get("elements")
    if not isinstance(els, list):
        raise SourceError("Overpass response had no elements list")
    seen, out, skipped = set(), [], 0
    for el in els:
        key = (el.get("type"), el.get("id")) if isinstance(el, dict) else None
        if key in seen:
            continue
        seen.add(key)
        s = normalize_element(el)
        if s:
            out.append(s)
        else:
            skipped += 1
    out, _merged = merge_duplicates(out)
    return out, skipped


def fetch_lodging(client, lat, lng, radius_m):
    """Primary Overpass instance (one polite retry on overload), then the fallback mirror."""
    q = overpass_query(lat, lng, radius_m)
    errors = []
    attempts = [(OVERPASS[0], 70), (OVERPASS[0], 70), (OVERPASS[1], 45)]
    for i, (url, tmo) in enumerate(attempts):
        if i == 1 and not any(code in (errors[-1] if errors else "") for code in ("429", "502", "503", "504", "Timeout")):
            continue  # only retry the primary when it looked overloaded
        if i == 1:
            time.sleep(RETRY_SLEEP)
        try:
            payload = client.get_json(url, data={"data": q}, source="Overpass (OpenStreetMap)",
                                      what="lodging within %d m of %.5f,%.5f" % (radius_m, lat, lng), timeout=tmo)
            return parse_overpass(payload)
        except SourceError as e:
            errors.append(str(e))
    raise SourceError("All Overpass mirrors failed: " + "; ".join(errors))


# ---------------------------------------------------------------- routing
def _coord(p):
    return "%.6f,%.6f" % (p["lng"], p["lat"])  # OSRM wants lon,lat


def osrm_route(client, a, b, mode="driving"):
    base = OSRM_DRIVE if mode == "driving" else OSRM_FOOT
    url = "%s/route/v1/driving/%s;%s?overview=false" % (base, _coord(a), _coord(b))
    data = client.get_json(url, source="OSRM %s" % mode, what="%s route" % mode, timeout=20)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise SourceError("OSRM %s: no route (%s)" % (mode, data.get("code")))
    r = data["routes"][0]
    return {"distance_m": round(r["distance"]), "duration_s": round(r["duration"]), "source": base}


def osrm_table(client, origin, dests, mode="driving"):
    """List aligned with dests of {distance_m, duration_s} or None (unroutable)."""
    if not dests:
        return []
    base = OSRM_DRIVE if mode == "driving" else OSRM_FOOT
    coords = ";".join(_coord(p) for p in [origin] + list(dests))
    url = "%s/table/v1/driving/%s?sources=0&annotations=duration,distance" % (base, coords)
    data = client.get_json(url, source="OSRM %s" % mode, what="%s times from origin to %d stays" % (mode, len(dests)), timeout=25)
    if data.get("code") != "Ok":
        raise SourceError("OSRM %s table failed (%s)" % (mode, data.get("code")))
    durs = (data.get("durations") or [[]])[0]
    dists = (data.get("distances") or [[]])[0]
    out = []
    for i in range(1, len(dests) + 1):
        d = durs[i] if i < len(durs) else None
        m = dists[i] if i < len(dists) else None
        out.append(None if d is None or m is None else {"duration_s": round(d), "distance_m": round(m)})
    return out


def haversine_m(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)))


# ---------------------------------------------------------------- deep links (returned, never fetched)
def _q(params):
    return urllib.parse.urlencode(params, safe="[]")


def uber_link(a, b):
    return "https://m.uber.com/ul/?" + _q({
        "action": "setPickup",
        "pickup[latitude]": "%.6f" % a["lat"], "pickup[longitude]": "%.6f" % a["lng"], "pickup[nickname]": a.get("label") or "Pickup",
        "dropoff[latitude]": "%.6f" % b["lat"], "dropoff[longitude]": "%.6f" % b["lng"], "dropoff[nickname]": b.get("label") or b.get("name") or "Dropoff",
    })


def lyft_link(a, b):
    return "https://lyft.com/ride?" + _q({
        "id": "lyft",
        "pickup[latitude]": "%.6f" % a["lat"], "pickup[longitude]": "%.6f" % a["lng"],
        "destination[latitude]": "%.6f" % b["lat"], "destination[longitude]": "%.6f" % b["lng"],
    })


def maps_directions(a, b, mode="driving"):
    return "https://www.google.com/maps/dir/?" + _q({"api": 1, "origin": "%.6f,%.6f" % (a["lat"], a["lng"]),
                                                       "destination": "%.6f,%.6f" % (b["lat"], b["lng"]), "travelmode": mode})


def maps_pin(p):
    return "https://www.google.com/maps/search/?" + _q({"api": 1, "query": "%.6f,%.6f" % (p["lat"], p["lng"])})


def booking_link(stay, check_in=None, check_out=None):
    params = {"ss": ", ".join(x for x in [stay["name"], stay.get("city") or stay.get("city_hint")] if x),
              "latitude": "%.6f" % stay["lat"], "longitude": "%.6f" % stay["lng"], "group_adults": 1, "no_rooms": 1}
    if check_in and check_out:
        params.update(checkin=check_in, checkout=check_out)
    return "https://www.booking.com/searchresults.html?" + _q(params)


def airbnb_link(p, check_in=None, check_out=None, span=0.009):
    params = {"search_by_map": "true", "ne_lat": "%.6f" % (p["lat"] + span), "ne_lng": "%.6f" % (p["lng"] + span),
              "sw_lat": "%.6f" % (p["lat"] - span), "sw_lng": "%.6f" % (p["lng"] - span), "adults": 1}
    if p.get("city") or p.get("city_hint"):
        params["query"] = p.get("city") or p.get("city_hint")
    if check_in and check_out:
        params.update(checkin=check_in, checkout=check_out)
    return "https://www.airbnb.com/s/homes?" + _q(params)


def tel_link(phone):
    if not phone:
        return None
    first = phone.split(";")[0].strip()
    digits = re.sub(r"[^\d+]", "", first)
    return "tel:" + digits if len(re.sub(r"\D", "", digits)) >= 6 else None
