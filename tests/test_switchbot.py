"""SwitchBot 連携のテスト（API はモック、実機・実アカウント不要）。"""

import base64
import hashlib
import hmac
import threading
from unittest import mock

import pytest

from sonos_sleep_bgm import switchbot, webapp
from sonos_sleep_bgm.models import AppSettings, Schedule, Source, SwitchBotAction
from sonos_sleep_bgm.store import Store


def make_schedule(**kw):
    base = dict(name="夜", time="21:00", source=Source(type="playlist", title="Sleep"))
    base.update(kw)
    return Schedule(**base)


def make_settings():
    return AppSettings(room="主書斎", switchbot_token="tok", switchbot_secret="sec")


# ---- 署名 ---------------------------------------------------------------
def test_headers_signature_matches_spec():
    headers = switchbot._make_headers("tok", "sec", "1700000000000", "nonce1")
    expected = base64.b64encode(
        hmac.new(b"sec", b"tok1700000000000nonce1", hashlib.sha256).digest()
    ).decode().upper()
    assert headers["sign"] == expected
    assert headers["Authorization"] == "tok"
    assert headers["t"] == "1700000000000"
    assert headers["nonce"] == "nonce1"


# ---- デバイス一覧 -------------------------------------------------------
def test_list_devices_merges_physical_and_ir(monkeypatch):
    monkeypatch.setattr(
        switchbot, "_request",
        lambda *a, **k: {
            "deviceList": [
                {"deviceId": "P1", "deviceName": "プラグ", "deviceType": "Plug"},
            ],
            "infraredRemoteList": [
                {"deviceId": "IR1", "deviceName": "寝室エアコン", "remoteType": "Air Conditioner"},
            ],
        },
    )
    devices = switchbot.list_devices("tok", "sec")
    assert {d["id"] for d in devices} == {"P1", "IR1"}
    ir = next(d for d in devices if d["id"] == "IR1")
    assert ir["infrared"] is True and ir["name"] == "寝室エアコン"


def test_api_error_raises(monkeypatch):
    monkeypatch.setattr(
        switchbot, "_request",
        mock.Mock(side_effect=switchbot.SwitchBotError("認証エラー")),
    )
    with pytest.raises(switchbot.SwitchBotError):
        switchbot.list_devices("tok", "sec")


# ---- 実行タイミング -----------------------------------------------------
def test_start_timing_runs_immediately(monkeypatch):
    sent = []
    monkeypatch.setattr(
        switchbot, "send_command",
        lambda t, s, dev, cmd: sent.append((dev, cmd)),
    )
    schedule = make_schedule(
        switchbot_actions=[SwitchBotAction(device_id="IR1", command="turnOff")]
    )
    switchbot.run_schedule_actions(make_settings(), schedule)
    assert sent == [("IR1", "turnOff")]


def test_end_timing_uses_sleep_timer_delay(monkeypatch):
    delays = []

    class FakeTimer:
        def __init__(self, delay, fn, args=()):
            delays.append(delay)
        daemon = True
        def start(self):
            pass

    monkeypatch.setattr(switchbot.threading, "Timer", FakeTimer)
    schedule = make_schedule(
        sleep_timer_minutes=45,
        switchbot_actions=[SwitchBotAction(device_id="IR1", timing="end")],
    )
    switchbot.run_schedule_actions(make_settings(), schedule)
    assert delays == [45 * 60]  # スリープ終了時刻に合わせて遅延実行


def test_end_timing_without_sleep_timer_runs_now(monkeypatch):
    sent = []
    monkeypatch.setattr(
        switchbot, "send_command", lambda t, s, dev, cmd: sent.append(dev)
    )
    schedule = make_schedule(
        sleep_timer_minutes=None,
        switchbot_actions=[SwitchBotAction(device_id="IR1", timing="end")],
    )
    switchbot.run_schedule_actions(make_settings(), schedule)
    assert sent == ["IR1"]


def test_unconfigured_skips_silently(monkeypatch):
    called = mock.Mock()
    monkeypatch.setattr(switchbot, "send_command", called)
    schedule = make_schedule(
        switchbot_actions=[SwitchBotAction(device_id="IR1")]
    )
    switchbot.run_schedule_actions(AppSettings(room="主書斎"), schedule)
    called.assert_not_called()


def test_send_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(
        switchbot, "send_command",
        mock.Mock(side_effect=switchbot.SwitchBotError("boom")),
    )
    schedule = make_schedule(
        switchbot_actions=[SwitchBotAction(device_id="IR1")]
    )
    switchbot.run_schedule_actions(make_settings(), schedule)  # 例外が出ないこと


# ---- モデル -------------------------------------------------------------
def test_action_roundtrip():
    s = make_schedule(
        switchbot_actions=[
            SwitchBotAction(device_id="IR1", device_name="エアコン", timing="end")
        ]
    )
    again = Schedule.from_dict(s.to_dict())
    assert again.switchbot_actions[0].device_id == "IR1"
    assert again.switchbot_actions[0].timing == "end"


def test_invalid_command_rejected():
    s = make_schedule(
        switchbot_actions=[SwitchBotAction(device_id="IR1", command="explode")]
    )
    with pytest.raises(ValueError, match="コマンド"):
        s.validate()


def test_missing_device_id_rejected():
    s = make_schedule(switchbot_actions=[SwitchBotAction(device_id=" ")])
    with pytest.raises(ValueError, match="device_id"):
        s.validate()


# ---- Web API ------------------------------------------------------------
@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "data.json")
    store.update_settings(room="主書斎")
    app = webapp.create_app(store, runner=None)
    app.config.update(TESTING=True)
    return app.test_client(), store


def test_settings_do_not_leak_secrets(client):
    c, store = client
    store.update_settings(switchbot_token="tok", switchbot_secret="sec")
    body = c.get("/api/settings").get_json()
    assert "switchbot_token" not in body
    assert "switchbot_secret" not in body
    assert body["switchbot_configured"] is True


def test_put_settings_stores_credentials(client):
    c, store = client
    res = c.put(
        "/api/settings",
        json={"switchbot_token": "tok", "switchbot_secret": "sec"},
    )
    assert res.status_code == 200
    assert res.get_json()["switchbot_configured"] is True
    assert store.get_settings().switchbot_token == "tok"


def test_devices_endpoint_requires_config(client):
    c, _ = client
    res = c.get("/api/switchbot/devices")
    assert res.status_code == 400
    assert "未設定" in res.get_json()["error"]


def test_devices_endpoint_returns_list(client, monkeypatch):
    c, store = client
    store.update_settings(switchbot_token="tok", switchbot_secret="sec")
    monkeypatch.setattr(
        switchbot, "list_devices",
        lambda t, s: [{"id": "IR1", "name": "エアコン", "type": "Air Conditioner", "infrared": True}],
    )
    res = c.get("/api/switchbot/devices")
    assert res.status_code == 200
    assert res.get_json()[0]["name"] == "エアコン"


def test_schedule_with_actions_persists(client):
    c, _ = client
    res = c.post(
        "/api/schedules",
        json={
            "name": "夜",
            "time": "21:00",
            "source": {"type": "playlist", "title": "Sleep"},
            "switchbot_actions": [
                {"device_id": "IR1", "device_name": "エアコン", "command": "turnOff", "timing": "end"}
            ],
        },
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["switchbot_actions"][0]["command"] == "turnOff"
    assert body["switchbot_actions"][0]["timing"] == "end"
