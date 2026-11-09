"""Nightstop orchestration: find_stay, find_ride, plan_night.

Every number in the output comes from a named public source (OSRM for times
and road distances, OSM tags for stay facts) or is plain geometry clearly
labelled as straight-line. Nothing is invented: no prices, reviews, ratings,
availability or photos.
"""
from __future__ import annotations

import datetime as dt

from . import sources as S
from .sources import SourceError

WAT = dt.timezone(dt.timedelta(hours=1), "WAT")
HONESTY = ("Nightstop cannot log into Uber, Lyft, Airbnb or Booking.com and cannot complete a paid "
           "checkout. 'Get a ride' and 'Check Booking/Airbnb' open those apps or sites with pickup, "
           "dropoff or search prefilled; you confirm and pay there. No reservation has been made. "
           "OpenStreetMap does not know room availability or nightly prices.")
ATTRIBUTION = "Map data © OpenStreetMap contributors (ODbL). Routing by OSRM."
DEFAULT_RADIUS_KM = 3.0
EXPANDED_RADIUS_KM = 8.0  # kept for back-compat imports
RADIUS_STEPS_KM = (3.0, 6.0, 10.0)
MIN_STAYS_TARGET = 5
MAX_TABLE = 40
WALK_IF_WITHIN_M = 2500


def now_wat():
    return dt.datetime.now(WAT).strftime("%d %b %Y, %H:%M WAT")


def _dates(check_in, check_out):
    if not check_in and not check_out:
        return None, None
    if not (check_in and check_out):
        raise ValueError("Give both check_in and check_out (YYYY-MM-DD), or neither")
    try:
        a, b = dt.date.fromisoformat(str(check_in)), dt.date.fromisoformat(str(check_out))
    except ValueError:
        raise ValueError("check_in/check_out must be ISO dates like 2026-11-10") from None
    if b <= a:
        raise ValueError("check_out must be after check_in")
    return a.isoformat(), b.isoformat()


def _radius(v):
    if v is None:
        return DEFAULT_RADIUS_KM
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError("radius_km must be a number") from None
    if not 0.2 <= v <= 25:
        raise ValueError("radius_km must be between 0.2 and 25")
    return v


def _type(v):
    if v in (None, "", "any"):
        return None
    v = str(v).strip().lower().replace(" ", "_").replace("-", "_")
    if v == "guesthouse":
        v = "guest_house"
    if v not in S.STAY_TYPES:
        raise ValueError("stay_type must be one of: " + ", ".join(S.STAY_TYPES))
    return v


def _limit(v, default=12):
    try:
        v = int(default if v is None else v)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer") from None
    return max(1, min(v, 30))


def fmt_duration(s):
    if s is None:
        return "route unavailable"
    m = max(1, round(s / 60))
    return "%d min" % m if m < 60 else "%d h %02d min" % divmod(m, 60)


def fmt_distance(m):
    if m is None:
        return "—"
    return "%d m" % m if m < 1000 else "%.1f km" % (m / 1000)


def _expand_radii(start_km):
    """Yield search radii: the requested one, then larger steps until ~10 km."""
    start = float(start_km)
    seen = set()
    ordered = [start] + [r for r in RADIUS_STEPS_KM if r > start + 1e-9]
    # Always allow climbing the standard ladder even when start was already 3.
    if start <= DEFAULT_RADIUS_KM + 1e-9:
        ordered = list(RADIUS_STEPS_KM)
    out = []
    for r in ordered:
        r = round(r, 3)
        if r not in seen and 0.2 <= r <= 25:
            seen.add(r)
            out.append(r)
    return out


