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

VERSION = "0.1.3"
USER_AGENT = f"Nightstop/{VERSION} (Hermes plugin; https://hermes-agent.nousresearch.com)"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
OSRM_DRIVE = "https://router.project-osrm.org"
OSRM_FOOT = "https://routing.openstreetmap.de/routed-foot"
ALLOWED_HOSTS = {
    "nominatim.openstreetmap.org", "overpass-api.de", "overpass.kumi.systems",
    "router.project-osrm.org", "routing.openstreetmap.de",
    "ipinfo.io", "ipapi.co",
}
IPINFO = "https://ipinfo.io/json"
IPAPI = "https://ipapi.co/json/"

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
_MAPS_AT = re.compile(r"@(?:-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)|@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", re.I)
# Google Maps: @lat,lng  or  q=lat,lng  or  !3dlat!4dlng  or  /maps/place/.../@lat,lng
_MAPS_Q = re.compile(r"[?&](?:q|query|ll)=(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", re.I)
_MAPS_BANG = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", re.I)
_MAPS_AT2 = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", re.I)
_HERE = re.compile(
    r"^\s*(my\s+location|here|current\s+location|where\s+i\s+am|use\s+my\s+location|"
    r"use\s+current\s+location|approx(?:imate)?\s+location)\s*$",
    re.I,
)
_AIRPORT_HINT = re.compile(
    r"\b(airport|aeroporto|aeropuerto|a[eé]roport|aerodrome|airfield|"
    r"terminal\s*\d*|arrivals?|departures?|intl\.?|international)\b",
    re.I,
)
_STATION_HINT = re.compile(
    r"\b(station|bahnhof|hauptbahnhof|hbf|gare|railway\s*station|train\s*station|central\s*station)\b",
    re.I,
)
_IATA_TOKEN = re.compile(r"\b([A-Z]{3})\b")
_GEOCODE_FILLER = re.compile(
    r"\b(international|intl\.?|terminal\s*\d*|arrivals?|departures?|the|near|around|"
    r"just\s+landed\s+at|flying\s+to|flying\s+from)\b",
    re.I,
)
# Keep "airport"/"station" in variants when the user asked for one — stripping them
# caused Murtala Muhammed Airport to geocode as Murtala Muhammed Drive (Ikoyi).
_SOFT_FILLER = re.compile(
    r"\b(the|near|around|just\s+landed\s+at|flying\s+to|flying\s+from)\b",
    re.I,
)

# Small bundled table of major airports (IATA → coords). Used when Nominatim is
# ambiguous or returns a road; also matched by name aliases below.
MAJOR_AIRPORTS = {
    "LOS": {"lat": 6.577369, "lng": 3.321156, "label": "Murtala Muhammed International Airport",
            "city": "Lagos", "country": "Nigeria", "iata": "LOS"},
    "ABV": {"lat": 9.006645, "lng": 7.263172, "label": "Nnamdi Azikiwe International Airport",
            "city": "Abuja", "country": "Nigeria", "iata": "ABV"},
    "LIS": {"lat": 38.774167, "lng": -9.134167, "label": "Humberto Delgado Airport (Lisbon)",
            "city": "Lisbon", "country": "Portugal", "iata": "LIS"},
    "BER": {"lat": 52.366667, "lng": 13.503333, "label": "Berlin Brandenburg Airport",
            "city": "Berlin", "country": "Germany", "iata": "BER"},
    "LHR": {"lat": 51.470020, "lng": -0.454295, "label": "London Heathrow Airport",
            "city": "London", "country": "United Kingdom", "iata": "LHR"},
    "JFK": {"lat": 40.641311, "lng": -73.778139, "label": "John F. Kennedy International Airport",
            "city": "New York", "country": "United States", "iata": "JFK"},
    "CDG": {"lat": 49.009722, "lng": 2.547778, "label": "Paris Charles de Gaulle Airport",
            "city": "Paris", "country": "France", "iata": "CDG"},
    "AMS": {"lat": 52.310539, "lng": 4.768274, "label": "Amsterdam Airport Schiphol",
            "city": "Amsterdam", "country": "Netherlands", "iata": "AMS"},
    "DXB": {"lat": 25.253174, "lng": 55.365673, "label": "Dubai International Airport",
            "city": "Dubai", "country": "United Arab Emirates", "iata": "DXB"},
    "NBO": {"lat": -1.319167, "lng": 36.927778, "label": "Jomo Kenyatta International Airport",
            "city": "Nairobi", "country": "Kenya", "iata": "NBO"},
    "ACC": {"lat": 5.605186, "lng": -0.166786, "label": "Kotoka International Airport",
            "city": "Accra", "country": "Ghana", "iata": "ACC"},
    "CPT": {"lat": -33.971489, "lng": 18.602101, "label": "Cape Town International Airport",
            "city": "Cape Town", "country": "South Africa", "iata": "CPT"},
    "JNB": {"lat": -26.139166, "lng": 28.246000, "label": "O. R. Tambo International Airport",
            "city": "Johannesburg", "country": "South Africa", "iata": "JNB"},
}

