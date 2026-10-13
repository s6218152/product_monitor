import fcntl
import subprocess
import sys

from app.runtime import monitor_lock
from scripts import run_monitor


def test_lock_excludes_other_processes(tmp_path):
    lock = tmp_path / "monitor.lock"
    with monitor_lock(lock) as acquired:
        assert acquired
        result = subprocess.run([
            sys.executable, "-c",
            "from pathlib import Path; from app.runtime import monitor_lock; "
            "ctx=monitor_lock(Path(__import__('sys').argv[1])); "
            "print(ctx.__enter__())",
            str(lock),
        ], capture_output=True, text=True, check=True)
        assert result.stdout.strip() == "False"
    with monitor_lock(lock) as acquired:
        assert acquired


def test_lock_reuses_inherited_flock_descriptor(tmp_path):
    lock = tmp_path / "monitor.lock"
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([
            sys.executable, "-c",
            "from pathlib import Path; from app.runtime import monitor_lock; "
            "ctx=monitor_lock(Path(__import__('sys').argv[1])); "
            "print(ctx.__enter__())",
            str(lock),
        ], pass_fds=(handle.fileno(),), capture_output=True, text=True, check=True)
        assert result.stdout.strip() == "True"


def test_runner_continues_after_failed_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITOR_LOCK_PATH", str(tmp_path / "monitor.lock"))
    calls = []

    def run(command, timeout):
        calls.append((command, timeout))
        return 124 if "groups" in command else 0

    monkeypatch.setattr(run_monitor, "run_command", run)
    assert run_monitor.main() == 1
    assert [call[0][2] for call in calls] == ["groups", "marketplace", "telegram"]
    assert [call[1] for call in calls] == [420, 420, 90]


def test_runner_timeout_stops_process_group():
    assert run_monitor.run_command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.05) == 124
