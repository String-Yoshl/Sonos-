"""CLI ユーティリティ（Tailscale 検出など）のテスト。"""

import subprocess
from unittest import mock

from sonos_sleep_bgm import cli


def _fake_run(stdout, returncode=0):
    def run(cmd, capture_output, text, timeout):
        return mock.Mock(stdout=stdout, returncode=returncode)
    return run


def test_tailscale_ip_detected(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run", _fake_run("100.101.102.103\n"))
    assert cli._tailscale_ip() == "100.101.102.103"


def test_tailscale_ip_ignores_non_cgnat(monkeypatch):
    # Tailscale 範囲(100.64.0.0/10)外の IP は採用しない。
    monkeypatch.setattr(cli.subprocess, "run", _fake_run("192.168.1.5\n"))
    assert cli._tailscale_ip() is None


def test_tailscale_not_installed(monkeypatch):
    def raise_fnf(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(cli.subprocess, "run", raise_fnf)
    assert cli._tailscale_ip() is None


def test_tailscale_command_fails(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run", _fake_run("", returncode=1))
    assert cli._tailscale_ip() is None


def test_tailscale_timeout(monkeypatch):
    def raise_timeout(cmd, **k):
        raise subprocess.TimeoutExpired(cmd, 3)
    monkeypatch.setattr(cli.subprocess, "run", raise_timeout)
    assert cli._tailscale_ip() is None
