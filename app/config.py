from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    marketplace_location: str
    marketplace_radius_km: int
    log_level: str
    facebook_profile_dir: Path
    facebook_headless: bool
    marketplace_max_scrolls: int
    facebook_group_urls: tuple[str, ...]
    groups_max_scrolls: int
    telegram_bot_token: str | None
    telegram_chat_id: str | None


def load_settings(env_path: Path = Path(".env")) -> Settings:
    _load_dotenv(env_path)
    return Settings(
        database_path=Path(os.getenv("DATABASE_PATH", "data/facebook_monitor.db")),
        marketplace_location=os.getenv("MARKETPLACE_LOCATION", "Taiwan"),
        marketplace_radius_km=int(os.getenv("MARKETPLACE_RADIUS_KM", "200")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        facebook_profile_dir=Path(os.getenv("FACEBOOK_PROFILE_DIR", ".facebook-profile")),
        facebook_headless=os.getenv("FACEBOOK_HEADLESS", "false").casefold() in {"1", "true", "yes"},
        marketplace_max_scrolls=int(os.getenv("MARKETPLACE_MAX_SCROLLS", "3")),
        facebook_group_urls=tuple(
            url.strip()
            for url in os.getenv("FACEBOOK_GROUP_URLS", "").split(",")
            if url.strip()
        ),
        groups_max_scrolls=int(os.getenv("GROUPS_MAX_SCROLLS", "3")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
    )