_AIRPORT_ALIASES = (
    (re.compile(r"\bmurtal+a\b[^,;]{0,25}?\b(?:m[ou]h[ae]mm?[ae]d|airport|intl|international)\b(?!\s*(?:way|drive|road|rd|street|st|avenue|ave|close|crescent)\b)", re.I), "LOS"),
    (re.compile(r"\b(?:mmia|mm2|mm1)\b|\b(?:lagos|ikeja)\s+(?:international\s+)?(?:airport|intl)\b|\blos\s+airport\b", re.I), "LOS"),
    (re.compile(r"\b(nnamdi\s+azikiwe|abuja\s+(?:international\s+)?airport)\b", re.I), "ABV"),
    (re.compile(r"\b(lisbon|lisboa)\s+(?:international\s+)?airport\b|\baeroporto\s+de\s+lisboa\b", re.I), "LIS"),
    (re.compile(r"\b(berlin\s+brandenburg|ber\s+airport|sch[oö]nefeld)\b", re.I), "BER"),
    (re.compile(r"\bheathrow\b", re.I), "LHR"),
    (re.compile(r"\bjfk\b|\bkennedy\s+international\b", re.I), "JFK"),
    (re.compile(r"\b(charles\s+de\s+gaulle|cdg)\b", re.I), "CDG"),
    (re.compile(r"\bschiphol\b", re.I), "AMS"),
    (re.compile(r"\bdubai\s+(?:international\s+)?airport\b", re.I), "DXB"),
    (re.compile(r"\b(jomo\s+kenyatta|nairobi\s+(?:international\s+)?airport)\b", re.I), "NBO"),
    (re.compile(r"\bkotoka\b", re.I), "ACC"),
    (re.compile(r"\bcape\s+town\s+(?:international\s+)?airport\b", re.I), "CPT"),
    (re.compile(r"\b(o\.?\s*r\.?\s*tambo|johannesburg\s+(?:international\s+)?airport)\b", re.I), "JNB"),
)

# Ambiguous neighbourhoods OSM often maps as a school/ferry/shop instead of a place.
KNOWN_PLACES = {
    "lekki phase 1": {
        "lat": 6.4474, "lng": 3.4720,
        "label": "Lekki Phase 1", "city": "Lagos", "country": "Nigeria",
        "display_name": "Lekki Phase 1, Lekki, Lagos, Nigeria",
    },
    "lekki phase 2": {
        "lat": 6.4420, "lng": 3.5250,
        "label": "Lekki Phase 2", "city": "Lagos", "country": "Nigeria",
        "display_name": "Lekki Phase 2, Lekki, Lagos, Nigeria",
    },
    "victoria island": {
        "lat": 6.4281, "lng": 3.4219,
        "label": "Victoria Island", "city": "Lagos", "country": "Nigeria",
        "display_name": "Victoria Island, Lagos, Nigeria",
    },
    "ikeja": {
        "lat": 6.6018, "lng": 3.3515,
        "label": "Ikeja", "city": "Lagos", "country": "Nigeria",
        "display_name": "Ikeja, Lagos, Nigeria",
    },
}

