"""監査(2026-07-01)で見つかった不具合 B1〜B3 の回帰テスト。"""

import threading
from unittest import mock

import pytest

from sonos_sleep_bgm import sonos_client, webapp
from sonos_sleep_bgm.models import AppSettings, Schedule, Source
from sonos_sleep_bgm.store import Store


def make_schedule(**kw):
    base = dict(name="x", time="21:00", source=Source(type="playlist", title="Sleep"))
    base.update(kw)
    return Schedule(**base)


# ---- B1: 不正な timezone が保存されると次回起動不能 ---------------------
def test_invalid_timezone_rejected_and_not_persisted(tmp_path):
    path = tmp_path / "data.json"
    store = Store(path)
    store.update_settings(timezone="Asia/Tokyo")

    with pytest.raises(ValueError, match="timezone"):
        store.update_settings(timezone="Mars/Olympus")

    # メモリ上もファイル上も汚染されていないこと。
    assert store.get_settings().timezone == "Asia/Tokyo"
    assert Store(path).get_settings().timezone == "Asia/Tokyo"


def test_put_settings_invalid_timezone_returns_400(tmp_path):
    store = Store(tmp_path / "data.json")
    c = webapp.create_app(store, runner=None).test_client()
    res = c.put("/api/settings", json={"timezone": "Not/AZone"})
    assert res.status_code == 400
    assert "timezone" in res.get_json()["error"]


def test_appsettings_validate_accepts_iana_names():
    AppSettings(timezone="Asia/Tokyo").validate()
    AppSettings(timezone="UTC").validate()


# ---- B2: フェードインが呼び出し元をブロックする -------------------------
def test_play_with_fade_does_not_block(monkeypatch):
    device = mock.MagicMock()
    device.player_name = "主書斎"
    monkeypatch.setattr(sonos_client, "find_room", lambda room: device)
    started = threading.Event()

    def fake_apply(dev, target, fade):
        started.set()

    monkeypatch.setattr(sonos_client, "_apply_volume", fake_apply)
    schedule = make_schedule(
        source=Source(type="uri", uri="http://x/a.mp3"),
        volume=20,
        fade_in_seconds=30,
    )

    sonos_client.play_schedule("主書斎", schedule)  # 30 秒待たされないこと(即返る)

    assert started.wait(2), "フェードが別スレッドで開始されていない"
    assert device.volume == 0  # フェード開始時は無音から


def test_play_without_fade_sets_volume_directly(monkeypatch):
    device = mock.MagicMock()
    monkeypatch.setattr(sonos_client, "find_room", lambda room: device)
    schedule = make_schedule(
        source=Source(type="uri", uri="http://x/a.mp3"), volume=25, fade_in_seconds=0
    )
    sonos_client.play_schedule("主書斎", schedule)
    assert device.volume == 25


# ---- B3: 数値フィールドの型未検証 ---------------------------------------
def test_volume_string_coerced():
    s = make_schedule(volume="18")
    s.validate()
    assert s.volume == 18


@pytest.mark.parametrize("bad", ["abc", True, False, 1.5, [], {}])
def test_volume_bad_types_rejected(bad):
    with pytest.raises(ValueError, match="volume"):
        make_schedule(volume=bad).validate()


def test_sleep_timer_bool_rejected():
    # JSON の true は int のサブクラスで範囲チェックをすり抜けるため明示拒否。
    with pytest.raises(ValueError, match="sleep_timer_minutes"):
        make_schedule(sleep_timer_minutes=True).validate()


def test_fade_none_rejected():
    with pytest.raises(ValueError, match="fade_in_seconds"):
        make_schedule(fade_in_seconds=None).validate()


def test_put_settings_empty_room_does_not_overwrite(tmp_path):
    """部屋検出失敗時などに空文字が送られても、設定済みの部屋を消さない。"""
    store = Store(tmp_path / "data.json")
    store.update_settings(room="主書斎")
    c = webapp.create_app(store, runner=None).test_client()

    res = c.put("/api/settings", json={"room": ""})
    assert res.status_code == 200
    assert store.get_settings().room == "主書斎"  # 上書きされていない


def test_api_bad_volume_returns_400_not_500(tmp_path):
    store = Store(tmp_path / "data.json")
    c = webapp.create_app(store, runner=None).test_client()
    res = c.post(
        "/api/schedules",
        json={
            "name": "x",
            "time": "21:00",
            "source": {"type": "playlist", "title": "Sleep"},
            "volume": "loud",
        },
    )
    assert res.status_code == 400
    assert "volume" in res.get_json()["error"]
