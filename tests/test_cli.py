from pathlib import Path

import app.cli as cli

from app.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


def test_marketplace_cli_reports_new_and_existing(tmp_path: Path, capsys: object) -> None:
    args = ["marketplace", "--fixture", str(FIXTURES / "marketplace_iphone17_pro_max.json"), "--database", str(tmp_path / "db.sqlite")]
    assert main(args) == 0
    assert "Found 2 listings\nNew: 2\nExisting: 0" in capsys.readouterr().out  # type: ignore[attr-defined]
    assert main(args) == 0
    assert "Found 2 listings\nNew: 0\nExisting: 2" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_groups_cli_filters_wanted_posts(tmp_path: Path, capsys: object) -> None:
    result = main(["groups", "--fixture", str(FIXTURES / "group_iphone.json"), "--database", str(tmp_path / "db.sqlite")])
    assert result == 0
    assert "Found 2 listings\nNew: 2\nExisting: 0" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_telegram_cli(tmp_path: Path, capsys: object) -> None:
    database = tmp_path / "db.sqlite"
    main(["marketplace", "--fixture", str(FIXTURES / "marketplace_iphone17_pro_max.json"), "--database", str(database)])
    capsys.readouterr()  # type: ignore[attr-defined]
    assert main(["telegram", "--database", str(database), "--limit", "1"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "🔔 <b>iPhone 17 Pro Max 商品</b>" in output
    assert "🕒 上架：2026/10/05 08:30" in output


def test_telegram_send_marks_each_listing_once(
    tmp_path: Path, capsys: object, monkeypatch: object
) -> None:
    database = tmp_path / "db.sqlite"
    main(["marketplace", "--fixture", str(FIXTURES / "marketplace_iphone17_pro_max.json"), "--database", str(database)])
    capsys.readouterr()  # type: ignore[attr-defined]
    sent: list[str] = []

    def fake_send(_token: str, _chat_id: str, message: str) -> int:
        sent.append(message)
        return 1

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")  # type: ignore[attr-defined]
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "send_html", fake_send)  # type: ignore[attr-defined]

    args = ["telegram", "--database", str(database), "--limit", "10", "--send"]
    assert main(args) == 0
    assert len(sent) == 2
    assert "Sent 2 listing(s)" in capsys.readouterr().out  # type: ignore[attr-defined]
    assert main(args) == 0
    assert len(sent) == 2
    assert "No new Telegram listings" in capsys.readouterr().out  # type: ignore[attr-defined]
