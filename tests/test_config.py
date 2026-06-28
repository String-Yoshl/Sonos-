import textwrap

import pytest

from sonos_sleep_bgm.config import Config


def test_valid_config_parses_time():
    cfg = Config(room="主書斎", schedule_time="21:30", bgm_favorite="Sleep")
    assert cfg.hour == 21
    assert cfg.minute == 30


def test_room_required():
    with pytest.raises(ValueError, match="room"):
        Config(room="", bgm_favorite="Sleep")


def test_requires_a_source():
    with pytest.raises(ValueError, match="bgm_favorite"):
        Config(room="主書斎")


def test_invalid_time_rejected():
    with pytest.raises(ValueError, match="schedule_time"):
        Config(room="主書斎", schedule_time="25:00", bgm_favorite="Sleep")


def test_volume_range_validated():
    with pytest.raises(ValueError, match="volume"):
        Config(room="主書斎", bgm_favorite="Sleep", volume=150)


def test_negative_fade_rejected():
    with pytest.raises(ValueError, match="fade_in_seconds"):
        Config(room="主書斎", bgm_favorite="Sleep", fade_in_seconds=-1)


def test_from_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        textwrap.dedent(
            """
            room: "主書斎"
            schedule_time: "09:00"
            bgm_uri: "http://example.com/sleep.mp3"
            volume: 20
            """
        ),
        encoding="utf-8",
    )
    cfg = Config.from_file(path)
    assert cfg.room == "主書斎"
    assert cfg.hour == 9
    assert cfg.bgm_uri == "http://example.com/sleep.mp3"
    assert cfg.volume == 20


def test_from_file_rejects_unknown_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        'room: "主書斎"\nbgm_favorite: "Sleep"\nbogus: 1\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="未知の設定キー"):
        Config.from_file(path)


def test_from_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        Config.from_file(tmp_path / "nope.yaml")
