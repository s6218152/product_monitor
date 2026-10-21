"""Run in the VM desktop terminal to restore the dedicated Facebook session."""
from pathlib import Path
import os
import signal
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from app.config import load_settings
from app.runtime import monitor_lock
from app.collectors.marketplace.playwright_client import PlaywrightMarketplaceCollector


def main():
    os.chdir(PROJECT)
    pause = PROJECT / 'data/fast_monitor.pause'
    pid_file = PROJECT / 'data/fast_monitor.pid'
    pause.parent.mkdir(parents=True, exist_ok=True)
    pause.touch()
    try:
        settings = load_settings()
        if pid_file.exists():
            pid = int(pid_file.read_text())
            proc = Path(f'/proc/{pid}')
            if proc.exists():
                args = (proc/'cmdline').read_bytes().split(b'\0')
                if proc.stat().st_uid != os.getuid() or b'run' not in args or not any(
                    Path(os.fsdecode(arg)).name == 'fast_supervisor.py' for arg in args if arg
                ):
                    raise RuntimeError('PID does not belong to this monitor; no process stopped')
                os.kill(pid, signal.SIGTERM)
                deadline = time.monotonic() + 45
                while proc.exists() and time.monotonic() < deadline:
                    time.sleep(.5)
                if proc.exists():
                    raise RuntimeError('Monitor did not stop; browser was not opened')
        with monitor_lock(settings.monitor_lock_path) as acquired:
            if not acquired:
                raise RuntimeError('Profile is in use; browser was not opened')
            PlaywrightMarketplaceCollector(settings.facebook_profile_dir).login()
        print('登入流程已結束，Cron 將自動恢復監控；請在管理頁確認登入狀態。')
        return 0
    finally:
        pause.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
