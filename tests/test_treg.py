import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import enrich
import treg_client as tc


def resp(status=200, payload=None, headers=None):
    r = mock.Mock()
    r.status_code = status
    r.headers = headers or {}
    r.json = lambda: payload if payload is not None else {}
    return r


class Client(unittest.TestCase):
    def test_disabled_without_key_or_url(self):
        with mock.patch.dict(os.environ, {'TREG_API_KEY': '', 'TREG_API_URL': ''}):
            c = tc.TregClient()
        self.assertFalse(c.enabled)
        self.assertIn('TREG_API_KEY', c.reason_disabled())
        self.assertIsNone(c.call('litescrape.web.fetch.post', {'url': 'https://e.com'}))
        self.assertEqual(c.calls, 0)

    def test_max_cost_header_and_url(self):
        s = mock.Mock()
        s.post.return_value = resp(200, {'content': 'x'})
        c = tc.TregClient('k', 'https://gw.example/v1/call', session=s)
        self.assertEqual(c.call('litescrape.web.fetch.post', {'url': 'u'}), {'content': 'x'})
        args, kw = s.post.call_args
        self.assertEqual(args[0], 'https://gw.example/v1/call/litescrape.web.fetch.post')
        self.assertEqual(kw['headers']['X-Treg-Route-Max-Cost'], '0.000150')
        self.assertEqual(kw['headers']['Authorization'], 'Bearer k')
        c2 = tc.TregClient('k', 'https://gw.example/{endpoint}/run', session=s)
        self.assertEqual(c2.url_for('a.b'), 'https://gw.example/a.b/run')

    def test_budget_stops_further_calls(self):
        s = mock.Mock()
        s.post.return_value = resp(200, {'content': 'x'})
        c = tc.TregClient('k', 'https://gw', budget_usd=0.0065, session=s)
        self.assertEqual(c.affordable('litescrape.web.fetch.post'), 43)
        for _ in range(50):
            c.call('litescrape.web.fetch.post', {'url': 'u'})
        self.assertEqual(c.calls, 43)
        self.assertEqual(c.skipped_budget, 7)
        self.assertLessEqual(c.spent, 0.0065)
        self.assertIn('予算超過で中止 7', c.summary())

    def test_actual_cost_from_response_and_failures_free(self):
        s = mock.Mock()
        s.post.side_effect = [resp(200, {'status': 200, 'body': {'content': 'x'}, 'cost_usd': 0.0001}),
                              resp(500), resp(200, {'content': 'y'}, {'X-Treg-Cost': '0.00012'})]
        c = tc.TregClient('k', 'https://gw', session=s)
        self.assertEqual(c.call('litescrape.web.fetch.post', {}), {'content': 'x'})  # 包まれた応答は中身を返す
        self.assertIsNone(c.call('litescrape.web.fetch.post', {}))
        c.call('litescrape.web.fetch.post', {})
        self.assertAlmostEqual(c.spent, 0.00022)
        self.assertEqual((c.ok, c.failed), (2, 1))

    def test_auth_error_disables(self):
        s = mock.Mock()
        s.post.return_value = resp(401)
        c = tc.TregClient('k', 'https://gw', session=s)
        c.call('litescrape.web.fetch.post', {})
        self.assertFalse(c.enabled)
        c.call('litescrape.web.fetch.post', {})
        self.assertEqual(s.post.call_count, 1)

    def test_exception_is_logged_without_secret(self):
        s = mock.Mock()
        s.post.side_effect = RuntimeError('secret-key-in-message')
        c = tc.TregClient('secret-key', 'https://gw', session=s)
        with mock.patch('sys.stderr') as err:
            self.assertIsNone(c.call('litescrape.web.fetch.post', {}))
        self.assertNotIn('secret', ''.join(str(x) for x in err.write.call_args_list))


class FakeClient:
    """fetch_page が呼ぶ call() を差し替える。"""
    def __init__(self, pages, budget_calls=100):
        self.pages, self.enabled, self.calls, self.left = pages, True, 0, budget_calls

    def call(self, endpoint, body=None, query=None, price_usd=None):
        self.calls += 1
        md = self.pages.get(body['url'])
        return {'content': md} if md else None

    def affordable(self, endpoint):
        return self.left

    def reason_disabled(self):
        return ''


ARTICLE = """# Title

Menu Home Blog

Today we are releasing a new model that is faster and cheaper for developers. It supports long context and tool use.

Another paragraph with more details about the release and availability in the API.
"""


