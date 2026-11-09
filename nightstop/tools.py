"""Hermes handlers. Always return a JSON string, including errors."""
import json

from . import engine
from .render import PRESENTATION_HINT, reply_markdown
from .sources import SourceError

_STAY = ("location", "radius_km", "stay_type", "check_in", "check_out", "limit")
_NIGHT = ("origin", "area", "radius_km", "stay_type", "check_in", "check_out", "limit")


def _clean(args, allowed):
    if not isinstance(args, dict):
        raise ValueError("Arguments must be an object")
    a = {k: v for k, v in args.items() if k in allowed and v is not None}
    if a.get("stay_type") == "any":
        a.pop("stay_type")
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


def _run(fn, args, allowed, required):
    try:
        a = _clean(args, allowed)
        missing = [k for k in required if not str(a.get(k, "")).strip()]
        if missing:
            raise ValueError("Missing required: " + ", ".join(missing) + " (address, place name or 'lat,lng')")
        return _ok(fn(**a))
    except (ValueError, SourceError) as exc:
        return _err(str(exc))
    except Exception as exc:  # never leak tracebacks
        return _err("Nightstop failed: " + type(exc).__name__)


def find_stay(args: dict, **kwargs) -> str:
    return _run(engine.find_stay, args, _STAY, ("location",))


def find_ride(args: dict, **kwargs) -> str:
    return _run(engine.find_ride, args, ("pickup", "dropoff"), ("pickup", "dropoff"))


def plan_night(args: dict, **kwargs) -> str:
    return _run(engine.plan_night, args, _NIGHT, ("origin",))
