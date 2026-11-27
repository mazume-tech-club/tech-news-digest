"""
Treg を使う追加データ処理。設計は docs/treg-design.md を参照。

1. 記事本文の取得 → 要約(RSS に概要がない記事だけ・1 日 20 件まで・URL 単位でキャッシュ)
2. RSS のないページの変更検知(feeds.yml の watches:。毎日ページを取得し、前回のテキストと diff を取る)

どちらも Treg が使えない(キー未設定・失敗・予算超過)ときは何もしない。
"""

import difflib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from curation import article_id
from treg_client import fetch_page

CJK = re.compile(r'[぀-ヿ㐀-鿿]')
BODY_CACHE_VERSION = 1
SNAP_VERSION = 1
BODY_DAILY_LIMIT = 20
BODY_CACHE_DAYS = 14
BODY_MAX_FAILS = 2
WATCH_MIN_INTERVAL = timedelta(hours=20)   # 1 日に何度実行しても、同じページの取得は 1 回
CHANGE_SHOW_HOURS = 36                     # 検知した変化をページに出す期間
CHANGE_KEEP_DAYS = 7
WORKERS = 4

KIND_LABEL = {'status': '障害', 'price': '料金', 'terms': '規約', 'news': '発表'}
KIND_HEAD = {'status': 'ステータス', 'price': '料金表', 'terms': '利用規約', 'news': '発表ページ'}
KIND_LEVEL = {'status': 4, 'price': 4, 'terms': 4, 'news': 3}


def _load(path, version):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('version') == version:
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return {'version': version}


