// Nightstop — Hermes Desktop page. Public SDK only (@hermes/plugin-sdk + react).
// Data comes from this plugin's own backend (/api/plugins/nightstop/*). Nothing is invented:
// no prices, reviews, photos or availability. Buttons open Uber/Lyft/Maps/Booking/Airbnb externally.
import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { createElement as h, useState } from 'react'

const font = '-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif'
const page = { background: '#f5f5f6', color: '#111', minHeight: '100%', padding: '22px 20px 48px', fontFamily: font, overflow: 'auto' }
const card = { background: '#fff', borderRadius: 22, boxShadow: '0 1px 2px rgba(0,0,0,.04),0 12px 32px rgba(17,17,17,.06)' }
const chip = { display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid #e3e4e8', background: '#fff', borderRadius: 999, padding: '6px 13px', fontSize: 13, color: '#111' }
const dark = { ...chip, background: '#111', color: '#fff', borderColor: '#111' }
const muted = { color: '#6b6f76', fontSize: 12 }
const btnBase = { display: 'inline-flex', justifyContent: 'center', alignItems: 'center', border: '1px solid #dedfe3', background: '#fff', color: '#111', borderRadius: 999, padding: '11px 17px', fontWeight: 600, fontSize: 14, cursor: 'pointer', whiteSpace: 'nowrap', textDecoration: 'none' }
const input = { width: '100%', minWidth: 0, padding: '12px 14px', border: '1px solid #e3e4e8', borderRadius: 14, fontSize: 14, background: '#fff', color: '#111', outlineColor: '#111' }

function dur(s) { if (s === null || s === undefined) return 'Route unavailable'; const m = Math.max(1, Math.round(s / 60)); return m < 60 ? m + ' min' : Math.floor(m / 60) + ' h ' + String(m % 60).padStart(2, '0') + ' min' }
function dist(m) { if (m === null || m === undefined) return '—'; return m < 1000 ? m + ' m' : (m / 1000).toFixed(1) + ' km' }
const drive = s => s && s.drive ? dur(s.drive.duration_s) + ' drive' : 'Route unavailable'

function Btn({ ctx, label, url, primary, small, grow }) {
  if (!url) return null
  const open = async e => {
    e.preventDefault()
    let ok = false
    try { ok = await ctx.os.openExternal(url) } catch (_) { ok = false }
    if (!ok) { try { ctx.os.writeClipboard(url) } catch (_) {} }
  }
  return h('a', { href: url, onClick: open, rel: 'noopener noreferrer', style: { ...btnBase, ...(primary ? { background: '#111', color: '#fff', borderColor: '#111' } : {}), ...(small ? { padding: '8px 13px', fontSize: 13 } : {}), ...(grow ? { flex: 1 } : {}) } }, label)
}

// Real relative position of a stay vs the origin (equirectangular). Not a photo or map tile.
function Locator({ origin, stay, others = [], w = 420, hgt = 210 }) {
  const k = Math.cos(origin.lat * Math.PI / 180)
  const pts = [stay, ...others].map(p => [(p.lng - origin.lng) * k, p.lat - origin.lat])
  const span = Math.max(1e-4, ...pts.map(([x, y]) => Math.max(Math.abs(x), Math.abs(y))))
  const s = Math.min((w / 2 - 34) / span, (hgt / 2 - 34) / span)
  const xy = pts.map(([x, y]) => [w / 2 + x * s, hgt / 2 - y * s])
  const [sx, sy] = xy[0]
  const lines = []
  for (let x = 0; x <= w; x += 30) lines.push(h('line', { key: 'x' + x, x1: x, y1: 0, x2: x, y2: hgt }))
  for (let y = 0; y <= hgt; y += 30) lines.push(h('line', { key: 'y' + y, x1: 0, y1: y, x2: w, y2: y }))
  return h('svg', { viewBox: `0 0 ${w} ${hgt}`, preserveAspectRatio: 'xMidYMid slice', role: 'img', 'aria-label': stay.name + ' relative to ' + origin.label, style: { position: 'absolute', inset: 0, width: '100%', height: '100%' } },
    h('rect', { width: w, height: hgt, fill: '#eceef1' }),
    h('g', { stroke: '#e0e3e8', strokeWidth: 1 }, ...lines),
    ...xy.slice(1).map(([x, y], i) => h('circle', { key: 'o' + i, cx: x, cy: y, r: 3.5, fill: '#c9ccd3' })),
    h('line', { x1: w / 2, y1: hgt / 2, x2: sx, y2: sy, stroke: '#111', strokeWidth: 1.6, strokeDasharray: '4 5' }),
    h('circle', { cx: w / 2, cy: hgt / 2, r: 9, fill: '#fff', stroke: '#111', strokeWidth: 2.5 }),
    h('circle', { cx: w / 2, cy: hgt / 2, r: 3.5, fill: '#111' }),
    h('g', { transform: `translate(${sx},${sy})` }, h('path', { d: 'M0 0 C-11 -14 -11 -28 0 -28 C11 -28 11 -14 0 0Z', fill: '#111' }), h('circle', { cy: -19, r: 4.2, fill: '#fff' })))
}

const badge = { position: 'absolute', top: 14, left: 14, background: '#fff', borderRadius: 999, padding: '6px 12px', fontSize: 12, fontWeight: 600, boxShadow: '0 2px 8px rgba(0,0,0,.08)' }

function StayCard({ ctx, s, origin, all, onOpen }) {
  const L = s.links || {}
  const who = s.operator || s.brand
  const stat = { textAlign: 'center', fontSize: 13, paddingLeft: 12, borderLeft: '1px solid rgba(255,255,255,.18)' }
  return h('article', { style: { borderRadius: 22, overflow: 'hidden', background: '#fff', boxShadow: '0 14px 34px rgba(17,17,17,.10)', display: 'flex', flexDirection: 'column' } },
    h('button', { type: 'button', onClick: onOpen, 'aria-label': 'Details for ' + s.name, style: { border: 0, padding: 0, textAlign: 'left', cursor: 'pointer', background: 'none', color: 'inherit', font: 'inherit' } },
      h('div', { style: { position: 'relative', height: 190, background: '#eceef1' } }, h(Locator, { origin, stay: s, others: all.filter(o => o !== s) }),
        h('span', { style: badge }, s.rank === 1 && s.drive ? '★ Top pick' : s.type_label)),
      h('div', { style: { background: 'linear-gradient(180deg,#2b3038,#1d2127)', color: '#fff', padding: '15px 17px 13px' } },
        h('div', { style: { fontSize: 22, fontWeight: 700, letterSpacing: '-.5px' } }, drive(s)),
        h('div', { style: { display: 'flex', gap: 12, alignItems: 'flex-end', marginTop: 6 } },
          h('div', { style: { flex: 1, minWidth: 0, fontSize: 13.5 } }, h('div', { style: { fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }, s.name), h('div', { style: { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }, s.address || s.type_label + ' · address not tagged')),
          h('div', { style: stat }, s.drive ? dist(s.drive.distance_m) : dist(s.straight_line_m), h('br'), s.drive ? 'road' : 'straight'),
          s.stars ? h('div', { style: stat }, '★ ' + s.stars, h('br'), 'stars') : s.walk ? h('div', { style: stat }, dur(s.walk.duration_s), h('br'), 'walk') : null),
        h('div', { style: { borderTop: '1px solid rgba(255,255,255,.14)', marginTop: 11, paddingTop: 9, fontSize: 12, color: '#b9bec7', display: 'flex', justifyContent: 'space-between', gap: 8 } },
          h('span', null, who ? 'Operator: ' + who : 'Mapped in OSM · ' + s.id), h('span', null, s.type_label)))),
    h('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap', padding: '12px 14px 14px' } },
      h(Btn, { ctx, label: 'Get a ride', url: L.open_uber, primary: true, small: true, grow: true }),
      h(Btn, { ctx, label: 'See rooms', url: L.check_booking, small: true, grow: true }),
      h(Btn, { ctx, label: 'Check Airbnb', url: L.check_airbnb, small: true, grow: true }),
      h(Btn, { ctx, label: 'Call', url: L.call, small: true, grow: true })))
}

function Section({ title, open, children }) {
  return h('details', { open, style: { border: '1px solid #ececef', borderRadius: 16, padding: '12px 16px', marginTop: 10, background: '#fff' } },
    h('summary', { style: { cursor: 'pointer', fontWeight: 600 } }, title), h('div', { style: { marginTop: 10 } }, children))
}
const kvGrid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: '12px 18px' }
function KV({ k, v }) { return h('div', { style: { minWidth: 0, overflowWrap: 'anywhere', fontSize: 13.5 } }, h('div', { style: muted }, k), String(v)) }

