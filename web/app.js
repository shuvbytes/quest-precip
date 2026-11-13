/* India Rain Outlook: map page. Everything shown (times, labels, bins, colours, text) comes from
   data/manifest.json, written by pipeline/build.py. Nothing about the forecast is hard-coded here. */
"use strict";

const DATA = "data/";

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
  map.fitBounds(b);
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

async function main() {
  const m = await getJSON(DATA + "manifest.json");
  const map = makeMap(m);
  await addBasemap(map, m);
  // Skeleton: first HRES 24 h frame, to check placement. Controls come next.
  const f = m.products.hres_24h.frames[0];
  L.imageOverlay(DATA + f.file, m.image.bounds, { pane: "fill", className: "px", interactive: false }).addTo(map);
  document.getElementById("run-line").textContent = `Forecast run: ${m.run.ist} (${m.run.utc.replace("T", " ").replace("Z", " UTC")})`;
  setStatus("ready");
}

main().catch((e) => showError(e.message));