_PLACE_ALIASES = (
    (re.compile(r"\blekki\s+phase\s*(1|one)\b", re.I), "lekki phase 1"),
    (re.compile(r"\blekki\s+phase\s*(2|two)\b", re.I), "lekki phase 2"),
    (re.compile(r"\bvictoria\s+island\b", re.I), "victoria island"),
)


def match_place_alias(text):
    if not isinstance(text, str):
        return None
    for rx, key in _PLACE_ALIASES:
        if rx.search(text):
            return key
    key = re.sub(r"\s+", " ", text.strip().lower())
    key = re.sub(r",\s*(lagos|nigeria|ng)\s*$", "", key).strip()
    if key in KNOWN_PLACES:
        return key
    return None


def _from_place_table(key, *, via):
    a = KNOWN_PLACES[key]
    return _place(
        a["lat"], a["lng"], a["label"],
        display_name=a.get("display_name") or a["label"],
        city=a.get("city"), source="bundled place table",
        resolved_as=a["label"], confidence="medium",
        note="Neighbourhood centroid from Nightstop's place table (OSM had no clear place node).",
        extra={"matched_via": via},
    )


_HIGHWAY_TYPES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "residential", "service",
    "unclassified", "living_street", "road", "track", "path", "footway", "cycleway",
    "pedestrian", "highway",
}
_ROAD_CLASSES = {"highway", "road"}
_AERO_TYPES = {"aerodrome", "airport", "terminal", "airstrip", "helipad"}
_STATION_TYPES = {"station", "halt", "railway", "train_station", "subway_entrance", "tram_stop"}


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


def parse_maps_url(text):
    """Pull lat,lng from a Google Maps (or similar) URL/pin, else None."""
    if not isinstance(text, str) or "http" not in text.lower() and "@" not in text and "!3d" not in text:
        # still try if it looks like a maps path fragment
        if not isinstance(text, str):
            return None
        if not any(x in text for x in ("maps.", "google.com/maps", "!3d", "@")):
            return None
    for rx in (_MAPS_BANG, _MAPS_Q, _MAPS_AT2):
        m = rx.search(text)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
    return None


def is_current_location(text):
    return isinstance(text, str) and bool(_HERE.match(text.strip()))


def _place(lat, lng, label, *, display_name=None, city=None, source=None, osm=None,
           resolved_as=None, confidence="high", note=None, extra=None):
    out = {
        "lat": float(lat), "lng": float(lng),
        "label": label,
        "display_name": display_name or label,
        "city": city,
        "source": source,
        "osm": osm,
        "resolved_as": resolved_as or label,
        "confidence": confidence,
    }
    if note:
        out["note"] = note
    if extra:
        out.update(extra)
    return out


def _from_airport_table(code, *, via):
    a = MAJOR_AIRPORTS[code]
    return _place(
        a["lat"], a["lng"], a["label"],
        display_name="%s (%s), %s, %s" % (a["label"], a["iata"], a["city"], a["country"]),
        city=a["city"], source="bundled IATA table",
        resolved_as="%s (%s)" % (a["label"], a["iata"]),
        confidence="high",
        extra={"iata": a["iata"], "matched_via": via},
    )


def match_airport_alias(text):
    if not isinstance(text, str):
        return None
    for rx, code in _AIRPORT_ALIASES:
        if rx.search(text):
            return code
    # bare IATA when the query looks airport-ish or is just 3 letters
    tokens = _IATA_TOKEN.findall(text.upper())
    for t in tokens:
        if t in MAJOR_AIRPORTS and (_AIRPORT_HINT.search(text) or text.strip().upper() == t):
            return t
    if text.strip().upper() in MAJOR_AIRPORTS and len(text.strip()) == 3:
        return text.strip().upper()
    return None


