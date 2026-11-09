"""Markdown + self-contained static HTML (light consumer UI). Zero network calls from the HTML."""
from __future__ import annotations

import html
import math

from .engine import fmt_distance, fmt_duration

E = html.escape


# ------------------------------------------------------------------ markdown
def _stay_md(s):
    drive = "%s drive (%s by road)" % (fmt_duration(s["drive"]["duration_s"]), fmt_distance(s["drive"]["distance_m"])) if s.get("drive") else "driving time unavailable"
    bits = [f"**{s['rank'] if 'rank' in s else '•'}. {s['name']}** — {s['type_label']} · {drive}"]
    if s.get("walk"):
        bits[0] += " · %s walk" % fmt_duration(s["walk"]["duration_s"])
    meta = []
    if s.get("address"):
        meta.append(s["address"])
    meta.append("%s straight line" % fmt_distance(s.get("straight_line_m")))
    if s.get("stars"):
        meta.append("%s stars (OSM tag)" % s["stars"])
    if s.get("operator") or s.get("brand"):
        meta.append("operator: %s" % (s.get("operator") or s.get("brand")))
    if s.get("phone"):
        meta.append("phone: %s" % s["phone"])
    bits.append("   " + " · ".join(meta))
    L = s.get("links", {})
    row = []
    for key, label in (("open_uber", "Get an Uber"), ("open_lyft", "Lyft"), ("directions", "Directions"),
                       ("check_booking", "Book on Booking.com"), ("check_airbnb", "Airbnb nearby"),
                       ("call", "Call"), ("website", "Hotel website")):
        if L.get(key):
            row.append("[%s](%s)" % (label, L[key]))
    bits.append("   " + " · ".join(row))
    bits.append("   Price: %s" % s["price_note"])
    return "\n".join(bits)


def markdown(d):
    out = []
    if d["kind"] == "ride":
        a, b = d["pickup"], d["dropoff"]
        out.append(f"### Ride: {a['label']} → {b['label']}")
        if d.get("drive"):
            out.append("- Driving: **%s**, %s by road (OSRM, no live traffic)" % (fmt_duration(d["drive"]["duration_s"]), fmt_distance(d["drive"]["distance_m"])))
        if d.get("walk"):
            out.append("- Walking: %s, %s" % (fmt_duration(d["walk"]["duration_s"]), fmt_distance(d["walk"]["distance_m"])))
        L = d["links"]
        out.append("- [Get an Uber](%s) · [Lyft](%s) · [Directions](%s)" % (L["open_uber"], L["open_lyft"], L["open_maps"]))
        out.append("- Fares and pickup wait appear in the ride app.")
    else:
        where = d.get("origin") or d.get("center")
        title = "Tonight near" if d["kind"] == "night" else "Places to stay near"
        out.append(f"### {title} {where['label']}")
        if d.get("area"):
            out.append("Searching around %s; times measured from %s." % (d["area"]["label"], where["label"]))
        out.append("%d mapped stay(s) within %g km; showing %d, ranked by OSRM driving time." % (d["found_total"], d["radius_km"], len(d["stays"])))
        AL = d.get("area_links") or {}
        area_row = []
        if AL.get("check_booking"):
            area_row.append("[Book on Booking.com](%s)" % AL["check_booking"])
        if AL.get("check_airbnb"):
            area_row.append("[Airbnb nearby](%s)" % AL["check_airbnb"])
        if area_row:
            out.append("Area search: " + " · ".join(area_row))
        if d.get("top_pick"):
            out.append("**Top pick:** %s — %s." % (d["top_pick"]["name"], d["top_pick"]["why"].lower()))
        if d.get("nearest_on_foot"):
            out.append("**Closest on foot:** %s — %s walk (OSRM foot)." % (d["nearest_on_foot"]["name"], fmt_duration(d["nearest_on_foot"]["walk_s"])))
        out.append("")
        out.extend(_stay_md(s) for s in d["stays"])
    for w in d.get("warnings", []):
        out.append("> ⚠ " + w)
    out.append("")
    out.append("_" + d["honesty"] + "_")
    out.append("_%s Fetched %s._" % (d["attribution"], d["fetched_at"]))
    return "\n".join(out)


