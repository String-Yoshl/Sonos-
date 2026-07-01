"""設定とスケジュールを JSON ファイルに永続化するストア。

変更するまで設定が有効＝ファイルに保存して再起動後も保持する。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import AppSettings, Schedule

DEFAULT_DATA_PATH = Path("data") / "app_data.json"


class Store:
    """スレッドセーフな JSON 永続化ストア。"""

    def __init__(self, path: str | Path = DEFAULT_DATA_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._settings = AppSettings()
        self._schedules: list[Schedule] = []
        self._load()

    # ---- 永続化 ---------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._settings = AppSettings.from_dict(data.get("settings", {}))
        self._schedules = [Schedule.from_dict(s) for s in data.get("schedules", [])]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "settings": self._settings.to_dict(),
            "schedules": [s.to_dict() for s in self._schedules],
        }
        # 原子的に書き込む（途中で壊れないよう一時ファイル経由）。
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    # ---- 設定 -----------------------------------------------------------
    def get_settings(self) -> AppSettings:
        with self._lock:
            return AppSettings.from_dict(self._settings.to_dict())

    def update_settings(self, **changes) -> AppSettings:
        with self._lock:
            data = self._settings.to_dict()
            data.update({k: v for k, v in changes.items() if v is not None})
            candidate = AppSettings.from_dict(data)
            # 不正な値(壊れた timezone 等)を保存すると次回起動に失敗するため、
            # 検証を通ってから初めて反映・保存する。
            candidate.validate()
            self._settings = candidate
            self._save()
            return self.get_settings()

    # ---- スケジュール ---------------------------------------------------
    def list_schedules(self) -> list[Schedule]:
        with self._lock:
            return [Schedule.from_dict(s.to_dict()) for s in self._schedules]

    def get_schedule(self, schedule_id: str) -> Schedule | None:
        with self._lock:
            for s in self._schedules:
                if s.id == schedule_id:
                    return Schedule.from_dict(s.to_dict())
            return None

    def add_schedule(self, schedule: Schedule) -> Schedule:
        schedule.validate()
        with self._lock:
            self._schedules.append(schedule)
            self._save()
            return Schedule.from_dict(schedule.to_dict())

    def update_schedule(self, schedule_id: str, schedule: Schedule) -> Schedule:
        schedule.id = schedule_id
        schedule.validate()
        with self._lock:
            for i, existing in enumerate(self._schedules):
                if existing.id == schedule_id:
                    self._schedules[i] = schedule
                    self._save()
                    return Schedule.from_dict(schedule.to_dict())
            raise KeyError(schedule_id)

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._lock:
            before = len(self._schedules)
            self._schedules = [s for s in self._schedules if s.id != schedule_id]
            if len(self._schedules) != before:
                self._save()
                return True
            return False
