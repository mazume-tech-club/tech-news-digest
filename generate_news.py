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
import sys
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import feedparser
import requests
import yaml

from jev_client import score_items

UA = 'TechNewsDigest/3.0 (+https://github.com/mazume-tech-club/tech-news-digest)'
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
                'lang': feed.get('lang', 'ja'),
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


# ── HTML ──────────────────────────────────────────────────────────────────────

def esc(x):
    return HL.escape(str(x or ''))


_IMP = {5: ('<span class="imp imp-c">🔴 CRITICAL</span>', 'crit'),
        4: ('<span class="imp imp-h">🟠 HIGH</span>', 'high'),
        3: ('<span class="imp imp-n">🟡 注目</span>', 'note')}

CSS = """
:root{--bg:#0d1117;--sf:#161b22;--sf2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#8b949e;--ac:#58a6ff}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans JP',Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6;min-height:100vh}
.hdr{background:linear-gradient(135deg,#1a1f2e,#0d1117);border-bottom:1px solid var(--bd);padding:16px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.htitle{font-size:18px;font-weight:700;color:var(--ac)}.htitle span{color:var(--mu);font-weight:400;font-size:12px;display:block}
.hdate{color:var(--mu);font-size:12px;text-align:right}
.nav{background:var(--sf);border-bottom:1px solid var(--bd);padding:6px 16px;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;position:sticky;top:64px;z-index:90}
.nav a{color:var(--mu);text-decoration:none;padding:5px 10px;border-radius:6px;font-size:12px;white-space:nowrap}
.nav a:hover{background:var(--sf2);color:var(--tx)}
.main{max-width:900px;margin:0 auto;padding:16px 12px 60px}
.ns{margin-bottom:26px;scroll-margin-top:110px}
.sh{font-size:14px;font-weight:600;border-left:3px solid var(--ac);padding:4px 10px;margin-bottom:8px;display:flex;align-items:center;gap:6px}
.cnt{margin-left:auto;font-size:11px;background:var(--sf2);color:var(--mu);padding:1px 7px;border-radius:12px;font-weight:400}
.sc{display:flex;flex-direction:column;gap:6px}
.card{background:var(--sf);border:1px solid var(--bd);border-radius:8px;padding:10px 13px}
.card:hover{border-color:var(--ac)}
.tlink{color:var(--tx);text-decoration:none;font-weight:500;line-height:1.4;display:block}
.tlink:hover{color:var(--ac)}
.title-en{display:block;font-size:11px;color:var(--mu);margin-top:2px}
.desc{font-size:12px;color:var(--mu);margin:4px 0 5px;line-height:1.45}
.meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:5px}
.mi{font-size:11px;color:var(--mu)}
.src-tag{font-size:10px;background:#1a2640;color:var(--ac);padding:2px 6px;border-radius:3px}
.imp{font-size:10px;font-weight:700;padding:2px 7px;border-radius:3px;white-space:nowrap}
.imp-c{background:#3d1a1a;color:#f85149;border:1px solid rgba(248,81,73,.5)}
.imp-h{background:#2d1f0e;color:#f0883e;border:1px solid rgba(240,136,62,.4)}
.imp-n{background:#2a2710;color:#d29922;border:1px solid rgba(210,153,34,.4)}
.card.crit{border-left:3px solid #f85149}.card.high{border-left:3px solid #f0883e}.card.note{border-left:3px solid #d29922}
details.more{margin-top:6px}details.more summary{cursor:pointer;color:var(--mu);font-size:12px;padding:6px 4px}
details.more .sc{margin-top:6px}
.empty{color:var(--mu);font-size:13px;padding:8px 4px}
.arch-link{display:inline-block;margin:4px 0 16px;font-size:12px;color:var(--mu);text-decoration:none;padding:4px 10px;border:1px solid var(--bd);border-radius:6px}
.arch-link:hover{color:var(--ac);border-color:var(--ac)}
.ftr{text-align:center;padding:14px;color:var(--mu);font-size:11px;border-top:1px solid var(--bd)}
@media(max-width:640px){.hdr{flex-direction:column;align-items:flex-start;gap:4px}.nav{top:78px}.main{padding:12px 8px 70px}}
"""


def card(it):
    ja, en = it.get('title_ja') or it['title'], it['title']
    badge, cls = _IMP.get(it.get('importance', 1), ('', ''))
    date = it['published'].astimezone(JST).strftime('%m/%d %H:%M') if it.get('published') else ''
    desc = it.get('summary', '')
    return (f'<div class="card {cls}">'
            f'<a class="tlink" href="{esc(it["url"])}" target="_blank" rel="noopener">{esc(ja)}</a>'
            + (f'<span class="title-en">{esc(en)}</span>' if ja != en else '')
            + (f'<p class="desc">{esc(desc[:160])}{"…" if len(desc) > 160 else ""}</p>' if desc else '')
            + f'<div class="meta">{badge}<span class="src-tag">{esc(it["source"])}</span>'
            + (f'<span class="mi">{date}</span>' if date else '') + '</div></div>')


