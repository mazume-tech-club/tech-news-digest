import json
import re
import unittest
from datetime import datetime, timedelta, timezone

import curation as cu
import render

T = datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc)


def it(title, src='s', score=0.5, lv=3, bd=None, cat='security', **kw):
    d = {'title': title, 'url': f'https://e.com/{abs(hash((title, src)))}', 'source': src, 'category': cat,
         'published': T, 'importance': lv, 'importance_score': score, 'breakdown': bd, 'scored_by': 'jev' if bd else 'keyword'}
    d.update(kw)
    d['id'] = cu.article_id(d['url'])
    return d


class ArticleId(unittest.TestCase):
    def test_short_stable_cookie_safe(self):
        a = cu.article_id('https://example.com/a?x=1')
        self.assertEqual(a, cu.article_id('https://example.com/a?x=1'))
        self.assertRegex(a, r'^[0-9a-f]{7}$')
        self.assertNotEqual(a, cu.article_id('https://example.com/b'))

    def test_cookie_budget_for_7_days(self):
        # 1 件 = ID 7 文字 + 区切り 1 文字。1 日 65 件 × 7 日を読んでも、JS 側の上限 3,800 文字(4KB の手前)に収まる
        per_day = 5 + 1 + 65 * (cu.ID_LEN + 1) + 1
        self.assertLess(per_day * 7, 3800)
        self.assertIn('3800', render.BODY_JS)


class Keyword(unittest.TestCase):
    def test_prefers_quoted_then_product_name(self):
        self.assertEqual(cu.extract_keyword('プレイド「KARTE」への不正アクセス'), 'KARTE')
        self.assertEqual(cu.extract_keyword('Kubernetes 1.36 がリリース'), 'Kubernetes')
        self.assertEqual(cu.extract_keyword('東京電力、データセンター向け送電網を増強'), 'データセンター')


class FollowTopics(unittest.TestCase):
    def test_follow_uses_broad_topic_not_one_off_name(self):
        self.assertEqual(cu.follow_keyword({'title': 'マイナアプリに複数の脆弱性、最新版に更新を'}), 'マイナンバー')
        self.assertEqual(cu.follow_keyword({'title': 'Cloud Run で新機能が一般提供に'}), 'Google Cloud')
        self.assertEqual(cu.follow_keyword({'title': 'Claude Duet、日本でも利用可能に'}), 'Claude')
        x = {'title': '東京都「赤ちゃんファースト」で交換したQUOカードPayが使えなくなった件',
             'summary': 'リンベル公式オンラインストアで不正アクセス'}
        self.assertEqual(cu.follow_keyword(x), '情報漏えい')

    def test_topics_include_aliases_in_priority_order(self):
        self.assertEqual(cu.topics_of({'title': 'マイナアプリに複数の脆弱性'}), ['マイナンバー', '脆弱性'])
        self.assertEqual(cu.topics_of({'title': 'Lambda の料金改定'}), ['AWS', '料金改定'])

    def test_fallback_to_keyword(self):
        self.assertEqual(cu.follow_keyword({'title': '東京電力、データセンター向け送電網を増強'}), 'データセンター')


