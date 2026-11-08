"""1.2.200: control-error precedence, monotonic writes and honest poller state."""

from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from winport import agentpoll, control_status  # noqa: E402
from winport.paths import Layout  # noqa: E402


def _layout(tmp_path: Path) -> Layout:
    return Layout(program=tmp_path / "program", data=tmp_path / "data",
                  system=tmp_path / "system").ensure()


def _control() -> dict:
    return {
        "control_url": "https://control.example.test",
        "customer_id": "c_123",
        "customer_token": "customer-secret",
        "device_id": "d_456",
        "device_token": "device-secret",
        "binding_epoch": "0",
    }


def _poller(layout, *, stop_event=None):
    config = agentpoll.AgentConfig(
        customer_id="c_123", token="device-secret",
        control_url="https://control.example.test",
        data_root=str(layout.data), single_root=True,
        device_id="d_456", binding_epoch=0)
    return agentpoll.AgentPoller(
        config, stop_event=stop_event,
        logger=logging.getLogger("test-1200-poller"))


def test_first_poll_failure_only_logs_second_writes_error(tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    (Path(layout.data) / "control.json").write_text(
        json.dumps(_control()), encoding="utf-8")
    poller = _poller(layout)

    def _unauthorized(*_args, **_kwargs):
        raise agentpoll.AuthError("HTTP 401")

    monkeypatch.setattr(agentpoll, "poll_once", _unauthorized)
    with pytest.raises(agentpoll.AuthError):
        poller.run_once()

    assert control_status.read_status(layout) is None
    assert poller.status()["poll_failures"] == 1

    with pytest.raises(agentpoll.AuthError):
        poller.run_once()

    status = control_status.read_status(layout)
    assert status["state"] == "error"
    assert status["reason"] == "接入凭据失效"
    assert poller.status()["poll_failures"] == 2


def test_success_after_failures_overwrites_error_with_connected(
        tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    (Path(layout.data) / "control.json").write_text(
        json.dumps(_control()), encoding="utf-8")
    poller = _poller(layout)
    calls = []

    def _poll(*_args, **_kwargs):
        calls.append(1)
        if len(calls) <= 2:
            raise agentpoll.ControlPlaneError("connection timed out")
        return None

    monkeypatch.setattr(agentpoll, "poll_once", _poll)
    for _ in range(2):
        with pytest.raises(agentpoll.ControlPlaneError):
            poller.run_once()
    assert control_status.read_status(layout)["state"] == "error"

    poller.run_once()

    status = control_status.read_status(layout)
    assert status["state"] == "connected"
    assert status["reason"] == ""
    assert poller.status()["poll_failures"] == 0


def test_stopping_poller_does_not_write_error(tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    control_status.write_status(layout, "pending", "等待首次连接")
    stop_event = threading.Event()
    stop_event.set()
    poller = _poller(layout, stop_event=stop_event)

    def _unauthorized(*_args, **_kwargs):
        raise agentpoll.AuthError("HTTP 401")

    monkeypatch.setattr(agentpoll, "poll_once", _unauthorized)
    with pytest.raises(agentpoll.AuthError):
        poller.run_once()

    status = control_status.read_status(layout)
    assert status["state"] == "pending"
    assert status["reason"] == "等待首次连接"


def test_normal_poller_exit_writes_disabled(tmp_path):
    layout = _layout(tmp_path)
    poller = _poller(layout)
    poller.stop()

    poller._run_guarded()

    status = control_status.read_status(layout)
    assert status["state"] == "disabled"
    assert status["reason"] == "接入服务已停止"


def test_abnormal_poller_exit_writes_error_with_reason(tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    poller = _poller(layout)

    def _boom():
        raise RuntimeError("worker boom device-secret")

    monkeypatch.setattr(poller, "run", _boom)
    poller._run_guarded()

    status = control_status.read_status(layout)
    assert status["state"] == "error"
    assert "RuntimeError" in status["reason"]
    assert "worker boom" in status["reason"]
    assert "device-secret" not in status["reason"]
