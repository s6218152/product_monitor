"""Keep fixture tests independent of an operator's saved runtime settings."""
import pytest


@pytest.fixture(autouse=True)
def isolated_monitor_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'monitor-settings.json'))
    monkeypatch.setenv('MONITOR_STATUS_PATH', str(tmp_path/'monitor-status.json'))
