"""Shared, validated configuration for the local settings UI and collectors."""
from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def config_path() -> Path:
    return Path(os.getenv('MONITOR_CONFIG_PATH', 'data/monitor-settings.json'))


def validate(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError('設定格式不正確')
    query = data.get('marketplace_query', 'iPhone 17 Pro Max')
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValueError('Marketplace 搜尋關鍵字須為 1–120 字')
    groups, products = data.get('groups'), data.get('products')
    if not isinstance(groups, list) or not isinstance(products, list) or not groups:
        raise ValueError('請至少新增一個 Group，商品須為清單')
    if len(groups) > 100 or len(products) > 100:
        raise ValueError('Group 與商品各最多 100 項')
    clean_groups = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get('url'), str):
            raise ValueError('請輸入 Facebook Group 網址')
        url = group['url'].strip()
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc not in ('facebook.com', 'www.facebook.com', 'm.facebook.com') or not parsed.path.startswith('/groups/') or not parsed.path.split('/')[2]:
            raise ValueError('Group 網址須為 https://www.facebook.com/groups/群組ID')
        name = group.get('name', '')
        if not isinstance(name, str) or len(name) > 120:
            raise ValueError('群組名稱最多 120 字')
        canonical = 'https://www.facebook.com/groups/' + parsed.path.split('/')[2] + '/'
        if canonical not in [g['url'] for g in clean_groups]:
            clean_groups.append({'name': name.strip(), 'url': canonical})
    clean_products = []
    for product in products:
        if not isinstance(product, dict):
            raise ValueError('商品格式不正確')
        keyword, price = product.get('keyword'), product.get('max_price')
        if not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 120:
            raise ValueError('商品關鍵字須為 1–120 字')
        if type(price) is not int or not 0 < price <= 100000000:
            raise ValueError('價格須為 1–100,000,000 元的整數')
        clean_products.append({'keyword': keyword.strip(), 'max_price': price})
    return {'groups': clean_groups, 'products': clean_products, 'marketplace_query': query.strip()}


def read_config() -> dict | None:
    path = config_path()
    return validate(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else None


def save_config(data: object) -> dict:
    value = validate(data)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)
    return value


def marketplace_query():
    config = read_config()
    return config['marketplace_query'] if config else 'iPhone 17 Pro Max'