def _search(client, center, radius_km, stay_type, warnings):
    """Overpass search; widen 3→6→10 km (or upward from a custom radius) until ≥5 stays."""
    stays, skipped, used = [], 0, radius_km
    radii = _expand_radii(radius_km)
    for i, r in enumerate(radii):
        try:
            batch, skipped = S.fetch_lodging(client, center["lat"], center["lng"], r * 1000)
        except SourceError as e:
            if i == 0:
                raise
            warnings.append("Tried to expand search to %g km but Overpass failed: %s" % (r, e))
            break
        if stay_type:
            batch = [s for s in batch if s["type"] == stay_type]
        if i > 0 and len(batch) > len(stays):
            warnings.append(
                "Only %d stay(s) within %g km, so the search was expanded to %g km."
                % (len(stays), used, r)
            )
        stays, used = batch, r
        if len(stays) >= MIN_STAYS_TARGET:
            break
        if i + 1 < len(radii) and len(stays) < MIN_STAYS_TARGET:
            continue
    for s in stays:
        s["straight_line_m"] = S.haversine_m(center, s)
    stays.sort(key=lambda s: s["straight_line_m"])
    return stays, used, skipped


def _attach_routes(client, origin, stays, warnings, walk=True):
    """Driving (OSRM table) + walking for short hops. Failures leave None + a warning."""
    sub = stays[:MAX_TABLE]
    try:
        for s, r in zip(sub, S.osrm_table(client, origin, sub, "driving")):
            s["drive"] = r
    except SourceError as e:
        warnings.append("Driving times unavailable: %s" % e)
    near = [s for s in sub if s["straight_line_m"] <= WALK_IF_WITHIN_M] if walk else []
    if near:
        try:
            for s, r in zip(near, S.osrm_table(client, origin, near, "walking")):
                s["walk"] = r
        except SourceError as e:
            warnings.append("Walking times unavailable: %s" % e)
    for s in stays:
        s.setdefault("drive", None)
        s.setdefault("walk", None)


def _rank(stays):
    # Driving duration when known; unroutable/unknown fall back to straight-line after the routed ones.
    stays.sort(key=lambda s: (0, s["drive"]["duration_s"]) if s.get("drive") else (1, s["straight_line_m"]))
    for i, s in enumerate(stays, 1):
        s["rank"] = i
    return stays


def _stay_links(stay, origin, check_in, check_out, city_hint=None):
    if not stay.get("city") and city_hint:
        stay["city_hint"] = city_hint  # used only to disambiguate Booking/Airbnb searches
    links = {
        "check_booking": S.booking_link(stay, check_in, check_out),
        "check_airbnb": S.airbnb_link(stay, check_in, check_out),
        "open_maps": S.maps_pin(stay),
        "openstreetmap": stay["osm_url"],
    }
    if stay.get("website", "") and str(stay["website"]).startswith(("http://", "https://")):
        links["website"] = stay["website"]
    tel = S.tel_link(stay.get("phone"))
    if tel:
        links["call"] = tel
    if origin:
        links["open_uber"] = S.uber_link(origin, stay)
        links["open_lyft"] = S.lyft_link(origin, stay)
        links["directions"] = S.maps_directions(origin, stay)
    stay["links"] = links
    return stay


def _evidence(client):
    return [dict(e) for e in client.evidence]


def _resolution_warnings(place, warnings, role):
    if place.get("confidence") == "low":
        warnings.append(
            "%s resolved with low confidence as %s (%.5f, %.5f). Confirm before using ride/booking links."
            % (role.capitalize(), place.get("resolved_as") or place.get("label"), place["lat"], place["lng"])
        )
    if place.get("ip_approx") or place.get("source", "").startswith("ip"):
        warnings.append(
            place.get("note")
            or "Origin is an approximate IP-based city location — confirm with the person before relying on it."
        )
    if place.get("note") and place.get("confidence") != "low" and "IP-based" not in (place.get("note") or ""):
        warnings.append(place["note"])


def _location_privacy(places):
    for p in places:
        if p and (p.get("ip_approx") or "IP approximate" in str(p.get("source") or "")):
            return p.get("location_privacy") or S.LOCATION_PRIVACY
    return None


