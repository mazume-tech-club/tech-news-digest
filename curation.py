"""
記事の整理: 短い記事ID・キーワード抽出・重要な理由ラベル・同じ話題の束ね・Lv5 の相対評価。
設計は docs/reason-labels.md を参照。外部通信はしない(テストしやすい純粋な関数だけ)。
"""

import hashlib
import re
from datetime import timedelta

ID_LEN = 7   # Cookie に保存する既読ID(URL の SHA-1 先頭 7 文字)


def article_id(url):
    return hashlib.sha1((url or '').encode('utf-8')).hexdigest()[:ID_LEN]


# ── キーワード(「見ない」「フォロー」の対象) ──────────────────────────────

_STOP = {
    'the', 'and', 'for', 'with', 'from', 'that', 'this', 'your', 'how', 'what', 'why', 'new', 'now',
    'are', 'was', 'you', 'its', 'into', 'about', 'more', 'than', 'will', 'can', 'all', 'our', 'out',
    'news', 'blog', 'release', 'notes', 'update', 'updates', 'version', 'using', 'use',
}
_STOP_JA = {
    'について', 'お知らせ', 'ニュース', 'まとめ', 'リリース', 'アップデート', 'ブログ', 'サービス',
    'セキュリティ', 'システム', 'ユーザー', 'データ', 'エンジニア', 'プログラム', '公開', '発表', '開始',
    '対応', '提供', '記事', '解説', '紹介', '方法', '可能性', '注意喚起', '脆弱性', '情報',
}
_ASCII_TOKEN = re.compile(r'[A-Za-z][A-Za-z0-9.+#-]*[A-Za-z0-9+#]|[A-Za-z]{2,}')
_KATA = re.compile(r'[ァ-ヴー]{3,}')
_KANJI = re.compile(r'[一-龥々]{2,}')
_QUOTED = re.compile(r'[「『“"]([^」』”"]{2,20})[」』”"]')


def extract_keyword(title):
    """タイトルから「見ない/フォロー」に使う代表キーワードを 1 つ選ぶ。
    優先: かぎ括弧の語 → 大文字で始まる英単語(製品名など)→ カタカナ語 → 漢字語。"""
    title = title or ''
    m = _QUOTED.search(title)
    if m:
        return m.group(1).strip()
    asc = [t for t in _ASCII_TOKEN.findall(title) if t.lower() not in _STOP and len(t) >= 2]
    caps = [t for t in asc if t[0].isupper() or any(c.isdigit() for c in t)]
    if caps:
        return max(caps[:3], key=len) if len(caps[0]) < 3 else caps[0]
    for rx in (_KATA, _KANJI):
        for t in rx.findall(title):
            if t not in _STOP_JA:
                return t
    if asc:
        return asc[0]
    return title[:12]


# ── 重要な理由ラベル ─────────────────────────────────────────────────────
# tone: crit(赤) / high(茶) / info(灰)。色だけに頼らず、ラベル文字で理由を示す。

LABELS = {
    'leak':    ('情報漏えい発生', 'crit'),
    'exploit': ('悪用確認済み', 'crit'),
    'now':     ('今すぐ対応', 'crit'),
    'outage':  ('サービス障害', 'high'),
    'eol':     ('サービス終了予告', 'high'),
    'price':   ('料金改定', 'high'),
    'terms':   ('規約変更', 'high'),
    'vuln':    ('脆弱性', 'high'),
    'ga':      ('一般提供開始', 'high'),
    'wide':    ('影響：広い', 'high'),
    'fresh':   ('新情報', 'info'),
    'notable': ('注目', 'info'),
    'hot':     ('人気', 'info'),
    'curious': ('試したくなる', 'info'),
    'appeal':  ('共感が広い', 'info'),
}

_RULES = [  # (ラベル, 正規表現)。上から順に優先
    ('leak', r'情報漏え?い|情報漏洩|個人情報.{0,6}流出|流出|不正アクセス|data breach|leak(ed)?\b'),
    ('exploit', r'悪用(を|が)?確認|悪用され|ゼロデイ|0-?day|zero[- ]day|actively exploited|in the wild|ランサムウェア|ransomware'),
    ('outage', r'大規模(な)?障害|障害(が)?発生|サービス(が)?停止|outage|service disruption|ダウンして'),
    ('eol', r'サービス終了|提供終了|サポート終了|廃止|end of life|end-of-life|\beol\b|deprecat|sunset'),
    ('price', r'値上げ|値下げ|価格改定|料金改定|料金(を)?変更|新料金|pricing (change|update)|price (increase|cut)'),
    ('terms', r'利用規約|規約(の)?変更|プライバシーポリシー|terms of (service|use)|privacy policy'),
    ('vuln', r'脆弱性|cve-\d|vulnerabilit|セキュリティ(更新|アップデート)|security (update|advisory)'),
    ('ga', r'一般提供|正式(版|リリース|提供)|general(ly)? availab|\bGA\b|now available'),
]
_RULES = [(k, re.compile(rx, re.I)) for k, rx in _RULES]


