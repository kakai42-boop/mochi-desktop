from mochi.behavior import ClickPair


def test_pairs_completed_clicks_even_when_the_backend_reports_one():
    clicks = ClickPair()
    limits = dict(count=1, interval=0.5, distance=5)
    assert not clicks.release(20, 20, 10.0, **limits)
    assert clicks.release(23, 20, 10.1, **limits)
    assert not clicks.release(23, 20, 10.2, **limits)


def test_clicks_outside_time_or_distance_and_drag_release_do_not_pair():
    clicks = ClickPair()
    limits = dict(count=1, interval=0.5, distance=5)
    assert not clicks.release(20, 20, 10.0, **limits)
    assert not clicks.release(40, 20, 10.1, **limits)
    assert not clicks.release(40, 20, 11.0, **limits)
    clicks.clear()
    assert not clicks.release(40, 20, 11.1, **limits)