PRESENTATION_HINT = (
    "Present this result using reply_markdown (or formatted_output). "
    "Show every link as its short markdown label only — "
    "[Book on Booking.com](url), [Hotel website](url), [Get an Uber](url), "
    "[Lyft](url), [Directions](url), [Airbnb nearby](url). "
    "Never paste raw URLs into the chat. Do not invent prices, availability, "
    "reviews, or ETAs beyond the OSRM times given. Say availability is not "
    "confirmed and that no booking has been made."
)


def reply_markdown(d):
    """Hermes-facing markdown with short labeled links (never paste raw URLs)."""
    return markdown(d)


# ------------------------------------------------------------------ html helpers
def _href(u):
    return E(u) if isinstance(u, str) and u.startswith(("https://", "tel:")) else "#"


def _btn(label, url, primary=False, small=False):
    if not url:
        return ""
    cls = "btn" + (" primary" if primary else "") + (" small" if small else "")
    return f'<a class="{cls}" href="{_href(url)}" target="_blank" rel="noopener noreferrer">{E(label)}</a>'


def _project(origin, pts, w, h, pad=34):
    """Real coordinates -> SVG x,y (equirectangular around origin)."""
    k = math.cos(math.radians(origin["lat"]))
    xy = [((p["lng"] - origin["lng"]) * k, (p["lat"] - origin["lat"])) for p in pts]
    span = max([abs(x) for x, _ in xy] + [abs(y) for _, y in xy] + [1e-4])
    sx, sy = (w / 2 - pad) / span, (h / 2 - pad) / span
    s = min(sx, sy)
    return [(w / 2 + x * s, h / 2 - y * s) for x, y in xy]


def locator_svg(origin, stay, others=(), w=420, h=240, label_origin="You"):
    """Honest preview: real relative position of the stay vs origin. Not a photo, not a map tile."""
    pts = [stay] + list(others)
    proj = _project(origin, pts, w, h)
    sx, sy = proj[0]
    ox, oy = w / 2, h / 2
    grid = "".join(f'<line x1="{x}" y1="0" x2="{x}" y2="{h}"/>' for x in range(0, w + 1, 30)) + \
           "".join(f'<line x1="0" y1="{y}" x2="{w}" y2="{y}"/>' for y in range(0, h + 1, 30))
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#c9ccd3"/>' for x, y in proj[1:])
    return (f'<svg class="loc" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" role="img" '
            f'aria-label="{E(stay["name"])} relative to {E(label_origin)}">'
            f'<rect width="{w}" height="{h}" fill="#eceef1"/><g stroke="#e0e3e8" stroke-width="1">{grid}</g>{dots}'
            f'<line x1="{ox}" y1="{oy}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="#111" stroke-width="1.6" stroke-dasharray="4 5"/>'
            f'<circle cx="{ox}" cy="{oy}" r="9" fill="#fff" stroke="#111" stroke-width="2.5"/><circle cx="{ox}" cy="{oy}" r="3.5" fill="#111"/>'
            f'<g transform="translate({sx:.1f},{sy:.1f})"><path d="M0 0 C-11 -14 -11 -28 0 -28 C11 -28 11 -14 0 0Z" fill="#111"/>'
            f'<circle cy="-19" r="4.2" fill="#fff"/></g></svg>')