def _with_privacy(result, *places):
    note = _location_privacy(places)
    if note:
        result["location_privacy"] = note
    return result


def find_stay(location=None, radius_km=None, stay_type=None, check_in=None, check_out=None, limit=None,
              use_current_location=False, client=None):
    client = client or S.Client()
    radius_km, stay_type, limit = _radius(radius_km), _type(stay_type), _limit(limit)
    check_in, check_out = _dates(check_in, check_out)
    warnings = []
    if use_current_location and not (isinstance(location, str) and location.strip()):
        location = "my location"
    center = S.resolve(client, location, "location", use_current_location=bool(use_current_location))
    _resolution_warnings(center, warnings, "location")
    try:
        stays, used, skipped = _search(client, center, radius_km, stay_type, warnings)
    except SourceError as e:
        warnings.append("Lodging search failed (%s). Returning area booking links only; try again or widen the area." % e)
        stays, used, skipped = [], radius_km, 0
    total = len(stays)
    stays = stays[:limit]
    if stays:
        _attach_routes(client, center, stays, warnings)
        _rank(stays)
    origin = dict(center, label=center["label"])
    for s in stays:
        _stay_links(s, origin, check_in, check_out, center.get("city"))
    if not stays:
        warnings.append("No named hotels, hostels, guest houses, motels or apartments are mapped in OpenStreetMap within %g km." % used)
    if check_in:
        warnings.append("Dates %s → %s only prefill Booking/Airbnb links; OpenStreetMap does not know vacancy." % (check_in, check_out))
    return _with_privacy({
        "kind": "stay", "query": location, "center": center, "radius_km": used, "stay_type": stay_type,
        "check_in": check_in, "check_out": check_out, "found_total": total, "skipped_unnamed_or_invalid": skipped,
        "stays": stays, "area_links": {"check_booking": S.booking_link({"name": center["label"], "city_hint": center.get("city"), "lat": center["lat"], "lng": center["lng"]}, check_in, check_out),
                                        "check_airbnb": S.airbnb_link(center, check_in, check_out, span=0.02)},
        "warnings": warnings, "honesty": HONESTY, "attribution": ATTRIBUTION,
        "fetched_at": now_wat(), "evidence": _evidence(client),
    }, center)


def find_ride(pickup=None, dropoff=None, use_current_location=False, client=None):
    client = client or S.Client()
    warnings = []
    if use_current_location and not (isinstance(pickup, str) and pickup.strip()):
        pickup = "my location"
    a = S.resolve(client, pickup, "pickup", use_current_location=bool(use_current_location))
    b = S.resolve(client, dropoff, "dropoff")
    _resolution_warnings(a, warnings, "pickup")
    _resolution_warnings(b, warnings, "dropoff")
    # Refuse to ship a ride link when an airport/station was asked for but we got a road.
    if S._AIRPORT_HINT.search(str(dropoff or "")) or S.match_airport_alias(str(dropoff or "")):
        if b.get("nominatim_class") in S._ROAD_CLASSES or (b.get("nominatim_type") or "") in S._HIGHWAY_TYPES:
            raise SourceError(
                "Dropoff %r resolved to a road (%s), not an airport. Not returning a ride link."
                % (dropoff, b.get("resolved_as") or b.get("label"))
            )
    drive = None
    try:
        drive = S.osrm_route(client, a, b, "driving")
    except SourceError as e:
        warnings.append("Driving route unavailable: %s" % e)
    straight = S.haversine_m(a, b)
    walk = None
    if straight <= WALK_IF_WITHIN_M:
        try:
            walk = S.osrm_route(client, a, b, "walking")
        except SourceError as e:
            warnings.append("Walking route unavailable: %s" % e)
    if drive is None and walk is None:
        warnings.append(
            "No driving or walking route could be computed between %s and %s. "
            "Uber/Lyft/Directions links are still included so you can open them with pickup and dropoff set."
            % (a["label"], b["label"])
        )
    return _with_privacy({
        "kind": "ride", "pickup": a, "dropoff": b, "drive": drive, "walk": walk, "straight_line_m": straight,
        "links": {"open_uber": S.uber_link(a, b), "open_lyft": S.lyft_link(a, b), "open_maps": S.maps_directions(a, b),
                  "open_maps_walking": S.maps_directions(a, b, "walking") if walk else None},
        "note": "Durations are OSRM road-network estimates without live traffic. Ride price and pickup wait show in the Uber/Lyft app.",
        "warnings": warnings, "honesty": HONESTY, "attribution": ATTRIBUTION,
        "fetched_at": now_wat(), "evidence": _evidence(client),
    }, a, b)


