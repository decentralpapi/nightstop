"""Nightstop backend for Hermes Desktop/dashboard: /api/plugins/nightstop/{stay,ride,night}.

Install the shared package into Hermes's Python environment (README) so this
module resolves `nightstop` without touching sys.path or Hermes internals.
Auth and enable gates are owned by the Hermes host.
"""
import json

from fastapi import APIRouter
try:  # pip-installed shared package (README step 1)
    from nightstop.tools import find_ride, find_stay, plan_night
except ImportError:  # plugin folder itself importable as `nightstop`
    from nightstop.nightstop.tools import find_ride, find_stay, plan_night

router = APIRouter()


# Plain `def` routes: FastAPI runs the blocking, time-bounded HTTP work in its thread pool.
@router.post("/stay")
def stay_route(body: dict):
    return json.loads(find_stay(body))


@router.post("/ride")
def ride_route(body: dict):
    return json.loads(find_ride(body))


@router.post("/night")
def night_route(body: dict):
    return json.loads(plan_night(body))
