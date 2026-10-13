"""Monthly maintenance, protected by the same lock as the collector."""
import shutil
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import load_settings
from app.database.repository import ListingRepository
from app.runtime import monitor_lock


def main() -> int:
    os.chdir(Path(__file__).resolve().parents[1])
    settings = load_settings()
    with monitor_lock(settings.monitor_lock_path) as acquired:
        if not acquired:
            print("maintenance_skipped reason=lock_busy")
            return 0
        with ListingRepository(settings.database_path) as repository:
            print(f"pruned_notified_records={repository.prune(90)} retention_days=90")
        profile = settings.facebook_profile_dir.resolve()
        for name in ("Cache", "Code Cache", "GPUCache"):
            target = profile / "Default" / name
            if target.is_dir() and not target.is_symlink() and target.resolve().is_relative_to(profile):
                shutil.rmtree(target)
                print(f"removed_cache={name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
