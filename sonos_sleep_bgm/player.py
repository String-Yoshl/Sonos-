"""SoCo を使って Sonos スピーカーで睡眠 BGM を再生するロジック。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import soco
from soco import SoCo
from soco.exceptions import SoCoException

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


class PlayerError(RuntimeError):
    """再生に失敗したときに送出される例外。"""


def find_room(room: str) -> SoCo:
    """部屋名(ゾーン名)から Sonos デバイスを探して返す。

    Args:
        room: Sonos アプリ上の部屋名。例: "主書斎"

    Raises:
        PlayerError: 該当する部屋が見つからない場合。
    """
    device = soco.discovery.by_name(room)
    if device is not None:
        return device

    # 見つからなかった場合は、検出できた部屋名を添えてエラーにする。
    zones = soco.discover() or set()
    available = sorted(z.player_name for z in zones)
    raise PlayerError(
        f"部屋 '{room}' が見つかりませんでした。"
        f" 検出できた部屋: {available or '（なし。ネットワークを確認してください）'}"
    )


def _resolve_favorite_uri(device: SoCo, favorite_name: str):
    """お気に入り名から再生用のメタ情報を解決する。

    Returns:
        soco の DidlObject (favorite.reference 相当)。

    Raises:
        PlayerError: 一致するお気に入りが無い場合。
    """
    favorites = device.music_library.get_sonos_favorites()
    titles = []
    for fav in favorites:
        titles.append(fav.title)
        if fav.title == favorite_name:
            return fav.reference
    raise PlayerError(
        f"お気に入り '{favorite_name}' が見つかりませんでした。"
        f" 登録済みお気に入り: {titles or '（なし）'}"
    )


def _apply_volume(device: SoCo, target: int, fade_in_seconds: int) -> None:
    """音量を設定する。fade_in_seconds>0 なら段階的にフェードインする。"""
    if fade_in_seconds <= 0:
        device.volume = target
        return

    steps = min(target, fade_in_seconds) or 1
    interval = fade_in_seconds / steps
    device.volume = 0
    for step in range(1, steps + 1):
        device.volume = round(target * step / steps)
        time.sleep(interval)


def play_sleep_bgm(config: "Config") -> None:
    """設定にもとづいて主書斎の Sonos で睡眠 BGM を再生する。

    Raises:
        PlayerError: 再生に失敗した場合。
    """
    try:
        device = find_room(config.room)
        logger.info("Sonos デバイスに接続: %s (%s)", device.player_name, device.ip_address)

        # 既に他のグループに属していても、この部屋単体で鳴らせるようにする。
        try:
            device.unjoin()
        except SoCoException:
            # 単体再生で問題ない場合が多いので、unjoin の失敗は致命的ではない。
            logger.debug("unjoin に失敗しましたが処理を続行します。", exc_info=True)

        if config.bgm_favorite:
            logger.info("お気に入り '%s' を再生します。", config.bgm_favorite)
            reference = _resolve_favorite_uri(device, config.bgm_favorite)
            device.clear_queue()
            device.add_to_queue(reference)
            device.play_from_queue(0)
        else:
            logger.info("URI を再生します: %s", config.bgm_uri)
            device.play_uri(config.bgm_uri)

        if config.volume is not None:
            logger.info(
                "音量を %d に設定します (フェードイン %ds)。",
                config.volume,
                config.fade_in_seconds,
            )
            _apply_volume(device, config.volume, config.fade_in_seconds)

        logger.info("睡眠 BGM の再生を開始しました。")
    except PlayerError:
        raise
    except SoCoException as exc:
        raise PlayerError(f"Sonos の操作に失敗しました: {exc}") from exc
