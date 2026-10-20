"""Names discovered using the monitor's existing authenticated browser."""
import json
import logging
import re
from app.monitor_config import config_path
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)


def group_key(url):
    return urlsplit(url).path.strip('/').split('/')[1]


def names_path():
    return config_path().with_name('group-names.json')


def read_names():
    try:
        value = json.loads(names_path().read_text(encoding='utf-8'))
        return {key: name for key, name in value.items() if isinstance(name, str) and clean_name(name)} if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def clean_name(text):
    text = re.sub(r'^\s*\(\d+\)\s*', '', text or '')
    text = re.sub(r'\s*[|–—-]\s*Facebook\s*$', '', text, flags=re.I).strip()
    if not text or len(text) > 200 or text.casefold() in {'facebook', 'groups', '社團', '通知', 'notifications', 'notification', '動態消息', 'news feed', '首頁', 'home', 'facebook通知', 'facebook notifications', '登入 facebook', 'log into facebook', '登入或註冊', 'log in or sign up'}:
        return None
    if any(word in text.casefold() for word in ('此內容目前無法', 'content isn\'t available', 'content is not available', 'access denied', '無法查看此內容')):
        return None
    return text


def capture_name(page, url):
    try:
        if group_key(page.url) != group_key(url):
            return None
        candidates = page.evaluate('''() => {
            const key = location.pathname.split('/').filter(Boolean)[1];
            const headings = Array.from(document.querySelectorAll('[role="main"] h1, [role="main"] h2, main h1, main h2'))
                .filter(node => node.getClientRects().length && !node.closest('[role="dialog"], [role="navigation"], nav'));
            const groupHeadings = headings.filter(node => Array.from(node.querySelectorAll('a[href]')).some(link => {
                const parts = new URL(link.href, location.href).pathname.split('/').filter(Boolean);
                return parts.length === 2 && parts[0] === 'groups' && parts[1] === key;
            })).map(node => node.textContent);
            return [document.querySelector('meta[property="og:title"]')?.content,
                    document.title, ...groupHeadings];
        }''')
        for candidate in candidates:
            name = clean_name(candidate)
            if name:
                names = read_names()
                key = group_key(url)
                if names.get(key) != name:
                    names[key] = name
                    path = names_path()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(names, ensure_ascii=False), encoding='utf-8')
                    temporary.replace(path)
                return name
    except Exception:
        LOGGER.warning('group_name_capture_failed url=%s', url, exc_info=True)
    return None