def section(cat, items, show_n):
    ranked = sorted(items, key=lambda x: (x.get('importance', 1),
                    x['published'] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    body = ''.join(card(i) for i in ranked[:show_n]) or '<p class="empty">記事が見つかりませんでした</p>'
    rest = ranked[show_n:]
    if rest:
        body += (f'<details class="more"><summary>さらに {len(rest)} 件を表示</summary>'
                 f'<div class="sc">{"".join(card(i) for i in rest)}</div></details>')
    return (f'<section class="ns" id="{esc(cat["id"])}"><h2 class="sh" style="border-left-color:{esc(cat["color"])}">'
            f'<span>{cat["icon"]}</span>{esc(cat["title"])}<span class="cnt">{len(items)}件</span></h2>'
            f'<div class="sc">{body}</div></section>')


def build_html(items, categories, settings, archive_link):
    now = datetime.now(JST)
    crit = sum(1 for i in items if i.get('importance') == 5)
    note = (f' <span style="color:#f85149;font-weight:700">⚠ CRITICAL {crit}件</span>' if crit else '')
    by_cat = {c['id']: [] for c in categories}
    for it in items:
        by_cat.setdefault(it['category'], []).append(it)
    shown = [c for c in categories if by_cat.get(c['id'])]
    nav = ''.join(f'<a href="#{esc(c["id"])}">{c["icon"]} {esc(c["title"])}</a>' for c in shown)
    secs = ''.join(section(c, by_cat[c['id']], settings['show_per_category']) for c in shown)
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"><meta name="theme-color" content="#0d1117">
<title>📡 Tech News Digest — {now.strftime('%Y年%m月%d日')}</title><style>{CSS}</style></head>
<body>
<header class="hdr"><div class="htitle">📡 Tech News Digest<span>重要度順・カテゴリ別{note}</span></div>
<div class="hdate">🕐 {now.strftime('%Y年%m月%d日 %H:%M')} JST<br>{len(items)}件</div></header>
<nav class="nav">{nav}</nav>
<main class="main"><a class="arch-link" href="{esc(archive_link)}">📂 過去のアーカイブ</a>{secs}</main>
<footer class="ftr">Tech News Digest ｜ 収集元は feeds.yml で管理(Pull Request で追加できます)</footer>
</body></html>"""


def build_archive_index(dates, pages_url):
    groups = {}
    for d in sorted(dates, reverse=True):
        groups.setdefault(d[:7], []).append(d)
    body = ''
    for ym, ds in groups.items():
        rows = ''.join(f'<a class="entry" href="{esc(pages_url)}/{d[:4]}/{d[5:7]}/{d}.html">'
                       f'{d[:4]}年{d[5:7]}月{d[8:]}日<span>→</span></a>' for d in ds)
        body += f'<div class="mg"><div class="ml">{ym[:4]}年{ym[5:]}月</div>{rows}</div>'
    body = body or '<p style="color:var(--mu)">アーカイブはまだありません。</p>'
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>📡 Tech News Digest — アーカイブ</title>
<style>{CSS}.main{{max-width:700px}}.ml{{font-size:12px;color:var(--mu);font-weight:600;padding:4px 0 6px;border-bottom:1px solid var(--bd);margin:14px 0 8px}}
.entry{{display:flex;padding:8px 12px;background:var(--sf);border:1px solid var(--bd);border-radius:6px;margin-bottom:5px;text-decoration:none;color:var(--tx)}}
.entry:hover{{border-color:var(--ac);color:var(--ac)}}.entry span{{margin-left:auto;color:var(--mu)}}</style></head>
<body><header class="hdr"><div class="htitle">📡 Tech News Digest<span>アーカイブ一覧(全{len(dates)}件)</span></div>
<a class="arch-link" style="margin:0" href="{esc(pages_url)}/">← 最新へ</a></header>
<main class="main">{body}</main></body></html>"""


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

    print('\n[2/4] タイトル翻訳')
    translate_titles(items)

    print('\n[3/4] 重要度判定')
    score_items(items)

    print('\n[4/4] HTML生成')
    now = datetime.now(JST)
    date_file = now.strftime('%Y-%m-%d')
    dist = 'dist'
    dated_dir = os.path.join(dist, now.strftime('%Y'), now.strftime('%m'))
    os.makedirs(dated_dir, exist_ok=True)
    os.makedirs(os.path.join(dist, 'archive'), exist_ok=True)

    page = build_html(items, categories, settings, f'{pages_url}/archive/')
    for path in (os.path.join(dist, 'index.html'), os.path.join(dated_dir, f'{date_file}.html')):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)
    dates = existing_archive_dates(os.environ.get('PREV_PAGES_DIR', '_pages')) | {date_file}
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
