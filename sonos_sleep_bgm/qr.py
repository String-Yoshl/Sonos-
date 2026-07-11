"""QR コード生成ユーティリティ。

端末(特に Windows コンソール)はブロック文字を表示できず QR が読めないことが
あるため、QR を SVG として自前で描画し HTML ファイルに書き出す。これにより
端末の種類・フォント・文字コードに依存せず、ブラウザで確実にスキャンできる。
"""

from __future__ import annotations

import html
import sys
from pathlib import Path


def _matrix(url: str, border: int = 2):
    """qrcode で URL の QR 行列(True=黒)を得る。qrcode 未導入なら ImportError。"""
    import qrcode  # 遅延 import（未導入でも他機能は動く）

    qr = qrcode.QRCode(
        border=border,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()  # list[list[bool]]（余白込み）


def build_svg(url: str, scale: int = 8) -> str:
    """QR を SVG 文字列にする。Pillow / lxml 不要（矩形を自前で組み立て）。"""
    matrix = _matrix(url)
    n = len(matrix)
    size = n * scale
    rects = []
    for y in range(n):
        for x in range(n):
            if matrix[y][x]:
                rects.append(
                    f'<rect x="{x * scale}" y="{y * scale}" '
                    f'width="{scale}" height="{scale}"/>'
                )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
        f'<rect width="{size}" height="{size}" fill="#ffffff"/>'
        f'<g fill="#000000">{"".join(rects)}</g></svg>'
    )


def write_html(
    entries: str | list[tuple[str, str]], out_path: str | Path
) -> Path | None:
    """スキャン用の QR ページ(HTML)を書き出す。失敗時は None。

    entries には URL 1 つ、または (ラベル, URL) のリストを渡せる。
    複数渡すと「自宅 Wi-Fi 用」「外出先(Tailscale)用」のように並べて表示する。
    """
    if isinstance(entries, str):
        entries = [("📱 スマホのカメラでスキャン", entries)]
    sections = []
    for label, url in entries:
        try:
            svg = build_svg(url)
        except Exception:
            return None
        safe_url = html.escape(url, quote=True)
        sections.append(
            f"<section><h2>{html.escape(label)}</h2>"
            f'<div class="card">{svg}</div>'
            f'<p><a href="{safe_url}">{safe_url}</a></p></section>'
        )
    page = (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>睡眠BGM セットアップ QR</title><style>"
        "body{font-family:sans-serif;text-align:center;padding:24px;"
        "background:#0e1014;color:#e9edf2}"
        ".card{background:#fff;display:inline-block;padding:16px;border-radius:14px}"
        "section{margin-bottom:36px}"
        "a{color:#6ee7b7;word-break:break-all}</style></head><body>"
        + "".join(sections)
        + "<p>読み取って開いたら、共有 →「ホーム画面に追加」でアプリ完成です。<br>"
        "読めない場合は URL を直接入力しても同じです。</p>"
        "</body></html>"
    )
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path


def print_terminal(url: str) -> bool:
    """端末に ASCII QR を表示する（ベストエフォート）。表示できたら True。"""
    try:
        import qrcode

        try:
            # Windows コンソールでブロック文字を出せるよう UTF-8 に切り替える。
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        return True
    except Exception:
        return False