def parse_nominatim_result(top, query, *, resolved_as=None, confidence="high", note=None):
    try:
        lat, lng = float(top["lat"]), float(top["lon"])
    except (KeyError, TypeError, ValueError):
        raise SourceError("Nominatim result missing coordinates") from None
    name = top.get("name") or (top.get("display_name") or query).split(",")[0]
    addr = top.get("address") or {}
    city = next((addr[k] for k in ("city", "town", "village", "municipality", "suburb",
                                   "neighbourhood", "county", "state") if addr.get(k)), None)
    cls = top.get("class") or top.get("category")
    typ = top.get("type")
    return _place(
        lat, lng, name,
        display_name=top.get("display_name") or name,
        city=city,
        source="nominatim",
        osm="%s/%s" % (top.get("osm_type"), top.get("osm_id")),
        resolved_as=resolved_as or name,
        confidence=confidence,
        note=note,
        extra={
            "nominatim_class": cls,
            "nominatim_type": typ,
            "addresstype": top.get("addresstype"),
        },
    )


def parse_nominatim(results, query):
    """Back-compat: take the first result (callers that already filtered)."""
    if not isinstance(results, list) or not results:
        raise SourceError("Nominatim found no place for %r" % query)
    return parse_nominatim_result(results[0], query)


def _is_highway(r):
    cls = (r.get("class") or r.get("category") or "").lower()
    typ = (r.get("type") or "").lower()
    return cls in _ROAD_CLASSES or typ in _HIGHWAY_TYPES


def _is_aerodrome(r):
    cls = (r.get("class") or r.get("category") or "").lower()
    typ = (r.get("type") or "").lower()
    name = (r.get("name") or r.get("display_name") or "").lower()
    if cls == "aeroway" and typ in _AERO_TYPES:
        return True
    if typ in ("aerodrome", "airport"):
        return True
    if "airport" in name and cls in ("aeroway", "amenity", "building", "tourism"):
        return True
    if typ == "terminal" and ("airport" in name or cls == "aeroway"):
        return True
    return False


def _is_station(r):
    cls = (r.get("class") or r.get("category") or "").lower()
    typ = (r.get("type") or "").lower()
    if cls in ("railway", "public_transport") and typ in _STATION_TYPES:
        return True
    if typ in ("train_station", "station", "halt"):
        return True
    return False


def _is_place_area(r):
    cls = (r.get("class") or r.get("category") or "").lower()
    typ = (r.get("type") or "").lower()
    return cls == "place" or typ in {
        "suburb", "neighbourhood", "neighborhood", "quarter", "city_block",
        "city", "town", "village", "hamlet", "municipality", "borough", "district",
    }


def score_nominatim(r, *, want_airport=False, want_station=False, query=""):
    """Higher is better. Strongly prefer aerodromes/stations; reject roads when asked for an airport."""
    score = float(r.get("importance") or 0) * 10
    name = (r.get("name") or r.get("display_name") or "").lower()
    q = (query or "").lower()
    if want_airport:
        if _is_highway(r):
            return -1000
        if _is_aerodrome(r):
            score += 100
            if (r.get("class") or "") == "aeroway" and (r.get("type") or "") == "aerodrome":
                score += 40
            if (r.get("type") or "") == "terminal":
                score += 20
        elif "airport" in name or "aeroporto" in name:
            score += 50
        else:
            score -= 30
    if want_station:
        if _is_highway(r) and not _is_station(r):
            return -1000
        if _is_station(r):
            score += 100
    if not want_airport and not want_station:
        if _is_place_area(r):
            score += 25
        if _is_highway(r):
            score -= 15
        # schools / random amenities that steal neighbourhood names
        typ = (r.get("type") or "").lower()
        if typ in ("school", "college", "university", "hospital", "pharmacy", "bank",
                   "ferry_terminal", "bus_station", "fuel", "restaurant", "cafe", "fast_food",
                   "mall", "supermarket", "retail"):
            score -= 40
    # soft name overlap bonus
    for token in re.findall(r"[a-z0-9]{3,}", q):
        if token in name:
            score += 2
    return score