def plan_night(origin=None, area=None, radius_km=None, stay_type=None, check_in=None, check_out=None, limit=None,
               use_current_location=False, client=None):
    client = client or S.Client()
    radius_km, stay_type, limit = _radius(radius_km), _type(stay_type), _limit(limit, 8)
    check_in, check_out = _dates(check_in, check_out)
    warnings = []
    if use_current_location and not (isinstance(origin, str) and origin.strip()):
        origin = "my location"
    here = S.resolve(client, origin, "origin", use_current_location=bool(use_current_location))
    _resolution_warnings(here, warnings, "origin")
    center = S.resolve(client, area, "area") if area and str(area).strip() else here
    if center is not here:
        _resolution_warnings(center, warnings, "area")
    try:
        stays, used, skipped = _search(client, center, radius_km, stay_type, warnings)
    except SourceError as e:
        warnings.append("Lodging search failed (%s). Returning area booking links only; try again or widen the area." % e)
        stays, used, skipped = [], radius_km, 0
    total = len(stays)
    if center is not here:  # measure from where the person actually is
        for s in stays:
            s["straight_line_m"] = S.haversine_m(here, s)
        stays.sort(key=lambda s: s["straight_line_m"])
    pool = stays[:MAX_TABLE]
    if pool:
        _attach_routes(client, here, pool, warnings)
        _rank(pool)
    pool = pool[:limit]
    for s in pool:
        _stay_links(s, here, check_in, check_out, center.get("city"))
    if not pool:
        warnings.append("No named stays mapped in OpenStreetMap within %g km. Try an area hint (e.g. city centre) or a bigger radius." % used)
    if check_in:
        warnings.append("Dates %s → %s only prefill Booking/Airbnb links; OpenStreetMap does not know vacancy." % (check_in, check_out))
    top = pool[0] if pool else None
    walkers = [x for x in pool if x.get("walk")]
    near_walk = min(walkers, key=lambda x: x["walk"]["duration_s"]) if walkers else None
    return _with_privacy({
        "kind": "night", "origin": here, "area": center if center is not here else None, "radius_km": used,
        "stay_type": stay_type, "check_in": check_in, "check_out": check_out, "found_total": total,
        "skipped_unnamed_or_invalid": skipped, "stays": pool,
        "top_pick": {"id": top["id"], "name": top["name"], "why": "Shortest OSRM driving time from your origin" if top.get("drive") else "Closest in straight line (driving time unavailable)"} if top else None,
        "nearest_on_foot": {"id": near_walk["id"], "name": near_walk["name"], "walk_s": near_walk["walk"]["duration_s"]} if near_walk and near_walk is not top else None,
        "area_links": {"check_booking": S.booking_link({"name": center["label"], "city_hint": center.get("city"), "lat": center["lat"], "lng": center["lng"]}, check_in, check_out),
                       "check_airbnb": S.airbnb_link(center, check_in, check_out, span=0.02)},
        "warnings": warnings, "honesty": HONESTY, "attribution": ATTRIBUTION,
        "fetched_at": now_wat(), "evidence": _evidence(client),
    }, here, center)
