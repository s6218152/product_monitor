from datetime import datetime, timezone

from app.collectors.groups.playwright_client import post_from_article


def test_post_from_group_article() -> None:
    post = post_from_article(
        "iPhone 17 Pro Max 512G 桃園市 售 36,000",
        "https://www.facebook.com/groups/222470061618509/posts/987654321/?ref=share",
        author="王小明",
        timestamp="1791417600",
    )
    assert post is not None
    assert post.source_id == "987654321"
    assert post.group_id == "222470061618509"
    assert post.url == "https://www.facebook.com/groups/222470061618509/posts/987654321"
    assert post.author == "王小明"
    assert post.created_at == datetime.fromtimestamp(1791417600, timezone.utc)


def test_post_from_permalink_with_relative_time() -> None:
    now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    post = post_from_article(
        "iPhone17ProMax 256G 新竹市 31000",
        "/groups/apple1919/permalink/12345/",
        time_label="2小時前",
        now=now,
    )
    assert post is not None
    assert post.group_id == "apple1919"
    assert post.created_at == datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)


def test_non_post_article_is_ignored() -> None:
    assert post_from_article("group header", "/groups/123/") is None
