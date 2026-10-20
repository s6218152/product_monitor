import json
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from app.fast_monitor import Scheduler
from app.monitor_status import MonitorStatus, read_status, report_status, status_path
from app.monitor_config import save_config


def setup_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('MONITOR_CONFIG_PATH', str(tmp_path/'settings.json'))
    monkeypatch.setenv('MONITOR_STATUS_PATH', str(tmp_path/'status.json'))
    return SimpleNamespace(facebook_group_urls=('https://www.facebook.com/groups/123/',))


def test_no_report_is_unknown(tmp_path, monkeypatch):
    setup_paths(tmp_path, monkeypatch)
    assert read_status()['state'] == 'unknown'


def test_runtime_reports_actual_groups_and_scan_result(tmp_path, monkeypatch):
    settings = setup_paths(tmp_path, monkeypatch)
    reporter = MonitorStatus(settings, Scheduler(settings.facebook_group_urls))
    reporter.begin('marketplace')
    assert read_status()['state'] == 'running'
    reporter.finish('marketplace', 'failed', 2.5, 'TimeoutError')
    value = read_status()
    assert value['scans']['marketplace']['outcome'] == 'failed'
    assert value['scans']['marketplace']['error'] == 'TimeoutError'
    assert value['groups'] == list(settings.facebook_group_urls)
    save_config({'groups': [{'url': 'https://www.facebook.com/groups/456/'}], 'products': [{'keyword': '相機', 'max_price': 5000}]})
    assert read_status()['pending_changes']
    reporter.pulse()
    reporter.stop()
    assert read_status()['state'] == 'stopped'


def test_old_heartbeat_is_stale(tmp_path, monkeypatch):
    settings = setup_paths(tmp_path, monkeypatch)
    reporter = MonitorStatus(settings, Scheduler([]))
    reporter.begin('marketplace')
    data = reporter.data.copy()
    data['heartbeat_at'] = (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    status_path().write_text(json.dumps(data))
    assert read_status()['state'] == 'stale'


def test_failure_marks_report_stopped(tmp_path, monkeypatch):
    settings = setup_paths(tmp_path, monkeypatch)
    import pytest
    with pytest.raises(RuntimeError):
        with report_status(settings, Scheduler([])):
            raise RuntimeError('startup failed')
    assert read_status()['state'] == 'stopped'