function Detail({ ctx, d, s, origin, onBack }) {
  const L = s.links || {}
  const facts = [['Address', s.address || 'Not tagged in OSM'], ['Type', s.type_label]]
  for (const [k, key] of [['Operator', 'operator'], ['Brand', 'brand'], ['Phone', 'phone'], ['Opening hours', 'opening_hours'], ['Rooms', 'rooms'], ['Wheelchair', 'wheelchair'], ['Internet', 'internet_access'], ['Website', 'website']]) if (s[key]) facts.push([k, s[key]])
  return h('section', null,
    h('button', { type: 'button', onClick: onBack, style: { border: 0, background: 'none', ...muted, cursor: 'pointer', padding: 0, marginBottom: 12 } }, '← All stays'),
    h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 24 } },
      h('div', { style: { position: 'relative', borderRadius: 22, overflow: 'hidden', minHeight: 320, background: '#eceef1' } }, h(Locator, { origin, stay: s, others: d.stays.filter(o => o !== s), w: 560, hgt: 420 }),
        h('span', { style: badge }, s.rank === 1 && s.drive ? '★ Top pick · fastest drive' : s.type_label),
        h('span', { style: { position: 'absolute', right: 10, bottom: 8, fontSize: 10, color: '#6b6f76', background: 'rgba(255,255,255,.85)', padding: '2px 6px', borderRadius: 6 } }, 'Position from © OpenStreetMap contributors · not a photo')),
      h('div', null,
        h('span', { style: chip }, s.type_label + ((s.operator || s.brand) ? ' · ' + (s.operator || s.brand) : '')),
        h('h1', { style: { fontSize: 27, letterSpacing: '-.6px', margin: '12px 0 4px', lineHeight: 1.15 } }, s.name),
        h('div', { style: { fontSize: 29, fontWeight: 700, letterSpacing: '-.8px', margin: '8px 0 2px' } }, drive(s) + (s.drive ? ' · ' + dist(s.drive.distance_m) : '')),
        h('div', { style: muted }, 'from ' + origin.label + ' · price on Booking / Airbnb (OSM has no nightly rates)'),
        h('div', { style: { ...chip, fontSize: 12, color: '#55595f', margin: '10px 0 14px' } }, '🕑 Checked ' + d.fetched_at + ' · availability not known until you check'),
        h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 } },
          h('span', { style: dark }, '🚗 ' + drive(s)), s.walk && h('span', { style: chip }, '🚶 ' + dur(s.walk.duration_s) + ' walk'),
          h('span', { style: chip }, dist(s.straight_line_m) + ' straight line'), s.stars && h('span', { style: chip }, '★ ' + s.stars + ' stars · OSM tag')),
        h('div', { style: { display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 } }, h(Btn, { ctx, label: 'Get a ride', url: L.open_uber, primary: true, grow: true }), h(Btn, { ctx, label: 'See rooms', url: L.check_booking })),
        h('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } }, h(Btn, { ctx, label: 'Open Lyft', url: L.open_lyft, small: true }), h(Btn, { ctx, label: 'Open maps', url: L.directions || L.open_maps, small: true }), h(Btn, { ctx, label: 'Check Airbnb', url: L.check_airbnb, small: true }), h(Btn, { ctx, label: 'Call', url: L.call, small: true })),
        h(Section, { title: 'Details from OpenStreetMap', open: true }, h('div', { style: kvGrid }, ...facts.map(([k, v]) => h(KV, { key: k, k, v })))),
        h(Section, { title: 'Getting there', open: true }, h('div', { style: kvGrid },
          h(KV, { k: 'Driving (OSRM)', v: s.drive ? dur(s.drive.duration_s) + ' · ' + dist(s.drive.distance_m) + ' by road' : 'Unavailable' }),
          s.walk && h(KV, { k: 'Walking (OSRM foot)', v: dur(s.walk.duration_s) + ' · ' + dist(s.walk.distance_m) }),
          h(KV, { k: 'Traffic', v: 'Not included — road-network estimate' }))),
        h(Section, { title: 'Booking & payment' }, h('p', { style: { ...muted, margin: 0 } }, d.honesty)))))
}

