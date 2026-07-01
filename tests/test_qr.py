from pathlib import Path

from sonos_sleep_bgm import qr as qrgen

URL = "http://192.168.1.21:8765/?token=abc123"


def test_build_svg_is_wellformed():
    svg = qrgen.build_svg(URL)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "<rect" in svg  # 黒モジュールが存在する


def test_write_html_creates_scannable_page(tmp_path):
    out = qrgen.write_html(URL, tmp_path / "data" / "qr.html")
    assert out is not None and out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<svg" in text
    assert URL in text  # 読めない時のフォールバック URL も載る
    assert "ホーム画面に追加" in text


def test_write_html_escapes_url(tmp_path):
    tricky = 'http://x/?a="/><script>alert(1)</script>'
    out = qrgen.write_html(tricky, tmp_path / "qr.html")
    text = out.read_text(encoding="utf-8")
    # 生の <script> がそのまま埋め込まれていない（エスケープ済み）。
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_matrix_has_expected_structure():
    m = qrgen._matrix(URL)
    assert len(m) == len(m[0])  # 正方
    assert len(m) >= 21  # QR の最小サイズ以上
