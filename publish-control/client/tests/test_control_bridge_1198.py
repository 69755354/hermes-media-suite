"""1.2.198: forced control recovery, shared status root, no fake green."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from winport import activation, agentpoll, control_status, main, panel  # noqa: E402
from winport.paths import Layout  # noqa: E402


def _layout(tmp_path: Path) -> Layout:
    return Layout(program=tmp_path / "program", data=tmp_path / "data",
                  system=tmp_path / "system").ensure()


def _control(customer_token="stale-secret", customer_id="c_123") -> dict:
    return {
        "control_url": "https://control.example.test",
        "customer_id": customer_id,
        "customer_token": customer_token,
        "device_id": "d_456",
        "device_token": "device-secret",
        "binding_epoch": "0",
    }


def _formal_state():
    return {"publish_allowed": True, "status": "OK", "source": "licence",
            "days_left": 300, "text": "授权有效", "tombstone_error": None}


def _response(control):
    return {"license": {"machine_id": "MACHINE-1",
                        "expires_at": "2099-01-01"},
            "control": control}


def _clear_env(monkeypatch):
    for name in (
            "CONTROL_URL", "CUSTOMER_ID", "CUSTOMER_TOKEN", "DEVICE_ID",
            "DEVICE_TOKEN", "DEVICE_BINDING_EPOCH", "BINDING_EPOCH",
            "WINPORT_CUSTOMER_ID", "WINPORT_CUSTOMER_TOKEN",
            "WINPORT_DEVICE_ID", "AGENT_CUSTOMER_ID", "AGENT_TOKEN",
            "AGENT_DEVICE_ID", "WINPORT_CUSTOMER_ROOT", "AGENT_SINGLE_ROOT",
            "WINPORT_DATA"):
        monkeypatch.delenv(name, raising=False)


def _write_control(layout, token):
    target = Path(layout.data) / "control.json"
    target.write_text(json.dumps(_control(token)), encoding="utf-8")
    return json.loads(target.read_text(encoding="utf-8"))["customer_token"]


class _FakePoller:
    def __init__(self):
        self.stops = 0
        self.thread = None

    def stop(self):
        self.stops += 1


def test_refresh_with_same_code_forces_exchange_and_restarts_poller(
        tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    _write_control(layout, "stale-secret")
    control_status.write_status(layout, "error", "接入凭据失效")
    assert panel.control_banner(layout)["state"] == "error"

    exchanges = []
    restarts = []
    monkeypatch.setattr(activation, "fingerprint",
                        lambda: {"machine_id": "MACHINE-1"})
    monkeypatch.setattr(activation, "unified_license_state",
                        lambda *_args, **_kwargs: dict(_formal_state()))

    def _exchange(code, machine_id):
        exchanges.append((code, machine_id))
        return _response(_control("fresh-secret"))

    monkeypatch.setattr(activation, "exchange", _exchange)

    def _restart():
        restarts.append("restart")
        return {"ok": True, "reason": "接入服务已重启"}

    handlers = panel.PanelHandlers(layout, [], restart_poller=_restart)
    result = handlers.control_refresh("ABCD1234")

    assert exchanges == [("ABCD1234", "MACHINE-1")]
    assert restarts == ["restart"]
    target = Path(layout.data) / "control.json"
    assert json.loads(target.read_text(encoding="utf-8"))["customer_token"] == (
        "fresh-secret")
    status = control_status.read_status(layout)
    assert status["state"] == "pending"
    assert status["reason"] != "接入凭据失效"
    banner = panel.control_banner(layout)
    assert banner["state"] == "pending"
    assert banner["level"] == "warn"
    assert banner["state"] != "connected"
    assert "连接中" in banner["text"]


def test_refresh_restart_failure_is_visible_not_silent(tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    _write_control(layout, "stale-secret")
    monkeypatch.setattr(activation, "fingerprint",
                        lambda: {"machine_id": "MACHINE-1"})
    monkeypatch.setattr(activation, "unified_license_state",
                        lambda *_args, **_kwargs: dict(_formal_state()))
    monkeypatch.setattr(activation, "exchange",
                        lambda *_args, **_kwargs:
                        _response(_control("fresh-secret")))

    handlers = panel.PanelHandlers(
        layout, [], restart_poller=lambda: {"ok": False, "reason": "poller boom"})
    result = handlers.control_refresh("ABCD1234")

    assert result["control_written"] is True
    assert result["poller_restarted"] is False
    assert "接入服务重启失败" in result["reason"]
    assert "poller boom" in result["reason"]
    assert control_status.read_status(layout)["state"] == "pending"


def test_control_write_is_pending_until_first_successful_poll(
        tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    monkeypatch.setattr(activation, "fingerprint",
                        lambda: {"machine_id": "MACHINE-1"})
    monkeypatch.setattr(activation, "unified_license_state",
                        lambda *_args, **_kwargs: dict(_formal_state()))
    monkeypatch.setattr(activation, "exchange",
                        lambda *_args, **_kwargs:
                        _response(_control("fresh-secret")))

    result = activation.activate_with_code(layout, "ABCD1234")

    assert result["control_written"] is True
    assert control_status.read_status(layout)["state"] == "pending"
    assert panel.control_banner(layout)["state"] != "connected"

    config = agentpoll.AgentConfig(
        customer_id="c_123", token="fresh-secret",
        control_url="https://control.example.test",
        data_root=str(layout.data), single_root=True,
        device_id="d_456", binding_epoch=0)
    poller = agentpoll.AgentPoller(config,
                                   logger=logging.getLogger("test-1198-poll"))
    monkeypatch.setattr(agentpoll, "poll_once", lambda *_args, **_kwargs: None)

    poller.run_once()

    assert control_status.read_status(layout)["state"] == "connected"
    banner = panel.control_banner(layout)
    assert banner["state"] == "connected"
    assert banner["level"] == "ok"


def test_historical_tenant_poller_writes_shared_status_visible_to_panel(
        tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    _write_control(layout, "stale-secret")
    config = agentpoll.AgentConfig(
        customer_id="c_123", token="stale-secret",
        control_url="https://control.example.test",
        data_root=str(layout.data), single_root=False,
        device_id="d_456", binding_epoch=0)
    assert config.layout.root == Path(layout.data) / "customers" / "c_123"
    poller = agentpoll.AgentPoller(
        config, logger=logging.getLogger("test-1198-tenant"))

    def _unauthorized(*_args, **_kwargs):
        raise agentpoll.AuthError("HTTP 401")

    monkeypatch.setattr(agentpoll, "poll_once", _unauthorized)
    for _ in range(2):
        with pytest.raises(agentpoll.AuthError):
            poller.run_once()

    shared = Path(layout.data) / "control-status.json"
    tenant = Path(config.layout.root) / "control-status.json"
    assert shared.is_file()
    assert not tenant.exists()
    status = control_status.read_status(layout)
    assert status["state"] == "error"
    assert status["reason"] == "接入凭据失效"
    banner = panel.control_banner(layout)
    assert banner["state"] == "error"
    assert banner["state"] != "connected"
    assert "接入凭据失效" in banner["text"]
    assert "stale-secret" not in shared.read_text(encoding="utf-8")


def test_startup_config_error_writes_error_not_pending(tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    _write_control(layout, "stale-secret")
    _clear_env(monkeypatch)

    def _fail(*_args, **_kwargs):
        raise RuntimeError("bad config")

    monkeypatch.setattr(agentpoll.AgentConfig, "from_env", _fail)

    poller = main._start_agentpoll(layout, logging.getLogger("test-1198-config"))

    assert poller is None
    status = control_status.read_status(layout)
    assert status["state"] == "error"
    assert "bad config" in status["reason"]
    banner = panel.control_banner(layout)
    assert banner["state"] == "error"
    assert banner["state"] != "connected"


def test_restart_agentpoll_stops_old_then_starts_new(tmp_path):
    layout = _layout(tmp_path)
    old = _FakePoller()
    new = _FakePoller()
    slot = {"poller": old}
    order = []

    def _start(_layout, _logger):
        order.append("start")
        return new

    old_stop = old.stop

    def _stop():
        order.append("stop")
        old_stop()

    old.stop = _stop
    result = main._restart_agentpoll(
        layout, logging.getLogger("test-1198-restart"), slot, start_poller=_start)

    assert result["ok"] is True
    assert order == ["stop", "start"]
    assert old.stops == 1
    assert slot["poller"] is new


def test_restart_agentpoll_failure_writes_visible_error(tmp_path):
    layout = _layout(tmp_path)
    slot = {"poller": None}

    result = main._restart_agentpoll(
        layout, logging.getLogger("test-1198-restart-fail"), slot,
        start_poller=lambda *_args, **_kwargs: None)

    assert result["ok"] is False
    assert "接入服务未能重新启动" in result["reason"]
    status = control_status.read_status(layout)
    assert status["state"] == "error"
    assert panel.control_banner(layout)["state"] != "connected"