CSS = """
*{box-sizing:border-box}body{margin:0;background:#f5f5f6;color:#111;font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
a{color:inherit}.wrap{max-width:1080px;margin:0 auto;padding:22px 20px 60px}
.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}
.logo{display:flex;align-items:center;gap:9px;font-weight:650;font-size:18px;letter-spacing:-.3px}
.logo i{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#111;color:#fff;font-style:normal;font-size:14px}
.muted{color:#6b6f76}.tiny{font-size:12px}.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid #e3e4e8;background:#fff;border-radius:999px;padding:6px 13px;font-size:13px}
.chip.dark{background:#111;color:#fff;border-color:#111}.chips{display:flex;flex-wrap:wrap;gap:8px}
.crumb{font-size:12px;color:#6b6f76;margin:4px 0 14px}
.card{background:#fff;border-radius:22px;box-shadow:0 1px 2px rgba(0,0,0,.04),0 12px 32px rgba(17,17,17,.06)}
.hero{display:grid;grid-template-columns:1.15fr 1fr;gap:26px;margin-bottom:34px}
.hero .vis{position:relative;border-radius:22px;overflow:hidden;min-height:340px;background:#eceef1}
.hero .vis svg{position:absolute;inset:0;width:100%;height:100%}
.badge{position:absolute;top:14px;left:14px;background:#fff;border-radius:999px;padding:6px 12px;font-size:12px;font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.attr{position:absolute;right:10px;bottom:8px;font-size:10px;color:#6b6f76;background:rgba(255,255,255,.8);padding:2px 6px;border-radius:6px}
h1{font-size:28px;letter-spacing:-.6px;margin:12px 0 4px;line-height:1.15}h2{font-size:22px;letter-spacing:-.4px;margin:0 0 14px}
.big{font-size:30px;font-weight:700;letter-spacing:-.8px;margin:10px 0 2px}
.note{display:inline-block;border:1px solid #e3e4e8;border-radius:999px;padding:5px 12px;font-size:12px;color:#55595f;margin:8px 0 14px}
.btn{display:inline-flex;justify-content:center;align-items:center;gap:6px;text-decoration:none;border:1px solid #dedfe3;background:#fff;color:#111;border-radius:999px;padding:12px 18px;font-weight:600;font-size:14px;white-space:nowrap}
.btn.primary{background:#111;color:#fff;border-color:#111}.btn.small{padding:8px 13px;font-size:13px}
.cta{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 16px}.cta .primary{flex:1;min-width:180px}
details.sec{border:1px solid #ececef;border-radius:16px;padding:12px 16px;margin-top:10px;background:#fff}
details.sec summary{cursor:pointer;font-weight:600;list-style:none;display:flex;justify-content:space-between}
details.sec summary::after{content:"⌄";color:#6b6f76}details.sec[open] summary::after{content:"⌃"}
.kv{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 18px;margin-top:12px}
.kv>div{display:flex;gap:10px;align-items:flex-start;min-width:0}.kv b{display:block;font-size:12px;color:#6b6f76;font-weight:500}
.kv span.ic{flex:0 0 30px;height:30px;border-radius:50%;background:#f1f2f4;display:grid;place-items:center;font-size:13px}
.kv div>div{overflow-wrap:anywhere;font-size:13.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px}
.lc{position:relative;border-radius:22px;overflow:hidden;background:#fff;box-shadow:0 14px 34px rgba(17,17,17,.10);display:flex;flex-direction:column}
.lc .vis{position:relative;height:210px;background:#eceef1}.lc .vis svg{position:absolute;inset:0;width:100%;height:100%}
.lc .panel{background:linear-gradient(180deg,#2b3038,#1d2127);color:#fff;padding:16px 18px 14px}
.lc .eta{font-size:23px;font-weight:700;letter-spacing:-.5px}.lc .row{display:flex;gap:14px;align-items:flex-end;margin-top:6px}
.lc .name{flex:1;min-width:0;font-size:13.5px}.lc .name div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lc .stat{text-align:center;font-size:13px;padding-left:12px;border-left:1px solid rgba(255,255,255,.18)}
.lc .foot{border-top:1px solid rgba(255,255,255,.14);margin-top:12px;padding-top:10px;font-size:12px;color:#b9bec7;display:flex;justify-content:space-between;gap:8px}
.lc .acts{display:flex;gap:8px;flex-wrap:wrap;padding:12px 14px 14px}
.lc .acts .btn{flex:1}
.ride-hero{padding:26px;margin-bottom:22px}.route{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:6px}
.route .pt{display:flex;gap:8px;align-items:center;font-weight:500;font-size:14px}.dot{width:12px;height:12px;border-radius:50%;border:3px solid #111;background:#fff}.dot.fill{background:#111}
.rides{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:18px}
.pc{padding:12px;border-radius:26px}.pc .face{border-radius:18px;background:#eceef1;height:170px;display:grid;place-items:center;text-align:center;position:relative;overflow:hidden}
.pc .face .nm{font-size:24px;letter-spacing:-.5px;font-weight:500}.pc .face .st{font-size:13px;color:#55595f;margin-top:3px}
.pc .bot{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 4px 4px}
.av{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:700;position:relative}
.warn{background:#fff8e6;border:1px solid #f3e2b3;border-radius:14px;padding:10px 14px;font-size:13px;margin:8px 0}
.honest{font-size:12.5px;color:#55595f;background:#fff;border-radius:16px;padding:14px 16px;margin-top:26px;border:1px solid #ececef}
.ev{font-size:12px}.ev td{padding:5px 8px;border-top:1px solid #f0f0f2;vertical-align:top;overflow-wrap:anywhere}
.section-h{display:flex;justify-content:space-between;align-items:baseline;margin:6px 0 14px}
@media (max-width:760px){.hero{grid-template-columns:1fr}.hero .vis{min-height:250px}.kv{grid-template-columns:1fr}h1{font-size:24px}}
"""


