"""アクセストークンによる簡易認証。

初回起動時にランダムなトークンを生成してデータディレクトリに保存し、
以後の API 呼び出しに `X-Auth-Token` ヘッダ(または Bearer)を要求する。
"""

from __future__ import annotations

import secrets
from pathlib import Path

TOKEN_FILENAME = "auth_token"


def load_or_create_token(data_path: str | Path) -> str:
    """データファイルと同じディレクトリのトークンを読み込む。無ければ生成する。"""
    token_path = Path(data_path).parent / TOKEN_FILENAME
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_hex(16)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token + "\n", encoding="utf-8")
    try:
        # 所有者のみ読み書き可能にする。
        token_path.chmod(0o600)
    except OSError:
        pass
    return token
