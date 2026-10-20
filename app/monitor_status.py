"""Best-effort local runtime telemetry. Never infer running state from settings."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import socket
import time

from app.monitor_config import config_path, read_config

LOGGER = logging.getLogger(__name__)


def status_path():
    return Path(os.getenv('MONITOR_STATUS_PATH', str(config_path().with_name('monitor-status.json'))))


def stamp():
    return datetime.now(timezone.utc).isoformat()


class MonitorStatus:
    def __init__(self, settings, scheduler):
        self.data = {'pid': os.getpid(), 'host': socket.gethostname(), 'started_at': stamp(),
                     'state': 'starting', 'current_job': None,
                     'groups': list(settings.facebook_group_urls),
                     'marketplace_query': 'iPhone 17 Pro Max',
                     'scans': {job.name: {'interval_seconds': job.interval} for job in scheduler.jobs}}
        self.last_write = 0
        self.write()

    def write(self):
        try:
            self.data['heartbeat_at'] = stamp()
            self.data['rules'] = read_config()
            path = status_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f'.{os.getpid()}.tmp')
            temporary.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
            temporary.replace(path)
            self.last_write = time.monotonic()
        except (OSError, ValueError):
            LOGGER.warning('monitor_status_write_failed', exc_info=True)

    def groups_applied(self, urls, scheduler):
        self.data['groups'] = list(urls)
        self.data['groups_applied_at'] = stamp()
        previous = self.data['scans']
        self.data['scans'] = {job.name: previous.get(job.name, {'interval_seconds': job.interval})
                              for job in scheduler.jobs}
        self.write()

    def pulse(self):
        if time.monotonic() - self.last_write >= 10:
            self.write()

    def begin(self, source):
        self.data.update(state='running', current_job=source)
        self.write()

    def finish(self, source, outcome, elapsed, error=None):
        self.data['scans'][source].update(last_finished_at=stamp(), outcome=outcome,
                                           elapsed_seconds=round(elapsed, 1), error=error)
        self.data['current_job'] = None
        self.write()

    def stop(self):
        self.data.update(state='stopped', current_job=None)
        self.write()


@contextmanager
def report_status(settings, scheduler):
    reporter = MonitorStatus(settings, scheduler)
    try:
        yield reporter
    finally:
        reporter.stop()


def read_status():
    path = status_path()
    if not path.exists():
        return {'state': 'unknown', 'message': '尚未收到監控回報。請啟動或更新常駐監控程式。'}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(data['heartbeat_at'])).total_seconds()
        alive = False
        if data['host'] == socket.gethostname():
            try:
                os.kill(data['pid'], 0)
                alive = True
            except ProcessLookupError:
                pass
            except PermissionError:
                alive = True
        if data['state'] != 'stopped' and (not alive or age > 120):
            data['state'] = 'stale'
        from app.group_names import read_names
        data['group_names'] = read_names()
        data['heartbeat_age_seconds'] = round(age)
        configured = read_config()
        data['pending_changes'] = configured != data.get('rules') or (
            configured is not None and [g['url'] for g in configured['groups']] != data['groups'])
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return {'state': 'unknown', 'message': '無法讀取監控回報，請檢查監控程序與設定檔。'}
