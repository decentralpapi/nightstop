"""Hermes handlers. Always return a JSON string, including errors."""
import json

from . import engine
from .render import PRESENTATION_HINT, reply_markdown
from .sources import SourceError, is_current_location

_STAY = ("location", "radius_km", "stay_type", "check_in", "check_out", "limit", "use_current_location")
_RIDE = ("pickup", "dropoff", "use_current_location")
_NIGHT = ("origin", "area", "radius_km", "stay_type", "check_in", "check_out", "limit", "use_current_location")


def _clean(args, allowed):
    if not isinstance(args, dict):
        raise ValueError("Arguments must be an object")
    a = {k: v for k, v in args.items() if k in allowed and v is not None}
    if a.get("stay_type") == "any":
        a.pop("stay_type")
    if "use_current_location" in a:
        a["use_current_location"] = bool(a["use_current_location"])
    return a


def _ok(data):
    md = reply_markdown(data)
    return json.dumps({
        "formatted_output": md,
        "reply_markdown": md,
        "presentation_hint": PRESENTATION_HINT,
        "data": data,
    }, ensure_ascii=False)


def _err(msg):
    return json.dumps({
        "error": msg,
        "data": None,
        "reply_markdown": None,
        "presentation_hint": PRESENTATION_HINT,
        "honesty": engine.HONESTY,
    }, ensure_ascii=False)


def _has_place(val, use_current):
    if use_current:
        return True
    if not isinstance(val, str):
        return False
    s = val.strip()
    return bool(s) and (not is_current_location(s) or True)


def _run(fn, args, allowed, required, current_keys=()):
    try:
        a = _clean(args, allowed)
        use_current = bool(a.get("use_current_location"))
        # "my location" / here also counts as providing the place
        for k in current_keys:
            if is_current_location(str(a.get(k) or "")):
                use_current = True
                a["use_current_location"] = True
        missing = []
        for k in required:
            if k in current_keys and use_current:
                continue
            if not str(a.get(k, "")).strip():
                missing.append(k)
        if missing:
            raise ValueError(
                "Missing required: " + ", ".join(missing)
                + " (address, place name, Maps link, 'lat,lng', or set use_current_location / pass 'my location')"
            )
        return _ok(fn(**a))
    except (ValueError, SourceError) as exc:
        return _err(str(exc))
    except Exception as exc:  # never leak tracebacks
        return _err("Nightstop failed: " + type(exc).__name__)


def find_stay(args: dict, **kwargs) -> str:
    return _run(engine.find_stay, args, _STAY, ("location",), current_keys=("location",))


def find_ride(args: dict, **kwargs) -> str:
    return _run(engine.find_ride, args, _RIDE, ("pickup", "dropoff"), current_keys=("pickup",))


def plan_night(args: dict, **kwargs) -> str:
    return _run(engine.plan_night, args, _NIGHT, ("origin",), current_keys=("origin",))