def _text(item):
    return ' '.join(str(item.get(k) or '') for k in ('title', 'title_ja', 'summary'))


def _level(item):
    try:
        return max(1, min(5, int(item.get('importance', 2))))
    except (TypeError, ValueError):
        return 2


def reason_keys(item, limit=2):
    """記事の「重要な理由」ラベルのキーを最大 limit 個返す(重い順)。Lv3 以上には必ず 1 つ以上付く。"""
    if item.get('kind') == 'change':
        return [item.get('change_label_key') or 'notable']
    lv = _level(item)
    keys = []
    if item.get('profile') == 'heat':
        bd = item.get('breakdown') or {}
        if (item.get('likes') or 0) >= 50:
            keys.append('hot')
        if isinstance(bd.get('curiosity'), (int, float)) and bd['curiosity'] >= 0.67:
            keys.append('curious')
        if isinstance(bd.get('appeal'), (int, float)) and bd['appeal'] >= 0.67:
            keys.append('appeal')
        if not keys and lv >= 3:
            keys.append('hot')
        return keys[:limit]

    text = _text(item)
    for k, rx in _RULES:
        if rx.search(text):
            keys.append(k)
    bd = item.get('breakdown') or {}
    urg, imp, nov = (bd.get(k) for k in ('urgency', 'impact', 'novelty'))
    if isinstance(urg, (int, float)) and urg >= 0.99:
        keys.append('now')
    if isinstance(imp, (int, float)) and imp >= 0.66:
        keys.append('wide')
    if isinstance(nov, (int, float)) and nov >= 0.99:
        keys.append('fresh')
    # 「脆弱性」は「悪用確認済み」「今すぐ対応」があるときは冗長なので落とす
    if 'vuln' in keys and ({'exploit', 'now'} & set(keys)):
        keys.remove('vuln')
    order = {'crit': 0, 'high': 1, 'info': 2}
    seen, out = set(), []
    for k in sorted(keys, key=lambda k: order[LABELS[k][1]]):  # 安定ソート: 同じ重さはルール順
        if k not in seen:
            seen.add(k)
            out.append(k)
    if not out and lv >= 3:
        out.append('fresh' if (isinstance(nov, (int, float)) and nov >= 0.5) else 'notable')
    return out[:limit]


def reason_labels(item, limit=2):
    return [{'k': k, 't': LABELS[k][0], 'tone': LABELS[k][1]} for k in reason_keys(item, limit)]


_WHY = {
    'leak': '情報漏えいが発生しています。自社や取引先、利用中のサービスが該当していないか確認が必要です。',
    'exploit': '実際に悪用が確認されている内容です。該当する製品を使っていないか、早めの確認と対応が必要です。',
    'now': '今すぐ確認・対応が必要な内容と判定されました。',
    'outage': 'サービスの障害・停止に関する情報です。利用中のサービスに影響していないか確認してください。',
    'eol': 'サービスや機能の終了・非推奨化の予告です。移行の計画が必要になる可能性があります。',
    'price': '料金の改定に関する情報です。コストの見積もりに影響する可能性があります。',
    'terms': '利用規約・ポリシーの変更です。社内での利用条件や設定の見直しが必要か確認してください。',
    'vuln': '脆弱性の公表です。該当するバージョンを使っていないか確認してください。',
    'ga': '本番で使える一般提供(GA)・正式版になりました。',
    'wide': '広く使われている製品・サービス・技術の利用者に影響する内容です。',
    'fresh': '新しい発表・事象を伝える一次情報や速報です。',
    'notable': '技術者が把握しておくとよい話題と判定されました。',
    'hot': '多くの技術者から反応を集めている人気記事です。',
    'curious': '工夫や発見があり、試したくなる内容と判定されました。',
    'appeal': '職種や分野を問わず関心を集めそうな話題です。',
}

_CHANGE_WHY = {
    'status': '利用中のサービスに直接影響する可能性があります。',
    'price': '料金表が変わりました。コストの見積もりに影響する可能性があります。',
    'terms': '規約が変わりました。社内での利用条件や設定の見直しが必要か確認してください。',
    'news': 'RSS のない発表ページに新しい内容が追加されました。',
}


def why_text(item):
    """詳細を開いたときの「重要な理由」の 1〜2 文。"""
    if item.get('kind') == 'change':
        return _CHANGE_WHY.get(item.get('change_kind'), _CHANGE_WHY['news'])
    keys = reason_keys(item)
    if not keys:
        return '大きな影響や緊急性は見られない、参考情報です。'
    text = _WHY[keys[0]]
    if len(keys) > 1 and keys[1] == 'wide' and keys[0] != 'wide':
        text += '広く使われている製品・サービスに関わります。'
    if item.get('scored_by') == 'keyword':
        text += '(キーワードによる簡易判定)'
    return text


# ── 同じ話題の束ね ──────────────────────────────────────────────────────

