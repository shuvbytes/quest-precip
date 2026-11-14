/* Baरिश (Barish), a second opinion on rain: map page. Everything shown (times, labels, bins, colours, text) comes from
   data/manifest.json, written by pipeline/build.py. Nothing about the forecast is hard-coded here. */
"use strict";

const DATA = "data/";
// Small screens (M8 D): phones in portrait (narrow) or landscape / short windows. Same query as in style.css.
const SMALL = window.matchMedia("(max-width: 700px), (max-height: 560px)");
const $ = (id) => document.getElementById(id);

function setStatus(s) { document.body.dataset.status = s; }

function showError(msg) {
  setStatus("error: " + msg);
  const div = document.createElement("div");
  div.className = "error";
  div.textContent = "Could not load the forecast: " + msg;
  document.querySelector(".map-wrap").appendChild(div);
}
/* Error handling. The banner says "Could not load the forecast", so it is shown only when loading really failed:
   - main() rejecting is the authoritative signal (see the end of this file);
   - a window "error" counts only if it comes from THIS site's own scripts and the page is not ready yet.
   "Script error." with no file name is how browsers report an error inside a script from another origin (details
   are hidden). This page loads no such script, so it comes from a browser extension or a stale cached page, and
   must not be shown as a forecast failure (seen in Safari, 13 Nov). Such errors are only logged. */
function isOwnScriptError(e) {
  if (!e.filename) return false;                      // opaque cross-origin "Script error."
  try { return new URL(e.filename, location.href).origin === location.origin; } catch (_) { return false; }
}
window.addEventListener("error", (e) => {
  const own = isOwnScriptError(e);
  document.body.dataset.lasterror = (own ? "" : "[other origin] ") + e.message;
  if (!own) {
    // Everything the browser reveals about it: an empty file name means the browser hid it (another origin).
    console.warn("Ignored an error from a script that is not part of this page:", e.message,
      `| file: ${e.filename || "(hidden by the browser: not this site)"} | line ${e.lineno || "?"}:${e.colno || "?"}` +
      ` | this page's scripts: ${[...document.scripts].map((x) => x.src || "(inline)").join(", ")}`);
    return;
  }
  if (document.body.dataset.status === "ready") console.error(e.error || e.message);
  else showError(e.message);
});

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/* ---------------- map ---------------- */

function makeMap(m) {
  const map = L.map("map", {
    zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 3, maxZoom: 9,   // 3: a phone needs ~3.9 to fit the region
    keyboardPanDelta: 0,                    // arrows move the crosshair by grid points instead (M8 B, wire())
    attributionControl: false,              // full attribution is in the footer
  });
  // Draw order (bottom -> top): land fill, rain/chance image, disagreement hatch, coast + India boundary lines.
  // "outside" = shading beyond the forecast area (no data there); it never overlaps the data image.
  // "places" = city/country/sea labels (M8), above the data and lines, never clickable (clicks reach the map).
  [["land", 200], ["fill", 300], ["outside", 320], ["hatch", 350], ["lines", 450], ["places", 455], ["edge-labels", 460]].forEach(([name, z]) => {
    map.createPane(name).style.zIndex = z;
  });
  ["lines", "outside", "places", "edge-labels"].forEach((p) => { map.getPane(p).style.pointerEvents = "none"; });
  map.getContainer().style.background = m.basemap.sea;
  const b = m.image.bounds;
  map.setMaxBounds(L.latLngBounds(b).pad(0.15));
  map.fitBounds(b);                          // user decision: fit the whole region on every screen
  return map;
}

async function addBasemap(map, m) {
  const [land, coast, india, states, places] = await Promise.all([
    getJSON("geo/land.geojson"), getJSON("geo/coastline.geojson"), getJSON("geo/india-boundary.geojson"),
    getJSON("geo/states.geojson"), getJSON("geo/places.json")]);
  // Land as a fill only; the coastline comes from a separate line layer, so no clip edges are ever drawn.
  L.geoJSON(land, { pane: "land", interactive: false,
    style: { stroke: false, fillColor: m.basemap.land, fillOpacity: 1 } }).addTo(map);
  L.geoJSON(coast, { pane: "lines", interactive: false,
    style: { color: "#6b717b", weight: 1.1, fill: false } }).addTo(map);
  // internal state/UT boundaries (DataMeet, edges shared by two states only), thin grey, under the India outline
  L.geoJSON(states, { pane: "lines", interactive: false,
    style: { color: "#7d838c", weight: 0.9, fill: false } }).addTo(map);
  L.geoJSON(india, { pane: "lines", interactive: false,
    style: { color: "#2b2f36", weight: 1.4, fill: false } }).addTo(map);
  addForecastEdge(map, m);
  const list = places.places.map((p) => Object.fromEntries(places.fields.map((f, i) => [f, p[i]])));
  addPlaceLabels(map, list, m.image.bounds);
  return list;
}

/* ---------- place labels (M8 A): Natural Earth cities + hand-placed country and sea names ----------
   Density: a city is a candidate when zoom >= its Natural Earth MIN_ZOOM - CITY_ZOOM_OFFSET (capitals always);
   overlapping labels are then dropped greedily by priority (national capital, state capital, population), so the
   fitted view shows the main cities and zooming in adds towns. White halo (CSS) keeps text readable over rain. */
const CITY_ZOOM_OFFSET = 0.5;
const LABEL_FONT = { city: "12px system-ui, sans-serif", capital: "600 12px system-ui, sans-serif",
  country: "600 11px system-ui, sans-serif", sea: "italic 12px system-ui, sans-serif" };
let measureCtx = null;
function textWidth(text, font) {
  measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}

function addPlaceLabels(map, places, bounds) {
  // city names only inside the forecast area (outside it there is no data to place); countries and seas everywhere
  const [[s, w], [n, e]] = bounds;
  const inArea = (p) => p.lat >= s && p.lat <= n && p.lon >= w && p.lon <= e;
  const items = places.map((p) => {
    const cls = p.kind === "country" ? "country" : p.kind === "sea" ? "sea" : p.kind === "city" ? "city" : "capital";
    const text = p.kind === "country" ? p.name.toUpperCase() : p.name;
    const w = textWidth(text, LABEL_FONT[cls]) + (cls === "country" ? text.length * 1.2 : 0);
    if ((cls === "city" || cls === "capital") && !inArea(p)) return null;
    const dot = cls === "city" || cls === "capital";
    const html = (dot ? `<span class="pl-dot"></span>` : "") + `<span class="pl-txt">${text}</span>`;
    const marker = L.marker([p.lat, p.lon], { pane: "places", interactive: false, keyboard: false,
      icon: L.divIcon({ className: `pl pl-${cls}`, html, iconSize: null }) });
    return { p, cls, w: w + (dot ? 11 : 0), h: 15, dot, marker, on: false };
  }).filter(Boolean);
  items.sort((a, b) => a.p.priority - b.p.priority || b.p.population - a.p.population);
  const update = () => {
    const z = map.getZoom(), size = map.getSize(), taken = [], shown = { city: 0, capital: 0, country: 0, sea: 0 };
    for (const it of items) {
      const p = it.p;
      let want = it.cls === "sea" || it.cls === "country" ? z <= 7.5
        : it.cls === "capital" ? true : z >= p.min_zoom - CITY_ZOOM_OFFSET;
      let box = null;
      if (want) {
        const pt = map.latLngToContainerPoint([p.lat, p.lon]);
        // dot at the place, text to its right; country/sea text centred on the point
        box = it.dot ? [pt.x - 4, pt.y - it.h / 2, pt.x - 4 + it.w, pt.y + it.h / 2]
          : [pt.x - it.w / 2, pt.y - it.h / 2, pt.x + it.w / 2, pt.y + it.h / 2];
        const onScreen = box[0] >= 2 && box[2] <= size.x - 2 && box[1] >= 0 && box[3] <= size.y;   // whole label, never cut
        want = onScreen && !taken.some((t) => box[0] < t[2] + 3 && t[0] < box[2] + 3 && box[1] < t[3] && t[1] < box[3]);
      }
      if (want) { taken.push(box); shown[it.cls]++; }
      if (want && !it.on) it.marker.addTo(map);
      if (!want && it.on) it.marker.remove();
      it.on = want;
    }
    map.getContainer().dataset.labels = JSON.stringify(shown);     // for checks: labels shown per kind
  };
  map.on("zoomend moveend resize", update);
  update();
}

/* The forecast area: outside it "no colour" means "no data", not "no rain". Shown three ways (user, 13 Nov):
   a light veil over everything outside, a subtle dashed edge, and an on-map label that follows each side edge
   so it is readable whenever that edge is on screen (zoomed in, only the two side edges may be visible). */
function addForecastEdge(map, m) {
  const [[s, w], [n, e]] = m.image.bounds;
  const world = [[-85, -180], [85, -180], [85, 180], [-85, 180]];
  const hole = [[s, w], [n, w], [n, e], [s, e]];
  L.polygon([world, hole], { pane: "outside", interactive: false, stroke: false,
    fillColor: m.basemap.outside, fillOpacity: m.basemap.outside_opacity }).addTo(map);
  L.rectangle(m.image.bounds, { pane: "lines", interactive: false,
    color: "#9aa0a8", weight: 1, dashArray: "3 5", fill: false }).addTo(map);

  const label = (cls) => L.marker([0, 0], { pane: "edge-labels", interactive: false, keyboard: false,
    icon: L.divIcon({ className: "edge-label " + cls, html: "<span>Forecast area edge · no data beyond</span>",
                      iconSize: null }) }).addTo(map);
  const west = label("edge-w"), east = label("edge-e");
  const place = () => {
    const v = map.getBounds();
    const lat = Math.min(n - 1, Math.max(s + 1, v.getCenter().lat));   // stay on the edge, mid-screen
    west.setLatLng([lat, w]);
    east.setLatLng([lat, e]);
    const showW = v.getWest() < w && w < v.getEast(), showE = v.getWest() < e && e < v.getEast();
    west.getElement().style.display = showW ? "" : "none";
    east.getElement().style.display = showE ? "" : "none";
  };
  map.on("moveend zoomend", place);
  place();
}

