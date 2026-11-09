"""JSON schemas Hermes shows the model."""
_DATES = {
    "check_in": {"type": "string", "description": "Optional ISO date YYYY-MM-DD; only prefills Booking/Airbnb links (OSM has no vacancy data)."},
    "check_out": {"type": "string", "description": "Optional ISO date YYYY-MM-DD, after check_in."},
}
_TYPE = {"type": "string", "enum": ["any", "hotel", "hostel", "guest_house", "motel", "apartment", "chalet"],
         "description": "Optional filter on the OpenStreetMap tourism type."}
_CURRENT = {
    "use_current_location": {
        "type": "boolean",
        "description": (
            "If true, approximate the person's location once via a keyless IP geolocation lookup "
            "(city-level, not GPS). Only use when they ask for 'my location' / 'here' / 'use my location' "
            "and have not given a place. Confirm the city with them before relying on it. "
            "One-shot only: never cached, never stored, not reused across calls."
        ),
    }
}
_PLACE = (
    "Address, landmark, neighbourhood, airport, station, IATA code (e.g. LOS, ABV), "
    "'lat,lng', a Google Maps link/pin, or 'my location'/'here'/'current location'."
)
_PRESENT = (" The JSON includes reply_markdown (ready-to-show markdown with short labeled links) "
            "and presentation_hint. Always paste reply_markdown into the chat (or rewrite using the "
            "same short labels). Show links ONLY as markdown labels like "
            "[Book on Booking.com](url), [Hotel website](url), [Get an Uber](url), [Lyft](url), "
            "[Directions](url), [Airbnb nearby](url) — never paste raw URLs. Keep the raw url "
            "fields in data for machines; humans see the short labels.")
_TAIL = (" Cannot log into Uber/Lyft/Airbnb/Booking.com or pay: returns deep links the person opens to finish there. "
         "Never invent prices, reviews, availability or ETAs; report the tool's warnings. "
         "Say availability is not confirmed and that no booking has been made. "
         "When location_privacy is present, tell the person their approximate location was used once for this search and not stored."
         + _PRESENT)

FIND_STAY = {
    "name": "find_stay",
    "description": (
        "Find real, named last-minute places to sleep (hotels, hostels, guest houses, motels, serviced "
        "apartments, chalets) mapped in OpenStreetMap near a place or 'lat,lng'. For airports, pass the "
        "airport name or IATA (e.g. 'Nnamdi Azikiwe Airport' / ABV) — Nightstop prefers aerodrome results "
        "and rejects roads. Auto-widens the radius 3→6→10 km when fewer than ~5 stays are found (and says so). "
        "Adds OSRM driving/walking time, plus Book on Booking.com / Airbnb nearby / Get an Uber / Directions links."
        " For a trip like 'ride to airport A then stay near airport B', call find_stay with location=airport B "
        "(and separately find_ride for the departure leg)."
        + _TAIL
    ),
    "parameters": {"type": "object", "properties": {
        "location": {"type": "string", "description": _PLACE},
        "radius_km": {"type": "number", "minimum": 0.2, "maximum": 25,
                      "description": "Default 3; auto-expands 3→6→10 km if fewer than ~5 stays."},
        "stay_type": _TYPE, **_DATES,
        "limit": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Max stays returned, default 12."},
        **_CURRENT,
    }, "required": [], "additionalProperties": False},
}

FIND_RIDE = {
    "name": "find_ride",
    "description": (
        "Get a ride from A to B right now: geocodes both ends (airports prefer aerodrome/IATA; roads are "
        "rejected when an airport was asked for), returns real OSRM road distance (m) and duration (s), "
        "walking time for short hops, and Get an Uber / Lyft / Directions links with pickup and dropoff "
        "prefilled. No fares or driver data. If routing fails, still returns deep links and a clear warning "
        "instead of an error. For 'I'm in X, take me to airport Y, then I need a stay near airport Z': "
        "call find_ride(pickup=X, dropoff=airport Y) for the departure leg, and find_stay(location=airport Z) "
        "for the arrival stay — do not fold both airports into one find_ride."
        + _TAIL
    ),
    "parameters": {"type": "object", "properties": {
        "pickup": {"type": "string", "description": "Where the person is now. " + _PLACE},
        "dropoff": {"type": "string", "description": "Destination. " + _PLACE},
        **_CURRENT,
    }, "required": ["dropoff"], "additionalProperties": False},
}

PLAN_NIGHT = {
    "name": "plan_night",
    "description": (
        "Stranded mode: someone is out late with nowhere to sleep. Given where they are now (and an optional "
        "area to sleep in), finds nearby mapped stays, ranks them by OSRM driving time from the origin, adds "
        "walking time when close, and returns for each stay ride links (Get an Uber / Lyft / Directions from origin) and book "
        "links (Book on Booking.com / Airbnb nearby), plus a top pick. Auto-widens 3→6→10 km when thin. "
        "On lodging-search failure still returns geocoded origin plus area booking links. "
        "If they need a ride to a *different* place (e.g. departure airport) AND a stay near an arrival airport, "
        "prefer find_ride for the departure leg + find_stay near the arrival airport instead of one plan_night."
        + _TAIL
    ),
    "parameters": {"type": "object", "properties": {
        "origin": {"type": "string", "description": "Where they are now. " + _PLACE},
        "area": {"type": "string", "description": "Optional area to sleep in, e.g. 'Alfama, Lisbon' or an arrival airport. Defaults to around the origin."},
        "radius_km": {"type": "number", "minimum": 0.2, "maximum": 25,
                      "description": "Default 3; auto-expands 3→6→10 km if fewer than ~5 stays."},
        "stay_type": _TYPE, **_DATES,
        "limit": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Max stays returned, default 8."},
        **_CURRENT,
    }, "required": [], "additionalProperties": False},
}
