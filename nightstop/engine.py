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
EXPANDED_RADIUS_KM = 8.0
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


def _search(client, center, radius_km, stay_type, warnings):
    """Overpass search with one automatic expansion to ~8 km if fewer than 3 hits."""
    stays, skipped = S.fetch_lodging(client, center["lat"], center["lng"], radius_km * 1000)
    if stay_type:
        stays = [s for s in stays if s["type"] == stay_type]
    used = radius_km
    if len(stays) < 3 and radius_km < EXPANDED_RADIUS_KM:
        try:
            more, skipped = S.fetch_lodging(client, center["lat"], center["lng"], EXPANDED_RADIUS_KM * 1000)
            if stay_type:
                more = [s for s in more if s["type"] == stay_type]
            warnings.append("Only %d stay(s) within %g km, so the search was expanded to %g km." % (len(stays), radius_km, EXPANDED_RADIUS_KM))
            stays, used = more, EXPANDED_RADIUS_KM
        except SourceError as e:
            warnings.append("Tried to expand search to %g km but Overpass failed: %s" % (EXPANDED_RADIUS_KM, e))
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


def find_stay(location, radius_km=None, stay_type=None, check_in=None, check_out=None, limit=None, client=None):
    client = client or S.Client()
    radius_km, stay_type, limit = _radius(radius_km), _type(stay_type), _limit(limit)
    check_in, check_out = _dates(check_in, check_out)
    warnings = []
    center = S.resolve(client, location, "location")
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
    return {
        "kind": "stay", "query": location, "center": center, "radius_km": used, "stay_type": stay_type,
        "check_in": check_in, "check_out": check_out, "found_total": total, "skipped_unnamed_or_invalid": skipped,
        "stays": stays, "area_links": {"check_booking": S.booking_link({"name": center["label"], "city_hint": center.get("city"), "lat": center["lat"], "lng": center["lng"]}, check_in, check_out),
                                        "check_airbnb": S.airbnb_link(center, check_in, check_out, span=0.02)},
        "warnings": warnings, "honesty": HONESTY, "attribution": ATTRIBUTION,
        "fetched_at": now_wat(), "evidence": _evidence(client),
    }


def find_ride(pickup, dropoff, client=None):
    client = client or S.Client()
    a = S.resolve(client, pickup, "pickup")
    b = S.resolve(client, dropoff, "dropoff")
    warnings = []
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
    return {
        "kind": "ride", "pickup": a, "dropoff": b, "drive": drive, "walk": walk, "straight_line_m": straight,
        "links": {"open_uber": S.uber_link(a, b), "open_lyft": S.lyft_link(a, b), "open_maps": S.maps_directions(a, b),
                  "open_maps_walking": S.maps_directions(a, b, "walking") if walk else None},
        "note": "Durations are OSRM road-network estimates without live traffic. Ride price and pickup wait show in the Uber/Lyft app.",
        "warnings": warnings, "honesty": HONESTY, "attribution": ATTRIBUTION,
        "fetched_at": now_wat(), "evidence": _evidence(client),
    }


def plan_night(origin, area=None, radius_km=None, stay_type=None, check_in=None, check_out=None, limit=None, client=None):
    client = client or S.Client()
    radius_km, stay_type, limit = _radius(radius_km), _type(stay_type), _limit(limit, 8)
    check_in, check_out = _dates(check_in, check_out)
    warnings = []
    here = S.resolve(client, origin, "origin")
    center = S.resolve(client, area, "area") if area and str(area).strip() else here
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
    return {
        "kind": "night", "origin": here, "area": center if center is not here else None, "radius_km": used,
        "stay_type": stay_type, "check_in": check_in, "check_out": check_out, "found_total": total,
        "skipped_unnamed_or_invalid": skipped, "stays": pool,
        "top_pick": {"id": top["id"], "name": top["name"], "why": "Shortest OSRM driving time from your origin" if top.get("drive") else "Closest in straight line (driving time unavailable)"} if top else None,
        "nearest_on_foot": {"id": near_walk["id"], "name": near_walk["name"], "walk_s": near_walk["walk"]["duration_s"]} if near_walk and near_walk is not top else None,
        "area_links": {"check_booking": S.booking_link({"name": center["label"], "city_hint": center.get("city"), "lat": center["lat"], "lng": center["lng"]}, check_in, check_out),
                       "check_airbnb": S.airbnb_link(center, check_in, check_out, span=0.02)},
        "warnings": warnings, "honesty": HONESTY, "attribution": ATTRIBUTION,
        "fetched_at": now_wat(), "evidence": _evidence(client),
    }
