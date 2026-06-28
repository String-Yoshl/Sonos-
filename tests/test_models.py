import pytest

from sonos_sleep_bgm.models import Schedule, Source


def make_schedule(**kw):
    base = dict(
        name="夜BGM",
        time="21:00",
        source=Source(type="playlist", title="Sleep"),
    )
    base.update(kw)
    return Schedule(**base)


def test_schedule_validates_and_parses_time():
    s = make_schedule(time="06:30")
    s.validate()
    assert (s.hour, s.minute) == (6, 30)


def test_schedule_gets_an_id():
    assert make_schedule().id


def test_name_required():
    with pytest.raises(ValueError, match="name"):
        make_schedule(name="  ").validate()


def test_bad_time_rejected():
    with pytest.raises(ValueError):
        make_schedule(time="99:99").validate()


def test_sleep_timer_disabled_is_none():
    s = make_schedule(sleep_timer_minutes=None)
    s.validate()
    assert s.sleep_timer_minutes is None


def test_sleep_timer_zero_invalid():
    with pytest.raises(ValueError, match="sleep_timer"):
        make_schedule(sleep_timer_minutes=0).validate()


def test_volume_range():
    with pytest.raises(ValueError, match="volume"):
        make_schedule(volume=200).validate()


def test_uri_source_requires_uri():
    with pytest.raises(ValueError, match="uri"):
        make_schedule(source=Source(type="uri")).validate()


def test_favorite_requires_title():
    with pytest.raises(ValueError, match="title"):
        make_schedule(source=Source(type="favorite", title="")).validate()


def test_roundtrip_dict():
    s = make_schedule(sleep_timer_minutes=90, volume=12)
    again = Schedule.from_dict(s.to_dict())
    assert again.to_dict() == s.to_dict()
    assert again.id == s.id
