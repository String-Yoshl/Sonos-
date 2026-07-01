import stat

import pytest

from sonos_sleep_bgm.auth import load_or_create_token
from sonos_sleep_bgm.models import Schedule, Source
from sonos_sleep_bgm.store import Store
from sonos_sleep_bgm.webapp import create_app

TOKEN = "test-token-abc123"


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "data.json")
    store.update_settings(room="主書斎")
    app = create_app(store, runner=None, auth_token=TOKEN)
    app.config.update(TESTING=True)
    return app.test_client()


# ---- S1: API 認証 -----------------------------------------------------
def test_api_requires_token(client):
    assert client.get("/api/schedules").status_code == 401
    assert client.get("/api/settings").status_code == 401
    assert client.post("/api/schedules", json={}).status_code == 401
    assert client.delete("/api/schedules/x").status_code == 401


def test_api_accepts_header_token(client):
    res = client.get("/api/schedules", headers={"X-Auth-Token": TOKEN})
    assert res.status_code == 200


def test_api_accepts_bearer_token(client):
    res = client.get("/api/settings", headers={"Authorization": f"Bearer {TOKEN}"})
    assert res.status_code == 200


def test_api_rejects_wrong_token(client):
    res = client.get("/api/schedules", headers={"X-Auth-Token": "wrong"})
    assert res.status_code == 401


def test_ui_shell_served_without_token(client):
    # UI シェル(秘密を含まない)はログイン前でも取得できる必要がある。
    assert client.get("/").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200


def test_auth_disabled_when_no_token(tmp_path):
    store = Store(tmp_path / "data.json")
    app = create_app(store, runner=None)  # auth_token 未指定 = 認証なし(テスト用)
    assert app.test_client().get("/api/schedules").status_code == 200


# ---- S2/S4: セキュリティヘッダとキャッシュ抑止 -------------------------
def test_security_headers_on_ui(client):
    res = client.get("/")
    assert "default-src 'self'" in res.headers["Content-Security-Policy"]
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "no-referrer"


def test_api_responses_not_cached(client):
    res = client.get("/api/schedules", headers={"X-Auth-Token": TOKEN})
    assert res.headers["Cache-Control"] == "no-store"


def test_index_has_no_inline_script(client):
    # インラインスクリプトがあると CSP を緩めることになるため禁止。
    html = client.get("/").get_data(as_text=True)
    assert "<script>" not in html


# ---- S3: URI スキーム検証 ----------------------------------------------
@pytest.mark.parametrize(
    "bad_uri",
    ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,x", "no-scheme"],
)
def test_dangerous_uri_schemes_rejected(bad_uri):
    s = Schedule(name="x", time="21:00", source=Source(type="uri", uri=bad_uri))
    with pytest.raises(ValueError, match="スキーム"):
        s.validate()


@pytest.mark.parametrize(
    "good_uri",
    [
        "http://192.168.1.5:8000/sleep.mp3",
        "https://stream.example.com/radio",
        "x-rincon-mp3radio://stream.example.com/radio",
    ],
)
def test_valid_uri_schemes_accepted(good_uri):
    s = Schedule(name="x", time="21:00", source=Source(type="uri", uri=good_uri))
    s.validate()


# ---- トークンの生成と再利用 --------------------------------------------
def test_token_created_and_reused(tmp_path):
    data = tmp_path / "data.json"
    t1 = load_or_create_token(data)
    t2 = load_or_create_token(data)
    assert t1 == t2
    assert len(t1) >= 32


def test_token_file_permissions(tmp_path):
    load_or_create_token(tmp_path / "data.json")
    mode = stat.S_IMODE((tmp_path / "auth_token").stat().st_mode)
    assert mode == 0o600