class Bodies(unittest.TestCase):
    def test_summary_cache_limit_and_failure(self):
        now = datetime(2026, 11, 27, tzinfo=timezone.utc)
        items = [{'url': f'https://e.com/{i}', 'summary': '', 'lang': 'en', 'published': now - timedelta(hours=i)} for i in range(5)]
        items.append({'url': 'https://e.com/has', 'summary': 'RSS の概要がある記事なので本文は取得しない', 'published': now})
        items.append({'url': 'https://e.com/heat', 'summary': '', 'profile': 'heat', 'published': now})
        fc = FakeClient({f'https://e.com/{i}': ARTICLE for i in range(4)})  # /4 は失敗
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'body.json')
            n = enrich.fetch_bodies(items, fc, cache_out=out, now=now, limit=20, translate=lambda s: '[ja]' + s)
            self.assertEqual(n, 4)
            self.assertEqual(fc.calls, 5)
            self.assertEqual(items[0]['summary_src'], 'body')
            self.assertTrue(items[0]['summary'].startswith('[ja]Today we are releasing'))
            self.assertLessEqual(len(items[0]['summary']), 110)
            self.assertNotIn('summary_src', items[4])  # 失敗 → タイトルのみ
            self.assertNotIn('summary_src', items[5])
            # 2 回目: キャッシュから。失敗した記事だけ再挑戦し、2 回失敗したら以後取得しない
            again = [dict(x, summary='') if x['url'].endswith(('/0', '/4')) else x for x in items[:5]]
            fc2 = FakeClient({})
            enrich.fetch_bodies(again, fc2, cache_in=out, cache_out=out, now=now)
            self.assertEqual(fc2.calls, 1)
            self.assertEqual(again[0]['summary_src'], 'body')
            fc3 = FakeClient({})
            enrich.fetch_bodies([dict(items[4], summary='')], fc3, cache_in=out, cache_out=out, now=now)
            self.assertEqual(fc3.calls, 0)

    def test_daily_limit_and_budget(self):
        items = [{'url': f'https://e.com/{i}', 'summary': ''} for i in range(30)]
        fc = FakeClient({x['url']: ARTICLE for x in items}, budget_calls=12)
        enrich.fetch_bodies(items, fc, limit=20, translate=lambda s: s)
        self.assertEqual(fc.calls, 12)
        fc = FakeClient({x['url']: ARTICLE for x in items})
        enrich.fetch_bodies([dict(x, summary='') for x in items], fc, limit=20, translate=lambda s: s)
        self.assertEqual(fc.calls, 20)


class Watches(unittest.TestCase):
    W = [{'name': 'Status', 'url': 'https://s.example/', 'kind': 'status'}]

    def test_baseline_then_diff_ignores_timestamps(self):
        t0 = datetime(2026, 11, 26, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'snap.json')
            fc = FakeClient({'https://s.example/': 'All Systems Operational\nUpdated 3 minutes ago\nLast check 10:21 UTC'})
            self.assertEqual(enrich.check_watches(self.W, fc, None, p, now=t0), [])  # 初回は基準を保存するだけ
            fc = FakeClient({'https://s.example/': 'All Systems Operational\nUpdated 9 minutes ago\nLast check 11:40 UTC'})
            self.assertEqual(enrich.check_watches(self.W, fc, p, p, now=t0 + timedelta(hours=21)), [])  # 時刻だけの変化は無視
            fc = FakeClient({'https://s.example/': 'Partial outage in Tokyo region\nUpdated 1 minutes ago\nLast check 09:00 UTC'})
            out = enrich.check_watches(self.W, fc, p, p, now=t0 + timedelta(hours=42))
            self.assertEqual(len(out), 1)
            ch = out[0]
            self.assertEqual(ch['change_label'], '障害')
            self.assertEqual(ch['before'], 'All Systems Operational')
            self.assertEqual(ch['after'], 'Partial outage in Tokyo region')
            self.assertIn('[Status] ステータス', ch['title'])
            # 同じ日にもう一度実行してもページを取り直さず、検知済みの変化は表示し続ける
            fc = FakeClient({})
            out = enrich.check_watches(self.W, fc, p, p, now=t0 + timedelta(hours=43))
            self.assertEqual(fc.calls, 0)
            self.assertEqual(len(out), 1)
            # 36 時間を過ぎたら表示しない
            self.assertEqual(enrich.check_watches(self.W, FakeClient({}), p, p, now=t0 + timedelta(hours=80)), [])

    def test_fetch_failure_keeps_previous(self):
        t0 = datetime(2026, 11, 26, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'snap.json')
            enrich.check_watches(self.W, FakeClient({'https://s.example/': 'Operational status line'}), None, p, now=t0)
            enrich.check_watches(self.W, FakeClient({}), p, p, now=t0 + timedelta(days=1))
            out = enrich.check_watches(self.W, FakeClient({'https://s.example/': 'Major outage status line'}), p, p,
                                       now=t0 + timedelta(days=2))
            self.assertEqual(out[0]['before'], 'Operational status line')

    def test_disabled_client_keeps_snapshots(self):
        t0 = datetime(2026, 11, 26, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'snap.json')
            enrich.check_watches(self.W, FakeClient({'https://s.example/': 'Operational status line'}), None, p, now=t0)
            off = tc.TregClient('', '')
            self.assertEqual(enrich.check_watches(self.W, off, p, p, now=t0 + timedelta(days=1)), [])
            out = enrich.check_watches(self.W, FakeClient({'https://s.example/': 'Major outage status line'}), p, p,
                                       now=t0 + timedelta(days=2))
            self.assertEqual(len(out), 1)


if __name__ == '__main__':
    unittest.main()
