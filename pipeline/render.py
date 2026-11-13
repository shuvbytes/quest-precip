"""Render gridded frames to PNGs that Leaflet can place with L.imageOverlay.

Why reproject: Leaflet's map is Web Mercator (EPSG:3857). L.imageOverlay stretches an image
linearly between its corner lat/lons *in Mercator space*. Our data is a regular lat/lon grid,
so drawing it as-is would put rows at the wrong latitudes (rows are evenly spaced in latitude,
but Mercator rows are not). Each output pixel row is therefore assigned the source row whose
latitude band it falls in, using the Mercator formula.

No smoothing: every pixel takes the value of exactly one source grid point (nearest neighbour),
so each 0.25 deg point shows as a block. That matches what the data is (point samples on a grid).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


def merc_y(lat_deg):
    """Web Mercator northing for a sphere of radius 1 (scale cancels out in the overlay)."""
    lat = np.radians(np.asarray(lat_deg, float))
    return np.log(np.tan(np.pi / 4 + lat / 2))


def merc_lat(y):
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


@dataclass(frozen=True)
class Grid:
    """Regular grid of point samples; image bounds are the cell EDGES (half a step outside)."""
    lat_n: float        # northernmost grid-point latitude (row 0)
    lon_w: float        # westernmost grid-point longitude (col 0)
    dlat: float
    dlon: float
    nlat: int
    nlon: int
    px_per_cell: int = 4

    @classmethod
    def from_coords(cls, lat, lon, px_per_cell=4):
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        assert lat[0] > lat[-1], "expects latitude north -> south"
        dlat, dlon = lat[0] - lat[1], lon[1] - lon[0]
        assert np.allclose(np.diff(lat), -dlat) and np.allclose(np.diff(lon), dlon)
        return cls(float(lat[0]), float(lon[0]), float(dlat), float(dlon), len(lat), len(lon), px_per_cell)

    @property
    def bounds(self):
        """Leaflet bounds [[south, west], [north, east]] of the image (cell edges)."""
        s = self.lat_n - (self.nlat - 1) * self.dlat - self.dlat / 2
        n = self.lat_n + self.dlat / 2
        w = self.lon_w - self.dlon / 2
        e = self.lon_w + (self.nlon - 1) * self.dlon + self.dlon / 2
        return [[s, w], [n, e]]

    @property
    def width(self):
        return self.nlon * self.px_per_cell

    @property
    def height(self):
        """Pixels tall so that pixels are square on the Mercator map."""
        (s, w), (n, e) = self.bounds
        return int(round(self.width * (merc_y(n) - merc_y(s)) / np.radians(e - w)))

    # --- the mapping Leaflet uses: pixel <-> (lat, lon), linear in Mercator inside the bounds ---
    def pixel_to_latlon(self, row, col):
        (s, w), (n, e) = self.bounds
        y = merc_y(n) - (np.asarray(row) + 0.5) * (merc_y(n) - merc_y(s)) / self.height
        lon = w + (np.asarray(col) + 0.5) * (e - w) / self.width
        return merc_lat(y), lon

    def latlon_to_pixel(self, lat, lon):
        (s, w), (n, e) = self.bounds
        row = (merc_y(n) - merc_y(lat)) / (merc_y(n) - merc_y(s)) * self.height - 0.5
        col = (np.asarray(lon) - w) / (e - w) * self.width - 0.5
        return np.round(row).astype(int), np.round(col).astype(int)

    def source_index(self, lat, lon):
        """Grid point whose cell contains (lat, lon)."""
        i = np.floor((self.lat_n + self.dlat / 2 - np.asarray(lat)) / self.dlat).astype(int)
        j = np.floor((np.asarray(lon) - (self.lon_w - self.dlon / 2)) / self.dlon).astype(int)
        return np.clip(i, 0, self.nlat - 1), np.clip(j, 0, self.nlon - 1)

    def resample_index(self):
        """Source row index for every output row, source col index for every output col."""
        lat, _ = self.pixel_to_latlon(np.arange(self.height), 0)
        _, lon = self.pixel_to_latlon(0, np.arange(self.width))
        rows, _ = self.source_index(lat, self.lon_w)
        _, cols = self.source_index(self.lat_n, lon)
        return rows, cols


def classify(values, bins, lowest_drawn, n_colours):
    """Colour index per value: 0 = transparent, 1..n_colours = palette entries.

    Bins [b0, b1, ..., bk]: value in [b_i, b_{i+1}) -> colour i. Values >= bk take the last colour
    (over-range for rain; exactly 100 % for probabilities). Values < lowest_drawn (the frame's
    display floor, normally b0) and NaN are transparent.
    """
    v = np.asarray(values, float)
    idx = np.digitize(v, bins) - 1                    # -1 below b0, k at/above bk
    idx = np.clip(idx, -1, n_colours - 1)
    out = (idx + 1).astype(np.uint8)
    out[(v < lowest_drawn) | np.isnan(v)] = 0
    return out


HATCH_INK = "#111111"
HATCH_EDGE = "#ffffff"


HATCH_PX_PER_CELL = {"fine": 12,   # zoom >= 6: whole symbol per cell, thin strokes
                     "bold": 4}    # zoom < 6 (user, 13 Nov): fewer, thicker marks that survive downscaling


def hatch_grid(grid: Grid, style: str = "fine") -> Grid:
    """Same grid and bounds, more pixels per cell (the overlay is placed by bounds, so it aligns)."""
    return Grid(grid.lat_n, grid.lon_w, grid.dlat, grid.dlon, grid.nlat, grid.nlon, HATCH_PX_PER_CELL[style])


def hatch_codes(wetter, drier, grid: Grid, style: str = "fine"):
    """Pattern codes per output pixel: 0 transparent, 1 ink, 2 white edge.

    wetter -> diagonal lines; drier -> ONE round dot centred in each cell, so a single flagged cell
    always shows a complete symbol. Ink with a white edge stays visible on both the palest and darkest
    probability colours; the shape (not colour) carries the meaning.
    fine: 1-px lines every 6 px, small dot.  bold: 2-px lines every 4 px, dot filling most of the cell.
    """
    rows, cols = grid.resample_index()
    wet = np.asarray(wetter, bool)[np.ix_(rows, cols)]
    dry = np.asarray(drier, bool)[np.ix_(rows, cols)]
    r, c = np.meshgrid(np.arange(grid.height), np.arange(grid.width), indexing="ij")
    out = np.zeros((grid.height, grid.width), np.uint8)
    if style == "fine":
        d = (r + c) % 6
        ink, edge = d == 0, d == 1
        r_ink, r_edge = 0.24, 0.36
    else:
        d = (r + c) % 4
        ink, edge = d <= 1, d == 2
        r_ink, r_edge = 0.30, 0.50
    out[wet & ink] = 1
    out[wet & edge] = 2
    # position of each pixel inside its source cell, in cell units (-0.5..0.5)
    plat, _ = grid.pixel_to_latlon(np.arange(grid.height), 0)
    _, plon = grid.pixel_to_latlon(0, np.arange(grid.width))
    fy = (plat - (grid.lat_n - rows * grid.dlat)) / grid.dlat
    fx = (plon - (grid.lon_w + cols * grid.dlon)) / grid.dlon
    rad = np.hypot(fy[:, None], fx[None, :])
    out[dry & (rad <= r_edge)] = 2
    out[dry & (rad <= r_ink)] = 1
    return out


def render_hatch(wetter, drier, grid: Grid, path: Path, style: str = "fine"):
    grid = hatch_grid(grid, style)
    codes = hatch_codes(wetter, drier, grid, style)
    img = Image.fromarray(codes, mode="P")
    pal = [0, 0, 0] + [int(h[i:i + 2], 16) for h in (HATCH_INK, HATCH_EDGE) for i in (1, 3, 5)]
    img.putpalette(pal + [0, 0, 0] * (256 - len(pal) // 3))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True, transparency=0)
    return path


def render_png(field, grid: Grid, bins, colours, lowest_drawn, path: Path):
    """Write one frame as an indexed PNG with index 0 transparent."""
    assert field.shape == (grid.nlat, grid.nlon)
    rows, cols = grid.resample_index()
    codes = classify(field, bins, lowest_drawn, len(colours))[np.ix_(rows, cols)]
    img = Image.fromarray(codes, mode="P")
    pal = [0, 0, 0]
    for hx in colours:
        pal += [int(hx[i:i + 2], 16) for i in (1, 3, 5)]
    img.putpalette(pal + [0, 0, 0] * (256 - len(pal) // 3))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True, transparency=0)
    return path
