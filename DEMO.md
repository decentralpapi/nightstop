# 90-second X demo — Nightstop (stranded mode)

**Post must tag @NousResearch** and stay under 90 seconds.

Everything named below came from the real keyless run saved in `live/` on
**9 Nov 2026, ~07:13–07:19 WAT** (`live/summary.json`). OpenStreetMap and OSRM change, so
**re-run right before recording** (`python3 scripts/live_smoke.py lisbon-night lagos-night`)
and read the numbers off your fresh output, not off this script. Never type a hotel,
price or time that the tool didn't return.

Backup: if the public Overpass server is slow during recording (it sometimes returns
502/504), use the saved `live/lisbon-night.html` / `live/lagos-night.html` and say they
are saved runs from earlier that day.

---

**0–10 s — The problem.** Phone-style framing, dark room vibe.
> "It's 1am, you just landed, your booking fell through and you have nowhere to sleep.
> This is Nightstop, a Hermes plugin."

**10–35 s — Stranded mode in Hermes.** Type in Hermes chat:
> "I just landed at Lisbon airport, it's late and I have nowhere to sleep. Use plan_night."

Show the tool call and the reply. In our run: origin **Aeroporto Humberto Delgado**,
**21** mapped stays within 3 km, top pick **Holiday Inn Express Lisbon Airport —
4 min drive, 1.4 km by road** (OSRM), then Plaza Lisbon, Alojamentos da Praça,
B&B Hotel Lisboa Aeroporto, Stay Hotel Lisboa Aeroporto, Lisbon Hostel Terminal 4…
> "Real places from OpenStreetMap, ranked by real driving time from where I'm standing."

**35–55 s — Desktop page.** Open **Nightstop** in the Hermes Desktop sidebar (or the
saved HTML report). Show the listing cards, tap the top pick → detail view: drive and
walk chips, details from OSM, "Get a ride" / "See rooms".
> "No fake prices, no fake reviews. OSM doesn't know nightly rates, so it says so and
> sends me to Booking or Airbnb with the area prefilled."

**55–72 s — One tap to a ride.** Click **Get a ride** → Uber opens with pickup at the
airport and dropoff at the hotel already set. (Do not complete a booking on camera
unless you mean to; Nightstop doesn't book or pay — the app does.)
> "Pickup and dropoff are prefilled. I confirm and pay in Uber. Nightstop never logs in
> or charges anything."

**72–85 s — Works at home too.** Switch to Lagos: "Murtala Muhammed Airport" → our run
found **14** stays within 3 km; top pick **Ehi Guest House, 4 min drive (2.4 km)**,
plus Haute Aparthotel, Best Western Plus Lagos Ikeja, Radisson, Hyatt Regency Lagos Ikeja
(★5 as tagged in OSM). Or `find_ride` Berlin Hbf → BER: **40 min, 27.1 km by road**.

**85–90 s — Close.**
> "Nightstop: a ride and a bed, tonight. Open data, honest limits. Built for the Hermes
> plugin hackathon @NousResearch."

Suggested post text:
> Stuck somewhere at 1am with nowhere to sleep? Nightstop for Hermes finds real nearby
> stays (OpenStreetMap), ranks them by actual drive time (OSRM) and opens Uber/Lyft/
> Booking/Airbnb with everything prefilled. No fake prices. @NousResearch #HermesAgent