class ReasonLabels(unittest.TestCase):
    def test_text_rules_and_order(self):
        x = it('ランサムウェア攻撃で個人情報が流出', bd={'impact': 1.0, 'urgency': 1.0, 'novelty': 1.0, 'noise': 0})
        keys = cu.reason_keys(x)
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], 'leak')                 # 赤(crit)が先
        self.assertIn(cu.LABELS[keys[1]][1], ('crit',))

    def test_price_terms_eol_ga(self):
        self.assertEqual(cu.reason_keys(it('API の料金改定を発表'))[0], 'price')
        self.assertEqual(cu.reason_keys(it('利用規約の変更について'))[0], 'terms')
        self.assertEqual(cu.reason_keys(it('旧APIのサポート終了を予告'))[0], 'eol')
        self.assertEqual(cu.reason_keys(it('Cloud Run の新機能が一般提供に'))[0], 'ga')

    def test_breakdown_only(self):
        x = it('ある発表', bd={'impact': 0.67, 'urgency': 0.0, 'novelty': 1.0, 'noise': 0})
        self.assertEqual(cu.reason_keys(x), ['wide', 'fresh'])

    def test_every_lv3_plus_gets_a_label(self):
        for lv in (3, 4, 5):
            self.assertTrue(cu.reason_labels(it('特に何もない話', lv=lv)))
        self.assertEqual(cu.reason_labels(it('特に何もない話', lv=2)), [])

    def test_vuln_dropped_when_exploit(self):
        keys = cu.reason_keys(it('ゼロデイ脆弱性が悪用されている'))
        self.assertIn('exploit', keys)
        self.assertNotIn('vuln', keys)

    def test_heat_and_change(self):
        self.assertEqual(cu.reason_keys(it('Zenn記事', lv=4, profile='heat', likes=120)), ['hot'])
        ch = {'kind': 'change', 'change_kind': 'price', 'change_label': '料金'}
        self.assertIn('コスト', cu.why_text(ch))

    def test_why_text(self):
        self.assertIn('情報漏えい', cu.why_text(it('情報漏えいを公表')))
        self.assertIn('簡易判定', cu.why_text(it('情報漏えいを公表')))
        self.assertNotIn('簡易判定', cu.why_text(it('情報漏えいを公表', bd={'impact': 0, 'urgency': 0, 'novelty': 0, 'noise': 0})))


class Clustering(unittest.TestCase):
    def test_groups_same_event_across_sources(self):
        a = it('1Passwordに不正アクセス、顧客の氏名など流出', src='ITmedia', score=0.8)
        b = it('1Passwordへの不正アクセスについてまとめてみた', src='piyolog', score=0.6)
        c = it('Kubernetes 1.36 がリリース', src='Zenn', score=0.9)
        self.assertEqual(cu.cluster_items([a, b, c]), 1)
        self.assertEqual([r['id'] for r in a['related']], [b['id']])
        self.assertEqual(b['cluster_of'], a['id'])
        self.assertNotIn('related', c)

    def test_does_not_group_generic_or_date_titles(self):
        a = it('November 20, 2026', src='Cloud Run')
        b = it('November 21, 2026', src='GKE')
        c = it('Claude Codeのhooksで危険な命令は止められる？', src='Zenn')
        d = it('パナソニックのドアホンをClaude Codeに解析させた', src='Qiita')
        self.assertEqual(cu.cluster_items([a, b, c, d]), 0)

    def test_same_source_and_far_apart_not_grouped(self):
        a = it('OpenSSLにおける脆弱性に対するアップデート', src='JPCERT')
        b = it('OpenSSLにおける脆弱性に対するアップデート', src='JPCERT')
        c = it('OpenSSLにおける脆弱性に対するアップデート', src='JVN', published=T + timedelta(days=5))
        self.assertEqual(cu.cluster_items([a, b, c]), 0)

    def test_heat_and_changes_excluded(self):
        a = it('同じタイトルの記事です', src='A', profile='heat')
        b = it('同じタイトルの記事です', src='B')
        self.assertEqual(cu.cluster_items([a, b]), 0)


class TopLevelCap(unittest.TestCase):
    def test_caps_lv5_to_top_n(self):
        items = [it(f'記事{i}', score=0.7 + i / 100, lv=5) for i in range(29)]
        self.assertEqual(cu.cap_top_level(items, max_n=5), 5)
        lv5 = sorted((x for x in items if x['importance'] == 5), key=lambda x: -x['importance_score'])
        self.assertEqual(len(lv5), 5)
        self.assertAlmostEqual(lv5[-1]['importance_score'], 0.7 + 24 / 100)
        self.assertEqual(sum(1 for x in items if x['importance'] == 4), 24)

    def test_promotes_to_minimum(self):
        items = [it('a', score=0.9, lv=5), it('b', score=0.6, lv=4), it('c', score=0.55, lv=4), it('d', score=0.3, lv=3)]
        self.assertEqual(cu.cap_top_level(items, max_n=5, min_n=3), 3)
        self.assertEqual([x['importance'] for x in items], [5, 5, 5, 3])

    def test_heat_and_followers_untouched(self):
        h = it('h', score=0.99, lv=5, profile='heat')
        f = it('f', score=0.98, lv=5, cluster_of='x')
        items = [h, f] + [it(f'n{i}', score=0.5, lv=5) for i in range(3)]
        cu.cap_top_level(items, max_n=2, min_n=0)
        self.assertEqual(h['importance'], 5)
        self.assertEqual(f['importance'], 4)
        self.assertEqual(sum(1 for x in items[2:] if x['importance'] == 5), 2)


