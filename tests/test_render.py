import numpy as np
import pytest

from render import Grid, classify, merc_lat, merc_y

LAT = np.arange(38.0, 4.99, -0.25)
LON = np.arange(65.0, 100.01, 0.25)


def test_grid_shape_and_bounds():
    g = Grid.from_coords(LAT, LON)
    assert (g.nlat, g.nlon) == (133, 141)
    assert g.bounds == [[4.875, 64.875], [38.125, 100.125]]


def test_mercator_roundtrip():
    lat = np.linspace(-80, 80, 17)
    np.testing.assert_allclose(merc_lat(merc_y(lat)), lat, atol=1e-9)


def test_every_pixel_samples_the_cell_it_is_drawn_in():
    """Where Leaflet draws a pixel (linear in Mercator) must lie inside the source cell used."""
    g = Grid.from_coords(LAT, LON)
    rows, cols = g.resample_index()
    lat, _ = g.pixel_to_latlon(np.arange(g.height), 0)
    _, lon = g.pixel_to_latlon(0, np.arange(g.width))
    assert np.all(np.abs(lat - LAT[rows]) <= g.dlat / 2 + 1e-9)
    assert np.all(np.abs(lon - LON[cols]) <= g.dlon / 2 + 1e-9)
    # every source row and column appears at least once
    assert set(rows) == set(range(g.nlat)) and set(cols) == set(range(g.nlon))


@pytest.mark.parametrize("style", ["fine", "bold"])
def test_hatch_only_inside_flagged_cells(style):
    from render import hatch_codes, hatch_grid
    g = hatch_grid(Grid.from_coords(LAT, LON), style)
    wet = np.zeros((g.nlat, g.nlon), bool); dry = np.zeros_like(wet)
    wet[40, 50] = True; dry[100, 20] = True
    codes = hatch_codes(wet, dry, g, style)
    rows, cols = g.resample_index()
    in_wet = (rows[:, None] == 40) & (cols[None, :] == 50)
    in_dry = (rows[:, None] == 100) & (cols[None, :] == 20)
    assert codes[~(in_wet | in_dry)].max() == 0          # nothing drawn outside flagged cells
    assert (codes[in_wet] == 1).any() and (codes[in_dry] == 1).any()


@pytest.mark.parametrize("style", ["fine", "bold"])
def test_drier_dot_is_whole_and_centred_in_its_cell(style):
    from render import hatch_codes, hatch_grid
    g = hatch_grid(Grid.from_coords(LAT, LON), style)
    dry = np.zeros((g.nlat, g.nlon), bool)
    dry[100, 20] = True                                  # one isolated cell
    codes = hatch_codes(np.zeros_like(dry), dry, g, style)
    rr, cc = np.nonzero(codes == 1)
    # ink forms one compact blob in the middle of the cell, surrounded by white
    assert rr.max() - rr.min() <= 6 and cc.max() - cc.min() <= 6
    r0, c0 = g.latlon_to_pixel(LAT[100], LON[20])         # cell centre in pixels
    assert abs(rr.mean() - r0) <= 1 and abs(cc.mean() - c0) <= 1
    ring = np.nonzero(codes == 2)
    assert ring[0].min() < rr.min() and ring[0].max() > rr.max()


def test_classify_bins_floor_and_over():
    bins = [0.5, 1, 2, 5]
    v = np.array([np.nan, 0.0, 0.49, 0.5, 0.99, 1.0, 4.9, 5.0, 999])
    # 3 bins + over colour = 4 colours
    np.testing.assert_array_equal(classify(v, bins, 0.5, 4), [0, 0, 0, 1, 1, 2, 3, 4, 4])
    # raised floor: lowest drawn edge 1.0 hides the 0.5-1 bin
    np.testing.assert_array_equal(classify(v, bins, 1.0, 4), [0, 0, 0, 0, 0, 2, 3, 4, 4])
    # probabilities: 3 colours for 3 bins, exactly-top value takes the top colour
    np.testing.assert_array_equal(classify(np.array([1, 2, 99, 100]), [2, 10, 50, 100], 2, 3), [0, 1, 3, 3])


def test_render_png_hides_values_below_a_raised_floor(tmp_path):
    """End of the floor chain on its own: a written PNG has no colour for 0.7 mm when lowest_drawn is 1.0 (a coarse
    frame), but does when lowest_drawn is 0.5. Never vacuous, unlike a check that needs a real run with raised floors."""
    from PIL import Image
    from render import Grid, render_png
    g = Grid(10.0, 80.0, 0.25, 0.25, 3, 3)
    field = np.full((3, 3), 0.7)
    field[0, 0] = 3.0                                          # one clearly visible cell
    bins, colours = [0.5, 1, 2, 5], ["#111111", "#222222", "#333333", "#444444"]
    for lowest, want in ((1.0, {0, 3}), (0.5, {1, 3})):         # code 1 = 0.5-1 mm, code 3 = 2-5 mm
        render_png(field, g, bins, colours, lowest, tmp_path / "f.png")
        codes = set(np.unique(np.asarray(Image.open(tmp_path / "f.png"))).tolist())
        assert codes == want, (lowest, codes)
