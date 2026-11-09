"""JSON schemas Hermes shows the model."""
_DATES = {
    "check_in": {"type": "string", "description": "Optional ISO date YYYY-MM-DD; only prefills Booking/Airbnb links (OSM has no vacancy data)."},
    "check_out": {"type": "string", "description": "Optional ISO date YYYY-MM-DD, after check_in."},
}
_TYPE = {"type": "string", "enum": ["any", "hotel", "hostel", "guest_house", "motel", "apartment", "chalet"],
         "description": "Optional filter on the OpenStreetMap tourism type."}
_PRESENT = (" The JSON includes reply_markdown (ready-to-show markdown with short labeled links) "
            "and presentation_hint. Always paste reply_markdown into the chat (or rewrite using the "
            "same short labels). Show links ONLY as markdown labels like "
            "[Book on Booking.com](url), [Hotel website](url), [Get an Uber](url), [Lyft](url), "
            "[Directions](url), [Airbnb nearby](url) — never paste raw URLs. Keep the raw url "
            "fields in data for machines; humans see the short labels.")
_TAIL = (" Cannot log into Uber/Lyft/Airbnb/Booking.com or pay: returns deep links the person opens to finish there. "
         "Never invent prices, reviews, availability or ETAs; report the tool's warnings. "
         "Say availability is not confirmed and that no booking has been made." + _PRESENT)

FIND_STAY = {
    "name": "find_stay",
    "description": ("Find real, named last-minute places to sleep (hotels, hostels, guest houses, motels, serviced "
                    "apartments, chalets) mapped in OpenStreetMap near a place or 'lat,lng'. Adds OSRM driving/walking "
                    "time from that point, stars/phone/website only when tagged, plus Book on Booking.com / Airbnb nearby "
                    "/ Get an Uber / Directions links." + _TAIL),
    "parameters": {"type": "object", "properties": {
        "location": {"type": "string", "description": "Address, landmark, city, airport, or 'lat,lng'."},
        "radius_km": {"type": "number", "minimum": 0.2, "maximum": 25, "description": "Default 3; auto-expands once to 8 if fewer than 3 stays."},
        "stay_type": _TYPE, **_DATES,
        "limit": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Max stays returned, default 12."},
    }, "required": ["location"], "additionalProperties": False},
}

FIND_RIDE = {
    "name": "find_ride",
    "description": ("Get a ride from A to B right now: geocodes both ends, returns real OSRM road distance (m) and "
                    "duration (s), walking time for short hops, and Get an Uber / Lyft / Directions links with pickup "
                    "and dropoff prefilled. No fares or driver data. If routing fails, still returns deep links and "
                    "a clear warning instead of an error." + _TAIL),
    "parameters": {"type": "object", "properties": {
        "pickup": {"type": "string", "description": "Where the person is: address, place, or 'lat,lng'."},
        "dropoff": {"type": "string", "description": "Destination: address, place, or 'lat,lng'."},
    }, "required": ["pickup", "dropoff"], "additionalProperties": False},
}

PLAN_NIGHT = {
    "name": "plan_night",
    "description": ("Stranded mode: someone is out late with nowhere to sleep. Given where they are now (and an optional "
                    "area to sleep in), finds nearby mapped stays, ranks them by OSRM driving time from the origin, adds "
                    "walking time when close, and returns for each stay ride links (Get an Uber / Lyft / Directions from origin) and book "
                    "links (Book on Booking.com / Airbnb nearby), plus a top pick. On lodging-search failure still returns "
                    "geocoded origin plus area booking links." + _TAIL),
    "parameters": {"type": "object", "properties": {
        "origin": {"type": "string", "description": "Where they are now: address, station, airport, or 'lat,lng'."},
        "area": {"type": "string", "description": "Optional area to sleep in, e.g. 'Alfama, Lisbon'. Defaults to around the origin."},
        "radius_km": {"type": "number", "minimum": 0.2, "maximum": 25, "description": "Default 3; auto-expands once to 8."},
        "stay_type": _TYPE, **_DATES,
        "limit": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Max stays returned, default 8."},
    }, "required": ["origin"], "additionalProperties": False},
}
