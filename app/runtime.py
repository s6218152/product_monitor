"""Shared process lock for collectors and profile/database maintenance."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from collections.abc import Iterator


DEFAULT_LOCK_PATH = Path("/tmp/facebook-product-monitor.lock")


@contextmanager
def monitor_lock(path: Path | None = None) -> Iterator[bool]:
    path = path or Path(os.environ.get("MONITOR_LOCK_PATH", str(DEFAULT_LOCK_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a")
    lock_stat = os.fstat(handle.fileno())
    inherited_fd = None
    # Older cron entries may wrap us in flock. Reuse its inherited descriptor
    # instead of contending against our own parent process's lock.
    fd_directory = Path("/proc/self/fd") if Path("/proc/self/fd").is_dir() else Path("/dev/fd")
    for entry in fd_directory.iterdir():
        try:
            fd = int(entry.name)
            if fd < 3 or fd == handle.fileno():
                continue
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == (lock_stat.st_dev, lock_stat.st_ino):
                inherited_fd = fd
                break
        except (OSError, ValueError):
            continue
    lock_fd = inherited_fd if inherited_fd is not None else handle.fileno()
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            try:
                yield True
            finally:
                if inherited_fd is None:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        handle.close()
