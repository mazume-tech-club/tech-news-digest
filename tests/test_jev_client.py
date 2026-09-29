import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

import jev_client as jc


def answers(impact, urgency, novelty, noise, conf=0.9):
    return {
        'impact': {'type': 'score', 'score': impact, 'confidence': conf},
        'urgency': {'type': 'score', 'score': urgency, 'confidence': conf},
        'novelty': {'type': 'score', 'score': novelty, 'confidence': conf},
        'noise': {'type': 'noul', 'noul': noise},
    }


def item(url='https://e.com/1', category='security', title='t'):
    return {'title': title, 'summary': '', 'url': url, 'source': 's', 'category': category,
            'published': datetime(2026, 9, 29, tzinfo=timezone.utc)}


class Compose(unittest.TestCase):
    def test_max_and_min(self):
        s, _, _ = jc.compose(answers(3, 3, 2, 0.0), 'security')
        self.assertAlmostEqual(s, 1.0)
        self.assertEqual(jc.level_from_score(s), 5)
        s, _, _ = jc.compose(answers(0, 0, 0, 0.0), 'security')
        self.assertEqual(jc.level_from_score(s), 1)

    def test_noise_lowers_score(self):
        a, _, _ = jc.compose(answers(3, 3, 2, 0.0), 'general')
        b, _, _ = jc.compose(answers(3, 3, 2, 1.0), 'general')
        self.assertAlmostEqual(b, a * 0.5)

    def test_category_weights_differ(self):
        urgent = answers(0, 3, 0, 0.0)
        sec, _, _ = jc.compose(urgent, 'security')
        gen, _, _ = jc.compose(urgent, 'general')
        self.assertGreater(sec, gen)

    def test_missing_answer_returns_none(self):
        bad = answers(1, 1, 1, 0.0)
        del bad['urgency']
        self.assertIsNone(jc.compose(bad, 'ai'))

    def test_weights_sum_to_one(self):
        for w in jc.WEIGHTS.values():
            self.assertAlmostEqual(sum(w.values()), 1.0)


class ScoreItems(unittest.TestCase):
    def test_no_key_uses_keyword(self):
        with mock.patch.dict(os.environ, {'JEV_API_KEY': ''}):
            items = jc.score_items([item(title='ゼロデイ脆弱性が悪用されている')])
        self.assertEqual(items[0]['scored_by'], 'keyword')
        self.assertEqual(items[0]['importance'], 5)

    def test_jev_success_and_cache(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'JEV_API_KEY': 'k'}):
            cache = os.path.join(d, 'c.json')
            with mock.patch.object(jc, 'call_jev', return_value=answers(3, 3, 2, 0.0)) as m:
                items = jc.score_items([item()], cache_out=cache)
                self.assertEqual(m.call_count, 1)
            self.assertEqual(items[0]['importance'], 5)
            self.assertEqual(items[0]['scored_by'], 'jev')
            # 2 回目はキャッシュから取得し API を呼ばない
            with mock.patch.object(jc, 'call_jev') as m:
                items = jc.score_items([item()], cache_in=cache, cache_out=cache)
                m.assert_not_called()
            self.assertEqual(items[0]['importance'], 5)

    def test_auth_error_falls_back_and_stops_calling(self):
        with mock.patch.dict(os.environ, {'JEV_API_KEY': 'bad'}), \
             mock.patch.object(jc, 'call_jev', side_effect=jc.AuthError('HTTP 401')) as m, \
             mock.patch.object(jc, 'MAX_WORKERS', 1):
            items = jc.score_items([item(url=f'https://e.com/{i}') for i in range(5)])
        self.assertEqual(m.call_count, 1)  # 2 件目以降は呼ばない
        self.assertTrue(all(i['scored_by'] == 'keyword' for i in items))

    def test_api_error_falls_back_per_item(self):
        with mock.patch.dict(os.environ, {'JEV_API_KEY': 'k'}), \
             mock.patch.object(jc, 'call_jev', side_effect=RuntimeError('boom')):
            items = jc.score_items([item()])
        self.assertEqual(items[0]['scored_by'], 'keyword')

    def test_low_confidence_blends_keyword(self):
        with mock.patch.dict(os.environ, {'JEV_API_KEY': 'k'}), \
             mock.patch.object(jc, 'call_jev', return_value=answers(3, 3, 2, 0.0, conf=0.1)):
            items = jc.score_items([item(title='入門解説')])
        self.assertEqual(items[0]['scored_by'], 'jev+keyword')
        self.assertLess(items[0]['importance_score'], 1.0)


class CallJev(unittest.TestCase):
    def test_retries_on_429_then_succeeds(self):
        r429 = mock.Mock(status_code=429, headers={'Retry-After': '0'})
        ok = mock.Mock(status_code=200, headers={})
        ok.raise_for_status = lambda: None
        ok.json = lambda: {'answers': {'x': 1}}
        session = mock.Mock()
        session.post.side_effect = [r429, ok]
        self.assertEqual(jc.call_jev(item(), 'k', session=session), {'x': 1})
        self.assertEqual(session.post.call_count, 2)
        kwargs = session.post.call_args.kwargs
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer k')
        self.assertEqual(set(kwargs['json']['questions']), {'impact', 'urgency', 'novelty', 'noise'})

    def test_401_raises_auth_error(self):
        session = mock.Mock()
        session.post.return_value = mock.Mock(status_code=401, headers={})
        with self.assertRaises(jc.AuthError):
            jc.call_jev(item(), 'k', session=session)


if __name__ == '__main__':
    unittest.main()
