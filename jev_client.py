"""
記事の重要度判定。

1. JEV API が設定されていれば、そちらで 1〜5 の重要度を判定する
2. 未設定・失敗時はキーワードによるフォールバック判定を使う

重要度レベル: 5=CRITICAL / 4=HIGH / 3=NOTABLE / 2,1=通常

---- JEV API 仕様(暫定・仮定) -------------------------------------------
JEV API の正式仕様が未確定のため、以下の汎用JSON形式を仮定している。
実際の仕様が違う場合は _call_jev() と _parse_results() だけ直せばよい。

  環境変数:  JEV_API_URL  (エンドポイント)  /  JEV_API_KEY (GitHub Secrets)
  Request :  POST JEV_API_URL
             Authorization: Bearer <JEV_API_KEY>
             {"items": [{"id": "0", "title": "...", "summary": "...",
                         "source": "...", "category": "security"}, ...]}
  Response:  {"results": [{"id": "0", "importance": 4}, ...]}
             (importance は 1〜5。0〜100 の値は自動で 1〜5 に換算する)
-------------------------------------------------------------------------
"""

import os
import re
import sys

import requests

BATCH_SIZE = 40
TIMEOUT = 60

_CRITICAL_KW = [
    'ゼロデイ', '0-day', 'zero-day', 'zero day', '緊急', '悪用を確認', '悪用が確認',
    'actively exploited', 'リモートコード実行', 'remote code execution', 'ランサムウェア',
    'ransomware', 'サプライチェーン攻撃', 'supply chain attack', '大規模障害', '大規模な障害',
    '情報漏えい', '情報漏洩', '不正アクセス', 
]
_HIGH_KW = [
    '脆弱性', 'vulnerability', 'cve-', 'セキュリティ更新', 'patch', '更新プログラム',
    '注意喚起', '障害', '正式版', 'general availability',
    '一般提供', 'gpt-', 'claude', 'gemini', 'llama', 'deprecat', '廃止', 'サービス終了',
    'サポート終了', 'end of life', 'breaking change', '価格改定', '値上げ',
]
_NOTABLE_KW = [
    '新機能', 'preview', 'プレビュー', 'ベータ', 'beta', '登場', '公開', 'v\\d', '入門', '解説',
]


def _keyword_score(item):
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    level = 2
    if any(k in text for k in _CRITICAL_KW):
        level = 5
    elif any(k in text for k in _HIGH_KW):
        level = 4
    elif any(re.search(k, text) if '\\' in k else k in text for k in _NOTABLE_KW):
        level = 3
    if item.get('category') == 'security' and level < 4:
        level = 4 if level == 3 else 3
    return level


def _call_jev(url, key, batch):
    payload = {'items': [
        {'id': str(i), 'title': it.get('title', ''), 'summary': (it.get('summary') or '')[:300],
         'source': it.get('source', ''), 'category': it.get('category', '')}
        for i, it in enumerate(batch)
    ]}
    resp = requests.post(url, json=payload, timeout=TIMEOUT,
                         headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    resp.raise_for_status()
    return resp.json()


def _normalize(value):
    v = float(value)
    if v > 5:  # 0-100 スケール
        v = 1 + round(v / 100 * 4)
    return max(1, min(5, int(round(v))))


def _parse_results(data, batch):
    scores = {}
    for r in data.get('results', []):
        raw = r.get('importance', r.get('score'))
        if raw is None or 'id' not in r:
            continue
        scores[str(r['id'])] = _normalize(raw)
    return [scores.get(str(i)) for i in range(len(batch))]


def score_items(items):
    """各 item に item['importance'] (1-5) と item['scored_by'] を付与する。"""
    url = os.environ.get('JEV_API_URL', '').strip()
    key = os.environ.get('JEV_API_KEY', '').strip()
    use_jev = bool(url and key)
    if not use_jev:
        print('  JEV_API_URL / JEV_API_KEY 未設定 → キーワード判定を使用')

    jev_ok = 0
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        results = [None] * len(batch)
        if use_jev:
            try:
                results = _parse_results(_call_jev(url, key, batch), batch)
            except Exception as e:  # キー等は出力しない
                print(f'  [WARN] JEV API batch {i // BATCH_SIZE} failed: {type(e).__name__}', file=sys.stderr)
        for it, score in zip(batch, results):
            if score is None:
                it['importance'], it['scored_by'] = _keyword_score(it), 'keyword'
            else:
                it['importance'], it['scored_by'] = score, 'jev'
                jev_ok += 1
    print(f'  → JEV判定 {jev_ok}件 / キーワード判定 {len(items) - jev_ok}件')
    return items
