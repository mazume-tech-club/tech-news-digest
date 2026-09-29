"""
記事の重要度判定 (Jev / TypeSafe AI)。設計は docs/jev-design.md を参照。

- 記事 1 件につき Jev API を 1 回呼ぶ(state=記事、questions=複数の観点を並列に質問=ファンアウト)
- 観点ごとの Score/Noul を「重み付き合成スコア」にして、コード側で重要度(1〜5)を決める
- 確信度(confidence)が低い判定はキーワード判定と平均する
- API 失敗・キー未設定・認証エラー時はキーワード判定にフォールバックする
- 判定結果は data/jev-cache.json に URL 単位でキャッシュし、同じ記事を再判定しない

API: POST https://api.typesafe.ai/v1/systemone  (Authorization: Bearer <JEV_API_KEY>)
     https://docs.typesafe.ai/api.md
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

API_URL = os.environ.get('JEV_API_URL', '').strip() or 'https://api.typesafe.ai/v1/systemone'
MODEL = os.environ.get('JEV_MODEL', '').strip() or 'jev-latest'
CACHE_VERSION = 1            # 質問・重みを変えたら上げる(キャッシュが破棄される)
MAX_WORKERS = 6              # 上限 1,200 req/分 に対して十分低い
MAX_ATTEMPTS = 3
TIMEOUT = 30
LOW_CONFIDENCE = 0.4         # これ未満はキーワード判定と平均する

# ── 質問定義 ──────────────────────────────────────────────────────────────────
# 1 観点 = 1 質問。レベルは「程度」ではなく具体的な状況で書く(Jev のベストプラクティス)。
# レベル数-1 が最大値。合成時に 0〜1 へ正規化する。

QUESTIONS = {
    'impact': {
        'type': 'score',
        'instructions': 'この記事の内容は、日本のソフトウェア技術者・IT担当者にどの程度の範囲で影響しますか?',
        'criteria': [
            '個人の体験談や特定の小さな話題で、多くの技術者には影響しない',
            '特定の製品・技術の利用者に限られる',
            '広く使われている製品・サービス・技術の利用者に影響する',
            '業界全体・社会インフラ・非常に多くのユーザーに大きく影響する',
        ],
    },
    'urgency': {
        'type': 'score',
        'instructions': 'この記事の内容に対して、読者はどれくらい急いで確認・対応する必要がありますか?',
        'criteria': [
            '急ぐ必要はない(解説・意見・読み物・体験談)',
            '近いうちに把握しておくとよい(新機能・リリース・仕様変更の告知)',
            '早めの確認や対応が必要(脆弱性の公表、非推奨化・サービス終了の予告、料金改定)',
            '今すぐ対応が必要(悪用が確認されている脆弱性、大規模障害、情報漏えいの発生)',
        ],
    },
    'novelty': {
        'type': 'score',
        'instructions': 'この記事は、どれくらい新しい情報ですか?',
        'criteria': [
            '既知の内容の再整理・入門・まとめ・体験談',
            '既知の話題に対する新しい知見や事例',
            '新しい発表・新製品・新しい事象を伝える一次情報や速報',
        ],
    },
    'noise': {
        'type': 'noul',
        'instructions': 'この記事は、広告・PR・セール情報・ランキング・雑談などで、技術者の判断材料にならない内容ですか?',
        'criteria': {
            'true': '広告、キャンペーン、セール、ランキング、雑談・エンタメが中心で、技術的な判断材料がない',
            'false': '技術・製品・セキュリティ・サービスに関する情報を伝えている',
        },
    },
}
_MAX_LEVEL = {k: len(q['criteria']) - 1 for k, q in QUESTIONS.items() if q['type'] == 'score'}

# カテゴリ別の重み(合計 1.0)。セキュリティは緊急性、総合/面白技術は新規性を重視。
WEIGHTS = {
    'default':  {'impact': 0.40, 'urgency': 0.35, 'novelty': 0.25},
    'security': {'impact': 0.30, 'urgency': 0.55, 'novelty': 0.15},
    'general':  {'impact': 0.45, 'urgency': 0.15, 'novelty': 0.40},
    'fun':      {'impact': 0.45, 'urgency': 0.15, 'novelty': 0.40},
}
NOISE_PENALTY = 0.5          # noise=1.0 のとき合成スコアを半分にする

# 合成スコア(0〜1) → 重要度(1〜5)。実データを見て調整する。
THRESHOLDS = [(0.70, 5), (0.50, 4), (0.32, 3), (0.15, 2)]

# ── キーワード判定(フォールバック) ───────────────────────────────────────────
_CRITICAL_KW = [
    'ゼロデイ', '0-day', 'zero-day', 'zero day', '緊急', '悪用を確認', '悪用が確認',
    'actively exploited', 'リモートコード実行', 'remote code execution', 'ランサムウェア',
    'ransomware', 'サプライチェーン攻撃', 'supply chain attack', '大規模障害', '大規模な障害',
    '情報漏えい', '情報漏洩', '不正アクセス',
]
_HIGH_KW = [
    '脆弱性', 'vulnerability', 'cve-', 'セキュリティ更新', 'patch', '更新プログラム',
    '注意喚起', '障害', '正式版', 'general availability', '一般提供', 'gpt-', 'claude',
    'gemini', 'llama', 'deprecat', '廃止', 'サービス終了', 'サポート終了', 'end of life',
    'breaking change', '価格改定', '値上げ',
]
_NOTABLE_KW = ['新機能', 'preview', 'プレビュー', 'ベータ', 'beta', '登場', '公開', '入門', '解説']


def keyword_level(item):
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    level = 2
    if any(k in text for k in _CRITICAL_KW):
        level = 5
    elif any(k in text for k in _HIGH_KW):
        level = 4
    elif any(k in text for k in _NOTABLE_KW):
        level = 3
    if item.get('category') == 'security' and level < 4:
        level = 4 if level == 3 else 3
    return level


# ── 合成スコア ────────────────────────────────────────────────────────────────

def level_from_score(score):
    for threshold, level in THRESHOLDS:
        if score >= threshold:
            return level
    return 1


def compose(answers, category):
    """Jev の answers から (合成スコア0-1, 平均confidence, 内訳) を返す。欠けていれば None。"""
    try:
        norm, confs = {}, []
        for key, top in _MAX_LEVEL.items():
            a = answers[key]
            norm[key] = max(0.0, min(1.0, float(a['score']) / top))
            confs.append(float(a.get('confidence', 1.0)))
        noise = max(0.0, min(1.0, float(answers['noise']['noul'])))
    except (KeyError, TypeError, ValueError):
        return None
    w = WEIGHTS.get(category, WEIGHTS['default'])
    base = sum(w[k] * norm[k] for k in w)
    score = base * (1 - NOISE_PENALTY * noise)
    return score, sum(confs) / len(confs), {**norm, 'noise': noise}


def build_state(item):
    return {
        'title': item.get('title', ''),
        'summary': (item.get('summary') or '')[:300],
        'source': item.get('source', ''),
        'published': item['published'].isoformat() if item.get('published') else None,
    }


# ── API 呼び出し ──────────────────────────────────────────────────────────────

class AuthError(Exception):
    pass


def call_jev(item, key, session=requests):
    """1 記事を判定して answers を返す。429/529 は指数バックオフで再試行する。"""
    payload = {'model': MODEL, 'state': build_state(item), 'questions': QUESTIONS}
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    for attempt in range(MAX_ATTEMPTS):
        resp = session.post(API_URL, json=payload, headers=headers, timeout=TIMEOUT)
        if resp.status_code in (401, 403):
            raise AuthError(f'HTTP {resp.status_code}')
        if resp.status_code in (429, 529) and attempt < MAX_ATTEMPTS - 1:
            wait = float(resp.headers.get('Retry-After') or 2 ** attempt)
            time.sleep(min(wait, 20))
            continue
        resp.raise_for_status()
        return resp.json()['answers']
    raise RuntimeError('unreachable')


# ── キャッシュ ────────────────────────────────────────────────────────────────

def load_cache(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('version') == CACHE_VERSION:
            return data.get('items', {})
    except (OSError, ValueError):
        pass
    return {}


def save_cache(path, items):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'version': CACHE_VERSION, 'items': items}, f, ensure_ascii=False, separators=(',', ':'))


# ── エントリポイント ──────────────────────────────────────────────────────────

def _apply_keyword(item):
    item['importance'] = keyword_level(item)
    item['importance_score'] = (item['importance'] - 1) / 4
    item['scored_by'] = 'keyword'
    item['breakdown'] = None


def _apply_composite(item, composite):
    score, conf, breakdown = composite
    if conf < LOW_CONFIDENCE:  # 確信度が低い判定はキーワード判定と平均する(confidence routing)
        score = 0.5 * score + 0.5 * (keyword_level(item) - 1) / 4
        item['scored_by'] = 'jev+keyword'
    else:
        item['scored_by'] = 'jev'
    item['importance_score'] = round(score, 4)
    item['importance'] = level_from_score(score)
    item['breakdown'] = breakdown


def score_items(items, cache_in=None, cache_out=None):
    """各 item に importance(1-5) / importance_score(0-1) / scored_by / breakdown を付与する。"""
    key = os.environ.get('JEV_API_KEY', '').strip()
    cache = load_cache(cache_in) if cache_in else {}

    todo = []
    for it in items:
        hit = cache.get(it['url'])
        if hit:
            it.update(importance=hit['importance'], importance_score=hit['score'],
                      scored_by=hit['by'], breakdown=hit.get('breakdown'))
        else:
            todo.append(it)
    cached_n = len(items) - len(todo)

    if not key:
        print('  JEV_API_KEY 未設定 → キーワード判定を使用')
        for it in todo:
            _apply_keyword(it)
    else:
        auth_failed = []

        def work(it):
            if auth_failed:
                return it, None
            try:
                return it, compose(call_jev(it, key), it.get('category'))
            except AuthError as e:
                auth_failed.append(str(e))
            except Exception as e:  # キーやレスポンス本文は出力しない
                print(f'  [WARN] Jev failed: {type(e).__name__}', file=sys.stderr)
            return it, None

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            results = list(ex.map(work, todo))
        if auth_failed:
            print(f'  [ERROR] Jev 認証エラー({auth_failed[0]}) → JEV_API_KEY を確認してください', file=sys.stderr)
        for it, composite in results:
            if composite is None:
                _apply_keyword(it)
            else:
                _apply_composite(it, composite)

    # キャッシュには Jev で判定できたものだけ保存(キーワード判定は次回再挑戦する)
    if cache_out:
        save_cache(cache_out, {
            i['url']: {'importance': i['importance'], 'score': i['importance_score'],
                       'by': i['scored_by'], 'breakdown': i.get('breakdown')}
            for i in items if i.get('scored_by', '').startswith('jev')})

    jev_n = sum(1 for i in items if i.get('scored_by', '').startswith('jev'))
    print(f'  → Jev {jev_n}件(うちキャッシュ {cached_n}件) / キーワード {len(items) - jev_n}件')
    return items
