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


def test_real_posts_outside_empty_article_placeholders(page):
    page.set_content('''<div role="feed">
      <div role="article"></div><div role="article"></div>
      <section><header><a href="https://www.facebook.com/groups/123/posts/456/">2小時前</a></header>
        <div><div data-ad-preview="message">iPhone 17 Pro Max 512G 竹北 售36000</div></div>
        <div role="article">留言 256G</div>
      </section>
      <section><a href="https://www.facebook.com/groups/123/posts/789/">1小時前</a>
        <div data-ad-comet-preview="message">iPhone 17 Pro Max 256G 中壢 售31000</div>
      </section>
    </div>''')
    records = snapshot(page)
    posts = [post_from_article(r['text'], r['href']) for r in records]
    posts = [p for p in posts if p]
    assert {p.source_id for p in posts} == {'456', '789'}
    assert all('留言' not in p.text for p in posts)


def test_never_pairs_body_with_neighbor_post_link(page):
    page.set_content('''<div role="feed"><section><div data-ad-preview="message">missing link</div></section>
      <section><a href="https://www.facebook.com/groups/123/posts/789/">time</a>
        <div data-ad-preview="message">second post</div></section></div>''')
    records = snapshot(page)
    assert len(records) == 1
    assert records[0]['text'] == 'second post'


def test_group_commerce_card_without_post_permalink(page):
    page.set_content('''<div role="feed"><section>
      <a href="https://www.facebook.com/groups/123/user/999/">author</a>
      <a href="https://www.facebook.com/commerce/listing/456/?media_id=7">商品</a>
      <div data-ad-preview="message">iPhone 17 Pro Max 512G 竹北 售36000</div>
    </section><div role="article"></div></div>''')
    from app.collectors.groups.playwright_client import has_usable_posts
    records = snapshot(page)
    assert has_usable_posts(records)
    record = records[0]
    post = post_from_article(record['text'], record['href'], group_id=record['groupId'])
    assert post is not None
    assert post.source_id == 'commerce:456'
    assert post.group_id == '123'
    assert post.url == 'https://www.facebook.com/commerce/listing/456'


def test_nested_comment_message_cannot_replace_post_body(page):
    page.set_content('''<div role="feed"><div role="article">
      <a href="https://www.facebook.com/groups/123/posts/456/">2小時前</a>
      <div>actual content 512G</div>
      <div role="article"><div data-ad-preview="message">comment content 256G</div></div>
    </div></div>''')
    records = snapshot(page)
    assert len(records) == 1
    assert records[0]['href'].endswith('/posts/456/')
    assert 'actual content 512G' in records[0]['text']
    assert 'comment content 256G' not in records[0]['text']


def test_nested_quote_cannot_supply_parent_permalink_or_time(page):
    page.set_content('''<div role="feed"><div role="article">
      <div role="article"><a href="https://www.facebook.com/groups/123/posts/999/">3天前</a>
        <time datetime="2026-09-01T00:00:00Z"></time>
        <div data-ad-preview="message">quoted content 256G</div></div>
      <a href="https://www.facebook.com/groups/123/posts/456/">1小時前</a>
      <time datetime="2026-10-13T00:00:00Z"></time>
      <div data-ad-preview="message">actual content 512G</div>
    </div></div>''')
    records = snapshot(page)
    assert len(records) == 1
    assert records[0]['text'] == 'actual content 512G'
    assert records[0]['href'].endswith('/posts/456/')
    assert records[0]['timeLabel'] == '1小時前'
    assert records[0]['timestamp'] == '2026-10-13T00:00:00Z'


def test_commerce_title_and_author_body_both_used_for_filtering(page):
    page.set_content('''<div role="feed"><section>
      <a href="https://www.facebook.com/groups/625327679762262/permalink/1439020191726336/">1小時前</a>
      <div data-ad-preview="message">【顏色】：白色 【售價】：32000 【交易地點及方式】：新竹縣竹北市</div>
      <a href="https://www.facebook.com/commerce/listing/1786160482330710/?ref=share_attachment">NT$32,000 竹北市, 新竹縣 iPhone 17 pro max 256GB 白色</a>
      <div role="article"><a href="https://www.facebook.com/commerce/listing/999/">512GB 10000</a></div>
    </section></div>''')
    from app.products.normalizer import normalize_group
    from app.products.target_filter import rejection_reason
    record = next(r for r in snapshot(page) if r['href'])
    post = post_from_article(record['text'], record['href'])
    assert post is not None
    listing = normalize_group(post)
    assert listing.price == 32000
    assert listing.location == '新竹縣'
    assert '512GB' not in listing.description
    assert rejection_reason(listing.description, listing.price, listing.location) is None
