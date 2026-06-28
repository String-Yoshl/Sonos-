"""設定ファイル(YAML)の読み込みとバリデーション。"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import yaml


@dataclasses.dataclass
class Config:
    """アプリの動作設定。

    Attributes:
        room: 再生元にする Sonos の部屋(ゾーン)名。例: "主書斎"
        schedule_time: 毎日再生を開始する時刻 (HH:MM, 24時間表記)。
        bgm_favorite: 再生する Sonos お気に入りの名前。bgm_uri より優先される。
        bgm_uri: 直接再生する音源 URI (例: ストリーミング URL やローカル HTTP 配信)。
        volume: 再生時の音量 (0-100)。None の場合は変更しない。
        fade_in_seconds: 0 より大きい場合、目標音量までフェードインする秒数。
        timezone: スケジューラが使うタイムゾーン名 (例: "Asia/Tokyo")。
    """

    room: str
    schedule_time: str = "21:00"
    bgm_favorite: str | None = None
    bgm_uri: str | None = None
    volume: int | None = 18
    fade_in_seconds: int = 0
    timezone: str = "Asia/Tokyo"

    def __post_init__(self) -> None:
        if not self.room or not str(self.room).strip():
            raise ValueError("room(部屋名)は必須です。例: 主書斎")

        if not self.bgm_favorite and not self.bgm_uri:
            raise ValueError(
                "bgm_favorite か bgm_uri のどちらかを指定してください。"
            )

        # HH:MM のパースを試みて妥当性を検証する。
        try:
            self.hour, self.minute = self._parse_time(self.schedule_time)
        except ValueError as exc:
            raise ValueError(
                f"schedule_time は HH:MM 形式で指定してください: {self.schedule_time!r}"
            ) from exc

        if self.volume is not None and not (0 <= self.volume <= 100):
            raise ValueError("volume は 0〜100 の範囲で指定してください。")

        if self.fade_in_seconds < 0:
            raise ValueError("fade_in_seconds は 0 以上で指定してください。")

    @staticmethod
    def _parse_time(value: str) -> tuple[int, int]:
        """"HH:MM" を (hour, minute) に変換する。"""
        parsed = dt.datetime.strptime(value.strip(), "%H:%M")
        return parsed.hour, parsed.minute

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        """YAML 設定ファイルから Config を生成する。"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {path}")

        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        if not isinstance(data, dict):
            raise ValueError("設定ファイルのトップレベルはマッピングである必要があります。")

        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"未知の設定キーがあります: {sorted(unknown)}")

        return cls(**data)
