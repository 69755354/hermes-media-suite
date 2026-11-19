"""1.2.223: control-plane ops must not receive the poller's CustomerLayout.

Regression: agentpoll set ``config.layout = CustomerLayout(...)``; remote_agent
passed it straight into remote_policy / named_ops, which read ``layout.data``.
Every read/ls/write and every data-backed named op then died with
``AttributeError: 'CustomerLayout' object has no attribute 'data'``.
"""
from pathlib import Path

from agent.winport import remote_agent
from agent.winport.customer_paths import CustomerLayout
from agent.winport.paths import Layout


class _Cfg:
    def __init__(self, layout):
        self.layout = layout


def _customer_layout(tmp_path):
    return CustomerLayout(data_root=tmp_path, customer_id="c_test", scoped=True)


def test_poller_layout_is_converted_to_worker_layout(tmp_path):
    cfg = _Cfg(_customer_layout(tmp_path))
    layout = remote_agent._policy_layout(cfg)
    assert isinstance(layout, Layout)
    assert layout.data == Path(cfg.layout.root), (layout.data, cfg.layout.root)
    assert layout.program and Path(layout.program).is_dir()


def test_worker_layout_passes_through_unchanged():
    worker = Layout()
    assert remote_agent._policy_layout(_Cfg(worker)) is worker
    assert remote_agent._policy_layout(None).data


def test_inbox_scan_runs_on_control_plane_config(tmp_path):
    cfg = _Cfg(_customer_layout(tmp_path))
    layout = remote_agent._policy_layout(cfg)
    (Path(layout.data) / "inbox").mkdir(parents=True, exist_ok=True)
    (Path(layout.data) / "inbox" / "a.mp4").write_bytes(b"x")
    result = remote_agent.execute(
        "named", {"name": "inbox-scan", "args": {}}, config=cfg)
    assert result.get("ok") is True, result
