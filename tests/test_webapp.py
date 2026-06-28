import pytest

from sonos_sleep_bgm import sonos_client, webapp
from sonos_sleep_bgm.store import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = Store(tmp_path / "data.json")
    store.update_settings(room="主書斎")
    app = webapp.create_app(store, runner=None)
    app.config.update(TESTING=True)
    # Sonos 実機に触れないようモック化。
    monkeypatch.setattr(
        sonos_client, "list_sources",
        lambda room, query="": [
            {"type": "playlist", "title": "Sleep", "uri": None, "subtitle": "プレイリスト"}
        ],
    )
    monkeypatch.setattr(sonos_client, "play_schedule", lambda room, sched: None)
    return app.test_client(), store


def _payload(**kw):
    base = {
        "name": "夜BGM",
        "time": "21:00",
        "source": {"type": "playlist", "title": "Sleep"},
        "volume": 18,
        "sleep_timer_minutes": 60,
    }
    base.update(kw)
    return base


def test_get_settings(client):
    c, _ = client
    res = c.get("/api/settings")
    assert res.status_code == 200
    assert res.get_json()["room"] == "主書斎"


def test_sources_endpoint(client):
    c, _ = client
    res = c.get("/api/sources?q=sl")
    assert res.status_code == 200
    assert res.get_json()[0]["title"] == "Sleep"


def test_schedule_crud_flow(client):
    c, _ = client
    # 作成
    res = c.post("/api/schedules", json=_payload())
    assert res.status_code == 201
    sid = res.get_json()["id"]

    # 一覧
    res = c.get("/api/schedules")
    assert len(res.get_json()) == 1

    # 更新
    res = c.put(f"/api/schedules/{sid}", json=_payload(name="変更", time="07:30"))
    assert res.status_code == 200
    assert res.get_json()["name"] == "変更"

    # 即再生（モック）
    res = c.post(f"/api/schedules/{sid}/play-now")
    assert res.status_code == 200

    # 削除
    res = c.delete(f"/api/schedules/{sid}")
    assert res.status_code == 200
    assert c.get("/api/schedules").get_json() == []


def test_validation_error_returns_400(client):
    c, _ = client
    res = c.post("/api/schedules", json=_payload(time="99:99"))
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_sleep_timer_disabled_persisted(client):
    c, _ = client
    res = c.post("/api/schedules", json=_payload(sleep_timer_minutes=None))
    assert res.status_code == 201
    assert res.get_json()["sleep_timer_minutes"] is None


def test_update_missing_returns_404(client):
    c, _ = client
    res = c.put("/api/schedules/nope", json=_payload())
    assert res.status_code == 404
