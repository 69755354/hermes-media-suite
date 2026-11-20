"""1.2.224: the panel's consent switch must reach the gate that reads it.

Regression: the panel writes the remote-assist switch through the base layout
(``<data>/config/settings.json``) while the poller is scoped to one tenant
(``<data>/customers/<id>/config/settings.json``).  The gate read the scoped
copy only, so turning 远程协助 on in the panel did nothing and every operator
command stayed blocked.
"""
import json
import time
from pathlib import Path

from agent.winport import remote_policy
from agent.winport.paths import Layout


def _base_layout(tmp_path):
    return Layout(program=tmp_path / "prog", data=tmp_path)


def _scoped_layout(tmp_path):
    root = tmp_path / "customers" / "c_test"
    root.mkdir(parents=True, exist_ok=True)
    return Layout(program=tmp_path / "prog", data=root)


def test_panel_switch_is_visible_to_the_scoped_poller(tmp_path):
    base = _base_layout(tmp_path)
    scoped = _scoped_layout(tmp_path)
    base.config.mkdir(parents=True, exist_ok=True)
    base.settings_file.write_text(json.dumps(
        {"remote_assist": {"enabled": True, "until": time.time() + 3600}}),
        encoding="utf-8")

    state = remote_policy.assist_state(scoped)
    assert state["active"] is True, state
    assert state["remaining_s"] > 0


def test_panel_toggle_written_through_scoped_layout_lands_on_the_machine(tmp_path):
    scoped = _scoped_layout(tmp_path)
    base = _base_layout(tmp_path)
    base.config.mkdir(parents=True, exist_ok=True)
    base.settings_file.write_text("{}", encoding="utf-8")

    state = remote_policy.set_assist(scoped, True, hours=2, actor="panel")
    assert state["active"] is True, state

    written = json.loads(base.settings_file.read_text(encoding="utf-8"))
    assert written["remote_assist"]["enabled"] is True
    assert not scoped.settings_file.exists(), "consent must not be tenant-local"


def test_real_layout_switch_stays_on_the_machine(tmp_path):
    base = _base_layout(tmp_path)
    base.config.mkdir(parents=True, exist_ok=True)
    base.settings_file.write_text("{}", encoding="utf-8")
    state = remote_policy.set_assist(base, True, hours=1, actor="panel")
    assert state["active"] is True
    assert remote_policy.assist_state(base)["active"] is True
    remote_policy.set_assist(base, False)
    assert remote_policy.assist_state(base)["active"] is False