/* ---------------- state (kept in the URL hash, so a view can be shared or bookmarked) ---------------- */

const state = { mode: "24h", fill: "chance", x: "10", hatch: true, t: 0, p: null };   // p = [lat, lon] of a grid point

function readHash(m) {
  const h = new URLSearchParams(location.hash.slice(1));
  if (["3h", "24h"].includes(h.get("mode"))) state.mode = h.get("mode");
  if (["rain", "chance"].includes(h.get("fill"))) state.fill = h.get("fill");
  if (h.get("x") && m.products.ens_prob.frames_by_threshold[h.get("x")]) state.x = h.get("x");
  if (h.get("hatch") === "0") state.hatch = false;
  if (h.get("t") !== null && !isNaN(+h.get("t"))) state.t = +h.get("t");
  const pp = (h.get("p") || "").split(",").map(Number);
  if (pp.length === 2 && pp.every(Number.isFinite)) state.p = pp;
  const z = h.get("z"), c = h.get("c");
  return z && c ? { zoom: +z, center: c.split(",").map(Number) } : null;
}

/* Browsers limit history.replaceState (Safari: 100 calls per 10 s, then a "SecurityError"). Dragging the slider
   renders many times per second, so the URL is written only once things are still for 400 ms, only if it changed,
   and never in a way that can break the map. */
let hashTimer = null;
function writeHash() {
  clearTimeout(hashTimer);
  hashTimer = setTimeout(() => {
    const h = new URLSearchParams({ mode: state.mode, t: state.t });
    if (state.mode === "24h") { h.set("fill", state.fill); h.set("x", state.x); h.set("hatch", state.hatch ? 1 : 0); }
    if (state.p) h.set("p", state.p.map((v) => v.toFixed(2)).join(","));
    const next = "#" + h.toString();
    if (next === location.hash) return;
    try { history.replaceState(null, "", next); } catch (e) { console.warn("URL not updated:", e.message); }
  }, 400);
}

/* ---------------- frames ---------------- */

function xLabel(x) { return `${Number(x)}`; }

function framesFor(m) {
  if (state.mode === "3h") return m.products.hres_3h.frames;
  return state.fill === "rain" ? m.products.hres_24h.frames : m.products.ens_prob.frames_by_threshold[state.x];
}

/* Index of the frame to show for start hour state.t: the last frame starting at or before it. */
function frameIndex(frames) {
  let k = 0;
  frames.forEach((f, i) => { if (f.start_h <= state.t) k = i; });
  return k;
}

function hatchFrame(m, k) {
  return m.products.disagreement.frames_by_threshold[state.x][k];
}

function showingText(m) {
  const P = m.products;
  if (state.mode === "3h") return P.hres_3h.title;
  if (state.fill === "rain") return P.hres_24h.title;
  return P.ens_prob.title.replace(" X ", ` ${xLabel(state.x)} `);
}

/* ---------------- times (never use the viewer's time zone: shift UTC by +05:30 and format as UTC) ---------------- */

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");

function parseUTC(iso) {            // "2026-11-12T12:00Z"
  const t = Date.parse(iso);
  if (isNaN(t)) throw new Error("bad time in manifest: " + iso);
  return t;
}
function istLabel(ms) {
  const d = new Date(ms + 330 * 60 * 1000);
  return `${DAYS[d.getUTCDay()]} ${pad(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} IST`;
}
function ago(ms) {
  const h = (Date.now() - ms) / 3.6e6;
  return h < 1 ? "less than an hour ago" : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`;
}

function renderHeader(m) {
  const run = parseUTC(m.run.utc);
  const runAgeH = (Date.now() - run) / 3.6e6;
  const runLine = $("run-line");
  // long text for normal screens, short one for short screens (one header line; style.css chooses)
  runLine.innerHTML = "";
  runLine.append(el("span", "long", `Forecast run: ${m.run.ist} (${m.run.utc.slice(11, 16)} UTC, ${m.run.utc.slice(0, 10)}) · issued ${ago(run)}`),
    el("span", "short", `Run ${m.run.ist} · issued ${ago(run)}`));
  // Amber when the run is more than 30 h old (user, 13 Nov): a 12z run is routinely ~19 h old before the
  // next 00z is published, so a lower threshold would warn in normal operation.
  if (runAgeH > 30) {
    const b = document.createElement("span");
    b.className = "stale";
    b.textContent = "Older than usual: newer runs may exist";
    runLine.appendChild(b);
  }
  const gen = parseUTC(m.generated_utc);
  const up = $("updated-line");
  up.innerHTML = "";
  up.append(el("span", "long", `Last updated: ${istLabel(gen)} (${ago(gen)})`), el("span", "short", `updated ${ago(gen)}`));
}

/* ---------------- legend & footer (bins, colours, units, notes all from the manifest) ---------------- */

function fmt(v) { return Number(v).toString(); }

function legendList(bins, colours, units, topInclusive) {
  const ul = document.createElement("ul");
  colours.forEach((c, i) => {
    let text;
    if (i < bins.length - 1) text = `${fmt(bins[i])}–${fmt(bins[i + 1])}`;
    else text = `≥ ${fmt(bins[bins.length - 1])}`;           // over-range colour (rain)
    if (topInclusive && i === bins.length - 2) text = `${fmt(bins[i])}–${fmt(bins[i + 1])}`;
    const li = document.createElement("li");
    li.innerHTML = `<span class="sw" style="background:${c}"></span><span></span>`;
    li.lastChild.textContent = `${text} ${units}`;
    ul.appendChild(li);
  });
  return ul;
}

function renderLegend(m, f) {
  const P = m.products;
  const box = $("legend");
  box.innerHTML = "";
  let prod, title;
  if (state.mode === "3h") { prod = P.hres_3h; title = "Rain in the 3-hour window"; }
  else if (state.fill === "rain") { prod = P.hres_24h; title = "Rain in the 24-hour window"; }
  else { prod = P.ens_prob; title = `Chance of ≥ ${fmt(state.x)} mm in the 24-hour window`; }

  const h = document.createElement("h3");
  h.innerHTML = `<span></span> <span class="units"></span>`;
  h.firstChild.textContent = title;
  h.lastChild.textContent = `(${prod.units})`;
  box.appendChild(h);
  box.appendChild(legendList(prod.bins, prod.colours, prod.units, !!prod.top_edge_inclusive));

  const note = document.createElement("p");
  note.className = "note";
  const what = prod.units === "%" ? "Chances" : "Amounts";
  note.textContent = `${what} below ${fmt(f.lowest_drawn)} ${prod.units} are not shown.` +
    (prod.units === "mm" ? " Below that, values are within the data's storage precision or too light to matter." : "");
  box.appendChild(note);
  if (f.floor_raised) {
    const w = document.createElement("p");
    w.className = "note warn";
    w.textContent = `In this window the data is stored more coarsely, so the map starts at ${fmt(f.lowest_drawn)} ${prod.units} instead of ${fmt(prod.bins[0])}.`;
    box.appendChild(w);
  }
  const pt = document.createElement("p");
  pt.className = "note";
  pt.textContent = m.grid.value_meaning;
  box.appendChild(pt);

  if (state.mode === "24h" && state.hatch) {
    const D = P.disagreement;
    const k = document.createElement("div");
    k.className = "hatch-key";
    k.innerHTML = `<h3>Where the models disagree (≥ ${fmt(state.x)} mm)</h3><ul>
      <li><span class="sw sw-wet"></span><span></span></li>
      <li><span class="sw sw-dry"></span><span></span></li></ul>
      <p class="note"></p>`;
    const spans = k.querySelectorAll("li > span:last-child");
    spans[0].textContent = D.legend.wetter;
    spans[1].textContent = D.legend.drier;
    k.querySelector(".note").textContent =
      `Wetter: the detailed run gives ≥ X mm, but the ensemble's chance is under ${D.rule.p_unlikely} % here and at all neighbouring points. ` +
      `Drier: the ensemble's chance is ${D.rule.p_likely} % or more, but the detailed run is below X here and nearby. ` +
      `Only groups of ${D.map_min_cluster} or more touching grid points are marked.`;
    box.appendChild(k);
  }
}

function renderFooter(m) {
  const foot = $("foot");
  foot.innerHTML = "";
  const p1 = document.createElement("p");
  p1.style.margin = "0";
  p1.textContent = m.attribution + " ";
  const a = document.createElement("a");
  a.href = m.source.url; a.textContent = "About ECMWF Open Data"; a.rel = "noopener";
  p1.appendChild(a);
  const p2 = document.createElement("p");
  p2.style.margin = "2px 0 0";
  p2.innerHTML = `India boundary: <a href="https://github.com/datameet/maps/blob/master/Country/india-composite.geojson" rel="noopener">India boundaries</a>
    by <a href="http://datameet.org/" rel="noopener">DataMeet India community</a> (CC-0 per the dataset's README), drawn as per the Survey of India official boundary.
    State boundaries: <a href="https://github.com/datameet/maps/tree/master/States" rel="noopener">State boundaries</a> by DataMeet India community (CC BY 4.0; internal lines only).
    Land, coastline and place names: Natural Earth (public domain). No third-party map tiles.`;
  // Small screens (M8 D): one short attribution line + "About & sources", which opens the full text as a bottom sheet.
  // Large screens: the full text, as before (the details element is kept open and its summary hidden).
  const about = el("details", "about");
  about.id = "about";
  const sum = document.createElement("summary");
  sum.append(el("span", "about-short", "© ECMWF Open Data (CC BY 4.0, modified) · DataMeet · Natural Earth"),
    el("span", "about-link", "About & sources"));
  const body = el("div", "about-body");
  const close = el("button", "about-close", "Close");
  close.type = "button";
  close.addEventListener("click", () => { about.open = false; sum.focus(); });
  body.append(p1, p2, close);
  about.append(sum, body);
  foot.append(about);
  const apply = () => { about.open = !SMALL.matches; };
  apply();
  SMALL.addEventListener("change", apply);
}

