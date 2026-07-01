# Sonos 睡眠 BGM ワンコマンドインストーラ (Windows / PowerShell)
#
#   実行方法 (このファイルのあるフォルダで):
#     powershell -ExecutionPolicy Bypass -File .\install.ps1
#   セットアップのみ:  .\install.ps1 setup
#
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venv = ".venv"

# python か py を探す
$py = $null
foreach ($cand in @("python", "py")) {
  if (Get-Command $cand -ErrorAction SilentlyContinue) { $py = $cand; break }
}
if (-not $py) {
  Write-Error "python が見つかりません。先に Python 3.10 以上を入れてください。"
  exit 1
}

Write-Host "==> 仮想環境を作成 ($venv)"
& $py -m venv $venv

Write-Host "==> 依存パッケージをインストール"
& "$venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt

Write-Host "==> 完了しました。"

if ($args.Count -ge 1 -and $args[0] -eq "setup") {
  Write-Host "起動するには:  $venv\Scripts\python.exe -m sonos_sleep_bgm.cli serve"
  exit 0
}

Write-Host "==> サーバを起動します (Ctrl+C で終了)"
Write-Host ""
& "$venv\Scripts\python.exe" -m sonos_sleep_bgm.cli serve
