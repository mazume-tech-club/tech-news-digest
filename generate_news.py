#!/usr/bin/env python3
"""
Tech News Digest — GitHub Actions 版

feeds.yml に列挙した RSS/Atom を収集 → 英語タイトルを日本語へ翻訳 →
JEV API(未設定時はキーワード)で重要度判定 → カテゴリ別・重要度順の静的HTMLを生成する。

出力:
  dist/index.html                  最新版
  dist/YYYY/MM/YYYY-MM-DD.html     日別アーカイブ
  dist/archive/index.html          アーカイブ一覧
"""

import html as HL
import os
import re
import shutil
import sys
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import feedparser
import requests
import yaml

from jev_client import score_items
from render import build_html, build_archive_index

UA = 'Mozilla/5.0 (compatible; TechNewsDigest/3.0; +https://github.com/mazume-tech-club/tech-news-digest)'
JST = timezone(timedelta(hours=9))
FEEDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'feeds.yml')
TRANSLATE = os.environ.get('TRANSLATE', '1') != '0'
CJK = re.compile(r'[぀-ヿ㐀-鿿]')


# ── Config ────────────────────────────────────────────────────────────────────

def load_config(path=FEEDS_FILE):
    with open(path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    settings = {'lookback_hours': 72, 'max_items_per_feed': 10, 'show_per_category': 20}
    settings.update(cfg.get('settings') or {})
    return settings, cfg['categories'], [f for f in cfg['feeds'] if f.get('enabled', True)]


# ── Fetch ─────────────────────────────────────────────────────────────────────

def _entry_time(e):
    for key in ('published_parsed', 'updated_parsed'):
        t = e.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def _clean(text, limit=200):
    text = re.sub(r'<[^>]+>', '', text or '')
    return HL.unescape(re.sub(r'\s+', ' ', text)).strip()[:limit]


def fetch_feed(feed, settings):
    """1フィードを取得し (items, error) を返す。失敗しても全体は止めない。"""
    try:
        resp = requests.get(feed['url'], headers={'User-Agent': UA}, timeout=20)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if not parsed.entries and parsed.bozo:
            raise ValueError(f'parse error: {parsed.bozo_exception}')
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings['lookback_hours'])
        limit = feed.get('max_items', settings['max_items_per_feed'])
        items = []
        for e in parsed.entries:
            title, link = _clean(e.get('title'), 300), e.get('link')
            if not title or not link:
                continue
            ts = _entry_time(e)
            if ts and ts < cutoff:
                continue
            items.append({
                'title': title, 'url': link, 'summary': _clean(e.get('summary') or e.get('description')),
                'published': ts, 'source': feed['name'], 'category': feed['category'],
                'lang': feed.get('lang', 'ja'), 'likes_src': feed.get('likes'),
            })
        items.sort(key=lambda x: x['published'] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:limit], None
    except Exception as e:
        return [], f'{type(e).__name__}: {e}'


def fetch_all(feeds, settings):
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda f: fetch_feed(f, settings), feeds))
    items, report, seen = [], [], set()
    for feed, (got, err) in zip(feeds, results):
        report.append((feed['name'], len(got), err))
        print(f"  {'✗' if err else '✓'} {feed['name']}: {len(got)}件" + (f'  [{err}]' if err else ''))
        for it in got:
            if it['url'] not in seen:  # 複数フィードの重複記事を除去
                seen.add(it['url'])
                items.append(it)
    return items, report


# ── Likes(いいね数) ──────────────────────────────────────────────────────────
# RSS にはいいね数がないため、feeds.yml で `likes: zenn|qiita` を付けたフィードの記事だけ、
# 各サイトの公開APIから取得する(失敗した記事は likes=None のまま)。

_ZENN_RE = re.compile(r'https://zenn\.dev/[^/]+/articles/([^/?#]+)')
_QIITA_RE = re.compile(r'https://qiita\.com/[^/]+/items/([0-9a-f]+)')


def fetch_likes(item):
    src, url = item.get('likes_src'), item['url']
    try:
        if src == 'zenn' and (m := _ZENN_RE.match(url)):
            r = requests.get(f'https://zenn.dev/api/articles/{m.group(1)}', headers={'User-Agent': UA}, timeout=15)
            r.raise_for_status()
            return int(r.json()['article']['liked_count'])
        if src == 'qiita' and (m := _QIITA_RE.match(url)):
            headers = {'User-Agent': UA}
            if os.environ.get('QIITA_TOKEN'):  # 任意。未設定でも取得できるが、レート制限が厳しい
                headers['Authorization'] = f"Bearer {os.environ['QIITA_TOKEN']}"
            r = requests.get(f'https://qiita.com/api/v2/items/{m.group(1)}', headers=headers, timeout=15)
            r.raise_for_status()
            return int(r.json()['likes_count'])
    except Exception:
        pass
    return None