/* ---------------- point panel (M6) ---------------- */

/* points.bin is fetched once, on the first point selection, with a visible progress state. */
let pointsPromise = null;
function loadPoints(m, onProgress) {
  if (pointsPromise) return pointsPromise;
  pointsPromise = (async () => {
    const r = await fetch(DATA + m.points.file, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${m.points.file}: HTTP ${r.status}`);
    // Progress total = decoded size from the manifest. Not Content-Length: GitHub Pages gzips this file, so that
    // header is the compressed size (~0.62 MB) while the stream yields decoded bytes (3.66 MB) -> bar went to ~590 %.
    const total = m.points.bytes;
    let buf;
    if (r.body && r.body.getReader) {
      const reader = r.body.getReader();
      const chunks = [];
      let got = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value); got += value.length;
        onProgress(got, total);
      }
      buf = new Uint8Array(got);
      let o = 0;
      for (const c of chunks) { buf.set(c, o); o += c.length; }
      buf = buf.buffer;
    } else {
      buf = await r.arrayBuffer();
    }
    if (buf.byteLength !== m.points.bytes) throw new Error(`points.bin is ${buf.byteLength} bytes, expected ${m.points.bytes}`);
    const view = new DataView(buf);                     // explicit little-endian reads, whatever the device
    const arrays = {};
    for (const a of m.points.arrays) arrays[a.name] = a;
    return { view, arrays };
  })();
  pointsPromise.catch(() => { pointsPromise = null; });  // allow Retry after a failure
  return pointsPromise;
}

/* Value of array `name` at (leading indices..., row, col), in its units (scale applied). */
function pointValue(P, name, lead, row, col) {
  const a = P.arrays[name];
  const [nlat, nlon] = a.shape.slice(-2);
  let idx = 0;
  const dims = a.shape.slice(0, -2);
  lead.forEach((v, i) => { idx = idx * dims[i] + v; });
  idx = (idx * nlat + row) * nlon + col;
  const raw = a.dtype === "uint16" ? P.view.getUint16(a.offset + idx * 2, true) : P.view.getUint8(a.offset + idx);
  return raw * a.scale;
}

/* ---------- where the point values come from (M7b) ----------
   1) the point API (Render web service, manifest.api), with a short timeout, accepted only if it serves the same
      forecast build as this page; 2) otherwise the in-browser lookup in points.bin (downloaded once).
   Both give {val(name, lead), near(name, lead), note}, so the panel has one renderer. ?api=off forces 2 (checks). */
const API_OFF = new URLSearchParams(location.search).get("api") === "off";

async function apiPoint(m, point) {
  const ctl = new AbortController(), t0 = performance.now();
  const timer = setTimeout(() => ctl.abort(), m.api.timeout_ms);
  try {
    const r = await fetch(`${m.api.url}/point?lat=${point.lat}&lon=${point.lon}`, { signal: ctl.signal });
    if (!r.ok) throw new Error(`API answered with error ${r.status}`);
    const j = await r.json();
    if (j.run.utc !== m.run.utc || j.run.generated_utc !== m.generated_utc)
      throw new Error(`API has a different forecast build (run ${j.run.utc}, built ${j.run.generated_utc})`);
    if (j.grid_point.row !== point.row || j.grid_point.col !== point.col) throw new Error("API chose another grid point");
    return { j, ms: Math.round(performance.now() - t0) };
  } catch (e) {
    if (e.name === "AbortError") throw new Error(`API did not answer within ${m.api.timeout_ms / 1000} s`);
    if (e instanceof TypeError) throw new Error("API could not be reached");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function apiSource(m, j, ms) {
  const keys = m.products.ens_prob.thresholds_mm.map(thrKey);
  const val = (name, lead) => name === "ens_prob" ? j.ens_chance[keys[lead[0]]][lead[1]].pct : j[name][lead[0]].mm;
  const near = (name, lead) => [j[name][lead[0]].nearby_min_mm, j[name][lead[0]].nearby_max_mm];
  return { kind: "api", val, near, note: `${m.api.name} · answered in ${ms} ms` };
}

function localSource(m, P, point, reason) {
  const g = m.grid, { row, col } = point;
  return {
    kind: "local",
    val: (name, lead) => pointValue(P, name, lead, row, col),
    near: (name, lead) => nearby((r, c) => pointValue(P, name, lead, r, c), row, col, g.nlat, g.nlon),
    note: "in-browser lookup (points.bin)" + (reason ? ` · ${reason}` : ""),
  };
}

/* "Near <place>" (M8 A), same rule as api/pointcore.py near(): nearest listed city (great circle), bearing from it
   to the grid point. Up to 25 km "Near Chennai (9 km)", beyond "420 km E of Chennai". */
const NEAR_KM = 25, COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
function distanceKm(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dp = p2 - p1, dl = (lon2 - lon1) * r;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * 6371.0 * Math.asin(Math.sqrt(a));
}
function bearingDeg(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dl = (lon2 - lon1) * r;
  const y = Math.sin(dl) * Math.cos(p2), x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return (Math.atan2(y, x) / r + 360) % 360;
}
function nearText(places, lat, lon) {
  let best = null, bd = Infinity;
  for (const p of places) {
    if (!(p.kind === "city" || p.kind === "capital" || p.kind === "state_capital")) continue;
    const d = distanceKm(lat, lon, p.lat, p.lon);
    if (d < bd) { bd = d; best = p; }
  }
  if (!best) return "";
  const km = Math.round(bd), side = COMPASS[Math.round(bearingDeg(best.lat, best.lon, lat, lon) / 45) % 8];
  return bd <= NEAR_KM ? `Near ${best.name} (${km} km)` : `${km} km ${side} of ${best.name}`;
}

/* Nearest grid point to (lat, lon); null if outside the forecast area (the image covers the cell edges). */
function gridPoint(m, lat, lon) {
  const g = m.grid;
  const [[s, w], [n, e]] = m.image.bounds;
  if (!(lat >= s && lat <= n && lon >= w && lon <= e)) return null;
  const row = Math.min(g.nlat - 1, Math.max(0, Math.round((g.lat_north - lat) / g.dlat)));
  const col = Math.min(g.nlon - 1, Math.max(0, Math.round((lon - g.lon_west) / g.dlon)));
  return { row, col, lat: g.lat_north - row * g.dlat, lon: g.lon_west + col * g.dlon };
}

function fmtLat(v) { return `${Math.abs(v).toFixed(2)}°${v >= 0 ? "N" : "S"}`; }
function fmtLon(v) { return `${Math.abs(v).toFixed(2)}°${v >= 0 ? "E" : "W"}`; }

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/* Select the grid point nearest to a clicked/tapped location (or restore one from the URL). */
function selectPoint(app, lat, lon, clicked) {
  const { m, map } = app;
  const box = $("point"), body = $("point-body");
  box.hidden = false;
  $("point-hint").hidden = true;
  body.innerHTML = "";
  const gp = gridPoint(m, lat, lon);
  if (app.marker) { map.removeLayer(app.marker); app.marker = null; }
  if (!gp) {
    state.p = null; app.point = null;
    $("point-title").textContent = "No forecast here";
    const r = m.region;
    body.appendChild(el("p", "outside",
      `This point (${fmtLat(lat)}, ${fmtLon(lon)}) is outside the forecast area, ${r.lat_min}–${r.lat_max}°N, ` +
      `${r.lon_min}–${r.lon_max}°E (grey shading beyond the dashed edge). Tap inside the area for a forecast.`));
    document.body.dataset.point = "outside";
    $("pcard").hidden = true;
    writeHash();
    return;
  }
  state.p = [gp.lat, gp.lon];
  app.point = { ...gp, clicked: clicked ? [lat, lon] : null };
  app.cardClosed = false;
  $("pcard").hidden = true;                  // shown again once this point's values are in (renderCard)
  // ONE current point for mouse and keyboard (user, 14 Nov): every selection (click/tap, p= link, search, Enter) moves
  // the keyboard cursor here, so the next arrow press starts from the selected grid point.
  if (app.cursor) {
    app.cursor.row = gp.row; app.cursor.col = gp.col;
    if (app.drawCross) app.drawCross();
  }
  app.marker = L.circleMarker([gp.lat, gp.lon], { pane: "lines", radius: 6, weight: 2, color: "#111",
    fillColor: "#fff", fillOpacity: 0.9, interactive: false }).addTo(map);
  writeHash();
  renderPoint(app);
  if (clicked && SMALL.matches) box.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function closePoint(app) {
  $("pcard").hidden = true;
  $("point").hidden = true;
  $("point-hint").hidden = false;
  if (app.marker) { app.map.removeLayer(app.marker); app.marker = null; }
  state.p = null; app.point = null;
  document.body.dataset.point = "";
  writeHash();
}

/* Header + loading state; the content itself is filled by renderPointContent once points.bin is in. */
function renderPoint(app) {
  const { m, point } = app;
  if (!point) return;
  $("point-title").textContent = `Grid point ${fmtLat(point.lat)}, ${fmtLon(point.lon)}`;
  const body = $("point-body");
  body.innerHTML = "";
  if (app.places) {
    const nr = el("p", "near-place", nearText(app.places, point.lat, point.lon));
    nr.dataset.field = "near";
    body.appendChild(nr);
  }
  if (point.clicked) body.appendChild(el("p", "sub", `You selected ${fmtLat(point.clicked[0])}, ${fmtLon(point.clicked[1])}`));
  body.appendChild(el("p", "meaning", m.grid.value_meaning));
  const content = el("div", "point-content");
  body.appendChild(content);
  const loading = el("div", "loading");
  const label = el("span", null, "Asking the forecast API…");
  const bar = el("progress");
  bar.max = 100;
  loading.append(label, bar);
  content.appendChild(loading);
  document.body.dataset.point = "loading";
  app.src = null;
  const useApi = m.api && !API_OFF;
  (useApi ? apiPoint(m, point) : Promise.reject(new Error(m.api ? "API switched off (?api=off)" : "")))
    .then(({ j, ms }) => apiSource(m, j, ms))
    .catch((e) => {
      if (useApi) console.info("Point API not used:", e.message);
      if (!app.P) label.textContent = "Loading point data (first time only)…";
      return loadPoints(m, (got, total) => {
        const pct = Math.min(100, Math.round(100 * got / total));
        bar.value = pct;
        // percent only: the decoded size (3.7 MB) is not what is downloaded (~0.6 MB gzip on GitHub Pages)
        label.textContent = `Loading point data (first time only)… ${pct} %`;
      }).then((P) => { app.P = P; return localSource(m, P, point, e.message); });
    })
    .then((src) => {
      if (app.point !== point) return;           // another point was selected meanwhile
      app.src = src;
      renderPointContent(app);
    }).catch((e) => {
    content.innerHTML = "";
    const p = el("p", "err", `Could not load the point data: ${e.message}`);
    const retry = el("button", null, "Retry");
    retry.type = "button";
    retry.addEventListener("click", () => renderPoint(app));
    p.appendChild(retry);
    content.appendChild(p);
    document.body.dataset.point = "error";
  });
}

/* ---------- formatting: same floor rule as the map legend (user, 13 Nov) ---------- */
function fmtMm(v, floor) { return v < floor ? `< ${fmt(floor)} mm` : `${v.toFixed(1)} mm`; }
function fmtPct(v, floor) { return v < floor ? `< ${fmt(floor)} %` : `${Math.round(v)} %`; }
function istShort(iso) {                     // "Thu 17:30" for table headers
  const d = new Date(parseUTC(iso) + 330 * 60 * 1000);
  return `${DAYS[d.getUTCDay()]} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}
function thrKey(t) { return `${Number(t)}`; }

/* min and max of a 2-D field (given as fn(row, col)) over the 3x3 neighbourhood that exists */
function nearbyText(lo, hi, floor) {
  if (hi < floor) return `nearby: all < ${fmt(floor)} mm`;
  return `nearby: ${lo < floor ? "< " + fmt(floor) : lo.toFixed(1)}–${hi.toFixed(1)} mm`;
}
function nearby(fn, row, col, nlat, nlon) {
  let lo = Infinity, hi = -Infinity;
  for (let r = Math.max(0, row - 1); r <= Math.min(nlat - 1, row + 1); r++)
    for (let c = Math.max(0, col - 1); c <= Math.min(nlon - 1, col + 1); c++) {
      const v = fn(r, c); lo = Math.min(lo, v); hi = Math.max(hi, v);
    }
  return [lo, hi];
}

/* Size of the 8-connected group of flagged cells that contains idx (to tell "isolated, not on the map"). */
function clusterSize(cells, idx, nlon) {
  const set = new Set(cells);
  if (!set.has(idx)) return 0;
  const seen = new Set([idx]), queue = [idx];
  while (queue.length) {
    const i = queue.pop(), r = Math.floor(i / nlon), c = i % nlon;
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      const cc = c + dc, j = (r + dr) * nlon + cc;
      if (cc < 0 || cc >= nlon || seen.has(j) || !set.has(j)) continue;
      seen.add(j); queue.push(j);
    }
  }
  return seen.size;
}

/* Flag of this cell for threshold key x and window index k: {kind, onMap} or null. */
function cellFlag(m, x, k, idx) {
  const D = m.products.disagreement, f = D.frames_by_threshold[x][k];
  for (const kind of ["wetter", "drier"]) {
    const cells = f["cells_" + kind];
    if (cells.includes(idx)) return { kind, onMap: clusterSize(cells, idx, m.grid.nlon) >= D.map_min_cluster };
  }
  return null;
}

function textOn(bg) {                          // dark or white text on a palette colour
  const n = parseInt(bg.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 150 ? "#1d1f23" : "#ffffff";
}
function binColour(prod, v) {
  const b = prod.bins;
  if (v < b[0]) return null;
  let i = 0;
  while (i < b.length - 1 && v >= b[i + 1]) i++;
  return prod.colours[Math.min(i, prod.colours.length - 1)];
}

/* 3-hourly HRES bars over 0-144 h. Plain inline SVG (no chart library): 48 rects + a few lines, exact control over
   IST day boundaries and the floor rule, crisp at any size, and the numbers are also in a table below.
   Dataviz skill: one series -> one colour, no legend (title names it); selection = background band, not recolouring;
   thin bars with gaps; recessive grid; per-bar hover/tap readout with full-height hit targets. */
function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v))), f = v / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}
const SVGNS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  return e;
}

