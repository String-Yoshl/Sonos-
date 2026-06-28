# sonos-sleep-bgm

主書斎の **Sonos** から、**毎日決まった時刻に指定した睡眠 BGM を自動再生**する自分用アプリです。
Sonos のローカル制御 API（[SoCo](https://github.com/SoCo/SoCo)）を使うので、同じ LAN にいれば
クラウドのアカウント連携なしで動きます。

## 仕組み

- `SoCo` で部屋名（例: `主書斎`）から Sonos スピーカーを特定して再生する
- 音源は **Sonos のお気に入り名** か **直接 URI** のどちらでも指定できる
- `APScheduler` の cron トリガーで、毎日 `schedule_time` に再生ジョブを起動する
- 常駐プロセス（`run`）として動かす。1 回の再生失敗ではプロセスは落ちない

## セットアップ

```bash
# 依存をインストール（仮想環境推奨）
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 設定ファイルを用意して編集する
cp config.example.yaml config.yaml
```

`config.yaml` の主な項目:

| キー | 説明 |
| --- | --- |
| `room` | Sonos アプリ上の部屋名。例 `主書斎` |
| `schedule_time` | 毎日の再生開始時刻 `HH:MM`（24時間表記）。睡眠 BGM なので既定は `21:00` |
| `bgm_favorite` | 再生する Sonos お気に入りの名前（推奨） |
| `bgm_uri` | お気に入りの代わりに直接指定する音源 URI |
| `volume` | 再生音量 0〜100（`null` で変更しない） |
| `fade_in_seconds` | 目標音量までフェードインする秒数（0 で即時） |
| `timezone` | スケジューラのタイムゾーン。例 `Asia/Tokyo` |

> ⏰ **9 時について**: 睡眠 BGM なので既定は夜 9 時（`21:00`）にしています。
> 朝 9 時にしたい場合は `schedule_time: "09:00"` に変更してください。

## 使い方

```bash
# まず部屋名を確認（Sonos が検出できるか確認できる）
python -m sonos_sleep_bgm.cli list-rooms

# お気に入り名を確認
python -m sonos_sleep_bgm.cli list-favorites

# その場で 1 回再生して動作確認
python -m sonos_sleep_bgm.cli play-now

# 常駐してスケジュール通りに毎日再生する
python -m sonos_sleep_bgm.cli run
```

`pip install -e .` でインストールすると `sonos-sleep-bgm` コマンドとしても使えます。

## 常時起動（おすすめ: systemd）

PC や Raspberry Pi で常駐させる例（`/etc/systemd/system/sonos-sleep-bgm.service`）:

```ini
[Unit]
Description=Sonos Sleep BGM Scheduler
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/home/youruser/sonos-sleep-bgm
ExecStart=/home/youruser/sonos-sleep-bgm/.venv/bin/python -m sonos_sleep_bgm.cli run
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now sonos-sleep-bgm
journalctl -u sonos-sleep-bgm -f   # ログ確認
```

## テスト

```bash
pip install pytest
pytest
```

Sonos 実機がなくても通るよう、再生まわりはモックでテストしています。

## 注意

- アプリを動かす機器は Sonos と **同じネットワーク**（同一サブネット）にいる必要があります。
- `config.yaml`（音源 URL やお気に入り名）は `.gitignore` 済みでコミットされません。
