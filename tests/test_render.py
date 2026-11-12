import numpy as np

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


def test_hatch_only_inside_flagged_cells():
    from render import hatch_codes
    g = Grid.from_coords(LAT, LON)
    wet = np.zeros((g.nlat, g.nlon), bool); dry = np.zeros_like(wet)
    wet[40, 50] = True; dry[100, 20] = True
    codes = hatch_codes(wet, dry, g)
    rows, cols = g.resample_index()
    in_wet = (rows[:, None] == 40) & (cols[None, :] == 50)
    in_dry = (rows[:, None] == 100) & (cols[None, :] == 20)
    assert codes[~(in_wet | in_dry)].max() == 0          # nothing drawn outside flagged cells
    assert (codes[in_wet] == 1).any() and (codes[in_dry] == 1).any()


def test_classify_bins_floor_and_over():
    bins = [0.5, 1, 2, 5]
    v = np.array([np.nan, 0.0, 0.49, 0.5, 0.99, 1.0, 4.9, 5.0, 999])
    # 3 bins + over colour = 4 colours
    np.testing.assert_array_equal(classify(v, bins, 0.5, 4), [0, 0, 0, 1, 1, 2, 3, 4, 4])
    # raised floor: lowest drawn edge 1.0 hides the 0.5-1 bin
    np.testing.assert_array_equal(classify(v, bins, 1.0, 4), [0, 0, 0, 0, 0, 2, 3, 4, 4])
    # probabilities: 3 colours for 3 bins, exactly-top value takes the top colour
    np.testing.assert_array_equal(classify(np.array([1, 2, 99, 100]), [2, 10, 50, 100], 2, 3), [0, 1, 3, 3])