function drawChart(app, container, val) {
  const { m } = app;
  const frames = m.products.hres_3h.frames;
  const vals = frames.map((f, k) => val("hres_3h", [k]));
  const shown = vals.map((v, k) => (v < frames[k].lowest_drawn ? 0 : v));      // floor rule: no bar
  const W = Math.max(260, Math.floor(container.clientWidth || 300)), H = 150;
  const pad = { l: 30, r: 6, t: 16, b: 30 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  // At least 5 mm on the axis: a single 0.6 mm bar must not fill the chart (no exaggeration of trace rain).
  const ymax = Math.max(5, niceMax(Math.max(...shown)));
  const n = frames.length, bw = iw / n;
  const x = (h) => pad.l + (h / frames[n - 1].end_h) * iw;
  const y = (v) => pad.t + ih - (v / ymax) * ih;

  const svg = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Rain in each 3-hour window at this point, 0 to ${frames[n - 1].end_h} hours; values are in the table below` });

  // selected window band (3 h frame or the 24 h window), behind the bars
  const sel = state.mode === "3h" ? frames[frameIndex(frames)] : m.products.hres_24h.frames[frameIndex(m.products.hres_24h.frames)];
  svg.appendChild(svgEl("rect", { x: x(sel.start_h), y: pad.t, width: x(sel.end_h) - x(sel.start_h), height: ih,
    fill: "#e8eef7" }));

  // recessive horizontal grid + y labels (mm)
  [0, 0.5, 1].forEach((fr) => {
    const v = ymax * fr, yy = y(v);
    svg.appendChild(svgEl("line", { x1: pad.l, x2: W - pad.r, y1: yy, y2: yy, stroke: "#e3e6ea", "stroke-width": 1 }));
    const t = svgEl("text", { x: pad.l - 4, y: yy + 3, "text-anchor": "end", class: "ax" });
    t.textContent = fmt(+v.toPrecision(3));
    svg.appendChild(t);
  });
  const unit = svgEl("text", { x: pad.l - 4, y: 9, "text-anchor": "end", class: "ax" });
  unit.textContent = "mm";
  svg.appendChild(unit);

  // IST midnights: day boundaries and day labels
  const run = parseUTC(m.run.utc), istOff = 330 * 60 * 1000, end = run + frames[n - 1].end_h * 3.6e6;
  const firstMid = Math.ceil((run + istOff) / 864e5) * 864e5 - istOff;           // first IST midnight after run
  for (let t = firstMid - 864e5; t < end; t += 864e5) {
    const h0 = Math.max(0, (t - run) / 3.6e6), h1 = Math.min(frames[n - 1].end_h, (t + 864e5 - run) / 3.6e6);
    if (t >= run) svg.appendChild(svgEl("line", { x1: x(h0), x2: x(h0), y1: pad.t, y2: pad.t + ih + 4,
      stroke: "#b9bfc7", "stroke-width": 1 }));
    if (h1 - h0 >= 9) {                                                         // label days with room for it
      const d = new Date(Math.max(t, run) + istOff);
      const lab = svgEl("text", { x: (x(h0) + x(h1)) / 2, y: H - 14, "text-anchor": "middle", class: "ax" });
      lab.textContent = `${DAYS[d.getUTCDay()]} ${d.getUTCDate()}`;
      svg.appendChild(lab);
    }
  }
  const note = svgEl("text", { x: W - pad.r, y: H - 2, "text-anchor": "end", class: "ax" });
  note.textContent = "IST days";
  svg.appendChild(note);

  // bars (thin, 2 px gap) + full-height hit targets with a readout
  const colour = m.products.hres_3h.colours[4];
  const readout = el("p", "readout", "Hover or tap a bar for its value.");
  frames.forEach((f, k) => {
    if (shown[k] > 0) {
      const top = y(shown[k]);
      svg.appendChild(svgEl("rect", { x: x(f.start_h) + 1, y: top, width: Math.max(1, bw - 2),
        height: Math.max(1, pad.t + ih - top), rx: 1, fill: colour }));
    }
    const hit = svgEl("rect", { x: x(f.start_h), y: pad.t, width: bw, height: ih, fill: "transparent", class: "hit" });
    const label = `${f.label_ist}: ${fmtMm(vals[k], f.lowest_drawn)}`;
    const title = svgEl("title");
    title.textContent = label;
    hit.appendChild(title);
    const show = () => { readout.textContent = label; };
    hit.addEventListener("mouseenter", show);
    hit.addEventListener("click", show);
    svg.appendChild(hit);
  });
  // baseline
  svg.appendChild(svgEl("line", { x1: pad.l, x2: W - pad.r, y1: pad.t + ih, y2: pad.t + ih, stroke: "#8a8f98", "stroke-width": 1 }));

  container.appendChild(el("p", "eyebrow", "Rain in each 3 hours (HRES), 0–" + frames[n - 1].end_h + " h"));
  if (Math.max(...shown) === 0) {
    // floors differ per window when ECMWF stores later steps more coarsely (floor_raised, e.g. 13 Nov 12z from +105 h)
    const lo = Math.min(...frames.map((f) => f.lowest_drawn)), hi = Math.max(...frames.map((f) => f.lowest_drawn));
    container.appendChild(el("p", "sub", lo === hi
      ? `No 3-hour window reaches ${fmt(lo)} mm at this point.`
      : `No 3-hour window reaches the lowest amount shown at this point (${fmt(lo)} mm; ${fmt(hi)} mm in windows ` +
        `where the data is stored more coarsely).`));
  } else {
    container.appendChild(svg);
    container.appendChild(readout);
  }

  // the same numbers as a table (screen readers, and the exact-match check)
  const det = el("details", "vals");
  det.appendChild(el("summary", null, "3-hour values as a table"));
  const t = el("table", "ptable");
  frames.forEach((f, k) => {
    const tr = el("tr");
    const th = el("th", "rowh", f.label_ist); th.scope = "row";
    const td = el("td", null, fmtMm(vals[k], f.lowest_drawn));
    td.dataset.field = `h3-${k}`;
    tr.append(th, td);
    t.appendChild(tr);
  });
  det.appendChild(t);
  container.appendChild(det);
}

/* Window summary, nearby range, disagreement sentence, 24 h table (and, step 4, the 3 h chart). */
function renderPointContent(app) {
  const { m, src, point } = app;
  const content = $("point-body").querySelector(".point-content");
  if (!content || !src || !point) return;
  content.innerHTML = "";
  const Pr = m.products, g = m.grid, idx = point.row * g.nlon + point.col;
  const { val, near } = src;

  // 1. selected window summary (follows mode + slider)
  const sum = el("div", "summary");
  if (state.mode === "3h") {
    const k = frameIndex(Pr.hres_3h.frames), f = Pr.hres_3h.frames[k], fl = f.lowest_drawn;
    const [lo, hi] = near("hres_3h", [k]);
    sum.append(el("p", "when", f.label_ist),
      el("p", "big", `Rain in 3 hours: ${fmtMm(val("hres_3h", [k]), fl)}`),
      el("p", "near", nearbyText(lo, hi, fl)));
    sum.querySelector(".big").dataset.field = "sum-3h";
    sum.querySelector(".near").dataset.field = "near-3h";
  } else {
    const k = frameIndex(Pr.hres_24h.frames), f = Pr.hres_24h.frames[k], fl = f.lowest_drawn;
    const x = state.x, kx = Pr.ens_prob.thresholds_mm.map(thrKey).indexOf(x);
    const ef = Pr.ens_prob.frames_by_threshold[x][k];
    const [lo, hi] = near("hres_24h", [k]);
    const pct = val("ens_prob", [kx, k]);
    const big = el("p", "big", `Rain in 24 hours (HRES): ${fmtMm(val("hres_24h", [k]), fl)}`);
    const nr = el("p", "near", nearbyText(lo, hi, fl));
    const ch = el("p", "big", `Chance of ≥ ${fmt(x)} mm (ENS): ${fmtPct(pct, ef.lowest_drawn)}`);
    big.dataset.field = "sum-24h"; nr.dataset.field = "near-24h"; ch.dataset.field = "sum-ens";
    sum.append(el("p", "when", f.label_ist), big, nr, ch);

    // 2. disagreement sentence for this cell, threshold and window (also isolated cells not hatched on the map)
    const flag = cellFlag(m, x, k, idx);
    if (flag) {
      // wetter at X >= heavy_from_mm (50) says "Heavy rain is possible"; below that it names X (user, 13 Nov)
      const key = flag.kind === "wetter" && Number(x) >= Pr.disagreement.heavy_from_mm ? "wetter_heavy" : flag.kind;
      const txt = Pr.disagreement.point_text[key]
        .replaceAll("{hres}", val("hres_24h", [k]).toFixed(1))
        .replaceAll("{pct}", `${Math.round(pct)}`)
        .replaceAll("{x}", fmt(x));
      const d = el("p", "disagree " + flag.kind, txt);
      d.dataset.field = "disagree";
      sum.appendChild(d);
      if (!flag.onMap) sum.appendChild(el("p", "sub",
        `This point is not marked on the map: the map only marks groups of ${Pr.disagreement.map_min_cluster} or more touching grid points.`));
    }
  }
  content.appendChild(sum);

  // 3 h bar chart
  const chartBox = el("div", "chart");
  content.appendChild(chartBox);
  drawChart(app, chartBox, val);

  // 3. 24 h windows table: HRES total + ENS chance for every threshold, flags marked
  const wrap = el("div", "table-wrap");
  const tbl = el("table", "ptable");
  // Key to the table. The <caption> stays for screen readers but is visually hidden: inside the sideways-scrolling
  // box it scrolled with the columns and its start was cut off (13 Nov). The visible copy goes below the box.
  const capText = "24-hour windows (start time, IST). ▨ HRES much wetter than the ensemble, • much drier.";
  tbl.appendChild(el("caption", "sr-only", capText));
  const frames24 = Pr.hres_24h.frames, kNow = frameIndex(frames24);
  const head = el("tr");
  head.appendChild(el("th", "rowh", ""));          // pinned like the row labels, so scrolled headers never peek out
  frames24.forEach((f, k) => {
    const th = el("th", k === kNow ? "now" : "", istShort(f.start_utc));
    th.title = f.label_ist; th.scope = "col";
    head.appendChild(th);
  });
  tbl.appendChild(head);
  const rowH = el("tr");
  const thH = el("th", "rowh", "HRES total (mm)"); thH.scope = "row";
  rowH.appendChild(thH);
  frames24.forEach((f, k) => {
    const v = val("hres_24h", [k]);
    const td = el("td", k === kNow ? "now" : "", v < f.lowest_drawn ? `< ${fmt(f.lowest_drawn)}` : v.toFixed(1));
    td.dataset.field = `h24-${k}`;
    rowH.appendChild(td);
  });
  tbl.appendChild(rowH);
  Pr.ens_prob.thresholds_mm.forEach((t, kx) => {
    const x = thrKey(t), tr = el("tr");
    const th = el("th", "rowh", `Chance ≥ ${fmt(t)} mm`); th.scope = "row";
    tr.appendChild(th);
    Pr.ens_prob.frames_by_threshold[x].forEach((f, k) => {
      const v = val("ens_prob", [kx, k]);
      const td = el("td", k === kNow ? "now" : "", v < f.lowest_drawn ? `< ${fmt(f.lowest_drawn)}` : `${Math.round(v)}`);
      const bg = v < f.lowest_drawn ? null : binColour(Pr.ens_prob, v);
      if (bg) { td.style.background = bg; td.style.color = textOn(bg); }
      const flag = cellFlag(m, x, k, idx);
      if (flag) { td.append(flag.kind === "wetter" ? " ▨" : " •"); td.title = Pr.disagreement.legend[flag.kind]; }
      td.dataset.field = `ens-${x}-${k}`;
      tr.appendChild(td);
    });
    tbl.appendChild(tr);
  });
  wrap.appendChild(tbl);
  content.appendChild(el("p", "eyebrow", "Every 24-hour window"));
  content.appendChild(wrap);
  content.appendChild(el("p", "sub tkey", capText));
  // bring the current window's column into view (the table scrolls sideways inside its box on narrow panels)
  // start at a column boundary (the previous window, then the current one), so no column is half hidden
  const firstTh = head.children[Math.max(1, kNow)];
  wrap.scrollLeft = Math.max(0, firstTh.offsetLeft - head.children[1].offsetLeft);
  content.appendChild(el("p", "sub", "Chances in %. Values below the map's lowest step are shown as “< …”."));

  const so = el("p", "sub source", `Values from: ${src.note}`);
  so.dataset.field = "source";
  content.appendChild(so);
  document.body.dataset.point = `${point.lat.toFixed(2)},${point.lon.toFixed(2)}`;
  document.body.dataset.source = src.kind;
  renderCard(app);
}

/* ---------- place search (M8 A): a WAI-ARIA combobox over the same local place list (no external service) ----------
   Matches the start of a name or of any word in it, and old names (Madras, Bombay, ...), ignoring case and accents.
   Up/Down move, Enter selects (the first match if none is highlighted), Esc closes; mouse/tap works too.
   Selecting zooms to the place and opens the point panel for its nearest grid point. */
const fold = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function placeMatches(app, q) {
  const f = fold(q.trim());
  if (!f) return [];
  const [[s, w], [n, e]] = app.m.image.bounds;
  const out = [];
  for (const p of app.places) {
    if (!(p.kind === "city" || p.kind === "capital" || p.kind === "state_capital")) continue;
    if (!(p.lat >= s && p.lat <= n && p.lon >= w && p.lon <= e)) continue;
    const name = fold(p.name);
    let score = name === f ? 0 : name.startsWith(f) ? 1 : name.split(/[\s-]+/).some((x) => x.startsWith(f)) ? 2 : 9;
    let alias = null;
    if (score === 9) {
      alias = p.aliases.find((a) => fold(a).startsWith(f)) || null;
      if (alias) score = 3;
    }
    if (score < 9) out.push({ p, score, alias });
  }
  out.sort((a, b) => a.score - b.score || a.p.priority - b.p.priority || b.p.population - a.p.population);
  return out.slice(0, 8);
}

function wireSearch(app) {
  const input = $("place-q"), list = $("place-list"), status = $("place-status");
  let results = [], active = -1;
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
  const highlight = (i) => {
    active = i;
    [...list.children].forEach((li, k) => li.setAttribute("aria-selected", String(k === i)));
    if (i >= 0) input.setAttribute("aria-activedescendant", `place-opt-${i}`);
    else input.removeAttribute("aria-activedescendant");
  };
  const choose = (i) => {
    const r = results[i];
    if (!r) return;
    input.value = r.p.name;
    close();
    status.textContent = `${r.p.name}, ${r.p.area} selected; forecast panel opened.`;
    app.map.setView([r.p.lat, r.p.lon], Math.max(app.map.getZoom(), 7), { animate: false });
    selectPoint(app, r.p.lat, r.p.lon, true);
  };
  const show = () => {
    results = placeMatches(app, input.value);
    list.innerHTML = "";
    if (!input.value.trim()) { close(); status.textContent = ""; return; }
    if (!results.length) {
      const li = el("li", "none", "No matching place in the forecast area");
      li.setAttribute("aria-disabled", "true");
      list.appendChild(li);
    }
    results.forEach((r, i) => {
      const li = el("li", null, "");
      li.id = `place-opt-${i}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      const b = el("b", null, r.p.name);
      li.append(b, ` · ${r.p.area}` + (r.alias ? ` (${r.alias})` : ""));
      li.addEventListener("pointerdown", (e) => { e.preventDefault(); choose(i); });   // keep focus, then select
      list.appendChild(li);
    });
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    highlight(-1);
    status.textContent = results.length ? `${results.length} place${results.length > 1 ? "s" : ""} found` : "No matching place";
  };
  input.addEventListener("input", show);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (list.hidden) show();
      if (!results.length) return;
      const d = e.key === "ArrowDown" ? 1 : -1;
      highlight((active + d + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(active >= 0 ? active : 0);
    } else if (e.key === "Escape") {
      if (!list.hidden) { e.stopPropagation(); close(); }
    }
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
}