def pick_nominatim(results, query, *, want_airport=False, want_station=False):
    if not isinstance(results, list) or not results:
        return None
    ranked = sorted(
        ((score_nominatim(r, want_airport=want_airport, want_station=want_station, query=query), r) for r in results),
        key=lambda x: x[0], reverse=True,
    )
    best_score, best = ranked[0]
    if best_score <= -500:
        return None
    conf = "high" if best_score >= 80 else ("medium" if best_score >= 20 else "low")
    note = None
    if want_airport and not _is_aerodrome(best) and "airport" not in (best.get("name") or "").lower():
        conf = "low"
        note = "Best Nominatim hit did not look like an aerodrome; treat as uncertain."
    return parse_nominatim_result(
        best, query,
        resolved_as=best.get("name") or (best.get("display_name") or query).split(",")[0],
        confidence=conf, note=note,
    )


def geocode_queries(text, *, keep_airport_words=False):
    """Yield the original query, then progressively simpler Nominatim variants."""
    seen, out = set(), []

    def add(q):
        q = re.sub(r"\s+", " ", (q or "").strip(" ,.-"))
        key = q.lower()
        if q and len(q) >= 2 and key not in seen:
            seen.add(key)
            out.append(q)

    add(text)
    soft = _SOFT_FILLER.sub(" ", text)
    add(soft)
    if keep_airport_words:
        # Prefer forms that KEEP airport/station; also try International variants.
        add(re.sub(r"\s+", " ", soft))
        if _AIRPORT_HINT.search(text) and "international" not in text.lower():
            # "X Airport" -> "X International Airport"
            add(re.sub(r"\bairport\b", "International Airport", text, flags=re.I))
            add(re.sub(r"\bairport\b", "International Airport", soft, flags=re.I))
        # Strip only intl/terminal noise, keep "airport"
        keep = _GEOCODE_FILLER.sub(" ", text)
        # restore airport if filler ate it somehow
        if "airport" in text.lower() and "airport" not in keep.lower():
            keep = keep + " Airport"
        add(keep)
    else:
        simplified = _GEOCODE_FILLER.sub(" ", text)
        # Also strip airport/station words for non-airport queries (old behaviour).
        simplified = re.sub(
            r"\b(airport|aeroporto|aeropuerto|a[eé]roport|terminal\s*\d*)\b", " ", simplified, flags=re.I
        )
        add(simplified)
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if parts:
        add(parts[0])
        if keep_airport_words:
            add(parts[0] if _AIRPORT_HINT.search(parts[0]) else parts[0])
        else:
            add(_GEOCODE_FILLER.sub(" ", parts[0]))
        if len(parts) >= 2:
            add(parts[-1])
            add("%s, %s" % (parts[0], parts[-1]))
            head = parts[0]
            if keep_airport_words and "airport" in text.lower() and "airport" not in head.lower():
                head = head + " Airport"
            add("%s, %s" % (head, parts[-1]))
            if keep_airport_words:
                add("%s International Airport, %s" % (
                    re.sub(r"\b(airport|international)\b", "", parts[0], flags=re.I).strip(" ,.-") or parts[0],
                    parts[-1],
                ))
    tokens = text.split()
    if len(tokens) > 2 and not keep_airport_words:
        add(" ".join(tokens[:2]))
        add(tokens[0])
    return out


def _nominatim_search(client, params, *, what):
    url = NOMINATIM + "?" + urllib.parse.urlencode(params)
    return client.get_json(url, source="Nominatim (OpenStreetMap)", what=what, timeout=20)


