"""SoCo ラッパー: 部屋検出・プレイリスト/お気に入り一覧・検索・再生・スリープタイマー。"""

from __future__ import annotations

import logging
import threading
import time

import soco
from soco import SoCo
from soco.exceptions import SoCoException

from .models import (
    SOURCE_FAVORITE,
    SOURCE_PLAYLIST,
    SOURCE_URI,
    Schedule,
    Source,
)

logger = logging.getLogger(__name__)


class SonosError(RuntimeError):
    """Sonos 操作の失敗を表す例外。"""


def list_rooms() -> list[dict]:
    """ネットワーク上で検出できた部屋（ゾーン）の一覧。"""
    zones = soco.discover() or set()
    return sorted(
        ({"name": z.player_name, "ip": z.ip_address} for z in zones),
        key=lambda d: d["name"],
    )


def find_room(room: str) -> SoCo:
    """部屋名から Sonos デバイスを取得する。見つからなければ SonosError。"""
    if not room:
        raise SonosError("部屋（room）が設定されていません。設定画面で選んでください。")
    device = soco.discovery.by_name(room)
    if device is None:
        available = [r["name"] for r in list_rooms()]
        raise SonosError(
            f"部屋 '{room}' が見つかりません。検出できた部屋: "
            f"{available or '（なし。同一ネットワークか確認してください）'}"
        )
    return device


def _list_playlists(device: SoCo) -> list[dict]:
    items = []
    for pl in device.get_sonos_playlists(complete_result=True):
        items.append(
            {
                "type": SOURCE_PLAYLIST,
                "title": pl.title,
                "uri": getattr(pl, "resources", None) and pl.resources[0].uri or None,
                "subtitle": "プレイリスト",
            }
        )
    return items


def _list_favorites(device: SoCo) -> list[dict]:
    items = []
    for fav in device.music_library.get_sonos_favorites(complete_result=True):
        items.append(
            {
                "type": SOURCE_FAVORITE,
                "title": fav.title,
                "uri": None,
                "subtitle": "お気に入り",
            }
        )
    return items


def list_sources(room: str, query: str = "") -> list[dict]:
    """プレイリストとお気に入りをまとめて返す。query で部分一致フィルタ（検索）。

    Sonos アプリのように音源を一覧・検索するための関数。
    """
    device = find_room(room)
    try:
        sources = _list_playlists(device) + _list_favorites(device)
    except SoCoException as exc:
        raise SonosError(f"音源一覧の取得に失敗しました: {exc}") from exc

    q = query.strip().lower()
    if q:
        sources = [s for s in sources if q in s["title"].lower()]
    sources.sort(key=lambda s: (s["subtitle"], s["title"].lower()))
    return sources


def _resolve_playable(device: SoCo, source: Source):
    """Source を再生可能な DidlObject に解決する（タイトルで再照合）。

    再起動後も確実に再生できるよう、保存したタイトルから実機の最新一覧を引き直す。
    """
    if source.type == SOURCE_PLAYLIST:
        for pl in device.get_sonos_playlists(complete_result=True):
            if pl.title == source.title:
                return pl
        raise SonosError(f"プレイリスト '{source.title}' が見つかりません。")
    if source.type == SOURCE_FAVORITE:
        for fav in device.music_library.get_sonos_favorites(complete_result=True):
            if fav.title == source.title:
                return fav.reference
        raise SonosError(f"お気に入り '{source.title}' が見つかりません。")
    raise SonosError(f"解決できない音源タイプです: {source.type}")


def _apply_volume(device: SoCo, target: int, fade_in_seconds: int) -> None:
    if fade_in_seconds <= 0:
        device.volume = target
        return
    steps = min(target, fade_in_seconds) or 1
    interval = fade_in_seconds / steps
    device.volume = 0
    for step in range(1, steps + 1):
        device.volume = round(target * step / steps)
        time.sleep(interval)


def play_schedule(room: str, schedule: Schedule) -> None:
    """指定スケジュールの BGM を再生し、スリープタイマーを設定する。"""
    try:
        device = find_room(room)
        logger.info(
            "再生: '%s' を %s で（音源: %s）",
            schedule.name,
            device.player_name,
            schedule.source.display_name,
        )

        try:
            device.unjoin()
        except SoCoException:
            logger.debug("unjoin に失敗（続行）", exc_info=True)

        if schedule.source.type == SOURCE_URI:
            device.play_uri(schedule.source.uri)
        else:
            playable = _resolve_playable(device, schedule.source)
            device.clear_queue()
            device.add_to_queue(playable)
            device.play_from_queue(0)

        if schedule.volume is not None:
            if schedule.fade_in_seconds > 0:
                # フェードは最大数十秒かかるため、呼び出し元(HTTP リクエストや
                # スケジューラのジョブスレッド)をブロックしないよう別スレッドで行う。
                device.volume = 0
                threading.Thread(
                    target=_apply_volume,
                    args=(device, schedule.volume, schedule.fade_in_seconds),
                    daemon=True,
                    name=f"fade-{schedule.id}",
                ).start()
            else:
                device.volume = schedule.volume

        # スリープタイマー（Sonos ネイティブ機能）。None で無効。
        if schedule.sleep_timer_minutes:
            device.set_sleep_timer(schedule.sleep_timer_minutes * 60)
            logger.info("スリープタイマー %d 分を設定。", schedule.sleep_timer_minutes)
        else:
            device.set_sleep_timer(None)

        logger.info("再生を開始しました。")
    except SonosError:
        raise
    except SoCoException as exc:
        raise SonosError(f"Sonos の操作に失敗しました: {exc}") from exc
