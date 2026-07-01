#!/usr/bin/env bash
#
# Sonos 睡眠 BGM ワンコマンドインストーラ (macOS / Linux / Raspberry Pi)
#
#   ./install.sh          … 仮想環境を作り依存をインストールしてサーバを起動
#   ./install.sh setup    … セットアップのみ(起動しない)
#
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
VENV=".venv"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "エラー: python3 が見つかりません。先に Python 3.10 以上を入れてください。" >&2
  exit 1
fi

echo "==> 仮想環境を作成 ($VENV)"
"$PY" -m venv "$VENV"

echo "==> 依存パッケージをインストール"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r requirements.txt

echo "==> 完了しました。"

if [ "${1:-run}" = "setup" ]; then
  echo "起動するには:  $VENV/bin/python -m sonos_sleep_bgm.cli serve"
  exit 0
fi

echo "==> サーバを起動します (Ctrl+C で終了)"
echo
exec "$VENV/bin/python" -m sonos_sleep_bgm.cli serve