def enrich_likes(items):
    targets = [it for it in items if it.get('likes_src')]
    if not targets:
        return
    with ThreadPoolExecutor(max_workers=4) as ex:
        for it, n in zip(targets, ex.map(fetch_likes, targets)):
            it['likes'] = n
    ok = sum(1 for it in targets if it.get('likes') is not None)
    print(f'  → いいね数 {ok}/{len(targets)}件を取得')


# ── Translate ─────────────────────────────────────────────────────────────────

def translate_titles(items, batch_size=40):
    """日本語を含まないタイトルに title_ja を付与(失敗時は原文のまま)。"""
    if not TRANSLATE:
        return
    targets = [it for it in items if not CJK.search(it['title'])]
    if not targets:
        return
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        return
    tr = GoogleTranslator(source='auto', target='ja')
    for i in range(0, len(targets), batch_size):
        batch = targets[i:i + batch_size]
        try:
            out = tr.translate_batch([b['title'] for b in batch])
            for it, ja in zip(batch, out):
                if ja:
                    it['title_ja'] = ja
        except Exception as e:
            print(f'  [WARN] translation failed: {type(e).__name__}', file=sys.stderr)


def existing_archive_dates(prev_dir):
    """前回の gh-pages チェックアウト(prev_dir)から既存アーカイブの日付を集める。"""
    dates = set()
    if os.path.isdir(prev_dir):
        for root, _, files in os.walk(prev_dir):
            for f in files:
                m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})\.html', f)
                if m and re.search(r'[\\/]\d{4}[\\/]\d{2}$', root):
                    dates.add(m.group(1))
    return dates


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print('=' * 55, '\n  Tech News Digest\n', '=' * 55, sep='')
    gh_owner = os.environ.get('GH_OWNER', 'mazume-tech-club')
    gh_repo = os.environ.get('GH_REPO', 'tech-news-digest')
    pages_url = os.environ.get('PAGES_URL', f'https://{gh_owner}.github.io/{gh_repo}').rstrip('/')

    settings, categories, feeds = load_config()
    print(f'\n[1/4] RSS収集 ({len(feeds)} feeds)')
    items, report = fetch_all(feeds, settings)
    failed = [r for r in report if r[2]]
    print(f'  → {len(items)}件 / 失敗フィード {len(failed)}件')
    if not items:
        sys.exit('記事を1件も取得できませんでした')

    # mode: heat のカテゴリは、Jev を「重要度」ではなく「アツさ」で判定する
    heat_cats = {c['id'] for c in categories if c.get('mode') == 'heat'}
    for it in items:
        if it['category'] in heat_cats:
            it['profile'] = 'heat'

    print('\n[1.5/4] いいね数の取得')
    enrich_likes(items)

    print('\n[2/4] タイトル翻訳')
    translate_titles(items)

    print('\n[3/4] 重要度判定')
    prev = os.environ.get('PREV_PAGES_DIR', '_pages')
    score_items(items, cache_in=os.path.join(prev, 'data', 'jev-cache.json'),
                cache_out=os.path.join('dist', 'data', 'jev-cache.json'))

    print('\n[4/4] HTML生成')
    now = datetime.now(JST)
    date_file = now.strftime('%Y-%m-%d')
    dist = 'dist'
    dated_dir = os.path.join(dist, now.strftime('%Y'), now.strftime('%m'))
    os.makedirs(dated_dir, exist_ok=True)
    os.makedirs(os.path.join(dist, 'archive'), exist_ok=True)
    # アイコン・manifest 一式(assets/ 配下)をサイトのルートへコピー
    shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets'), dist, dirs_exist_ok=True)

    page = build_html(items, categories, settings, f'{pages_url}/archive/')
    for path in (os.path.join(dist, 'index.html'), os.path.join(dated_dir, f'{date_file}.html')):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)
    dates = existing_archive_dates(prev) | {date_file}
    with open(os.path.join(dist, 'archive', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(build_archive_index(dates, pages_url))

    # ジョブサマリー用のフィード状況
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write(f'### RSS収集結果: {len(items)}件 / 失敗 {len(failed)}件\n\n')
            for name, n, err in failed:
                f.write(f'- ❌ {name}: {err}\n')
    print(f'\n✅ dist/index.html  ✅ dist/{now:%Y/%m}/{date_file}.html  ✅ dist/archive/index.html')


if __name__ == '__main__':
    main()
