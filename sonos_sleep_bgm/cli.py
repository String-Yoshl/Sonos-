"""コマンドラインインターフェース。

使い方:
    python -m sonos_sleep_bgm.cli serve         # Web UI + スケジューラを起動
    python -m sonos_sleep_bgm.cli list-rooms    # 検出できた部屋を表示
    python -m sonos_sleep_bgm.cli play-now <schedule-id>  # 指定セットを即再生
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import qr as qrgen
from . import sonos_client
from .auth import load_or_create_token
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


def _tailscale_ip() -> str | None:
    """Tailscale がインストール済みならその IPv4 (100.64.0.0/10) を返す。

    Tailscale を使うと、外出先(モバイル回線)からも自宅のこのサーバへ
    安全に(WireGuard 暗号化で)届くため、同じアプリが外でも使える。
    """
    candidates = (
        ["tailscale", "ip", "-4"],
        [r"C:\Program Files\Tailscale\tailscale.exe", "ip", "-4"],  # Windows 既定
    )
    for cmd in candidates:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
        if out.returncode != 0:
            continue
        for line in out.stdout.split():
            try:
                ip = ipaddress.ip_address(line.strip())
            except ValueError:
                continue
            if ip in ipaddress.ip_network("100.64.0.0/10"):
                return str(ip)
    return None


def _show_qr(entries: list[tuple[str, str]], data_path: str) -> None:
    """スマホ用 QR を提示する。

    端末依存を避けるため、まず QR 画像(HTML)をファイルに書き出して
    既定ブラウザで自動オープンする。あわせて端末にも ASCII QR を試みる。
    """
    # 1) 端末非依存の確実な方法: HTML ファイルに書き出してブラウザで開く。
    qr_path = qrgen.write_html(entries, Path(data_path).parent / "qr.html")
    if qr_path is not None:
        print(f"  ■ スマホ用 QR 画像を開きます: {qr_path}")
        print("    (自動で開かない場合は上記ファイルをブラウザで開いてください)")
        try:
            webbrowser.open(qr_path.resolve().as_uri())
        except Exception:
            pass
    else:
        print("  (QR 生成には `pip install qrcode` が必要です)")

    # 2) おまけ: 端末にも QR を出す(出せない環境では黙ってスキップ)。
    print("  ▼ 端末にも QR を表示します(文字化けする場合は上の画像を使用)")
    print()
    qrgen.print_terminal(entries[0][1])


def _cmd_serve(args: argparse.Namespace) -> int:
    store = Store(args.data)
    # LAN 内の第三者による操作を防ぐため、API はトークン認証必須にする。
    token = args.token or load_or_create_token(args.data)
    runner = ScheduleRunner(store)
    runner.start()
    app = create_app(store, runner, auth_token=token)
    if args.host == "0.0.0.0":
        lan_url = f"http://{_lan_ip()}:{args.port}/?token={token}"
        ts_ip = _tailscale_ip()
        print("=" * 60)
        print("  Sonos 睡眠 BGM を起動しました (Ctrl+C で終了)")
        print(f"  このPC:      http://127.0.0.1:{args.port}/?token={token}")
        print(f"  自宅Wi-Fi:   {lan_url}")
        entries = [("自宅 Wi-Fi 用", lan_url)]
        if ts_ip:
            ts_url = f"http://{ts_ip}:{args.port}/?token={token}"
            print(f"  外出先(Tailscale): {ts_url}")
            print("    → スマホにも Tailscale を入れておけば、外からも同じアプリが使えます")
            # Tailscale IP は自宅でも外でも同じ経路で届くため、こちらを常用推奨。
            entries.insert(0, ("📶 外出先でも使える (Tailscale・推奨)", ts_url))
        else:
            print("  (外出先からも使いたい場合は Tailscale を導入 → QUICKSTART.md 参照)")
        print("    → スマホで開いたら「ホーム画面に追加」でアプリ完成")
        print("=" * 60)
        if not args.no_qr:
            _show_qr(entries, args.data)
        print(f"  アクセストークン: {token}")
        print("    (data/auth_token に保存。URL で一度開けば端末に記憶されます)")
        print("=" * 60)
    else:
        print(f"Web UI: http://{args.host}:{args.port}/?token={token}  (Ctrl+C で終了)")
    try:
        # reloader はスケジューラと二重起動になるため無効。
        # threaded=True でないと 1 リクエストが全体をブロックする
        # (werkzeug の既定はシングルスレッド)。
        app.run(host=args.host, port=args.port, use_reloader=False, threaded=True)
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
    # スマホからアプリとして使えるよう、既定で LAN に公開する(API はトークン認証)。
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument(
        "--token",
        default=None,
        help="アクセストークンを明示指定する(省略時は data/auth_token を自動生成・再利用)",
    )
    p_serve.add_argument(
        "--no-qr", action="store_true", help="起動時の QR コード表示を無効にする"
    )
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