/* ---------- point card (M8 C): a compact summary next to the selected point ----------
   Same data as the panel (app.src.val, cellFlag, fmtMm/fmtPct, nearText). Esc or x closes it (the panel stays);
   "Full details" goes to the panel. Phones: a bottom sheet. The guide character's pose (24 h window under the slider):
     disagree: the point is flagged wetter/drier at the current threshold X (same flag as the panel's sentence)
     heavy:    ENS chance of >= 50 mm >= 50 %
     light:    HRES 24 h total >= 1 mm, or ENS chance of >= 1 mm >= 50 %
     dry:      otherwise                                         (first matching rule wins, in this order) */
const POSE = {
  dry: { caption: "Mostly dry", alt: "Weather guide holding a closed umbrella, relaxed: mostly dry here in this window." },
  light: { caption: "Some rain", alt: "Weather guide under a small open umbrella with a few raindrops: some rain here in this window." },
  heavy: { caption: "Heavy rain likely", alt: "Weather guide gripping a large umbrella in heavy rain, eyebrows raised: heavy rain likely here in this window." },
  disagree: { caption: "The models disagree", alt: "Weather guide shrugging with a question mark: the detailed run and the ensemble disagree here." },
};

function poseFor(app, k) {
  const { m, src, point } = app, Pr = m.products, idx = point.row * m.grid.nlon + point.col;
  if (cellFlag(m, state.x, k, idx)) return "disagree";
  const keys = Pr.ens_prob.thresholds_mm.map(thrKey);
  const p50 = src.val("ens_prob", [keys.indexOf("50"), k]), p1 = src.val("ens_prob", [keys.indexOf("1"), k]);
  if (p50 >= 50) return "heavy";
  if (src.val("hres_24h", [k]) >= 1 || p1 >= 50) return "light";
  return "dry";
}