function RideView({ ctx, d }) {
  const a = d.pickup, b = d.dropoff, L = d.links
  const big = d.drive ? dur(d.drive.duration_s) + ' · ' + dist(d.drive.distance_m) + ' by road' : 'Driving route unavailable'
  const opts = [['Uber', 'U', '#111', 'Pickup + dropoff set', L.open_uber, 'Open Uber'], ['Lyft', 'L', '#ff00bf', 'Pickup + destination set', L.open_lyft, 'Open Lyft'], ['Maps', 'M', '#1a73e8', 'Turn-by-turn directions', L.open_maps, 'Open maps']]
  return h('section', null,
    h('div', { style: { ...card, padding: 24, marginBottom: 20 } }, h('span', { style: chip }, 'Get a ride'),
      h('h1', { style: { fontSize: 26, letterSpacing: '-.6px', margin: '12px 0 4px' } }, a.label + ' → ' + b.label),
      h('div', { style: { fontSize: 29, fontWeight: 700, letterSpacing: '-.8px', margin: '6px 0' } }, big),
      h('div', { style: muted }, 'Checked ' + d.fetched_at + ' · no live traffic · ' + dist(d.straight_line_m) + ' straight line' + (d.walk ? ' · walk ' + dur(d.walk.duration_s) : '')),
      h('div', { style: { display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 14 } }, h(Btn, { ctx, label: 'Get a ride', url: L.open_uber, primary: true, grow: true }), h(Btn, { ctx, label: 'Open Lyft', url: L.open_lyft }), h(Btn, { ctx, label: 'Open maps', url: L.open_maps }))),
    h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))', gap: 16 } },
      ...opts.map(([n, l, c, st, u, cta]) => h('article', { key: n, style: { ...card, padding: 12, borderRadius: 26 } },
        h('div', { style: { borderRadius: 18, background: '#eceef1', height: 150, display: 'grid', placeItems: 'center', textAlign: 'center' } },
          h('div', null, h('div', { style: { fontSize: 24, fontWeight: 500, letterSpacing: '-.5px' } }, n), h('div', { style: { fontSize: 13, color: '#55595f' } }, '◌ ' + (d.drive ? dur(d.drive.duration_s) + ' drive' : 'Route unavailable') + ' · OSRM'), h('div', { style: { ...muted, marginTop: 8 } }, st))),
        h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '12px 4px 4px' } },
          h('div', { style: { display: 'flex', gap: 10, alignItems: 'center' } }, h('span', { style: { width: 36, height: 36, borderRadius: '50%', background: c, color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 700 } }, l), h('div', { style: muted }, 'Fare shown in app')),
          h(Btn, { ctx, label: '+ ' + cta, url: u, primary: true, small: true }))))))
}

