"""複数スケジュールを管理する常駐スケジューラ（変更時に再同期）。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import sonos_client
from .store import Store

logger = logging.getLogger(__name__)


class ScheduleRunner:
    """ストアの有効なスケジュールを APScheduler のジョブとして同期する。"""

    def __init__(self, store: Store) -> None:
        self.store = store
        self._scheduler = BackgroundScheduler(
            timezone=store.get_settings().timezone
        )

    def start(self) -> None:
        self._scheduler.start()
        self.sync()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _run(self, schedule_id: str) -> None:
        """ジョブ本体。実行時に最新のスケジュールと部屋を読み直す。"""
        schedule = self.store.get_schedule(schedule_id)
        if schedule is None or not schedule.enabled:
            return
        room = self.store.get_settings().room
        try:
            sonos_client.play_schedule(room, schedule)
        except sonos_client.SonosError as exc:
            logger.error("再生失敗 (%s): %s", schedule.name, exc)
        except Exception:  # noqa: BLE001 - デーモンを止めない
            logger.exception("再生ジョブで予期しないエラー (%s)", schedule.name)

    def sync(self) -> None:
        """ストアの内容に合わせてジョブ群を貼り直す。設定変更後に呼ぶ。"""
        settings = self.store.get_settings()
        # 各ジョブの CronTrigger に明示的に timezone を渡すため、
        # 起動中のスケジューラ既定 timezone を変更する必要はない。
        self._scheduler.remove_all_jobs()
        for schedule in self.store.list_schedules():
            if not schedule.enabled:
                continue
            self._scheduler.add_job(
                self._run,
                trigger=CronTrigger(
                    hour=schedule.hour,
                    minute=schedule.minute,
                    timezone=settings.timezone,
                ),
                args=[schedule.id],
                id=schedule.id,
                name=schedule.name,
                misfire_grace_time=300,
                coalesce=True,
                replace_existing=True,
            )
        logger.info(
            "スケジュールを同期しました（有効: %d 件）。",
            sum(1 for s in self.store.list_schedules() if s.enabled),
        )

    def next_run_times(self) -> dict[str, str | None]:
        """各ジョブの次回実行時刻（ISO文字列）を返す。"""
        result: dict[str, str | None] = {}
        for job in self._scheduler.get_jobs():
            nxt = job.next_run_time
            result[job.id] = nxt.isoformat() if nxt else None
        return result
