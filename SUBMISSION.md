# Hackathon submission checklist — Nightstop

Nous Research Hermes Agent Plugin Hackathon. **Deadline: 5 PM EST = 11:00 PM WAT,
Tuesday 11 Nov 2026.**

Nothing below has been done for you: no git repo, remote, pull request, X post or
form submission was created by this build. You do each step yourself.

You need three things:

1. **A public GitHub (or GitLab) repo + a catalog pull request**
2. **A demo video on X under 90 seconds that tags @NousResearch**
3. **The submission form** — https://form.typeform.com/to/FwJLvOln
   (you can submit it **as soon as the PR is open**; you don't have to wait for it to merge)

## 1. Repo

- Create a public repo you own (e.g. `github.com/<you>/nightstop`) and push this folder's
  contents at the repo root. Leave out `refs/` (style references), `__pycache__/`, `.pyc`,
  `build/`, `*.egg-info` (`.gitignore` already covers the generated ones).
- Install Hermes and run, on the exact commit you will pin:
  ```bash
  hermes plugins validate /path/to/nightstop --install-deps
  ```
  Fix every failure; read the warnings. (Not run on the build box — no Hermes CLI there.)
- Enable it in Hermes (README → Install) and try all three tools + the Desktop page once.
- Optional: once you know your Hermes version, add the same SemVer floor
  (e.g. `requires_hermes: ">=X.Y.Z"`) to both `plugin.yaml` and the catalog entry.
  Never a date, never newer than the current release.

## 2. Catalog pull request

Per https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission :

- Fork `NousResearch/hermes-agent` and add **one file**: `plugin-catalog/nightstop.yaml`.
  A ready draft is in `catalog/nightstop.yaml` — fill in your real `repo` URL and the
  full 40-character `sha` of the commit you validated. Keep `version: "0.1.1"` quoted.
- PR description (rule 13 disclosure) — paste and adapt:

  > **Nightstop** — last-minute ride + room SOS for Hermes. Registers three tools
  > (`find_stay`, `find_ride`, `plan_night`) on toolset `nightstop`, a Desktop SDK route
  > `/nightstop` + sidebar item, and a `dashboard/plugin_api.py` backend
  > (`/api/plugins/nightstop/{stay,ride,night}`).
  > **Network:** sends user-requested place names/coordinates to
  > nominatim.openstreetmap.org (≤1 req/s), overpass-api.de (fallback
  > overpass.kumi.systems), router.project-osrm.org and routing.openstreetmap.de.
  > Returns (does not contact) m.uber.com, lyft.com, google.com/maps, booking.com,
  > airbnb.com and openstreetmap.org links.
  > No API keys, no credentials, no file reads outside the plugin, no shell commands,
  > no background processes, no telemetry, no self-updater, no binaries. Python stdlib only.
  > Cannot log in or pay: booking/ride happens in the third-party app.
  > Screenshots: (attach `previews/*.png` and a real Hermes Desktop screenshot).

- Wait for the catalog CI to go green.

## 3. Demo on X (< 90 s, tag @NousResearch)

Follow `DEMO.md`. Record Hermes actually running `plan_night` (plus the Desktop page if
you installed it). Post it on X tagging **@NousResearch**, e.g.:

> Stuck somewhere at 1am with nowhere to sleep? Built Nightstop for the Hermes plugin
> hackathon @NousResearch — real nearby stays from OpenStreetMap ranked by actual drive
> time, one tap to Uber/Lyft/Booking/Airbnb. No fake prices. [PR link]

## 4. Form

Open https://form.typeform.com/to/FwJLvOln and submit your **PR link** and **X demo link**.
Submit as soon as the PR is open.

Questions: Nous Research Discord https://discord.com/invite/nousresearch (they open a
thread per entry when submissions close).

Docs read during the build:
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
- https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
- `plugin-catalog/README.md` entry schema in NousResearch/hermes-agent (main, 9 Nov 2026)