function Nightstop({ ctx }) {
  const [mode, setMode] = useState('night')
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [busy, setBusy] = useState(false)
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState(null)
  async function run(e) {
    e.preventDefault(); if (busy) return
    setBusy(true); setErr(''); setD(null); setSel(null)
    const path = mode === 'ride' ? '/ride' : mode === 'stay' ? '/stay' : '/night'
    const body = mode === 'ride' ? { pickup: a, dropoff: b } : mode === 'stay' ? { location: a } : { origin: a, area: b || undefined }
    try { const r = await ctx.rest(path, { method: 'POST', body }); if (r.error) setErr(r.error); else setD(r.data) }
    catch (_) { setErr('Nightstop backend unavailable. Install the Python package into Hermes, enable the plugin and restart the gateway (see README). Nothing was invented.') }
    finally { setBusy(false) }
  }
  const tabs = [['night', 'Tonight'], ['stay', 'Stay'], ['ride', 'Ride']]
  const origin = d && (d.origin || d.center)
  const ph = mode === 'ride' ? ['Pickup — address, place or lat,lng', 'Dropoff'] : mode === 'stay' ? ['Where do you want to sleep?', null] : ['Where are you now?', 'Area to sleep in (optional)']
  return h('main', { style: page }, h('div', { style: { maxWidth: 1080, margin: '0 auto' } },
    h('header', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 } },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: 9, fontWeight: 650, fontSize: 18 } }, h('span', { style: { width: 28, height: 28, borderRadius: '50%', background: '#111', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 14 } }, 'N'), 'Nightstop'),
      h('div', { style: { display: 'flex', gap: 8 } }, ...tabs.map(([k, l]) => h('button', { key: k, type: 'button', onClick: () => { setMode(k); setD(null); setErr(''); setSel(null) }, style: { ...(mode === k ? dark : chip), cursor: 'pointer' } }, l)))),
    h('form', { onSubmit: run, style: { ...card, padding: 16, marginBottom: 22, display: 'flex', gap: 10, flexWrap: 'wrap' } },
      h('input', { 'aria-label': ph[0], value: a, onChange: e => setA(e.target.value), required: true, placeholder: ph[0], style: { ...input, flex: '2 1 240px', width: 'auto' } }),
      ph[1] && h('input', { 'aria-label': ph[1], value: b, onChange: e => setB(e.target.value), required: mode === 'ride', placeholder: ph[1], style: { ...input, flex: '2 1 200px', width: 'auto' } }),
      h('button', { type: 'submit', disabled: busy, style: { ...btnBase, background: '#111', color: '#fff', borderColor: '#111', opacity: busy ? .7 : 1, cursor: busy ? 'wait' : 'pointer' } }, busy ? 'Checking OpenStreetMap…' : mode === 'ride' ? 'Get a ride' : 'See rooms')),
    err && h('p', { role: 'alert', style: { ...card, padding: 16, color: '#9b1c1c', fontSize: 13 } }, err),
    d && d.kind === 'ride' && h(RideView, { ctx, d }),
    d && d.kind !== 'ride' && sel && h(Detail, { ctx, d, s: sel, origin, onBack: () => setSel(null) }),
    d && d.kind !== 'ride' && !sel && h('section', { 'aria-live': 'polite' },
      h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8, marginBottom: 14 } },
        h('h2', { style: { fontSize: 22, letterSpacing: '-.4px', margin: 0 } }, (d.kind === 'night' ? 'Tonight near ' : 'Places to stay near ') + origin.label),
        h('span', { style: muted }, d.found_total + ' mapped within ' + d.radius_km + ' km · showing ' + d.stays.length + ' · ranked by OSRM driving time')),
      d.stays.length ? h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(290px,1fr))', gap: 18 } }, ...d.stays.map(s => h(StayCard, { key: s.id, ctx, s, origin, all: d.stays, onOpen: () => setSel(s) })))
        : h('div', { style: { ...card, padding: 20, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' } }, 'No named stays mapped in OpenStreetMap here.', h(Btn, { ctx, label: 'Check Booking', url: d.area_links.check_booking, primary: true, small: true }), h(Btn, { ctx, label: 'Check Airbnb', url: d.area_links.check_airbnb, small: true }))),
    d && (d.warnings || []).map((w, i) => h('div', { key: i, style: { background: '#fff8e6', border: '1px solid #f3e2b3', borderRadius: 14, padding: '10px 14px', fontSize: 13, marginTop: 10 } }, '⚠ ' + w)),
    h('p', { style: { ...muted, background: '#fff', border: '1px solid #ececef', borderRadius: 16, padding: '13px 16px', marginTop: 24 } },
      'Nightstop cannot log into Uber, Lyft, Airbnb or Booking.com and cannot pay. Buttons open those apps with pickup, dropoff or search prefilled; you confirm there. No reservation is made. Map data © OpenStreetMap contributors · routing by OSRM.' + (d ? ' Checked ' + d.fetched_at + '.' : ''))))
}

export default {
  id: 'nightstop', name: 'Nightstop',
  register(ctx) {
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/nightstop' }, render: () => h(Nightstop, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/nightstop', label: 'Nightstop', codicon: 'home' } }
    ])
  }
}
