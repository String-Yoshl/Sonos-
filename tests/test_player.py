from unittest import mock

import pytest

from sonos_sleep_bgm import player
from sonos_sleep_bgm.config import Config


class FakeFavorite:
    def __init__(self, title):
        self.title = title
        self.reference = f"ref:{title}"


def make_device(favorites=()):
    device = mock.MagicMock()
    device.player_name = "主書斎"
    device.ip_address = "192.168.1.10"
    device.music_library.get_sonos_favorites.return_value = list(favorites)
    return device


def test_apply_volume_without_fade():
    device = make_device()
    player._apply_volume(device, 25, 0)
    assert device.volume == 25


def test_apply_volume_with_fade(monkeypatch):
    device = make_device()
    monkeypatch.setattr(player.time, "sleep", lambda *_: None)
    player._apply_volume(device, 20, 4)
    # フェード終了後は目標音量に到達している。
    assert device.volume == 20


def test_play_uri_path(monkeypatch):
    device = make_device()
    monkeypatch.setattr(player, "find_room", lambda room: device)
    cfg = Config(room="主書斎", bgm_uri="http://x/sleep.mp3", volume=None)

    player.play_sleep_bgm(cfg)

    device.play_uri.assert_called_once_with("http://x/sleep.mp3")


def test_play_favorite_path(monkeypatch):
    fav = FakeFavorite("Sleep BGM")
    device = make_device(favorites=[fav])
    monkeypatch.setattr(player, "find_room", lambda room: device)
    cfg = Config(room="主書斎", bgm_favorite="Sleep BGM", volume=10, fade_in_seconds=0)

    player.play_sleep_bgm(cfg)

    device.add_to_queue.assert_called_once_with("ref:Sleep BGM")
    device.play_from_queue.assert_called_once_with(0)
    assert device.volume == 10


def test_missing_favorite_raises(monkeypatch):
    device = make_device(favorites=[FakeFavorite("Other")])
    monkeypatch.setattr(player, "find_room", lambda room: device)
    cfg = Config(room="主書斎", bgm_favorite="Nope")

    with pytest.raises(player.PlayerError, match="お気に入り 'Nope'"):
        player.play_sleep_bgm(cfg)


def test_find_room_not_found(monkeypatch):
    monkeypatch.setattr(player.soco.discovery, "by_name", lambda name: None)
    monkeypatch.setattr(player.soco, "discover", lambda: set())
    with pytest.raises(player.PlayerError, match="見つかりません"):
        player.find_room("存在しない部屋")
