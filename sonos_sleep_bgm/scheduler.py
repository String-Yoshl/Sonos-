"""毎日決まった時刻に再生をトリガーする常駐スケジューラ。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .player import PlayerError, play_sleep_bgm

logger = logging.getLogger(__name__)


def _run_job(config: Config) -> None:
    """スケジューラから呼ばれる再生ジョブ。例外は握りつぶしてログに残す。

    1 回の失敗で常駐プロセスが落ちないよう、ジョブ内で例外を処理する。
    """
    try:
        play_sleep_bgm(config)
    except PlayerError as exc:
        logger.error("再生に失敗しました: %s", exc)
    except Exception:  # noqa: BLE001 - デーモンを止めないため全例外を捕捉する。
        logger.exception("再生ジョブで予期しないエラーが発生しました。")


def run_forever(config: Config) -> None:
    """毎日 config.schedule_time に再生する常駐スケジューラを起動する。"""
    scheduler = BlockingScheduler(timezone=config.timezone)
    trigger = CronTrigger(
        hour=config.hour,
        minute=config.minute,
        timezone=config.timezone,
    )
    scheduler.add_job(
        _run_job,
        trigger=trigger,
        args=[config],
        id="sleep_bgm",
        name="毎日の睡眠 BGM",
        misfire_grace_time=300,
        coalesce=True,
    )
    logger.info(
        "スケジューラを起動しました。毎日 %02d:%02d (%s) に '%s' で再生します。",
        config.hour,
        config.minute,
        config.timezone,
        config.room,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("スケジューラを停止します。")
