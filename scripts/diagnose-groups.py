"""Read-only DOM metadata; never print post text, cookies or HTML."""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import load_settings
from app.collectors.groups.playwright_client import snapshot
from playwright.sync_api import sync_playwright


def inspect(page):
    metadata = page.evaluate(r"""() => {
        const articles = [...document.querySelectorAll('[role="article"]')];
        const lengths = el => ({chars: (el.innerText || '').length,
            links: el.querySelectorAll('a[href]').length,
            nestedArticles: el.querySelectorAll('[role="article"]').length,
            messages: el.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"]').length});
        const kinds = {};
        for (const a of document.querySelectorAll('a[href]')) {
            const u = new URL(a.href, location.href);
            let kind = null;
            if (/\/groups\/[^/]+\/(posts|permalink)\//.test(u.pathname)) kind = 'group_post';
            else if (u.searchParams.has('multi_permalinks')) kind = 'multi_permalinks';
            else if (u.pathname.includes('story.php')) kind = 'story_php';
            else if (u.pathname.includes('/groups/')) kind = 'group_other';
            if (kind) kinds[kind] = (kinds[kind] || 0) + 1;
        }
        return {feeds: document.querySelectorAll('[role="feed"]').length,
            messageAncestors: [...document.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"]')].slice(0, 4).map(message => {
                const chain = [];
                let root = message;
                for (let depth = 0; root && depth < 20; depth++, root = root.parentElement) {
                    const links = [...root.querySelectorAll('a[href]')];
                    chain.push({depth, tag: root.tagName, role: root.getAttribute('role'),
                        linkShapes: depth === 4 ? links.slice(0, 12).map(a => {
                            const u = new URL(a.href, location.href);
                            return {path: u.pathname.replace(/\d+/g, ':id'), queryKeys: [...u.searchParams.keys()],
                                textChars: (a.innerText || '').length, hasAriaLabel: !!a.getAttribute('aria-label')};
                        }) : undefined,
                        messageCount: root.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"]').length,
                        nestedMessageCount: root.querySelectorAll('[data-ad-preview="message"] [data-ad-comet-preview="message"], [data-ad-comet-preview="message"] [data-ad-preview="message"]').length,
                        postLinks: links.filter(a => /\/groups\/[^/]+\/(posts|permalink)\/\d+/.test(a.href)).length,
                        chars: (root.innerText || '').length});
                    if (root === document.body) break;
                }
                return chain;
            }),
            articles: articles.length,
            topLevel: articles.filter(el => !el.parentElement.closest('[role="article"]')).map(lengths).slice(0, 15),
            allSamples: articles.map(lengths).slice(0, 15), linkKinds: kinds,
            messages: document.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"]').length,
            busy: document.querySelectorAll('[aria-busy="true"], [role="progressbar"]').length,
            loginInput: !!document.querySelector('input[name="email"]'),
            bodyChars: (document.body.innerText || '').length};
    }""")
    records = snapshot(page)
    metadata['parsedCandidates'] = len(records)
    metadata['candidatesWithText'] = sum(bool(r['text'].strip()) for r in records)
    metadata['candidatesWithLink'] = sum(bool(r['href']) for r in records)
    return metadata


def main():
    settings = load_settings()
    url = sys.argv[1] if len(sys.argv) > 1 else settings.facebook_group_urls[0]
    parts = urlsplit(url)
    if parts.hostname != 'www.facebook.com' or not parts.path.startswith('/groups/'):
        raise ValueError('Expected https://www.facebook.com/groups/...')
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(settings.facebook_profile_dir, headless=settings.facebook_headless, locale='zh-TW')
        try:
            page = context.new_page()
            for mode, target in [('plain', url), ('chronological', url.rstrip('/') + '/?sorting_setting=CHRONOLOGICAL')]:
                page.goto(target, wait_until='domcontentloaded', timeout=60000)
                for stage in ('initial', 'after_wait', 'after_scroll', 'after_hover'):
                    if stage == 'after_wait':
                        page.wait_for_timeout(15000)
                    elif stage == 'after_scroll':
                        page.mouse.wheel(0, 1800)
                        page.wait_for_timeout(5000)
                    elif stage == 'after_hover':
                        links = page.locator('[role="feed"] a[href*="/groups/"]')
                        for index in range(min(links.count(), 12)):
                            try:
                                links.nth(index).hover(timeout=1000)
                            except Exception:
                                pass
                        page.wait_for_timeout(1500)
                    print(json.dumps({'mode': mode, 'stage': stage, **inspect(page)}, ensure_ascii=False), flush=True)
        finally:
            context.close()


if __name__ == '__main__':
    main()
