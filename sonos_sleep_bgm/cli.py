"""コマンドラインインターフェース。

使い方:
    python -m sonos_sleep_bgm.cli run          # 常駐してスケジュール再生
    python -m sonos_sleep_bgm.cli play-now     # その場で 1 回再生 (動作確認用)
    python -m sonos_sleep_bgm.cli list-rooms   # 検出できた部屋を一覧表示
    python -m sonos_sleep_bgm.cli list-favorites  # お気に入りを一覧表示
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config
from .player import PlayerError, find_room, play_sleep_bgm
from .scheduler import run_forever

DEFAULT_CONFIG = "config.yaml"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_config(path: str) -> Config:
    return Config.from_file(path)


def _cmd_run(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    run_forever(config)
    return 0


def _cmd_play_now(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    play_sleep_bgm(config)
    return 0


def _cmd_list_rooms(args: argparse.Namespace) -> int:
    import soco

    zones = soco.discover() or set()
    if not zones:
        print("Sonos デバイスが見つかりませんでした。同じネットワークにいるか確認してください。")
        return 1
    print("検出できた部屋:")
    for zone in sorted(zones, key=lambda z: z.player_name):
        print(f"  - {zone.player_name} ({zone.ip_address})")
    return 0


def _cmd_list_favorites(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    device = find_room(config.room)
    favorites = device.music_library.get_sonos_favorites()
    if not favorites:
        print("お気に入りが登録されていません。")
        return 0
    print(f"'{config.room}' から見えるお気に入り:")
    for fav in favorites:
        print(f"  - {fav.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sonos-sleep-bgm",
        description="主書斎の Sonos から毎日睡眠 BGM を再生する自分用アプリ。",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=DEFAULT_CONFIG,
        help=f"設定ファイルのパス (既定: {DEFAULT_CONFIG})",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細ログを出力する")

    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="常駐してスケジュール通りに再生する")
    p_run.set_defaults(func=_cmd_run)

    p_play = sub.add_parser("play-now", help="今すぐ 1 回再生する (動作確認用)")
    p_play.set_defaults(func=_cmd_play_now)

    p_rooms = sub.add_parser("list-rooms", help="検出できた部屋を一覧表示する")
    p_rooms.set_defaults(func=_cmd_list_rooms)

    p_favs = sub.add_parser("list-favorites", help="お気に入りを一覧表示する")
    p_favs.set_defaults(func=_cmd_list_favorites)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"設定エラー: {exc}", file=sys.stderr)
        return 2
    except PlayerError as exc:
        print(f"再生エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
