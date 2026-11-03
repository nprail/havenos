from havenos.core.timers import TimerBook


def test_pause_freezes_the_countdown_and_resume_continues_it():
    b = TimerBook()
    t = b.add(60, "Tea", 1_000_000)
    assert b.pause(t.id, 1_020_000) and t.paused and t.left == 40
    assert b.start_ringing(2_000_000) is None                  # never expires while paused
    assert b.pause(t.id, 1_500_000) and t.left == 40         # pausing twice changes nothing
    assert b.resume(t.id, 3_000_000) and not t.paused and t.end == 3_040_000
    assert b.resume(t.id, 9_000_000) and t.end == 3_040_000   # resuming a running timer changes nothing
    assert b.start_ringing(3_039_999) is None and b.start_ringing(3_040_000) is t


def test_pause_rounds_up_like_the_display_and_unknown_ids_are_refused():
    b = TimerBook()
    t = b.add(60, "Tea", 0)
    b.pause(t.id, 59_500)
    assert t.left == 1
    assert not b.pause(99, 0) and not b.resume(99, 0)
    assert b.snapshot()[0]["paused"] is True and b.snapshot()[0]["left"] == 1


def test_set_left_updates_a_paused_timers_remaining_time():
    b = TimerBook()
    t = b.add(60, "Tea", 0)
    b.pause(t.id, 10_000)
    b.set_left(t.id, 25, 20_000)
    b.pause(t.id, 20_000)
    assert t.left == 25


def test_extend_adds_time_and_grows_the_total():
    b = TimerBook()
    t = b.add(60, "Tea", 0)
    assert b.extend(t.id, 60, 10_000) and t.end == 120_000 and t.total == 120
    b.pause(t.id, 30_000)
    assert t.left == 90
    assert b.extend(t.id, 30, 30_000) and t.left == 120 and t.total == 150
    assert not b.extend(99, 60, 0)


def test_an_expired_timer_rings_in_place_and_snoozing_restarts_the_same_timer():
    b = TimerBook()
    t = b.add(5, "Tea", 0)
    t.local = False
    assert b.start_ringing(4_999) is None
    assert b.start_ringing(5_000) is t and t.ringing and b.get(t.id) is t     # stays in the book
    assert b.start_ringing(9_000) is None                                    # a ringing timer does not ring again
    assert b.snooze(t.id, 60, 10_000) and not t.ringing and t.local and t.total == 60 and t.end == 70_000
    assert not b.snooze(99, 60, 0)
