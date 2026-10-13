"""Run all sources and notifications under a shared lock with bounded time."""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.runtime import monitor_lock
from app.config import load_settings


def run_command(command: list[str], timeout: float) -> int:
    process = subprocess.Popen(command, cwd=PROJECT_DIR, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        # Chromium children can survive their Python parent. Always kill the
        # remaining process group before letting another source use the profile.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        return 124


def main() -> int:
    os.chdir(PROJECT_DIR)
    settings = load_settings()
    with monitor_lock(settings.monitor_lock_path) as acquired:
        if not acquired:
            print("monitor_skipped reason=lock_busy", flush=True)
            return 0
        start = time.monotonic()
        status = 0
        for source, arguments, timeout in (
            ("groups", ["--live"], 420),
            ("marketplace", ["--live"], 420),
            ("telegram", ["--limit", "30", "--send"], 90),
        ):
            try:
                code = run_command([sys.executable, str(PROJECT_DIR / "main.py"), source, *arguments], timeout)
            except OSError as error:
                print(f"source={source} error={error}", flush=True)
                code = 1
            print(f"source={source} exit={code}", flush=True)
            if code != 0:
                status = 1
        print(f"run_completed elapsed={time.monotonic() - start:.1f}s status={status}", flush=True)
        return status


if __name__ == "__main__":
    raise SystemExit(main())
