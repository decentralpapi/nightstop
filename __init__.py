"""Hermes native entry point. Registration is offline and side-effect free."""
from .nightstop.schemas import FIND_RIDE, FIND_STAY, PLAN_NIGHT
from .nightstop.tools import find_ride, find_stay, plan_night


def register(ctx):
    ctx.register_tool(name="find_stay", toolset="nightstop", schema=FIND_STAY, handler=find_stay)
    ctx.register_tool(name="find_ride", toolset="nightstop", schema=FIND_RIDE, handler=find_ride)
    ctx.register_tool(name="plan_night", toolset="nightstop", schema=PLAN_NIGHT, handler=plan_night)
