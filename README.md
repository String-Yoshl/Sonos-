# sonos-sleep-bgm

主書斎の **Sonos** で、**Sonos アプリのような UI** からプレイリスト／お気に入りを
閲覧・検索して BGM を選び、**「時刻 × BGM」のセットを複数ストック**して、
**毎日決まった時刻に自動再生**する自分用アプリです。
Sonos のローカル制御 API（[SoCo](https://github.com/SoCo/SoCo)）を使うので、
同じ LAN にいればクラウドのアカウント連携なしで動きます。

## 📱 スマホアプリとして使う（PWA）

このアプリは **PWA**（ホーム画面に追加できる Web アプリ）です。スマホのホーム画面に
追加すると、**全画面のネイティブ風アプリ**として起動できます。

**構成のポイント**

```
[常時起動のホスト]              [スマホ]
 PC / Raspberry Pi 等           iPhone / Android
 ├ スケジューラ(定時再生)  ◀──   └ ホーム画面の「睡眠BGM」アプリ
 └ Web/UI サーバ                    （操作盤として接続）
        │
        └── LAN ──▶ Sonos（主書斎）で再生
```

> ⚠️ **定時再生を担うのはサーバ側**です。スマホはスリープするとバックグラウンド実行が
> 止まるため、**サーバは常時起動のホスト**（自宅 PC や Raspberry Pi）で動かしてください。
> スマホアプリはあくまで「設定・操作のための画面」です。

**手順**

1. 常時起動するホストでサーバを起動: `python -m sonos_sleep_bgm.cli serve`
   （起動時にスマホ用 URL `http://<PCのIP>:8765` が表示されます）
2. スマホを**同じ Wi‑Fi** につなぎ、ブラウザでその URL を開く。
3. **ホーム画面に追加**する。
   - iPhone(Safari): 共有 → 「ホーム画面に追加」
   - Android(Chrome): メニュー → 「ホーム画面に追加 / アプリをインストール」
4. ホーム画面の「睡眠BGM」アイコンから、アプリとして起動。

> オフライン起動キャッシュ（Service Worker）は HTTPS か localhost でのみ有効です。
> LAN の HTTP でも「ホーム画面に追加」によるアプリ起動・操作は問題なく動きます。

## できること

- 🎚️ **Sonos アプリ風の Web UI** … プレイリスト／お気に入りを**一覧・検索**して選択。選んだ設定はファイルに保存され、**変更するまで有効**。
- 🕘 **時刻は任意設定** … 各セットごとに `HH:MM` を自由に指定。
- 🗂️ **セットを複数ストック** … 「夜は環境音、朝はジャズ」のように「時刻 + BGM」のセットをいくつでも登録でき、個別に有効/無効を切り替え可能。
- 😴 **スリープタイマー** … 既定 60 分。無効や任意の分数（15/30/45/60/90/120/その他）に変更可。Sonos ネイティブのスリープタイマーを使うので、指定時間で自動停止。
- 🔊 音量・フェードインも各セットで設定。「▶ 今すぐ再生」で動作確認もできる。

## 構成

| モジュール | 役割 |
| --- | --- |
| `models.py` | データモデル（設定・スケジュール・音源）とバリデーション |
| `store.py` | JSON ファイルへの永続化（再起動後も設定を保持） |
| `sonos_client.py` | SoCo ラッパー：部屋検出・音源一覧/検索・再生・スリープタイマー |
| `scheduler.py` | APScheduler で複数スケジュールを管理（設定変更時に再同期） |
| `webapp.py` | Flask の REST API ＋ UI 配信 |
| `static/` | Sonos アプリ風のフロントエンド（HTML/CSS/JS） |
| `cli.py` | `serve` / `list-rooms` / `play-now` |

## セットアップ

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方

```bash
# 部屋が検出できるか確認（任意）
python -m sonos_sleep_bgm.cli list-rooms

# Web UI + スケジューラを起動（既定で LAN に公開＝スマホからも使える）
python -m sonos_sleep_bgm.cli serve
#  → このPC:  http://127.0.0.1:8765
#  → スマホ:  http://<PCのIP>:8765  （起動時に実IPを表示）
#  このPCだけに限定したい場合:  serve --host 127.0.0.1
```

ブラウザでの操作:

1. 右上の**「再生する部屋」**で `主書斎` を選ぶ（自動保存）。
2. **「＋ 新しいセット」**をクリック。
3. 名前・**再生開始時刻**・**スリープタイマー**を設定。
4. 検索ボックスでプレイリスト／お気に入りを探して選択。
5. 音量・フェードインを調整して**保存**。
6. カードの **▶** で即時再生テスト、トグルで有効/無効、✎ で編集、🗑 で削除。

データは `data/app_data.json` に保存され、**変更するまで有効**です。

> `serve` の `--host 0.0.0.0` で同一 LAN の他端末（スマホ等）からも操作できます。

## 常時起動（おすすめ: systemd）

`/etc/systemd/system/sonos-sleep-bgm.service`:

```ini
[Unit]
Description=Sonos Sleep BGM
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/home/youruser/sonos-sleep-bgm
ExecStart=/home/youruser/sonos-sleep-bgm/.venv/bin/python -m sonos_sleep_bgm.cli serve --host 0.0.0.0
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now sonos-sleep-bgm
journalctl -u sonos-sleep-bgm -f
```

## テスト

```bash
pip install pytest
pytest
```

Sonos 実機がなくても通るよう、再生まわりはモックでテストしています。

## 注意

- アプリを動かす機器は Sonos と**同じネットワーク**（同一サブネット）にいる必要があります。
- `data/`（保存した設定）は `.gitignore` 済みでコミットされません。
