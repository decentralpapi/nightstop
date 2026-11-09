# Nightstop — a ride and a bed, tonight

Repo: https://github.com/decentralpapi/nightstop


**Nightstop is a Hermes Agent plugin for the moment you land late, miss the last
train, or realise you have nowhere to sleep.** Tell Hermes where you are. Nightstop
finds real, named places to stay mapped in OpenStreetMap near you, works out how
long it really takes to get to each one (OSRM road routing, plus walking time when
it's close), ranks them, and hands you one-tap **Get a ride** (Uber / Lyft / Maps)
and **See rooms** (Booking.com / Airbnb) links with everything prefilled.

It also does the two halves on their own: `find_stay` (places to sleep near X) and
`find_ride` (route + ride links from A to B).

> **Honest limits — read this.** Nightstop **cannot log into Uber, Lyft, Airbnb or
> Booking.com and cannot complete a paid checkout.** "Get a ride", "Open Uber",
> "Check Booking" and "Check Airbnb" open those apps or sites with pickup, dropoff
> or search prefilled; you confirm and pay there. **No reservation is ever made by
> the plugin.** OpenStreetMap does not know room availability or nightly prices, so
> Nightstop never shows a price, rating, review, photo or "rooms left" it doesn't
> have. Every number it shows is from a named source and listed in `evidence`.

## Why a plugin and not a prompt

A prompt or skill can't do this reliably: the model would have to guess hotel names,
distances and drive times. Nightstop adds three real tools backed by live, keyless
open data, a ranking engine, deep-link builders and a Desktop page:

| Tool | What it does | Sources |
|---|---|---|
| `find_stay` | Named hotels, hostels, guest houses, motels, serviced apartments and chalets near an address / place / `lat,lng`. Default 3 km, auto-widens **3→6→10 km** if fewer than ~5 are found (and says so). Optional `stay_type`, `check_in`/`check_out` (only prefill Booking/Airbnb links). | Nominatim, Overpass, OSRM |
| `find_ride` | Pickup → dropoff (airports prefer aerodrome/IATA; roads rejected when an airport was asked for): OSRM road distance/duration, walking time if under ~2.5 km, Get an Uber / Lyft / Directions links. For "ride to airport A, stay near airport B" call `find_ride` + `find_stay` separately. | Nominatim, OSRM |
| `plan_night` | **Stranded mode.** Where you are now (+ optional area to sleep in) → nearby stays ranked by OSRM driving time from you, walking time when close, a top pick, ride links from you to *each* stay and book links for each stay. Auto-widens 3→6→10 km when thin. | Nominatim, Overpass, OSRM |

Every handler returns a JSON string with `formatted_output` (Markdown for chat) and
`data`, including an `evidence` array: `{source, host, url, what, ok | error}` for
every request made. Errors come back as `{"error": ..., "data": null}`.

Not a clone of existing catalog entries: `letsfg`, `maqami-travel`, `pricewin` and
`viajante` are flight/hotel price search; `solverforge-routing` is a multi-stop trip
planner. None is a last-minute ride + room SOS with ride-hail deep links, OSM lodging,
OSRM ETAs and a consumer listing UI.

## What you see

- **Chat (any Hermes surface):** ranked list with drive/walk times and links.
- **Hermes Desktop:** a **Nightstop** sidebar page (`/nightstop`) with Tonight / Stay /
  Ride tabs, listing cards, a stay detail view and ride option cards — a light,
  consumer UI. It calls this plugin's own backend (`/api/plugins/nightstop/*`).
- **Standalone HTML report** (no Hermes needed) from the CLI — same look.

Card visuals are an honest **locator**: the stay's real position relative to you,
drawn from OpenStreetMap coordinates. It is not a photo and not a map tile;
OSM has no room photos, so Nightstop doesn't fake any.

What each field means:

| Field | Source / meaning |
|---|---|
| Name, type, address, stars, phone, website, opening hours, operator/brand, rooms, wheelchair, internet | Only the OSM tags on that element. Missing tag → not shown. Stars are labelled "OSM tag". |
| Drive time / road distance | OSRM `router.project-osrm.org` table/route, car profile, **no live traffic**. "Route unavailable" if OSRM fails — never estimated. |
| Walk time | OSRM foot profile at `routing.openstreetmap.de` for stays within ~2.5 km straight line. |
| Straight line | Plain haversine geometry between coordinates, always labelled "straight line". |
| Price | Always `null` + "Price on Booking / Airbnb — OpenStreetMap has no nightly rates". |
| Top pick | Shortest OSRM driving time from your origin (or closest straight-line if OSRM was down — labelled). |
| Closest on foot | Shortest OSRM walking time, when it isn't already the top pick. |

Likely duplicate OSM entries (same/prefix name within 150 m — e.g. a hotel mapped
as both a node and a building) are merged; the extra ids are kept in `also_mapped_as`.
Residential `building=apartments` blocks are never treated as stays; only
`tourism=hotel|hostel|guest_house|motel|apartment|chalet` and `amenity=hotel` with a
name are used.

## Quick start (no Hermes, no keys)

Needs Python 3.10+ and nothing else (stdlib only).

```bash
cd nightstop
python3 run.py night "Lisbon airport" --html night.html
python3 run.py stay "Berlin Hauptbahnhof" --html stay.html
python3 run.py ride "Berlin Hbf" "Berlin Brandenburg Airport" --html ride.html
python3 run.py night "52.5250,13.3694" --area "Mitte, Berlin" --type hostel --check-in 2026-11-10 --check-out 2026-11-11 --json out.json
```

Options: `--radius-km`, `--type hotel|hostel|guest_house|motel|apartment|chalet`,
`--check-in/--check-out YYYY-MM-DD`, `--limit`, `--json FILE`, `--html FILE`,
`--view full|list|detail`. The HTML is a self-contained static snapshot: no scripts,
images, fonts or network calls; the buttons are plain links.

A full lookup usually takes 20–60 s because the public Overpass server is shared and
sometimes slow. When it returns 429/502/503/504 or times out, Nightstop retries once
after 4 s, then tries the `overpass.kumi.systems` mirror. If both fail you get a clear
error, never made-up results.

## Install in Hermes

Follows the official [plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins),
[Desktop SDK](https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk) and
[catalog rules](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission).
No Hermes core code or app markup is patched.

1. Validate (same check the catalog CI runs):
   ```bash
   hermes plugins validate /path/to/nightstop --install-deps
   ```
2. For the Desktop page's backend, install the shared package into **the same Python
   environment Hermes runs in** (no runtime dependencies):
   ```bash
   python -m pip install /path/to/nightstop
   ```
   Not needed for the chat tools or the CLI.
3. Link the plugin folder and enable it:
   ```bash
   mkdir -p "${HERMES_HOME:-$HOME/.hermes}/plugins"
   ln -s /path/to/nightstop "${HERMES_HOME:-$HOME/.hermes}/plugins/nightstop"
   hermes plugins enable nightstop
   ```
   Restart Hermes / the gateway as your version requires.
4. In Hermes Desktop: **Capabilities → Plugins → Rescan**, enable **Nightstop**, then
   click **Nightstop** in the sidebar.
5. Or just ask Hermes: *"I just landed at Lisbon airport, it's 1am and I have nowhere
   to sleep — use plan_night."*

`requires_hermes` is intentionally omitted until you confirm a floor on the Hermes
version you test with (catalog rule 14: never invent a too-new floor).

## External hosts (disclosure, catalog rule 13)

Nightstop sends the place names or coordinates you ask about to:

| Host | Why | Policy respected |
|---|---|---|
| `nominatim.openstreetmap.org` | geocode text to coordinates (skipped if you pass `lat,lng`) | ≤1 request/second (process-wide lock), descriptive User-Agent, multi-result ranking (airports prefer aeroway) |
| `overpass-api.de` | nearby lodging from OSM | one query per search (+1 if radius expands), one retry on overload |
| `overpass.kumi.systems` | Overpass fallback mirror | only if the primary fails |
| `router.project-osrm.org` | driving distance/duration (table + route) | one table call per search |
| `routing.openstreetmap.de` | walking distance/duration (OSRM foot) | one table call, only for close stays |
| `ipinfo.io` / `ipapi.co` | one-shot city-level approximate location **only** when the person asks for `my location` / `use_current_location` | never cached; see Privacy |

User-Agent: `Nightstop/0.1.2 (Hermes plugin; https://hermes-agent.nousresearch.com)`.
HTTPS only, allowlisted hosts only, redirects refused, 8 MB response cap, ~200 s
budget per call. **Returned but never contacted:** `m.uber.com`, `lyft.com`,
`www.google.com/maps`, `www.booking.com`, `www.airbnb.com`, `www.openstreetmap.org`,
`tel:` links. No scraping of Booking/Airbnb/Uber/Lyft. No API keys, no credentials,
no `.env` reads, no telemetry, no background processes, no self-updater, no compiled
binaries. The CLI writes files only where you pass `--json` / `--html`. Location
queries are sensitive: the hosts above see what you searched.

The OSRM demo server and FOSSGIS routing are free community services meant for light
use; heavy/commercial use should point at your own OSRM/Overpass instance.


## Privacy (location)

Nightstop never tracks you in the background.

- **Explicit only.** Approximate location is fetched only when that call passes
  `use_current_location: true` or a place string like `my location` / `here` /
  `current location`. Otherwise no IP lookup runs.
- **One-shot.** The lookup runs for that single tool call, then the coordinates live
  only in that response. They are **not** cached in memory across calls, **not**
  written to disk, `ctx.state`, logs, or `plugin_data`, and there is **no** background
  polling or reuse on later turns.
- **Minimal sharing.** The approximate coordinates are sent only to the routing /
  geocode / lodging hosts needed for *that* search (Nominatim / Overpass / OSRM as
  usual). The raw IP is not kept on the result object and is not logged.
- **Honest label.** Results include a `location_privacy` note such as
  *"Used once for this search, not stored."* Confidence is `low` (city-level, not GPS);
  confirm the city with the person before relying on it for a pickup.
- Exact `lat,lng` and Google Maps links/pins are treated as user-supplied coordinates
  (no IP lookup).

## Tests

```bash
python3 -m unittest discover -s tests -v       # offline; HTTP mocked with real captured fixtures
node --input-type=module --check < desktop/plugin.js
python3 scripts/live_smoke.py                  # real keyless run → live/*.json|md|html + summary.json
```

`tests/fixtures/*.json` are small real responses saved from Nominatim, Overpass and OSRM
by `scripts/capture_fixtures.py` (Berlin Hauptbahnhof). FastAPI backend tests skip
cleanly if `fastapi`/`httpx` aren't installed.

## Files

- `plugin.yaml`, `__init__.py` — manifest + side-effect-free `register(ctx)` (toolset `nightstop`).
- `nightstop/` — `sources.py` (HTTP, geocode, Overpass, OSRM, deep links), `engine.py`,
  `schemas.py`, `tools.py`, `render.py` (Markdown + HTML), `cli.py`.
- `desktop/plugin.js` — Desktop SDK page + sidebar item (only `@hermes/plugin-sdk` + `react`).
- `dashboard/manifest.json`, `dashboard/plugin_api.py` — backend routes `/stay`, `/ride`, `/night`.
- `run.py`, `pyproject.toml`, `LICENSE` (MIT).
- `tests/`, `scripts/`, `live/` (real run outputs), `previews/` (screenshots + HTML).
- `DEMO.md` (90-second X demo script), `SUBMISSION.md` (catalog PR + demo + form checklist).

## Attribution

Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors,
available under the ODbL. Routing by [OSRM](https://project-osrm.org/) (demo server)
and [FOSSGIS](https://routing.openstreetmap.de/) foot routing. Uber, Lyft, Booking.com,
Airbnb and Google Maps are trademarks of their owners; Nightstop is not affiliated with
them and only builds links to their public pages/apps.
