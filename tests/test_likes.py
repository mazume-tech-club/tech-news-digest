import unittest
from datetime import datetime, timezone
from unittest import mock

import generate_news as gn
import render


def fake_response(payload):
    r = mock.Mock()
    r.raise_for_status = lambda: None
    r.json = lambda: payload
    return r


class FetchLikes(unittest.TestCase):
    def test_zenn(self):
        item = {'likes_src': 'zenn', 'url': 'https://zenn.dev/someone/articles/abc-123?x=1'}
        with mock.patch.object(gn.requests, 'get', return_value=fake_response({'article': {'liked_count': 42}})) as g:
            self.assertEqual(gn.fetch_likes(item), 42)
        self.assertEqual(g.call_args.args[0], 'https://zenn.dev/api/articles/abc-123')

    def test_qiita_with_optional_token(self):
        item = {'likes_src': 'qiita', 'url': 'https://qiita.com/someone/items/0a1b2c3d4e5f'}
        with mock.patch.dict(gn.os.environ, {'QIITA_TOKEN': 't'}), \
             mock.patch.object(gn.requests, 'get', return_value=fake_response({'likes_count': 7})) as g:
            self.assertEqual(gn.fetch_likes(item), 7)
        self.assertEqual(g.call_args.args[0], 'https://qiita.com/api/v2/items/0a1b2c3d4e5f')
        self.assertEqual(g.call_args.kwargs['headers']['Authorization'], 'Bearer t')

    def test_failure_and_unmatched_url_return_none(self):
        with mock.patch.object(gn.requests, 'get', side_effect=RuntimeError('x')):
            self.assertIsNone(gn.fetch_likes({'likes_src': 'zenn', 'url': 'https://zenn.dev/u/articles/a'}))
        self.assertIsNone(gn.fetch_likes({'likes_src': 'zenn', 'url': 'https://example.com/other'}))
        self.assertIsNone(gn.fetch_likes({'url': 'https://zenn.dev/u/articles/a'}))  # likes 未指定

    def test_enrich_only_targets_marked_feeds(self):
        items = [{'likes_src': 'zenn', 'url': 'https://zenn.dev/u/articles/a'}, {'url': 'https://e.com/1'}]
        with mock.patch.object(gn, 'fetch_likes', return_value=5):
            gn.enrich_likes(items)
        self.assertEqual(items[0]['likes'], 5)
        self.assertNotIn('likes', items[1])


class Rendering(unittest.TestCase):
    def test_chip(self):
        self.assertEqual(render.likes_chip({}), '')
        self.assertEqual(render.likes_chip({'likes': None}), '')
        html = render.likes_chip({'likes': 1234})
        self.assertIn('<b>1,234</b>', html)
        self.assertIn('aria-label="いいね 1234件"', html)
        self.assertIn('hot', html)
        self.assertNotIn('hot', render.likes_chip({'likes': 3}))

    def test_section_sorted_by_likes_when_configured(self):
        t = datetime(2026, 9, 30, tzinfo=timezone.utc)
        base = {'category': 'trend', 'source': 's', 'published': t, 'importance': 2, 'importance_score': 0.9}
        items = [dict(base, url='u1', title='low', likes=3), dict(base, url='u2', title='high', likes=99),
                 dict(base, url='u3', title='none', likes=None)]
        html = render.category_section({'id': 'trend', 'title': 'T', 'sort': 'likes'}, items, 20)
        self.assertLess(html.index('>high<'), html.index('>low<'))
        self.assertLess(html.index('>low<'), html.index('>none<'))
        self.assertIn('いいね数の多い順', html)
        self.assertNotIn('いいね数の多い順', render.category_section({'id': 'x', 'title': 'X'}, items, 20))


if __name__ == '__main__':
    unittest.main()
