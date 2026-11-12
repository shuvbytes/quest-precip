import numpy as np

from palette import LAND, OCEAN, PROB, RAIN, adjacent_delta_e, hex_to_oklab


def de(a, b):
    return float(np.linalg.norm(hex_to_oklab(a) - hex_to_oklab(b)) * 100)


def test_lightness_monotone():
    for r in (RAIN, PROB):
        L = [hex_to_oklab(h)[0] for h in r]
        assert all(a > b for a, b in zip(L, L[1:]))


def test_adjacent_steps_distinct():
    # Rain: two palest pairs accepted down to 5.5 (documented trade-off); all others >= 8.
    d = adjacent_delta_e(RAIN)
    assert min(d[:2]) >= 5.5 and min(d[2:]) >= 8
    assert min(adjacent_delta_e(PROB)) >= 8


def test_palest_steps_visible_on_both_backgrounds():
    for bg in (LAND, OCEAN):
        assert de(RAIN[0], bg) >= 8, (RAIN[0], bg)
        assert de(PROB[0], bg) >= 8, (PROB[0], bg)