def _page(title, body):
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\">"
            f"<title>{E(title)}</title><style>{CSS}</style></head><body><div class=wrap>"
            '<div class=top><div class=logo><i>N</i>Nightstop</div><div class="chips"><span class=chip>Stay</span><span class=chip>Ride</span><span class="chip dark">Tonight</span></div></div>'
            f"{body}</div></body></html>")


def _drive_txt(s):
    return fmt_duration(s["drive"]["duration_s"]) + " drive" if s.get("drive") else "Route unavailable"


def _detail(d, s, origin, all_stays):
    L = s.get("links", {})
    chips = [f'<span class="chip dark">🚗 {E(_drive_txt(s))}</span>']
    if s.get("walk"):
        chips.append(f'<span class=chip>🚶 {E(fmt_duration(s["walk"]["duration_s"]))} walk</span>')
    chips.append(f'<span class=chip>{E(fmt_distance(s.get("straight_line_m")))} straight line</span>')
    if s.get("stars"):
        chips.append(f'<span class=chip>★ {E(str(s["stars"]))} stars · OSM tag</span>')
    facts = [("📍", "Address", s.get("address") or "Not tagged in OSM"), ("🏷", "Type", s["type_label"])]
    for ic, k, key in (("🏢", "Operator", "operator"), ("🔖", "Brand", "brand"), ("☎", "Phone", "phone"),
                       ("🕑", "Opening hours", "opening_hours"), ("🛏", "Rooms", "rooms"), ("♿", "Wheelchair", "wheelchair"),
                       ("📶", "Internet", "internet_access")):
        if s.get(key):
            facts.append((ic, k, s[key]))
    if s.get("website"):
        facts.append(("🌐", "Website", s["website"]))
    kv = "".join(f'<div><span class=ic>{ic}</span><div><b>{E(k)}</b>{E(str(v))}</div></div>' for ic, k, v in facts)
    route_kv = ""
    if s.get("drive"):
        route_kv += f'<div><span class=ic>🚗</span><div><b>Driving (OSRM)</b>{E(fmt_duration(s["drive"]["duration_s"]))} · {E(fmt_distance(s["drive"]["distance_m"]))} by road</div></div>'
    if s.get("walk"):
        route_kv += f'<div><span class=ic>🚶</span><div><b>Walking (OSRM foot)</b>{E(fmt_duration(s["walk"]["duration_s"]))} · {E(fmt_distance(s["walk"]["distance_m"]))}</div></div>'
    if not route_kv:
        route_kv = '<div><span class=ic>!</span><div><b>Route</b>Unavailable from OSRM for this stay</div></div>'
    route_kv += '<div><span class=ic>⏱</span><div><b>Traffic</b>Not included — road-network estimate</div></div>'
    others = [o for o in all_stays if o is not s]
    pick = '<span class=badge>★ Top pick · fastest drive</span>' if s.get("rank") == 1 and s.get("drive") else f'<span class=badge>{E(s["type_label"])}</span>'
    return f"""
<div class=crumb>← Tonight · {E(origin['label'])} · Stay details</div>
<section class=hero>
  <div class=vis>{locator_svg(origin, s, others, 560, 420, origin['label'])}{pick}<span class=attr>Position from © OpenStreetMap contributors · not a photo</span></div>
  <div>
    <span class=chip>{E(s['type_label'])}{' · ' + E(s.get('operator') or s.get('brand')) if (s.get('operator') or s.get('brand')) else ''}</span>
    <h1>{E(s['name'])}</h1>
    <div class=big>{E(_drive_txt(s))}{(' · ' + E(fmt_distance(s['drive']['distance_m']))) if s.get('drive') else ''}</div>
    <div class="muted tiny">from {E(origin['label'])} · price on Booking / Airbnb (OSM has no nightly rates)</div>
    <div class=note>🕑 Checked {E(d['fetched_at'])} · availability not known until you check</div>
    <div class=muted style="font-size:12px;margin-bottom:6px">Getting there</div>
    <div class=chips style="margin-bottom:16px">{''.join(chips)}</div>
    <div class=cta>{_btn('Get a ride', L.get('open_uber'), True)}{_btn('See rooms', L.get('check_booking'))}</div>
    <div class=chips>{_btn('Open Lyft', L.get('open_lyft'), small=True)}{_btn('Open maps', L.get('directions') or L.get('open_maps'), small=True)}{_btn('Check Airbnb', L.get('check_airbnb'), small=True)}{_btn('Call', L.get('call'), small=True)}</div>
    <details class=sec open><summary>Details from OpenStreetMap</summary><div class=kv>{kv}</div></details>
    <details class=sec open><summary>Getting there</summary><div class=kv>{route_kv}</div></details>
    <details class=sec><summary>Booking &amp; payment</summary><p class="tiny muted">{E(d['honesty'])}</p></details>
  </div>
</section>"""


