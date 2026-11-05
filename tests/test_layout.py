"""Test di follow_resize: i vicini restano a contatto quando cambia la taglia."""

from monique.layout import follow_resize
from monique.models import MonitorConfig, PositionMode, Transform


def mon(name, x, y, w=1920, h=1080, scale=1.0, **kw):
    return MonitorConfig(
        name=name, x=x, y=y, width=w, height=h, scale=scale,
        position_mode=PositionMode.EXPLICIT, **kw,
    )


def resize(monitors, index, **changes):
    m = monitors[index]
    old = (m.logical_width, m.logical_height)
    for k, v in changes.items():
        setattr(m, k, v)
    follow_resize(monitors, index, *old)


def test_lg_samsung_grow():
    lg = mon("LG", 1080, 0, 3840, 2160, scale=1.25)
    sam = mon("SAM", 4152, 0, 2560, 1440)
    resize([lg, sam], 0, scale=1.0)
    assert (lg.x, sam.x) == (1080, 4920)


def test_lg_samsung_shrink():
    lg = mon("LG", 1080, 0, 3840, 2160, scale=1.0)
    sam = mon("SAM", 4920, 0, 2560, 1440)
    resize([lg, sam], 0, scale=1.25)
    assert sam.x == 4152


def test_chain_of_three():
    a = mon("A", 0, 0)
    b = mon("B", 1920, 0)
    c = mon("C", 3840, 0)
    resize([a, b, c], 0, width=2920)
    assert (a.x, b.x, c.x) == (0, 2920, 4840)


def test_stacked_below():
    a = mon("A", 0, 0)
    b = mon("B", 0, 1080)
    resize([a, b], 0, height=1440)
    assert (b.x, b.y) == (0, 1440)
    assert a.y == 0


def test_rotation_both_axes():
    a = mon("A", 0, 0, 1920, 1080)
    right = mon("R", 1920, 0)
    below = mon("D", 0, 1080)
    resize([a, right, below], 0, transform=Transform.ROTATE_90)
    assert (right.x, right.y) == (1080, 0)
    assert (below.x, below.y) == (0, 1920)


def test_gap_no_move():
    a = mon("A", 0, 0)
    b = mon("B", 2000, 0)
    resize([a, b], 0, width=3000)
    assert b.x == 2000


def test_no_vertical_overlap_no_move():
    a = mon("A", 0, 0)
    b = mon("B", 1920, 1080)
    resize([a, b], 0, width=3000)
    assert b.x == 1920


def test_left_neighbour_no_move():
    left = mon("L", -1920, 0)
    a = mon("A", 0, 0)
    resize([left, a], 1, width=3000)
    assert (left.x, a.x) == (-1920, 0)


def test_disabled_ignored_and_no_chain():
    a = mon("A", 0, 0)
    off = mon("OFF", 1920, 0, enabled=False)
    c = mon("C", 3840, 0)
    resize([a, off, c], 0, width=2920)
    assert (off.x, c.x) == (1920, 3840)


def test_non_explicit_not_moved():
    a = mon("A", 0, 0)
    b = mon("B", 1920, 0)
    b.position_mode = PositionMode.AUTO
    resize([a, b], 0, width=2920)
    assert b.x == 1920


def test_fractional_sizes_round():
    a = mon("A", 0, 0, 1920, 1080, scale=1.5)  # 1280 x 720
    b = mon("B", 1280, 0)
    c = mon("C", 3200, 0)
    resize([a, b, c], 0, scale=1.25)  # 1536 x 864
    assert (b.x, c.x) == (1536, 3456)
    assert all(isinstance(m.x, int) for m in (b, c))


def test_fractional_edge_tolerance():
    a = mon("A", 0, 0, 1920, 1080, scale=1.5)
    b = mon("B", 1281, 0)  # arrotondato di 1 px
    resize([a, b], 0, scale=1.0)
    assert b.x == 1921


def test_same_size_noop():
    a = mon("A", 0, 0)
    b = mon("B", 1920, 0)
    follow_resize([a, b], 0, a.logical_width, a.logical_height)
    assert b.x == 1920
