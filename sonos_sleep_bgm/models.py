"""アプリのデータモデル（設定・スケジュール・音源）。"""

from __future__ import annotations

import dataclasses
import datetime as dt
import urllib.parse
import uuid

# 音源の種類。
SOURCE_PLAYLIST = "playlist"   # Sonos プレイリスト
SOURCE_FAVORITE = "favorite"   # Sonos お気に入り
SOURCE_URI = "uri"             # 直接 URI
VALID_SOURCE_TYPES = {SOURCE_PLAYLIST, SOURCE_FAVORITE, SOURCE_URI}

# 音源 URI として意味がなく、注入の温床になり得るスキームは拒否する。
# (Sonos 独自の x-rincon-* / x-sonosapi-* 等は許可したいため拒否リスト方式)
BLOCKED_URI_SCHEMES = {"javascript", "data", "file", "vbscript", "about", "blob"}


def parse_hhmm(value: str) -> tuple[int, int]:
    """"HH:MM" を (hour, minute) に変換する。不正なら ValueError。"""
    parsed = dt.datetime.strptime(str(value).strip(), "%H:%M")
    return parsed.hour, parsed.minute


@dataclasses.dataclass
class Source:
    """再生する音源。type に応じて title か uri を使う。"""

    type: str
    title: str = ""
    uri: str | None = None

    def validate(self) -> None:
        if self.type not in VALID_SOURCE_TYPES:
            raise ValueError(f"未知の音源タイプです: {self.type!r}")
        if self.type == SOURCE_URI:
            if not self.uri:
                raise ValueError("uri タイプには uri が必要です。")
            scheme = urllib.parse.urlsplit(self.uri).scheme.lower()
            if not scheme or scheme in BLOCKED_URI_SCHEMES:
                raise ValueError(
                    f"uri のスキームが不正です: {self.uri!r}"
                    "（http/https や Sonos 用スキームを指定してください）"
                )
        else:
            if not self.title:
                raise ValueError(f"{self.type} タイプには title が必要です。")

    @property
    def display_name(self) -> str:
        return self.title or self.uri or "(不明な音源)"

    def to_dict(self) -> dict:
        return {"type": self.type, "title": self.title, "uri": self.uri}

    @classmethod
    def from_dict(cls, data: dict) -> "Source":
        return cls(
            type=data["type"],
            title=data.get("title", ""),
            uri=data.get("uri"),
        )


@dataclasses.dataclass
class Schedule:
    """「時刻 + BGM」を紐づけた 1 つのセット。複数ストックできる。"""

    name: str
    time: str  # "HH:MM"
    source: Source
    id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex[:12])
    enabled: bool = True
    volume: int | None = 18
    fade_in_seconds: int = 0
    # スリープタイマー（分）。None は無効。既定は 60 分。
    sleep_timer_minutes: int | None = 60

    def validate(self) -> None:
        if not str(self.name).strip():
            raise ValueError("name（セット名）は必須です。")
        # 時刻の妥当性チェック。
        parse_hhmm(self.time)
        self.source.validate()
        if self.volume is not None and not (0 <= self.volume <= 100):
            raise ValueError("volume は 0〜100 で指定してください。")
        if self.fade_in_seconds < 0:
            raise ValueError("fade_in_seconds は 0 以上で指定してください。")
        if self.sleep_timer_minutes is not None and self.sleep_timer_minutes <= 0:
            raise ValueError(
                "sleep_timer_minutes は 1 以上、無効にする場合は null にしてください。"
            )

    @property
    def hour(self) -> int:
        return parse_hhmm(self.time)[0]

    @property
    def minute(self) -> int:
        return parse_hhmm(self.time)[1]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "time": self.time,
            "enabled": self.enabled,
            "source": self.source.to_dict(),
            "volume": self.volume,
            "fade_in_seconds": self.fade_in_seconds,
            "sleep_timer_minutes": self.sleep_timer_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Schedule":
        kwargs = dict(
            name=data["name"],
            time=data["time"],
            source=Source.from_dict(data["source"]),
            enabled=data.get("enabled", True),
            volume=data.get("volume", 18),
            fade_in_seconds=data.get("fade_in_seconds", 0),
            sleep_timer_minutes=data.get("sleep_timer_minutes", 60),
        )
        if data.get("id"):
            kwargs["id"] = data["id"]
        return cls(**kwargs)


@dataclasses.dataclass
class AppSettings:
    """アプリ全体の設定。"""

    room: str | None = None  # 再生元の Sonos 部屋名（例: 主書斎）
    timezone: str = "Asia/Tokyo"

    def to_dict(self) -> dict:
        return {"room": self.room, "timezone": self.timezone}

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        return cls(
            room=data.get("room"),
            timezone=data.get("timezone", "Asia/Tokyo"),
        )