def nominatim_lookup(client, query, *, want_airport=False, want_station=False, limit=7,
                     featuretype=None, countrycodes=None, viewbox=None):
    params = {"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1}
    if featuretype:
        params["featuretype"] = featuretype
    if countrycodes:
        params["countrycodes"] = countrycodes
    if viewbox:
        params["viewbox"] = viewbox
        params["bounded"] = 1
    results = _nominatim_search(client, params, what="geocode: %s" % query)
    return pick_nominatim(results, query, want_airport=want_airport, want_station=want_station)


def nominatim_structured(client, *, city=None, country=None, amenity=None, street=None,
                         want_airport=False, want_station=False, limit=5):
    params = {"format": "jsonv2", "limit": limit, "addressdetails": 1}
    if city:
        params["city"] = city
    if country:
        params["country"] = country
    if amenity:
        params["amenity"] = amenity
    if street:
        params["street"] = street
    if len(params) <= 3:
        return None
    results = _nominatim_search(client, params, what="structured geocode %s" % params)
    return pick_nominatim(results, amenity or city or street or "", want_airport=want_airport, want_station=want_station)


def overpass_aerodrome(client, name, near=None, radius_m=80000):
    """Find aeroway=aerodrome by name, optionally near a lat/lng hint."""
    # Escape Overpass regex specials loosely
    safe = re.sub(r'([\\^$.|?*+()\[\]{}])', r"\\\\\1", name)
    safe = safe.replace('"', "")
    if near:
        around = "(around:%d,%.6f,%.6f)" % (int(radius_m), near["lat"], near["lng"])
    else:
        around = ""
    q = (
        '[out:json][timeout:25];'
        '('
        'nwr["aeroway"="aerodrome"]["name"~"%s",i]%s;'
        'nwr["aeroway"="aerodrome"]["iata"]%s;'
        ');out tags center 10;'
    ) % (safe, around, around)
    errors = []
    for url in OVERPASS:
        try:
            payload = client.get_json(
                url, data={"data": q}, source="Overpass (OpenStreetMap)",
                what="aerodrome named like %s" % name, timeout=45,
            )
            els = (payload or {}).get("elements") or []
            best = None
            best_score = -1
            name_l = name.lower()
            for el in els:
                if not isinstance(el, dict):
                    continue
                tags = el.get("tags") or {}
                if tags.get("aeroway") != "aerodrome":
                    continue
                lat = el.get("lat", (el.get("center") or {}).get("lat"))
                lng = el.get("lon", (el.get("center") or {}).get("lon"))
                if lat is None or lng is None:
                    continue
                n = tags.get("name") or tags.get("name:en") or ""
                score = 10
                if name_l and name_l in n.lower():
                    score += 50
                if tags.get("iata"):
                    score += 20
                    if tags.get("iata").upper() in MAJOR_AIRPORTS:
                        score += 10
                if score > best_score:
                    best_score = score
                    best = _place(
                        lat, lng, n or name,
                        display_name=n or name,
                        city=tags.get("addr:city"),
                        source="overpass aerodrome",
                        osm="%s/%s" % (el.get("type"), el.get("id")),
                        resolved_as=n or name,
                        confidence="high" if score >= 50 else "medium",
                        extra={"iata": tags.get("iata"), "icao": tags.get("icao")},
                    )
            if best:
                return best
        except SourceError as e:
            errors.append(str(e))
            continue
    if errors:
        raise SourceError("Overpass aerodrome lookup failed: " + "; ".join(errors))
    return None


LOCATION_PRIVACY = (
    "Used once for this search, not stored. Nightstop never caches, logs, or writes "
    "your IP or coordinates to disk, ctx.state, or plugin_data; nothing is reused across calls."
)


def ip_geolocate(client):
    """One-shot approximate city-level location from the public IP (no key).

    Privacy: fetched only when explicitly requested for this call. Never cached at
    module/process level, never written to disk/ctx.state/logs/plugin_data, not reused
    across calls, no background polling. The raw IP is not kept on the returned place
    object and is not written into evidence. Coordinates are only forwarded to the
    routing/geocode hosts needed for *this* search, then dropped with the response.
    """
    note = ("Approximate IP-based location (city-level, not GPS). Confirm with the person "
            "before relying on it for a ride pickup or hotel search. " + LOCATION_PRIVACY)
    errors = []
    # ipinfo.io — discard response body after extracting city + lat/lng; never keep IP.
    try:
        data = client.get_json(IPINFO, source="ipinfo.io", what="approximate current location (one-shot)", timeout=12)
        loc = (data or {}).get("loc") or ""
        parts = loc.split(",")
        if len(parts) == 2:
            lat, lng = float(parts[0]), float(parts[1])
            city = data.get("city") or "Near you"
            region = data.get("region")
            country = data.get("country")
            display = ", ".join(x for x in (city, region, country) if x)
            # Drop any reference to the raw payload (includes IP) before returning.
            data = None
            place = _place(
                lat, lng, city, display_name=display or city, city=city,
                source="ipinfo.io (IP approximate, one-shot)", resolved_as="Approximate: %s" % display,
                confidence="low", note=note,
                extra={"ip_approx": True, "accuracy": "city", "location_privacy": LOCATION_PRIVACY},
            )
            # Scrub IP from evidence URLs/hosts notes if any leaked into 'what'
            for ev in client.evidence:
                if ev.get("host") in ("ipinfo.io", "ipapi.co"):
                    ev.pop("ip", None)
                    if "url" in ev:
                        # keep host path only; ipinfo/ipapi URLs have no IP in path
                        ev["url"] = ev["url"].split("?")[0]
            return place
    except (SourceError, TypeError, ValueError) as e:
        errors.append("ipinfo.io: %s" % e)
    # ipapi.co fallback — same one-shot rules
    try:
        data = client.get_json(IPAPI, source="ipapi.co", what="approximate current location (one-shot)", timeout=12)
        lat, lng = float(data["latitude"]), float(data["longitude"])
        city = data.get("city") or "Near you"
        region = data.get("region")
        country = data.get("country_name") or data.get("country")
        display = ", ".join(x for x in (city, region, country) if x)
        data = None
        place = _place(
            lat, lng, city, display_name=display or city, city=city,
            source="ipapi.co (IP approximate, one-shot)", resolved_as="Approximate: %s" % display,
            confidence="low", note=note,
            extra={"ip_approx": True, "accuracy": "city", "location_privacy": LOCATION_PRIVACY},
        )
        for ev in client.evidence:
            if ev.get("host") in ("ipinfo.io", "ipapi.co"):
                ev.pop("ip", None)
                if "url" in ev:
                    ev["url"] = ev["url"].split("?")[0]
        return place
    except (SourceError, TypeError, ValueError, KeyError) as e:
        errors.append("ipapi.co: %s" % e)
    raise SourceError("Could not approximate current location (%s)" % "; ".join(errors))


def _city_hint(text):
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-1]
    return None


