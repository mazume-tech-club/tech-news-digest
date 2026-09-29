#!/usr/bin/env python3
"""feeds.yml の検証。PR 時に実行される。

- 構文・必須項目・category/lang の妥当性・URL/名前の重複チェック(失敗でエラー)
- 各URLに実際にアクセスして取得できるか確認(失敗は警告。サイト側の一時障害で PR を止めないため)
"""
import sys
from urllib.parse import urlparse

import feedparser
import requests
import yaml

with open('feeds.yml', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

errors, warnings = [], []
cats = {c['id'] for c in cfg.get('categories', [])}
seen_url, seen_name = {}, {}

for i, feed in enumerate(cfg.get('feeds', []), 1):
    label = f"#{i} {feed.get('name', '?')}"
    for k in ('name', 'url', 'category'):
        if not feed.get(k):
            errors.append(f'{label}: 必須項目 {k} がありません')
    if feed.get('category') and feed['category'] not in cats:
        errors.append(f"{label}: category '{feed['category']}' は未定義 (使用可能: {', '.join(sorted(cats))})")
    if feed.get('likes') not in (None, 'zenn', 'qiita'):
        errors.append(f"{label}: likes は zenn か qiita")
    if feed.get('lang', 'ja') not in ('ja', 'en'):
        errors.append(f"{label}: lang は ja か en")
    url = feed.get('url', '')
    if urlparse(url).scheme not in ('http', 'https'):
        errors.append(f'{label}: URL は http(s) のみ')
    if url in seen_url:
        errors.append(f'{label}: URL が {seen_url[url]} と重複しています')
    seen_url[url] = label
    if feed.get('name') in seen_name:
        errors.append(f'{label}: name が {seen_name[feed["name"]]} と重複しています')
    seen_name[feed.get('name')] = label

if not errors:
    for feed in cfg['feeds']:
        if feed.get('enabled', True) is False:
            continue
        try:
            r = requests.get(feed['url'], headers={'User-Agent': 'TechNewsDigest-validate'}, timeout=20)
            r.raise_for_status()
            p = feedparser.parse(r.content)
            if not p.entries:
                warnings.append(f"{feed['name']}: 記事を取得できませんでした ({feed['url']})")
        except Exception as e:
            warnings.append(f"{feed['name']}: アクセス失敗 {type(e).__name__} ({feed['url']})")

for w in warnings:
    print(f'::warning::{w}')
for e in errors:
    print(f'::error::{e}')
print(f'feeds: {len(cfg.get("feeds", []))} / errors: {len(errors)} / warnings: {len(warnings)}')
sys.exit(1 if errors else 0)