def _norm_title(item):
    return re.sub(r'\s+', '', (item.get('title_ja') or item.get('title') or '').lower())


def _bigrams(s):
    s = re.sub(r'[\W_]+', '', s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _proper_nouns(item):
    """固有名詞らしい語(英単語・カタカナ語・漢字3字以上・かぎ括弧内)。"""
    t = item.get('title_ja') or item.get('title') or ''
    out = set()
    out |= {m.lower() for m in _ASCII_TOKEN.findall(t) if len(m) >= 3 and m.lower() not in _STOP}
    out |= {m for m in _KATA.findall(t) if m not in _STOP_JA}
    out |= {m for m in re.findall(r'[一-龥々]{3,}', t) if m not in _STOP_JA}
    out |= {m.group(1) for m in _QUOTED.finditer(t)}
    return out


# よく出る一般的な語(これだけが一致しても同じ話題とはみなさない)
_GENERIC = {
    'claude', 'code', 'google', 'cloud', 'aws', 'azure', 'microsoft', 'openai', 'chatgpt', 'gpt', 'gemini',
    'anthropic', 'llm', 'api', 'mcp', 'preview', 'public', 'general', 'availability', 'available',
    'amazon', 'apple', 'iphone', 'android', 'windows', 'linux', 'python', 'github', 'docker', 'kubernetes',
    'エージェント', 'ブラックフライデー', 'セール', 'モデル', 'アプリ', 'ツール', 'クラウド', 'サーバー',
    'november', 'december', 'october', 'september', 'january', 'february', 'march', 'april', 'june', 'july', 'august',
}
_DATEISH = re.compile(r'\d+|(january|february|march|april|may|june|july|august|september|october|november|december)', re.I)


def same_topic(a, b, window_hours=72):
    """タイトルの文字 bigram の Jaccard 係数と、固有名詞の一致で判定する。"""
    pa, pb = a.get('published'), b.get('published')
    if pa and pb and abs(pa - pb) > timedelta(hours=window_hours):
        return False
    ta, tb = _norm_title(a), _norm_title(b)
    # 日付だけのタイトル(リリースノートなど)は束ねない
    if len(re.sub(r'[\W_]+', '', _DATEISH.sub('', ta))) < 6 or len(re.sub(r'[\W_]+', '', _DATEISH.sub('', tb))) < 6:
        return False
    ba, bb = _bigrams(ta), _bigrams(tb)
    if not ba or not bb:
        return False
    jac = len(ba & bb) / len(ba | bb)
    if jac >= 0.5:
        return True
    shared = {w for w in _proper_nouns(a) & _proper_nouns(b) if w.lower() not in _GENERIC}
    strong = {w for w in shared if len(w) >= 4 or re.search(r'[一-龥々]{3,}', w)}
    return (len(shared) >= 2 and jac >= 0.25) or (len(strong) >= 1 and jac >= 0.3)


def _rank(it):
    return (it.get('importance_score', 0) or 0, it.get('published').timestamp() if it.get('published') else 0)


def cluster_items(items):
    """同じ出来事を報じた記事を束ねる。代表(スコア最上位)に related=[...] を付け、
    ほかの記事に cluster_of=<代表のID> を付ける。人気記事(heat)とページの変化は対象外。"""
    pool = [it for it in items if it.get('profile') != 'heat' and it.get('kind') != 'change']
    parent = list(range(len(pool)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            if pool[i].get('source') == pool[j].get('source'):
                continue  # 同じソースの別記事は束ねない(連載・続報を潰さない)
            if same_topic(pool[i], pool[j]):
                parent[find(i)] = find(j)
    groups = {}
    for i, it in enumerate(pool):
        groups.setdefault(find(i), []).append(it)
    n = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=_rank, reverse=True)
        lead = members[0]
        lead['related'] = members[1:]
        for m in members[1:]:
            m['cluster_of'] = lead['id']
        n += 1
    return n


# ── Lv5 の相対評価 ────────────────────────────────────────────────────────

def cap_top_level(items, max_n=5, min_n=3):
    """Lv5 を「その日のスコア上位 max_n 件」に絞る。閾値で Lv5 になった記事が min_n 件に満たない場合は、
    Lv4 の上位から min_n 件まで繰り上げる。人気記事(heat)とページの変化は対象外。戻り値は Lv5 の件数。"""
    news = [it for it in items if it.get('profile') != 'heat' and it.get('kind') != 'change'
            and not it.get('cluster_of')]
    ranked = sorted(news, key=_rank, reverse=True)
    top = [it for it in ranked if it.get('importance') == 5]
    keep = set(id(it) for it in top[:max_n])
    if len(keep) < min_n:
        for it in ranked:
            if len(keep) >= min_n:
                break
            if it.get('importance') == 4:
                keep.add(id(it))
    for it in items:
        if it.get('kind') == 'change' or it.get('profile') == 'heat':
            continue
        if id(it) in keep:
            it['importance'] = 5
        elif it.get('importance') == 5:
            it['importance'] = 4
    return len(keep)
