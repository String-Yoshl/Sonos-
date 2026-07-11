"""SwitchBot API v1.1 クライアント（標準ライブラリのみ使用）。

スケジュールの時刻に合わせて SwitchBot デバイス（エアコンのリモコン、
プラグ、ボット等）を ON/OFF する。認証は SwitchBot アプリの
「開発者向けオプション」で取得できるトークンとシークレットを使う。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AppSettings, Schedule, SwitchBotAction

logger = logging.getLogger(__name__)

API_BASE = "https://api.switch-bot.com"


class SwitchBotError(RuntimeError):
    """SwitchBot API の失敗を表す例外。"""


def _make_headers(token: str, secret: str, t: str, nonce: str) -> dict:
    """API v1.1 の署名付きヘッダを作る（HMAC-SHA256, 大文字 Base64）。"""
    sign = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            (token + t + nonce).encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8").upper()
    return {
        "Authorization": token,
        "sign": sign,
        "t": t,
        "nonce": nonce,
        "Content-Type": "application/json; charset=utf8",
    }


def _request(method: str, path: str, token: str, secret: str, payload: dict | None = None) -> dict:
    t = str(int(time.time() * 1000))
    nonce = uuid.uuid4().hex
    req = urllib.request.Request(
        API_BASE + path,
        method=method,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=_make_headers(token, secret, t, nonce),
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SwitchBotError(
            f"SwitchBot API エラー (HTTP {exc.code})。トークン/シークレットを確認してください。"
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SwitchBotError(f"SwitchBot API に接続できません: {exc}") from exc

    if body.get("statusCode") != 100:
        raise SwitchBotError(
            f"SwitchBot API エラー: {body.get('message', body.get('statusCode'))}"
        )
    return body.get("body", {})


def list_devices(token: str, secret: str) -> list[dict]:
    """物理デバイスと赤外線リモコン（エアコン等）をまとめて返す。"""
    body = _request("GET", "/v1.1/devices", token, secret)
    devices = []
    for d in body.get("deviceList", []) or []:
        devices.append(
            {
                "id": d.get("deviceId"),
                "name": d.get("deviceName") or d.get("deviceId"),
                "type": d.get("deviceType", ""),
                "infrared": False,
            }
        )
    for d in body.get("infraredRemoteList", []) or []:
        devices.append(
            {
                "id": d.get("deviceId"),
                "name": d.get("deviceName") or d.get("deviceId"),
                "type": d.get("remoteType", ""),
                "infrared": True,
            }
        )
    return [d for d in devices if d["id"]]


def send_command(token: str, secret: str, device_id: str, command: str) -> None:
    """デバイスにコマンド（turnOn/turnOff）を送る。"""
    _request(
        "POST",
        f"/v1.1/devices/{device_id}/commands",
        token,
        secret,
        {"commandType": "command", "command": command, "parameter": "default"},
    )


def _send_safe(settings: "AppSettings", action: "SwitchBotAction") -> None:
    """1 操作を実行する。失敗しても例外を上げず、ログに残すだけにする。"""
    label = action.device_name or action.device_id
    try:
        send_command(
            settings.switchbot_token, settings.switchbot_secret,
            action.device_id, action.command,
        )
        logger.info("SwitchBot: %s を %s しました。", label, action.command)
    except SwitchBotError as exc:
        logger.error("SwitchBot: %s の %s に失敗: %s", label, action.command, exc)
    except Exception:  # noqa: BLE001 - 家電操作の失敗で再生系を止めない
        logger.exception("SwitchBot: %s の操作で予期しないエラー", label)


def run_schedule_actions(settings: "AppSettings", schedule: "Schedule") -> None:
    """スケジュールに紐づく SwitchBot 操作を実行する。

    timing="start" は即時、"end" はスリープタイマー終了時刻に合わせて
    遅延実行する（タイマー無効のセットでは即時扱い）。
    失敗しても例外は呼び出し元へ伝播させない。
    """
    actions = schedule.switchbot_actions or []
    if not actions:
        return
    if not settings.switchbot_configured:
        logger.warning(
            "SwitchBot 操作が設定されていますが、トークン未登録のためスキップします。"
        )
        return
    for action in actions:
        delay = 0
        if action.timing == "end" and schedule.sleep_timer_minutes:
            delay = schedule.sleep_timer_minutes * 60
        if delay > 0:
            timer = threading.Timer(delay, _send_safe, args=(settings, action))
            timer.daemon = True
            timer.start()
            logger.info(
                "SwitchBot: %s を %d 分後(スリープ終了時)に %s します。",
                action.device_name or action.device_id,
                schedule.sleep_timer_minutes,
                action.command,
            )
        else:
            _send_safe(settings, action)