def resolve_airport(client, text):
    """Resolve an airport query robustly: aliases/IATA → Nominatim (prefer aeroway) → Overpass."""
    code = match_airport_alias(text)
    if code:
        return _from_airport_table(code, via="name/IATA alias")

    tried = []
    last = None
    city = _city_hint(text)
    # Build strong variants that keep "Airport"
    variants = geocode_queries(text, keep_airport_words=True)
    # Also try bare name + International Airport
    base = _AIRPORT_HINT.sub(" ", text)
    base = _GEOCODE_FILLER.sub(" ", base)
    base = re.sub(r"\s+", " ", base).strip(" ,.-")
    if base:
        variants = list(dict.fromkeys(variants + [
            base + " Airport",
            base + " International Airport",
            ("%s Airport, %s" % (base, city)) if city else None,
            ("%s International Airport, %s" % (base, city)) if city else None,
        ]))
        variants = [v for v in variants if v]

    for q in variants:
        tried.append(q)
        try:
            place = nominatim_lookup(client, q, want_airport=True, limit=8)
            if place and place.get("confidence") != "low":
                if q != text:
                    place["query_simplified_from"] = text
                    place["query_used"] = q
                place["resolved_as"] = place.get("resolved_as") or place["label"]
                return place
            if place:
                last = place
        except SourceError as e:
            last = e
            continue

    # Structured: amenity/airport-ish + city
    if city and base:
        try:
            place = nominatim_structured(
                client, city=city, amenity=base + " Airport", want_airport=True
            )
            if place:
                place["query_used"] = "structured:%s/%s" % (base, city)
                return place
        except SourceError as e:
            last = e

    # Overpass aerodrome by name
    near = None
    if city:
        try:
            near = nominatim_lookup(client, city, limit=3)
        except SourceError:
            near = None
    for name in (base, text, (base + " International Airport") if base else None):
        if not name:
            continue
        try:
            place = overpass_aerodrome(client, name, near=near)
            if place:
                place["query_used"] = "overpass:%s" % name
                return place
        except SourceError as e:
            last = e
            continue

    if last and isinstance(last, dict):
        last["confidence"] = "low"
        last["note"] = (last.get("note") or "") + " Airport match is uncertain; confirm before using ride links."
        return last

    raise SourceError(
        "Could not resolve airport %r (tried: %s)%s"
        % (text, ", ".join(repr(t) for t in tried[:8]), ("; last: %s" % last) if last else "")
    )


