/* India Rain Outlook: map page. Everything shown (times, labels, bins, colours, text) comes from
   data/manifest.json, written by pipeline/build.py. Nothing about the forecast is hard-coded here. */
"use strict";

const DATA = "data/";
const $ = (id) => document.getElementById(id);

function setStatus(s) { document.body.dataset.status = s; }

function showError(msg) {
  setStatus("error: " + msg);
  const div = document.createElement("div");
  div.className = "error";
  div.textContent = "Could not load the forecast: " + msg;
  document.querySelector(".map-wrap").appendChild(div);
}
window.addEventListener("error", (e) => showError(e.message));

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/* ---------------- map ---------------- */

function makeMap(m) {
  const map = L.map("map", {
    zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 4, maxZoom: 9,
    attributionControl: false,              // full attribution is in the footer
  });
  // Draw order (bottom -> top): land fill, rain/chance image, disagreement hatch, coast + India boundary lines.
  [["land", 200], ["fill", 300], ["hatch", 350], ["lines", 450]].forEach(([name, z]) => {
    map.createPane(name).style.zIndex = z;
  });
  map.getPane("lines").style.pointerEvents = "none";
  map.getContainer().style.background = m.basemap.sea;
  const b = m.image.bounds;
  map.setMaxBounds(L.latLngBounds(b).pad(0.15));
  map.fitBounds(b);                          // user decision: fit the whole region on every screen
  return map;
}

async function addBasemap(map, m) {
  const [land, coast, india] = await Promise.all([
    getJSON("geo/land.geojson"), getJSON("geo/coastline.geojson"), getJSON("geo/india-boundary.geojson")]);
  // Land as a fill only; the coastline comes from a separate line layer, so no clip edges are ever drawn.
  L.geoJSON(land, { pane: "land", interactive: false,
    style: { stroke: false, fillColor: m.basemap.land, fillOpacity: 1 } }).addTo(map);
  L.geoJSON(coast, { pane: "lines", interactive: false,
    style: { color: "#8a8f98", weight: 0.8, fill: false } }).addTo(map);
  L.geoJSON(india, { pane: "lines", interactive: false,
    style: { color: "#2b2f36", weight: 1.4, fill: false } }).addTo(map);
  // Outline of the area that has forecast data: outside it, "no colour" means "no data", not "no rain".
  L.rectangle(m.image.bounds, { pane: "lines", interactive: false,
    color: "#6b717b", weight: 1, dashArray: "4 4", fill: false }).addTo(map);
}

/* ---------------- state (kept in the URL hash, so a view can be shared or bookmarked) ---------------- */

const state = { mode: "24h", fill: "chance", x: "10", hatch: true, t: 0 };

function readHash(m) {
  const h = new URLSearchParams(location.hash.slice(1));
  if (["3h", "24h"].includes(h.get("mode"))) state.mode = h.get("mode");
  if (["rain", "chance"].includes(h.get("fill"))) state.fill = h.get("fill");
  if (h.get("x") && m.products.ens_prob.frames_by_threshold[h.get("x")]) state.x = h.get("x");
  if (h.get("hatch") === "0") state.hatch = false;
  if (h.get("t") !== null && !isNaN(+h.get("t"))) state.t = +h.get("t");
  const z = h.get("z"), c = h.get("c");
  return z && c ? { zoom: +z, center: c.split(",").map(Number) } : null;
}

function writeHash() {
  const h = new URLSearchParams({ mode: state.mode, t: state.t });
  if (state.mode === "24h") { h.set("fill", state.fill); h.set("x", state.x); h.set("hatch", state.hatch ? 1 : 0); }
  history.replaceState(null, "", "#" + h.toString());
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
  const note = $("zoom-note");
  note.textContent = m.products.disagreement.zoom_note;
  note.hidden = !(state.mode === "24h" && state.hatch && low);

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

  // For checks: what is on screen
  document.body.dataset.frame = f.file + (hatchFile ? " + " + hatchFile : "");
  writeHash();
  preload(frames, k);
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
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
    if (e.key === "ArrowLeft") step(-1);
    if (e.key === "ArrowRight") step(1);
  });
  map.on("zoomend", rerender);
}

async function main() {
  const m = await getJSON(DATA + "manifest.json");
  const view = readHash(m);
  const map = makeMap(m);
  if (view) map.setView(view.center, view.zoom);
  await addBasemap(map, m);
  const opts = { pane: "fill", className: "px", interactive: false };
  const fill = L.imageOverlay(DATA + m.products.hres_24h.frames[0].file, m.image.bounds, opts).addTo(map);
  const hatch = L.imageOverlay(DATA + m.products.hres_24h.frames[0].file, m.image.bounds,
    { pane: "hatch", className: "px", interactive: false });
  const app = { m, map, fill, hatch };
  wire(app);
  document.getElementById("run-line").textContent =
    `Forecast run: ${m.run.ist} (${m.run.utc.replace("T", " ").replace("Z", " UTC")})`;
  render(app);
  setStatus("ready");
}

main().catch((e) => showError(e.message));