/* Original character, drawn from simple shapes for this app: a round-headed figure in a raincoat collar. */
function guideSVG(pose) {
  const ink = "#2b2f36", face = "#fdf8ee", coat = "#e9b949", umb = "#1f5fa8", drop = "#4a90d9";
  const drops = (n, x0, y0) => Array.from({ length: n }, (_, i) =>
    `<path d="M${x0 + (i % 4) * 9 + (i > 3 ? 4 : 0)} ${y0 + Math.floor(i / 4) * 9} l-1.5 4 a1.6 1.6 0 0 0 3 0z" fill="${drop}"/>`).join("");
  const body = `<path d="M22 70 q0 -17 14 -17 q14 0 14 17z" fill="${coat}" stroke="${ink}" stroke-width="1.5"/>
    <circle cx="36" cy="42" r="11" fill="${face}" stroke="${ink}" stroke-width="1.5"/>`;
  const eyes = (dy = 0) => `<circle cx="32" cy="${41 + dy}" r="1.3" fill="${ink}"/><circle cx="40" cy="${41 + dy}" r="1.3" fill="${ink}"/>`;
  const parts = {
    dry: `${body}${eyes()}<path d="M32 46 q4 3 8 0" stroke="${ink}" stroke-width="1.4" fill="none"/>
      <path d="M53 50 v17" stroke="${ink}" stroke-width="1.6"/><path d="M53 50 q-1 -6 4 -6" stroke="${ink}" stroke-width="1.6" fill="none"/>
      <path d="M51 66 l2 4 l2 -4z" fill="${umb}" stroke="${ink}" stroke-width="1"/>
      <circle cx="60" cy="14" r="5" fill="#f2c94c"/>`,
    light: `${drops(4, 14, 8)}<path d="M18 30 q18 -16 36 0z" fill="${umb}" stroke="${ink}" stroke-width="1.5"/>
      <path d="M36 30 v8" stroke="${ink}" stroke-width="1.4"/>${body}${eyes()}
      <path d="M33 46 h6" stroke="${ink}" stroke-width="1.4"/>`,
    heavy: `${drops(8, 8, 4)}${drops(8, 42, 6)}<path d="M12 31 q24 -22 48 0z" fill="${umb}" stroke="${ink}" stroke-width="1.5"/>
      <path d="M36 31 v8" stroke="${ink}" stroke-width="1.5"/>${body}${eyes(1)}
      <path d="M29.5 37.5 l4 -1.5 M42.5 37.5 l-4 -1.5" stroke="${ink}" stroke-width="1.3"/>
      <path d="M32 47 q2 -2 4 0 q2 2 4 0" stroke="${ink}" stroke-width="1.3" fill="none"/>`,
    disagree: `${body}${eyes()}<path d="M32 47 q4 -1.5 8 1" stroke="${ink}" stroke-width="1.4" fill="none"/>
      <path d="M24 58 l-9 -7 M48 58 l9 -7" stroke="${ink}" stroke-width="2" stroke-linecap="round"/>
      <path d="M13 50 l-3 -2 M59 50 l3 -2" stroke="${ink}" stroke-width="1.5" stroke-linecap="round"/>
      <text x="36" y="25" text-anchor="middle" font-family="system-ui, sans-serif" font-size="17" font-weight="700" fill="${umb}">?</text>`,
  };
  return `<svg viewBox="0 0 72 72" width="64" height="64" role="img" aria-label="${POSE[pose].alt}">
    <title>${POSE[pose].alt}</title>${parts[pose]}</svg>`;
}

/* "100 skies" (feature 2, user 14 Nov): the ensemble chance for X as 100 small umbrellas, open = at least X mm.
   The open count is exactly the whole % in the chip (stored chances are whole percents); "< 2 %" shows 0 open and says
   "fewer than 2 in 100". Worded "in 100", never "members": the data file does not state the ensemble size. */
function skiesFigure(pct, floor, x, windowNote) {
  // Solid squares (user, 14 Nov: 6 px umbrella icons were unreadable): blue = at least X mm, pale sand = less
  // (4.1:1 between them, also for colour-blind viewers); a key with two readable umbrellas keeps the "100 skies" idea.
  const below = pct < floor, n = below ? 0 : Math.round(pct);
  const open = "#1f5fa8", shut = "#e6cb94", edge = "#b07a1e";
  const fig = el("figure", "skies");
  const umb = (isOpen) => isOpen
    ? `<svg viewBox="0 0 12 12" width="14" height="14" aria-hidden="true"><path d="M0.4 6.6 Q6 -0.6 11.6 6.6 Z" fill="${open}"/><path d="M6 6.4 V10.2 q0 1.4 -1.5 1.2" stroke="${open}" stroke-width="1.3" fill="none" stroke-linecap="round"/></svg>`
    : `<svg viewBox="0 0 12 12" width="14" height="14" aria-hidden="true"><path d="M6 0.6 Q9.4 5 8.2 8.6 H3.8 Q2.6 5 6 0.6 Z" fill="${shut}" stroke="${edge}" stroke-width="0.8"/><path d="M6 8.4 V10.2 q0 1.4 -1.5 1.2" stroke="${edge}" stroke-width="1.2" fill="none" stroke-linecap="round"/></svg>`;
  const key = el("p", "skies-key");
  key.setAttribute("aria-hidden", "true");          // the figure's alt text already says it
  key.innerHTML = `${umb(true)}<span>≥ ${fmt(x)} mm</span>${umb(false)}<span>less</span>`;
  let cells = "";
  for (let i = 0; i < 100; i++) {
    cells += `<rect x="${(i % 10) * 7}" y="${Math.floor(i / 10) * 7}" width="6" height="6" rx="1" fill="${i < n ? open : shut}" data-c="${i < n ? 1 : 0}"/>`;
  }
  const say = below ? `fewer than ${fmt(floor)} in 100` : `${n} in 100`;
  const alt = below
    ? `Picture of 100 possible skies ${windowNote}: fewer than ${fmt(floor)} get at least ${fmt(x)} mm, so all 100 squares are pale.`
    : `Picture of 100 possible skies ${windowNote}: ${n} blue squares get at least ${fmt(x)} mm, ${100 - n} pale squares get less.`;
  const row = el("div", "skies-row");
  row.innerHTML = `<svg class="skies-grid" viewBox="0 0 69 69" width="69" height="69" role="img" aria-label="${alt}"><title>${alt}</title>${cells}</svg>`;
  row.appendChild(el("p", "skies-cap", `${say} get ≥ ${fmt(x)} mm ${windowNote}`));
  fig.append(key, row);
  fig.dataset.open = String(n);
  return fig;
}

function guideOn() { try { return localStorage.getItem("guide") !== "off"; } catch (e) { return true; } }

