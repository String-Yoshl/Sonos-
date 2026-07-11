"""Flask Web アプリ: Sonos アプリ風 UI と REST API。"""

from __future__ import annotations

import hmac
import logging

from flask import Flask, jsonify, request, send_from_directory

from . import sonos_client, switchbot
from .models import Schedule, Source, SwitchBotAction
from .scheduler import ScheduleRunner
from .store import Store

logger = logging.getLogger(__name__)


def _schedule_from_payload(data: dict) -> Schedule:
    """リクエストの JSON から Schedule を生成する。"""
    if not isinstance(data, dict):
        raise ValueError("リクエスト本文が不正です。")
    src = data.get("source") or {}
    source = Source(
        type=src.get("type", ""),
        title=src.get("title", ""),
        uri=src.get("uri"),
    )
    actions = [
        SwitchBotAction.from_dict(a)
        for a in (data.get("switchbot_actions") or [])
        if isinstance(a, dict)
    ]
    return Schedule(
        name=data.get("name", ""),
        time=data.get("time", ""),
        source=source,
        enabled=bool(data.get("enabled", True)),
        volume=data.get("volume", 18),
        fade_in_seconds=data.get("fade_in_seconds", 0),
        sleep_timer_minutes=data.get("sleep_timer_minutes", 60),
        switchbot_actions=actions,
    )


def create_app(
    store: Store,
    runner: ScheduleRunner | None = None,
    auth_token: str | None = None,
) -> Flask:
    """アプリを生成する。auth_token を渡すと /api/* にトークン認証を要求する。"""
    app = Flask(__name__, static_folder="static", static_url_path="")

    # ---- 認証 (S1): /api/* はトークン必須 --------------------------------
    if auth_token:

        @app.before_request
        def require_token():
            if not request.path.startswith("/api/"):
                return None  # UI シェル・静的ファイルは認証不要（秘密を含まない）
            supplied = request.headers.get("X-Auth-Token", "")
            if not supplied:
                bearer = request.headers.get("Authorization", "")
                if bearer.startswith("Bearer "):
                    supplied = bearer[len("Bearer "):]
            # タイミング攻撃を避けるため定数時間比較を使う。
            if not hmac.compare_digest(supplied, auth_token):
                return jsonify(error="認証が必要です。アクセストークンを指定してください。"), 401
            return None

    # ---- セキュリティヘッダ (S2) / API キャッシュ抑止 (S4) ---------------
    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def sync_runner() -> None:
        if runner is not None:
            runner.sync()

    def next_runs() -> dict:
        return runner.next_run_times() if runner is not None else {}

    # ---- UI / PWA -------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/manifest.webmanifest")
    def manifest():
        # Flask は .webmanifest の MIME を知らないため明示する。
        return send_from_directory(
            app.static_folder,
            "manifest.webmanifest",
            mimetype="application/manifest+json",
        )

    @app.get("/sw.js")
    def service_worker():
        # ルートスコープを許可してサイト全体を制御できるようにする。
        resp = send_from_directory(
            app.static_folder, "sw.js", mimetype="text/javascript"
        )
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ---- 部屋・設定 -----------------------------------------------------
    @app.get("/api/rooms")
    def api_rooms():
        try:
            return jsonify(sonos_client.list_rooms())
        except Exception as exc:  # noqa: BLE001
            return jsonify(error=str(exc)), 502

    def _public_settings(settings) -> dict:
        """秘密情報(SwitchBot のトークン/シークレット)を UI へ返さない形にする。"""
        d = settings.to_dict()
        token = d.pop("switchbot_token", None)
        secret = d.pop("switchbot_secret", None)
        d["switchbot_configured"] = bool(token and secret)
        return d

    @app.get("/api/settings")
    def api_get_settings():
        return jsonify(_public_settings(store.get_settings()))

    @app.put("/api/settings")
    def api_put_settings():
        data = request.get_json(silent=True) or {}
        try:
            settings = store.update_settings(
                # 空文字は「未指定」と同義に扱い、設定済みの部屋を誤って消さない。
                room=data.get("room") or None,
                timezone=data.get("timezone") or None,
                # SwitchBot 認証情報は空文字で「解除」できるようそのまま通す。
                switchbot_token=data.get("switchbot_token"),
                switchbot_secret=data.get("switchbot_secret"),
            )
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        sync_runner()
        return jsonify(_public_settings(settings))

    # ---- SwitchBot 連携 --------------------------------------------------
    @app.get("/api/switchbot/devices")
    def api_switchbot_devices():
        s = store.get_settings()
        if not s.switchbot_configured:
            return jsonify(
                error="SwitchBot が未設定です。⚙ 設定からトークンとシークレットを登録してください。"
            ), 400
        try:
            return jsonify(switchbot.list_devices(s.switchbot_token, s.switchbot_secret))
        except switchbot.SwitchBotError as exc:
            return jsonify(error=str(exc)), 502

    # ---- 音源（プレイリスト/お気に入り）の閲覧・検索 -------------------
    @app.get("/api/sources")
    def api_sources():
        room = store.get_settings().room
        query = request.args.get("q", "")
        try:
            return jsonify(sonos_client.list_sources(room, query))
        except sonos_client.SonosError as exc:
            return jsonify(error=str(exc)), 502

    # ---- スケジュール CRUD ---------------------------------------------
    @app.get("/api/schedules")
    def api_list_schedules():
        runs = next_runs()
        items = []
        for s in store.list_schedules():
            d = s.to_dict()
            d["next_run"] = runs.get(s.id)
            items.append(d)
        return jsonify(items)

    @app.post("/api/schedules")
    def api_add_schedule():
        try:
            schedule = _schedule_from_payload(request.get_json(silent=True))
            created = store.add_schedule(schedule)
        except (ValueError, KeyError) as exc:
            return jsonify(error=str(exc)), 400
        sync_runner()
        return jsonify(created.to_dict()), 201

    @app.put("/api/schedules/<schedule_id>")
    def api_update_schedule(schedule_id: str):
        try:
            schedule = _schedule_from_payload(request.get_json(silent=True))
            updated = store.update_schedule(schedule_id, schedule)
        except KeyError:
            return jsonify(error="スケジュールが見つかりません。"), 404
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        sync_runner()
        return jsonify(updated.to_dict())

    @app.delete("/api/schedules/<schedule_id>")
    def api_delete_schedule(schedule_id: str):
        if not store.delete_schedule(schedule_id):
            return jsonify(error="スケジュールが見つかりません。"), 404
        sync_runner()
        return jsonify(ok=True)

    @app.post("/api/schedules/<schedule_id>/play-now")
    def api_play_now(schedule_id: str):
        schedule = store.get_schedule(schedule_id)
        if schedule is None:
            return jsonify(error="スケジュールが見つかりません。"), 404
        settings = store.get_settings()
        try:
            sonos_client.play_schedule(settings.room, schedule)
        except sonos_client.SonosError as exc:
            return jsonify(error=str(exc)), 502
        # 家電操作は再生と独立にベストエフォートで実行する(失敗はログのみ)。
        switchbot.run_schedule_actions(settings, schedule)
        return jsonify(ok=True)

    return app