def _card(s, origin, all_stays):
    L = s.get("links", {})
    who = s.get("operator") or s.get("brand")
    foot_l = f"Operator: {E(who)}" if who else f"Mapped in OSM · {E(s['id'])}"
    stat2 = (f'<div class=stat>{E(fmt_distance(s["drive"]["distance_m"]))}<br>road</div>' if s.get("drive")
             else f'<div class=stat>{E(fmt_distance(s.get("straight_line_m")))}<br>straight</div>')
    stat3 = f'<div class=stat>★ {E(str(s["stars"]))}<br>stars</div>' if s.get("stars") else (
        f'<div class=stat>{E(fmt_duration(s["walk"]["duration_s"]))}<br>walk</div>' if s.get("walk") else "")
    badge = '<span class=badge>★ Top pick</span>' if s.get("rank") == 1 and s.get("drive") else f'<span class=badge>{E(s["type_label"])}</span>'
    others = [o for o in all_stays if o is not s]
    return f"""<article class=lc id="stay-{s.get('rank', 0)}">
<div class=vis>{locator_svg(origin, s, others, 420, 210, origin['label'])}{badge}</div>
<div class=panel><div class=eta>{E(_drive_txt(s))}</div>
<div class=row><div class=name><div><b>{E(s['name'])}</b></div><div>{E(s.get('address') or s['type_label'] + ' · address not tagged')}</div></div>{stat2}{stat3}</div>
<div class=foot><span>{foot_l}</span><span>{E(s['type_label'])}</span></div></div>
<div class=acts>{_btn('Get a ride', L.get('open_uber'), True, True)}{_btn('See rooms', L.get('check_booking'), small=True)}{_btn('Check Airbnb', L.get('check_airbnb'), small=True)}{_btn('Call', L.get('call'), small=True)}</div>
</article>"""


def _footer(d):
    warn = "".join(f'<div class=warn>⚠ {E(w)}</div>' for w in d.get("warnings", []))
    rows = "".join(f'<tr><td>{"✅" if e.get("ok") else "❌"}</td><td>{E(e.get("source", ""))}</td><td>{E(e.get("host", ""))}</td><td>{E(e.get("what", ""))}{(" — " + E(e["error"])) if e.get("error") else ""}</td></tr>'
                   for e in d.get("evidence", []))
    return (f"{warn}<div class=honest><b>Honest limits.</b> {E(d['honesty'])}<br>{E(d['attribution'])} Generated {E(d['fetched_at'])}. "
            "This page is a static snapshot and makes no network calls; buttons open the listed apps/sites.</div>"
            f'<details class=sec><summary>Evidence &amp; sources ({len(d.get("evidence", []))} requests)</summary><table class=ev>{rows}</table></details>')


def _short(p):
    return ", ".join(x.strip() for x in (p.get("display_name") or p.get("label") or "").split(",")[:3])