function renderCard(app) {
  const card = $("pcard"), { m, src, point } = app;
  if (!src || !point || app.cardClosed) { card.hidden = true; return; }
  const Pr = m.products, idx = point.row * m.grid.nlon + point.col;
  const k24 = frameIndex(Pr.hres_24h.frames), f24 = Pr.hres_24h.frames[k24];
  const keys = Pr.ens_prob.thresholds_mm.map(thrKey), kx = keys.indexOf(state.x);
  const ef = Pr.ens_prob.frames_by_threshold[state.x][k24];
  let when, main;
  if (state.mode === "3h") {
    const k = frameIndex(Pr.hres_3h.frames), f = Pr.hres_3h.frames[k];
    when = f.label_ist; main = `Rain in 3 hours: ${fmtMm(src.val("hres_3h", [k]), f.lowest_drawn)}`;
  } else {
    when = f24.label_ist; main = `Rain in 24 hours (HRES): ${fmtMm(src.val("hres_24h", [k24]), f24.lowest_drawn)}`;
  }
  const pct = src.val("ens_prob", [kx, k24]);
  const flag = cellFlag(m, state.x, k24, idx);
  const pose = poseFor(app, k24);
  card.innerHTML = "";
  card.dataset.pose = pose;
  const head = el("div", "pc-head");
  const near = el("p", "pc-near", nearText(app.places || [], point.lat, point.lon));
  const x = el("button", "pc-close", "×");
  x.type = "button"; x.setAttribute("aria-label", "Close the point summary (Esc)");
  x.addEventListener("click", () => closeCard(app));
  head.append(near, x);
  const body = el("div", "pc-body");
  const text = el("div", "pc-text");
  text.append(el("p", "pc-when", when), el("p", "pc-main", main));
  // non-breaking spaces keep "100 %" and "10 mm" together in the narrow card
  const chip = el("span", "pc-chip", `${state.mode === "3h" ? "24 h chance" : "Chance"} of ≥\u00a0${fmt(state.x)}\u00a0mm: ${fmtPct(pct, ef.lowest_drawn).replace(" %", "\u00a0%")}`);
  const bg = pct < ef.lowest_drawn ? null : binColour(Pr.ens_prob, pct);
  if (bg) { chip.style.background = bg; chip.style.color = textOn(bg); }
  text.appendChild(chip);
  text.appendChild(skiesFigure(pct, ef.lowest_drawn, state.x,
    state.mode === "3h" ? "in the 24-hour window" : "in this 24-hour window"));
  if (flag) text.appendChild(el("p", "pc-badge " + flag.kind,
    flag.kind === "wetter" ? "▨ Detailed run much wetter than the ensemble" : "• Detailed run much drier than the ensemble"));
  body.appendChild(text);
  if (guideOn()) {
    const g = el("figure", "pc-guide");
    g.innerHTML = guideSVG(pose);
    g.appendChild(el("figcaption", null, POSE[pose].caption));
    body.appendChild(g);
  }
  const more = el("button", "pc-more", "Full details");
  more.type = "button";
  more.addEventListener("click", () => {
    closeCard(app);
    const box = $("point");
    box.scrollIntoView({ block: "nearest", behavior: "smooth" });
    $("point-title").setAttribute("tabindex", "-1");
    $("point-title").focus({ preventScroll: true });
  });
  card.append(head, body, more);
  // field names for checks: same texts as the panel's data-fields
  near.dataset.field = "card-near"; text.querySelector(".pc-main").dataset.field = "card-main"; chip.dataset.field = "card-chip";
  card.hidden = false;
  positionCard(app);
  updateMore();
}

/* "Full details" only when the panel's point details are NOT on screen (user, 14 Nov): phones (panel below the map),
   short screens (controls first in the panel), or a side panel scrolled away. On a desktop with them in view it would
   only repeat what is already visible, so it is hidden. */
function updateMore() {
  const more = document.querySelector("#pcard .pc-more");
  if (!more || $("point").hidden) return;
  const t = $("point-title").getBoundingClientRect(), p = $("panel").getBoundingClientRect();
  const card = $("pcard"), sheetTop = card.classList.contains("sheet") ? card.getBoundingClientRect().top : innerHeight;
  const top = Math.max(0, p.top), bottom = Math.min(innerHeight, p.bottom, sheetTop);   // the phone sheet covers the bottom
  const inView = t.height > 0 && t.top >= top - 1 && t.bottom <= bottom + 1;
  more.hidden = inView;
}

function positionCard(app) {
  const card = $("pcard");
  if (card.hidden || !app.point) return;
  if (window.matchMedia("(max-width: 700px)").matches) { card.classList.add("sheet"); card.style.left = card.style.top = ""; return; }
  card.classList.remove("sheet");
  const map = app.map, size = map.getSize(), pt = map.latLngToContainerPoint([app.point.lat, app.point.lon]);
  const w = card.offsetWidth, h = card.offsetHeight, gap = 16;
  let left = pt.x + gap, top = pt.y - h / 2;
  if (left + w > size.x - 6) left = pt.x - gap - w;              // flip to the left of the point near the right edge
  left = Math.max(6, Math.min(left, size.x - w - 6));
  top = Math.max(44, Math.min(top, size.y - h - 6));               // clear of the "Showing" pill at the top
  card.style.left = `${left}px`;
  card.style.top = `${top}px`;
}

function closeCard(app) {
  app.cardClosed = true;
  $("pcard").hidden = true;
}

/* ---------------- render ---------------- */

function render(app) {
  const { m, map, fill, hatch } = app;
  const frames = framesFor(m);
  const k = frameIndex(frames);
  const f = frames[k];
  state.t = f.start_h;

  fill.setUrl(DATA + f.file);

  // Disagreement marks: 24 h mode only; bold images below the readable zoom, fine ones above.
  const minZ = m.products.disagreement.min_zoom_for_marks;
  const low = map.getZoom() < minZ;
  let hatchFile = null;
  if (state.mode === "24h" && state.hatch) {
    const h = hatchFrame(m, k);
    hatchFile = low ? h.file_bold : h.file;
  }
  if (hatchFile) { hatch.setUrl(DATA + hatchFile); if (!map.hasLayer(hatch)) hatch.addTo(map); }
  else if (map.hasLayer(hatch)) map.removeLayer(hatch);

  // Zoom note: on load the region is fitted (below zoom 6), so the note is visible straight away.
  const note = $("zoom-note"), noteIn = $("zoom-note-inline");
  note.textContent = noteIn.textContent = m.products.disagreement.zoom_note;
  note.hidden = noteIn.hidden = !(state.mode === "24h" && state.hatch && low);

  // Controls reflect state
  document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.mode === state.mode));
  document.querySelectorAll("[data-fill]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.fill === state.fill));
  $("box24").hidden = state.mode !== "24h";
  $("x").value = state.x;
  $("hatch").checked = state.hatch;
  $("chance-btn-title").textContent = `Chance of ≥ ${xLabel(state.x)} mm`;
  const slider = $("t");
  slider.max = frames.length - 1;
  slider.value = k;
  slider.setAttribute("aria-valuetext", f.label_ist);
  $("t-label").textContent = f.label_ist;
  $("t-lead").textContent = `${f.start_h}–${f.end_h} h after the forecast run · frame ${k + 1} of ${frames.length}`;
  $("showing").innerHTML = "";
  const s = document.createElement("span");
  s.textContent = "Showing: " + showingText(m);
  $("showing").appendChild(s);

  renderLegend(m, f);
  if (app.point && app.src) renderPointContent(app);

  // For checks: what is on screen
  document.body.dataset.frame = f.file + (hatchFile ? " + " + hatchFile : "");
  writeHash();
  preload(frames, k);
  // For checks: does the page scroll sideways? (must be "false" at phone width)
  document.body.dataset.hscroll = document.documentElement.scrollWidth > window.innerWidth;
  document.body.dataset.zoom = map.getZoom();
}

const cache = new Map();
function preload(frames, k) {
  [k - 1, k + 1].forEach((i) => {
    if (i < 0 || i >= frames.length) return;
    const url = DATA + frames[i].file;
    if (!cache.has(url)) { const im = new Image(); im.src = url; cache.set(url, im); }
  });
}

