import pytest

from app.config import load_settings
from app.cli import main


def test_lock_path_can_be_configured_in_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITOR_LOCK_PATH", "unused")
    monkeypatch.delenv("MONITOR_LOCK_PATH")
    config = tmp_path / ".env"
    config.write_text(f"MONITOR_LOCK_PATH={tmp_path / 'shared.lock'}\n")
    assert load_settings(config).monitor_lock_path == tmp_path / "shared.lock"


@pytest.mark.parametrize("key", ["MARKETPLACE_MAX_SCROLLS", "GROUPS_MAX_SCROLLS"])
def test_negative_scroll_limit_is_rejected(tmp_path, monkeypatch, key):
    monkeypatch.setenv(key, "-1")
    with pytest.raises(ValueError, match=key):
        load_settings(tmp_path / "missing.env")


def test_cli_configuration_error_returns_failure(monkeypatch, caplog):
    monkeypatch.setenv("GROUPS_MAX_SCROLLS", "not-a-number")
    assert main(["telegram"]) == 1
    assert "Invalid configuration" in caplog.text