def _ride_cards(a, b, L, drive):
    dur = fmt_duration(drive["duration_s"]) + " drive" if drive else "Route unavailable"
    opts = [("Uber", "U", "#111", "Opens Uber with pickup + dropoff set", L.get("open_uber"), "Open Uber"),
            ("Lyft", "L", "#ff00bf", "Opens Lyft with pickup + destination set", L.get("open_lyft"), "Open Lyft"),
            ("Maps", "M", "#1a73e8", "Turn-by-turn in Google Maps", L.get("open_maps") or L.get("directions"), "Open maps")]
    return "".join(f"""<article class="card pc"><div class=face><div><div class=nm>{E(n)}</div><div class=st>🚗 {E(dur)} · OSRM estimate</div>
<div class=st style="margin-top:10px;font-size:12px">{E(st)}</div></div></div>
<div class=bot><div style="display:flex;gap:10px;align-items:center"><span class=av style="background:{c}">{l}</span><div><div style="font-weight:600;font-size:14px">{E(n)}</div><div class="muted tiny">Fare &amp; wait shown in app</div></div></div>
{_btn('+ ' + cta, u, True, True)}</div></article>""" for n, l, c, st, u, cta in opts if u)


def html_report(d, view="full"):
    if d["kind"] == "ride":
        a, b = d["pickup"], d["dropoff"]
        dr = d.get("drive")
        big = (fmt_duration(dr["duration_s"]) + " · " + fmt_distance(dr["distance_m"]) + " by road") if dr else "Driving route unavailable"
        walk = f'<span class=chip>🚶 {E(fmt_duration(d["walk"]["duration_s"]))} walk · {E(fmt_distance(d["walk"]["distance_m"]))}</span>' if d.get("walk") else ""
        body = f"""<div class=crumb>← Ride</div><section class="card ride-hero"><span class=chip>Get a ride</span>
<h1>{E(a['label'])} → {E(b['label'])}</h1><div class=big>{E(big)}</div>
<div class=route><div class=pt><span class=dot></span>{E(_short(a))}</div><span class=muted>→</span><div class=pt><span class="dot fill"></span>{E(_short(b))}</div></div>
<div class=note>🕑 Checked {E(d['fetched_at'])} · no live traffic · {E(fmt_distance(d['straight_line_m']))} straight line</div>
<div class=chips>{walk}</div>
<div class=cta style="margin-top:14px">{_btn('Get a ride', d['links']['open_uber'], True)}{_btn('Open Lyft', d['links']['open_lyft'])}{_btn('Open maps', d['links']['open_maps'])}</div></section>
<div class=section-h><h2>Ride options</h2><span class="muted tiny">Opens the app — you confirm and pay there</span></div>
<div class=rides>{_ride_cards(a, b, d['links'], dr)}</div>"""
        return _page("Nightstop ride · %s → %s" % (a["label"], b["label"]), body + _footer(d))

    origin = d.get("origin") or d.get("center")
    stays = d["stays"]
    head = "Tonight near" if d["kind"] == "night" else "Places to stay near"
    sub = (f"Sleeping around {E(d['area']['label'])}; times from {E(origin['label'])}. " if d.get("area") else "")
    intro = (f'<div class=section-h><h2>{head} {E(origin["label"])}</h2><span class="muted tiny">{d["found_total"]} mapped within {d["radius_km"]:g} km · '
             f'showing {len(stays)} · ranked by OSRM driving time</span></div><p class="muted tiny" style="margin-top:-6px">{sub}{E(origin.get("display_name", ""))}</p>')
    if not stays:
        return _page("Nightstop", intro + '<div class="card" style="padding:22px">No named stays found in OpenStreetMap here. Try Check Booking / Check Airbnb for this area: '
                     + _btn("Check Booking", d["area_links"]["check_booking"], True, True) + " " + _btn("Check Airbnb", d["area_links"]["check_airbnb"], small=True) + "</div>" + _footer(d))
    detail = _detail(d, stays[0], origin, stays)
    if view == "detail":
        return _page("Nightstop · " + stays[0]["name"], detail + _footer(d))
    cards = "".join(_card(s, origin, stays) for s in stays)
    if view == "list":
        return _page("Nightstop · stays near " + origin["label"], intro + f"<div class=grid>{cards}</div>" + _footer(d))
    return _page("Nightstop · " + origin["label"], detail + '<div style="height:8px"></div>' + intro +
                 f"<div class=grid>{cards}</div>" + _footer(d))