function wire(app) {
  const { m, map } = app;
  const rerender = () => render(app);
  document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
    state.mode = b.dataset.mode; rerender();
  }));
  document.querySelectorAll("[data-fill]").forEach((b) => b.addEventListener("click", () => {
    state.fill = b.dataset.fill; rerender();
  }));
  const sel = $("x");
  m.products.ens_prob.thresholds_mm.forEach((t) => {
    const o = document.createElement("option");
    o.value = `${t}`.replace(/\.0$/, "");
    o.textContent = `≥ ${Number(t)}`;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => { state.x = sel.value; rerender(); });
  $("hatch").addEventListener("change", (e) => { state.hatch = e.target.checked; rerender(); });
  const step = (d) => {
    const frames = framesFor(m);
    const k = Math.min(frames.length - 1, Math.max(0, frameIndex(frames) + d));
    state.t = frames[k].start_h; rerender();
  };
  $("t").addEventListener("input", (e) => { state.t = framesFor(m)[+e.target.value].start_h; rerender(); });
  $("prev").addEventListener("click", () => step(-1));
  $("next").addEventListener("click", () => step(1));

  /* Play (feature 1, user 14 Nov): steps the time slider about once a second and loops. Never autoplays; with
     prefers-reduced-motion it steps every 2 s. Any user interaction pauses it (except Space/Enter on the button). */
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)");
  const playBtn = $("play");
  let playTimer = null;
  const setPlayBtn = (on) => {
    playBtn.textContent = on ? "❚❚" : "▶";
    playBtn.setAttribute("aria-pressed", String(on));
    playBtn.setAttribute("aria-label", on ? "Pause time animation" : "Play time animation");
    document.body.dataset.playing = on ? "1" : "0";
  };
  const tick = () => {
    const frames = framesFor(m);
    state.t = frames[(frameIndex(frames) + 1) % frames.length].start_h;   // after the last window: back to the first
    rerender();
  };
  const play = () => { if (!playTimer) { playTimer = setInterval(tick, REDUCED.matches ? 2000 : 1000); setPlayBtn(true); } };
  const pause = () => { if (playTimer) { clearInterval(playTimer); playTimer = null; setPlayBtn(false); } };
  app.pause = pause;
  playBtn.addEventListener("click", () => (playTimer ? pause() : play()));
  const pauseOnPointer = (e) => { if (playTimer && !playBtn.contains(e.target)) pause(); };
  ["pointerdown", "wheel", "touchstart"].forEach((ev) =>
    document.addEventListener(ev, pauseOnPointer, { capture: true, passive: true }));
  document.addEventListener("keydown", (e) => {
    if (playTimer && !(e.target === playBtn && (e.key === " " || e.key === "Enter"))) pause();
  }, true);
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
  setPlayBtn(false);
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
    if (document.activeElement === map.getContainer()) return;   // on the focused map, arrows pan (Leaflet)
    if (e.key === "ArrowLeft") step(-1);
    if (e.key === "ArrowRight") step(1);
  });
  map.on("zoomend", rerender);
  map.on("click", (e) => selectPoint(app, e.latlng.lat, e.latlng.lng, true));
  // Keyboard (M8 B, user 14 Nov): the crosshair stands on a GRID POINT. Arrows move it one grid point (0.25 deg),
  // Shift+arrow ten; the map pans just enough to keep it in view; +/- zoom around it; Enter selects exactly that grid
  // point; a readout beside it gives its position and nearest place. Shown only for keyboard use (13 Nov).
  const mc = map.getContainer();
  mc.setAttribute("aria-label",
    "Forecast map. Arrow keys move the cross one grid point (0.25 degrees), Shift with an arrow moves ten, " +
    "plus and minus zoom around the cross, Enter shows the forecast at the cross, Escape closes it. " +
    "The position of the cross and the nearest place are read out.");
  const g = m.grid, ch = $("crosshair"), readout = $("cross-readout"), live = $("cross-live");
  const cur = app.cursor;                    // shared with selectPoint (click, p= link, search, Enter)
  let lastInput = "pointer", liveTimer = null;
  const crossLatLng = () => [g.lat_north - cur.row * g.dlat, g.lon_west + cur.col * g.dlon];
  const showCross = (on) => { ch.hidden = !on; readout.hidden = !on; };
  const clampRC = () => {
    cur.row = Math.min(g.nlat - 1, Math.max(0, cur.row));
    cur.col = Math.min(g.nlon - 1, Math.max(0, cur.col));
  };
  function startAt() {                       // the selected point, else the grid point nearest the map centre
    if (app.point) { cur.row = app.point.row; cur.col = app.point.col; return; }
    const c = map.getCenter();
    cur.row = Math.round((g.lat_north - c.lat) / g.dlat);
    cur.col = Math.round((c.lng - g.lon_west) / g.dlon);
    clampRC();
  }
  function drawCross() {
    if (cur.row === null || ch.hidden) return;
    const size = map.getSize(), pt = map.latLngToContainerPoint(crossLatLng());
    ch.style.left = `${pt.x}px`;
    ch.style.top = `${pt.y}px`;
    const [lat, lon] = crossLatLng();
    readout.textContent = `${fmtLat(lat)} ${fmtLon(lon)} · ${nearText(app.places || [], lat, lon)}`;
    // readout beside the cross, flipped to the other side near the right/bottom edge
    const rw = readout.offsetWidth || 220, flipX = pt.x + 18 + rw > size.x - 4, flipY = pt.y + 40 > size.y - 4;
    readout.style.left = `${flipX ? pt.x - 18 - rw : pt.x + 18}px`;
    readout.style.top = `${flipY ? pt.y - 34 : pt.y + 14}px`;
    mc.dataset.cross = `${cur.row},${cur.col}`;              // for checks
    clearTimeout(liveTimer);                                  // screen readers: announce once the cross rests
    liveTimer = setTimeout(() => { live.textContent = readout.textContent; }, 300);
  }
  function keepInView() {                    // pan just enough that the cross stays inside a margin of the map box
    const size = map.getSize(), pt = map.latLngToContainerPoint(crossLatLng());
    const mx = Math.min(48, size.x / 4), my = Math.min(48, size.y / 4);
    const dx = pt.x < mx ? pt.x - mx : pt.x > size.x - mx ? pt.x - (size.x - mx) : 0;
    const dy = pt.y < my ? pt.y - my : pt.y > size.y - my ? pt.y - (size.y - my) : 0;
    if (dx || dy) map.panBy([dx, dy], { animate: false });   // Leaflet then keeps the view inside its max bounds
  }
  document.addEventListener("keydown", () => { lastInput = "keyboard"; }, true);
  document.addEventListener("pointerdown", () => { lastInput = "pointer"; showCross(false); }, true);
  mc.addEventListener("focus", () => {
    if (lastInput !== "keyboard") return;
    if (cur.row === null) startAt();
    showCross(true);
    keepInView();
    drawCross();
  });
  app.drawCross = drawCross;
  mc.addEventListener("blur", () => showCross(false));
  map.on("move zoom resize", () => { if (!ch.hidden) drawCross(); });

  const ARROWS = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
  const ZOOM_KEYS = { "+": 1, "=": 1, "-": -1, "_": -1 };
  // capture phase + stopImmediatePropagation: this runs before Leaflet's own keyboard handler on the same element,
  // which must not pan or zoom as well
  mc.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const arrow = ARROWS[e.key], zoom = ZOOM_KEYS[e.key];
    if (!arrow && !zoom && e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    map.stop();
    if (cur.row === null) startAt();
    showCross(true);
    if (arrow) {
      const n = e.shiftKey ? 10 : 1;
      cur.row += arrow[0] * n; cur.col += arrow[1] * n;
      clampRC();
      keepInView();
      drawCross();
    } else if (zoom) {
      const z = Math.min(map.getMaxZoom(), Math.max(map.getMinZoom(), map.getZoom() + zoom * map.options.zoomDelta));
      map.setZoomAround(L.latLng(crossLatLng()), z, { animate: false });   // the cross keeps its place on screen
      keepInView();
      drawCross();
    } else {
      const [lat, lon] = crossLatLng();       // exactly this grid point: no pixel-to-location conversion
      selectPoint(app, lat, lon, true);
      drawCross();
    }
  }, true);
  window.__rainOutlook.cross = cur;          // for dev checks only (same object as app.cursor)
  $("point-close").addEventListener("click", () => closePoint(app));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("pcard").hidden) { closeCard(app); return; }       // first Esc: the card; second: the panel
    if (!$("point").hidden) closePoint(app);
  });
  map.on("move zoom resize", () => positionCard(app));
  $("panel").addEventListener("scroll", updateMore, { passive: true });
  window.addEventListener("scroll", updateMore, { passive: true });
  window.addEventListener("resize", updateMore);
  const guide = $("guide");
  guide.checked = guideOn();
  guide.addEventListener("change", () => {
    try { localStorage.setItem("guide", guide.checked ? "on" : "off"); } catch (e) { /* private mode: this page only */ }
    if (app.point && app.src && !$("pcard").hidden) renderCard(app);
  });
  window.__rainOutlook.app = app;            // dev checks
}

async function main() {
  if (typeof L === "undefined") {
    throw new Error("the map library (Leaflet, vendor/leaflet-1.9.4/leaflet.js) did not load. " +
      "Reload the page; if it persists, check the browser console for the blocked file.");
  }
  const m = await getJSON(DATA + "manifest.json");
  const view = readHash(m);
  const map = makeMap(m);
  // No animation: the zoom must be final before the first render picks fine/bold marks and the zoom note.
  if (view) map.setView(view.center, view.zoom, { animate: false });
  const places = await addBasemap(map, m);
  const opts = { pane: "fill", className: "px", interactive: false };
  const fill = L.imageOverlay(DATA + m.products.hres_24h.frames[0].file, m.image.bounds, opts).addTo(map);
  const hatch = L.imageOverlay(DATA + m.products.hres_24h.frames[0].file, m.image.bounds,
    { pane: "hatch", className: "px", interactive: false });
  const app = { m, map, fill, hatch, places, cursor: { row: null, col: null } };
  window.__rainOutlook = { map };                 // for dev checks (crosshair test); not used by the page
  // Leaflet measures its box once and only re-measures on window resize. The box also changes when the header and
  // footer text arrive, when fonts load, or when panels change height; a stale size put Leaflet's centre 33-49 px
  // below the crosshair (13 Nov). Tell Leaflet every time the box actually changes.
  // Until the user moves or zooms the map (or a shared link set the view), keep the whole region fitted when the
  // map box changes size: the first fit happens before the header text arrives, so on short screens (M8 D) the
  // final, shorter map no longer fitted the region.
  let userMoved = !!view;
  ["mousedown", "touchstart", "wheel", "keydown"].forEach((ev) =>
    map.getContainer().addEventListener(ev, () => { userMoved = true; }, { capture: true, passive: true }));
  if ("ResizeObserver" in window) {
    new ResizeObserver(() => {
      map.invalidateSize({ pan: false });
      if (!userMoved) map.fitBounds(m.image.bounds, { animate: false });
    }).observe(map.getContainer());
  }
  wire(app);
  wireSearch(app);
  renderHeader(m);
  renderFooter(m);
  render(app);
  // wake the point API early (a sleeping free Space takes a while); errors are irrelevant here
  if (m.api && !API_OFF) fetch(`${m.api.url}/health`).catch(() => {});
  if (state.p) selectPoint(app, state.p[0], state.p[1], false);   // shared link with a selected point
  setStatus("ready");
  // The forecast did load, so any banner left by an earlier error would be false: remove it.
  document.querySelectorAll(".map-wrap .error").forEach((el) => el.remove());
}

main().catch((e) => showError(e.message));