def resolve_station(client, text):
    tried, last = [], None
    for q in geocode_queries(text, keep_airport_words=True):
        tried.append(q)
        try:
            place = nominatim_lookup(client, q, want_station=True, limit=8)
            if place:
                if q != text:
                    place["query_simplified_from"] = text
                    place["query_used"] = q
                return place
        except SourceError as e:
            last = e
            continue
    raise SourceError(
        "Could not resolve station %r (tried: %s)%s"
        % (text, ", ".join(repr(t) for t in tried[:8]), ("; last: %s" % last) if last else "")
    )


def resolve(client, text, role="location", *, use_current_location=False):
    if use_current_location or (isinstance(text, str) and is_current_location(text)):
        place = ip_geolocate(client)
        place["role"] = role
        return place
    if not isinstance(text, str) or not text.strip():
        raise ValueError("%s is required (address, place name, Maps link, 'lat,lng', or 'my location')" % role)
    text = text.strip()
    if len(text) > 500:
        raise ValueError("%s is too long" % role)

    ll = parse_latlng(text)
    if ll:
        return _place(ll[0], ll[1], "%.5f, %.5f" % ll, display_name=text,
                      source="coordinates (user supplied)", resolved_as="Exact coordinates",
                      confidence="high")

    maps = parse_maps_url(text)
    if maps:
        return _place(maps[0], maps[1], "%.5f, %.5f" % maps, display_name=text,
                      source="Google Maps link", resolved_as="Coordinates from Maps link",
                      confidence="high")

    # Airport / station paths
    if _AIRPORT_HINT.search(text) or match_airport_alias(text):
        return resolve_airport(client, text)
    if _STATION_HINT.search(text):
        return resolve_station(client, text)

    place_key = match_place_alias(text)
    if place_key:
        return _from_place_table(place_key, via="neighbourhood alias")

    # Neighbourhood / general place: prefer place/suburb over schools and roads
    tried, last = [], None
    variants = geocode_queries(text, keep_airport_words=False)
    for i, q in enumerate(variants):
        tried.append(q)
        try:
            # First try unbounded, then with featuretype=settlement for early variants
            place = nominatim_lookup(client, q, limit=8)
            if place and not (_is_highway_place(place) and i == 0):
                # Re-check raw: if top pick was a school, try settlement featuretype
                if place.get("nominatim_type") in ("school", "college", "university", "hospital"):
                    alt = nominatim_lookup(client, q, limit=8, featuretype="settlement")
                    if alt:
                        place = alt
                if q != text:
                    place["query_simplified_from"] = text
                    place["query_used"] = q
                return place
            if place:
                last = place
        except SourceError as e:
            last = e
            continue
    if last and isinstance(last, dict):
        return last
    raise SourceError(
        "Nominatim found no place for %r (tried: %s)%s"
        % (text, ", ".join(repr(t) for t in tried), ("; last: %s" % last) if last else "")
    )


def _is_highway_place(place):
    return (place.get("nominatim_class") in _ROAD_CLASSES
            or (place.get("nominatim_type") or "") in _HIGHWAY_TYPES)


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
