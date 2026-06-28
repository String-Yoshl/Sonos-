"""コマンドラインインターフェース。

使い方:
    python -m sonos_sleep_bgm.cli serve         # Web UI + スケジューラを起動
    python -m sonos_sleep_bgm.cli list-rooms    # 検出できた部屋を表示
    python -m sonos_sleep_bgm.cli play-now <schedule-id>  # 指定セットを即再生
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys

from . import sonos_client
from .scheduler import ScheduleRunner
from .store import DEFAULT_DATA_PATH, Store
from .webapp import create_app


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _lan_ip() -> str:
    """このホストの LAN IP を推定する（スマホからのアクセス URL 表示用）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # 実際には送信しない。ルーティング先IPを得るだけ。
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _cmd_serve(args: argparse.Namespace) -> int:
    store = Store(args.data)
    runner = ScheduleRunner(store)
    runner.start()
    app = create_app(store, runner)
    if args.host == "0.0.0.0":
        print("=" * 52)
        print("  Sonos 睡眠 BGM を起動しました (Ctrl+C で終了)")
        print(f"  このPC:   http://127.0.0.1:{args.port}")
        print(f"  スマホ:   http://{_lan_ip()}:{args.port}")
        print("    → スマホのブラウザで上記を開き、")
        print("      『ホーム画面に追加』でアプリとして使えます。")
        print("=" * 52)
    else:
        print(f"Web UI: http://{args.host}:{args.port}  (Ctrl+C で終了)")
    try:
        # スケジューラは別スレッドなので reloader は無効にする。
        app.run(host=args.host, port=args.port, use_reloader=False)
    finally:
        runner.shutdown()
    return 0


def _cmd_list_rooms(args: argparse.Namespace) -> int:
    rooms = sonos_client.list_rooms()
    if not rooms:
        print("Sonos が見つかりませんでした。同一ネットワークか確認してください。")
        return 1
    print("検出できた部屋:")
    for r in rooms:
        print(f"  - {r['name']} ({r['ip']})")
    return 0


def _cmd_play_now(args: argparse.Namespace) -> int:
    store = Store(args.data)
    schedule = store.get_schedule(args.schedule_id)
    if schedule is None:
        print(f"スケジュール '{args.schedule_id}' が見つかりません。", file=sys.stderr)
        return 2
    sonos_client.play_schedule(store.get_settings().room, schedule)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sonos-sleep-bgm",
        description="主書斎の Sonos で時刻×BGM のセットを管理・自動再生する自分用アプリ。",
    )
    parser.add_argument(
        "-d", "--data", default=str(DEFAULT_DATA_PATH), help="データファイルのパス"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細ログ")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Web UI + スケジューラを起動する")
    # スマホからアプリとして使えるよう、既定で LAN に公開する。
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.set_defaults(func=_cmd_serve)

    p_rooms = sub.add_parser("list-rooms", help="検出できた部屋を表示する")
    p_rooms.set_defaults(func=_cmd_list_rooms)

    p_play = sub.add_parser("play-now", help="指定セットを今すぐ再生する")
    p_play.add_argument("schedule_id")
    p_play.set_defaults(func=_cmd_play_now)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args)
    except sonos_client.SonosError as exc:
        print(f"Sonos エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