class PageRendering(unittest.TestCase):
    def build(self):
        a = it('1Passwordに不正アクセス、顧客の氏名など流出', src='ITmedia', score=0.8, lv=5)
        b = it('1Passwordへの不正アクセスについてまとめてみた', src='piyolog', score=0.6, lv=4)
        e = it('OpenAI ships a thing', src='OpenAI News', cat='ai', lv=3, summary='本文の要約', summary_src='body', title_ja='OpenAI が新機能')
        cu.cluster_items([a, b, e])
        chg = {'kind': 'change', 'change_kind': 'price', 'change_label': '料金', 'title': '[X] 料金表：$2', 'url': 'https://x/p',
               'source': 'X', 'category': '_changes', 'before': '$3', 'after': '$2', 'published': T, 'importance': 4, 'importance_score': .75}
        cats = [{'id': 'security', 'title': 'セキュリティ'}, {'id': 'ai', 'title': 'AI'}]
        return render.build_html([a, b, e], cats, {'show_per_category': 20},
                                 'https://o.github.io/tech-news-digest/archive/', changes=[chg], now=T), a, b

    def test_page_contains_design_parts(self):
        html, a, b = self.build()
        self.assertIn('前回以降の新着', html)
        self.assertIn('すべて既読にする', html)
        self.assertIn('ページの変化', html)
        self.assertIn('同じ話題 1件', html)
        self.assertIn('本文から要約', html)
        self.assertIn('「情報漏えい」をフォロー', html)
        self.assertIn('class="addf', html)            # 設定からキーワードを直接フォローできる
        self.assertIn('<s>$3</s>', html)
        self.assertIn('情報漏えい発生', html)       # 理由ラベルは一覧に常に表示(マウスオーバー不要)
        self.assertIn('重要な理由:', html)
        self.assertEqual(html.count(f'data-id="{b["id"]}"'), 0)  # 束ねられた記事は単独の行にしない

    def test_embedded_data_is_safe_and_has_cookie_ids(self):
        html, a, b = self.build()
        m = re.search(r'<script type="application/json" id="tnd-data">(.*?)</script>', html, re.S)
        data = json.loads(m.group(1))
        self.assertEqual(data['path'], '/tech-news-digest/')
        ids = {x['id'] for x in data['items']}
        self.assertIn(a['id'], ids)
        self.assertTrue(all(re.fullmatch(r'[0-9a-f]{7}', i) for i in ids))
        lead = next(x for x in data['items'] if x['id'] == a['id'])
        self.assertEqual(lead['rel'][0][3], b['id'])   # 代表を開くと関連記事も既読にする
        self.assertNotIn('</', m.group(1))
        self.assertIn('情報漏えい', lead['tp'])          # フォローは話題(別名込み)でも一致させる
        self.assertEqual(lead['fk'], '情報漏えい')

    def test_cookie_attributes(self):
        self.assertIn("SameSite=Lax", render.BODY_JS)
        self.assertIn("'; Secure'", render.BODY_JS)
        self.assertIn('Path=', render.BODY_JS)
        for name in ('tnd_r', 'tnd_w', 'tnd_follow', 'tnd_mute_src', 'tnd_mute_kw', 'tnd_theme'):
            self.assertIn(name, render.BODY_JS + render.HEAD_JS)

    def test_next_update_text(self):
        jst = timezone(timedelta(hours=9))
        self.assertEqual(render.next_update_text(datetime(2026, 11, 27, 4, 30, tzinfo=jst)), '次の更新は明日の朝です。')
        self.assertEqual(render.next_update_text(datetime(2026, 11, 27, 19, 5, tzinfo=jst)), '次の更新は明日の夜です。')


if __name__ == '__main__':
    unittest.main()
