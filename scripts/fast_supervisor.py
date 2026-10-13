"""Unprivileged cron supervisor, with coordinated monthly maintenance."""
from pathlib import Path
import os
import signal
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from app.config import load_settings
from app.runtime import monitor_lock

PID = PROJECT / 'data/fast_monitor.pid'
PAUSE = PROJECT / 'data/fast_monitor.pause'


def run():
    os.chdir(PROJECT)
    if PAUSE.exists():
        return 0
    settings = load_settings()
    with monitor_lock(settings.monitor_lock_path) as acquired:
        if not acquired or PAUSE.exists():
            return 0
        PID.parent.mkdir(parents=True, exist_ok=True)
        PID.write_text(str(os.getpid()))
        try:
            from scripts.fast_monitor import main
            return main()
        finally:
            PID.unlink(missing_ok=True)


def maintain():
    os.chdir(PROJECT)
    PAUSE.parent.mkdir(parents=True, exist_ok=True)
    PAUSE.touch()
    try:
        if PID.exists():
            pid = int(PID.read_text())
            proc = Path(f'/proc/{pid}')
            # Never signal a reused PID or another user's process.
            if proc.exists() and proc.stat().st_uid == os.getuid():
                args = (proc/'cmdline').read_bytes().split(b'\0')
                if any(Path(os.fsdecode(arg)).name == 'fast_supervisor.py' for arg in args if arg) and b'run' in args:
                    os.kill(pid, signal.SIGTERM)
        settings = load_settings()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            with monitor_lock(settings.monitor_lock_path) as acquired:
                if acquired:
                    from scripts.maintenance import main
                    return main()
            time.sleep(1)
        raise RuntimeError('Maintenance lock timeout; nothing cleaned')
    finally:
        PAUSE.unlink(missing_ok=True)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if mode not in ('run', 'maintain'):
        raise SystemExit('Expected run or maintain')
    raise SystemExit(run() if mode == 'run' else maintain())
