import pytest
from playwright.sync_api import sync_playwright
from app.collectors.groups.playwright_client import snapshot, post_from_article


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_missing_message_marker_preserves_post_excludes_comments(page):
    page.set_content('''<div role="article">
      <a href="https://www.facebook.com/groups/123/posts/456/">2小時前</a>
      <div>iPhone 17 Pro Max 512G 竹北 售價36000 附手機殼</div>
      <div role="article">留言：256G 售價10000</div>
      <div role="textbox">留言輸入框</div>
    </div>''')
    records = snapshot(page)
    assert len(records) == 1
    assert records[0]['extraction'] == 'fallback'
    assert '512G' in records[0]['text']
    assert '256G' not in records[0]['text']
    assert post_from_article(records[0]['text'], records[0]['href']) is not None


def test_message_marker_preferred_and_non_posts_ignored(page):
    page.set_content('''<div role="feed"><div role="article">
      <a href="https://www.facebook.com/groups/123/posts/456/">1小時前</a>
      <div data-ad-preview="message">iPhone 17 Pro Max 256G 中壢 售31000</div>
      <div>其他區塊 512G</div>
    </div><div role="article">推薦社團</div></div>''')
    records = snapshot(page)
    assert records[0]['extraction'] == 'message'
    assert '512G' not in records[0]['text']
    assert post_from_article(records[1]['text'], records[1]['href']) is None
