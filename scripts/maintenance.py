"""Monthly maintenance, run under the same flock as the collector."""
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import load_settings
from app.database.repository import ListingRepository

settings = load_settings()
with ListingRepository(settings.database_path) as repository:
    print(f"pruned_notified_records={repository.prune(90)} retention_days=90")
for name in ("Cache", "Code Cache", "GPUCache"):
    target = settings.facebook_profile_dir / "Default" / name
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
        print(f"removed_cache={name}")