def _save(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


# ── 1. 本文 → 要約 ───────────────────────────────────────────────────────

_MD_NOISE = re.compile(r'!\[[^\]]*\]\([^)]*\)|\[([^\]]*)\]\([^)]*\)|[*_`>#|]+')


def body_paragraphs(markdown):
    """Markdown から本文らしい段落(40 文字以上・リンク集やメニューでない行)を取り出す。"""
    out = []
    for raw in (markdown or '').splitlines():
        line = _MD_NOISE.sub(lambda m: m.group(1) or ' ', raw)
        line = re.sub(r'\s+', ' ', line).strip()
        if len(line) < 40 or line.lower().startswith(('cookie', 'subscribe', 'sign in', 'share')):
            continue
        if line.count(' ') < 4 and not CJK.search(line):
            continue
        out.append(line)
    return out


def make_summary(markdown, translate=None, limit=110):
    """本文の冒頭 1〜2 文から、2 行程度(約 110 文字)の日本語要約を作る。英語は翻訳する。"""
    paras = body_paragraphs(markdown)
    if not paras:
        return ''
    text = ' '.join(paras[:2])
    sents = re.split(r'(?<=[。．.!?！？])\s*', text)
    lead = ''
    for s in sents:
        if not s:
            continue
        if lead and len(lead) + len(s) > 320:
            break
        lead = (lead + ' ' + s).strip()
        if len(lead) >= 160:
            break
    if not CJK.search(lead) and translate:
        try:
            lead = translate(lead) or lead
        except Exception:
            pass
    lead = lead.strip()
    return lead if len(lead) <= limit else lead[:limit - 1].rstrip() + '…'


def _translator():
    if os.environ.get('TRANSLATE', '1') == '0':
        return None
    try:
        from deep_translator import GoogleTranslator
        tr = GoogleTranslator(source='auto', target='ja')
        return tr.translate
    except Exception:
        return None


def needs_body(item):
    return (item.get('profile') != 'heat' and item.get('kind') != 'change'
            and len((item.get('summary') or '').strip()) < 20)


def fetch_bodies(items, client, cache_in=None, cache_out=None, now=None, limit=BODY_DAILY_LIMIT, translate=None):
    """概要のない記事の本文を取得し、item['summary'] に要約・item['summary_src']='body' を付ける。"""
    now = now or datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')
    cache = _load(cache_in, BODY_CACHE_VERSION) if cache_in else {'version': BODY_CACHE_VERSION}
    entries = cache.get('items', {})
    targets = [it for it in items if needs_body(it)]
    # 英語(海外記事)→ 新しい順に優先
    targets.sort(key=lambda it: (it.get('lang') == 'en', it['published'].timestamp() if it.get('published') else 0),
                 reverse=True)
    hit = 0
    todo = []
    for it in targets:
        e = entries.get(it['url'])
        if e and e.get('s'):
            _apply_body(it, e)
            hit += 1
        elif e and e.get('f', 0) >= BODY_MAX_FAILS:
            continue
        else:
            todo.append(it)
    # 予算の残りで払える件数までに絞る(呼べなかった記事を「失敗」と数えないため)
    todo = todo[:min(limit, client.affordable('litescrape.web.fetch.post'))]
    fetched = 0
    if todo and client.enabled:
        translate = translate if translate is not None else _translator()
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            results = list(ex.map(lambda it: fetch_page(client, it['url']), todo))
        for it, md in zip(todo, results):
            summary = make_summary(md, translate) if md else ''
            if summary:
                e = {'s': summary, 'b': ' '.join(body_paragraphs(md))[:800], 't': today}
                entries[it['url']] = e
                _apply_body(it, e)
                fetched += 1
            elif client.enabled:
                # 失敗はスキップ(タイトルのみ表示)。BODY_MAX_FAILS 回失敗した URL は以後取得しない
                old = entries.get(it['url']) or {}
                entries[it['url']] = {'f': old.get('f', 0) + 1, 't': today}
    elif targets and not client.enabled:
        print(f'  本文取得スキップ({client.reason_disabled() or "対象なし"})')
    cutoff = (now - timedelta(days=BODY_CACHE_DAYS)).strftime('%Y-%m-%d')
    entries = {u: e for u, e in entries.items() if e.get('t', today) >= cutoff}
    if cache_out:
        _save(cache_out, {'version': BODY_CACHE_VERSION, 'items': entries})
    print(f'  → 概要なし {len(targets)}件 / 本文から要約 {hit + fetched}件(うちキャッシュ {hit}件・新規 {fetched}件)')
    return fetched


def _apply_body(item, e):
    item['summary'] = e['s']
    item['summary_src'] = 'body'
    if e.get('b'):
        item['body_excerpt'] = e['b']


# ── 2. ページの変化 ──────────────────────────────────────────────────────

_VOLATILE = [
    re.compile(r'\b\d{1,2}:\d{2}(:\d{2})?\s*(am|pm|utc|jst|gmt)?\b', re.I),
    re.compile(r'\b\d+\s*(seconds?|minutes?|mins?|hours?|days?|weeks?)\s+ago\b', re.I),
    re.compile(r'\d+\s*(秒|分|時間|日)前'),
    re.compile(r'\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b'),
    re.compile(r'\d{4}年\d{1,2}月\d{1,2}日'),
    re.compile(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? \d{4}\b', re.I),
]


def normalize_lines(markdown, max_lines=400):
    """差分用にテキストを正規化する(日時など毎回変わる部分を伏せ、空行・記号だけの行を除く)。"""
    out = []
    for raw in (markdown or '').splitlines():
        line = _MD_NOISE.sub(lambda m: m.group(1) or ' ', raw)
        for rx in _VOLATILE:
            line = rx.sub('#', line)
        line = re.sub(r'\s+', ' ', line).strip()
        if len(re.sub(r'[\W#_]+', '', line)) < 3:
            continue
        out.append(line[:300])
        if len(out) >= max_lines:
            break
    return out


def diff_lines(old, new):
    """(削除された行, 追加された行) を返す。並び替えだけの変化は無視する。"""
    removed, added = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if op in ('replace', 'delete'):
            removed += old[i1:i2]
        if op in ('replace', 'insert'):
            added += new[j1:j2]
    rs, as_ = set(removed), set(added)
    removed = [x for x in removed if x not in as_]
    added = [x for x in added if x not in rs]
    return removed, added


def _short(lines, n=2, limit=160):
    s = ' / '.join(lines[:n])
    return s if len(s) <= limit else s[:limit - 1] + '…'


def make_change(watch, removed, added, detected):
    kind = watch.get('kind', 'news')
    head_src = added or removed
    head = _short(head_src, 1, 48)
    if not added and removed:
        head = '削除: ' + head
    return {
        'kind': 'change', 'change_kind': kind, 'change_label': KIND_LABEL.get(kind, '発表'),
        'title': f"[{watch['name']}] {KIND_HEAD.get(kind, '発表ページ')}：{head}",
        'url': watch['url'], 'source': watch['name'], 'category': '_changes',
        'before': _short(removed) if removed else '(なし)', 'after': _short(added) if added else '(削除)',
        'detected': detected,
    }


def check_watches(watches, client, snap_in=None, snap_out=None, now=None):
    """監視ページを取得して前回と比べ、変化を記事(dict)のリストで返す。直近 CHANGE_SHOW_HOURS 時間の変化を含む。"""
    now = now or datetime.now(timezone.utc)
    data = _load(snap_in, SNAP_VERSION) if snap_in else {'version': SNAP_VERSION}
    pages, changes = data.get('pages', {}), data.get('changes', [])
    due = []
    for w in watches or []:
        snap = pages.get(w['url'])
        last = _parse(snap.get('t')) if snap else None
        if not last or now - last >= WATCH_MIN_INTERVAL:
            due.append(w)
    if due and client.enabled:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            results = list(ex.map(lambda w: fetch_page(client, w['url'], max_tokens=6000), due))
        for w, md in zip(due, results):
            if md is None:
                print(f"  ✗ {w['name']}: 取得失敗(前回の内容を維持)")
                continue
            lines = normalize_lines(md)
            snap = pages.get(w['url'])
            if snap and snap.get('lines') is not None:
                removed, added = diff_lines(snap['lines'], lines)
                if removed or added:
                    ch = make_change(w, removed, added, now.isoformat())
                    changes.append({k: v for k, v in ch.items()})
                    print(f"  ● {w['name']}: 変化あり(-{len(removed)} / +{len(added)})")
                else:
                    print(f"  ✓ {w['name']}: 変化なし")
            else:
                print(f"  ✓ {w['name']}: 初回取得(基準として保存)")
            pages[w['url']] = {'lines': lines, 't': now.isoformat()}
    elif due:
        print(f'  ページ監視スキップ({client.reason_disabled()})')
    keep_from = now - timedelta(days=CHANGE_KEEP_DAYS)
    changes = [c for c in changes if (_parse(c.get('detected')) or now) >= keep_from]
    urls = {w['url'] for w in watches or []}
    pages = {u: p for u, p in pages.items() if u in urls}
    if snap_out:
        _save(snap_out, {'version': SNAP_VERSION, 'pages': pages, 'changes': changes})
    show_from = now - timedelta(hours=CHANGE_SHOW_HOURS)
    out = []
    for c in changes:
        t = _parse(c.get('detected'))
        if t and t >= show_from and c.get('url') in urls:
            it = dict(c)
            it['published'] = t
            it['importance'] = KIND_LEVEL.get(c.get('change_kind'), 3)
            it['importance_score'] = (it['importance'] - 1) / 4
            it['scored_by'] = 'watch'
            it['lang'] = 'ja'
            it['id'] = article_id(f"{c['url']}#{c['detected']}")
            out.append(it)
    out.sort(key=lambda x: x['published'], reverse=True)
    return out


def _parse(s):
    try:
        t = datetime.fromisoformat(s)
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
