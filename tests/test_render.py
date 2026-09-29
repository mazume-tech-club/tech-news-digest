import unittest
from datetime import datetime, timezone

import render


class LevelIndicator(unittest.TestCase):
    def test_level_and_accessible_label(self):
        html = render.level_indicator({'importance': 4})
        self.assertIn('Lv4', html)
        self.assertIn('aria-label="重要レベル 4(5段階)"', html)
        self.assertEqual(html.count('<i class="on">'), 4)
        self.assertEqual(html.count('<i class="">'), 1)

    def test_tooltip_includes_breakdown_and_confidence(self):
        html = render.level_indicator({
            'importance': 5, 'confidence': 0.876,
            'breakdown': {'impact': 1.0, 'urgency': 0.5, 'novelty': 0.0, 'noise': 0.1}})
        self.assertIn('影響範囲 100%', html)
        self.assertIn('Jev 確度 88%', html)

    def test_keyword_scored_tooltip(self):
        self.assertIn('簡易判定', render.level_indicator({'importance': 3, 'breakdown': None}))

    def test_out_of_range_is_clamped(self):
        self.assertIn('Lv5', render.level_indicator({'importance': 9}))
        self.assertIn('Lv1', render.level_indicator({'importance': 0}))


class Ranking(unittest.TestCase):
    def test_sorted_by_jev_score_not_bucket(self):
        t = datetime(2026, 9, 30, tzinfo=timezone.utc)
        a = {'importance': 4, 'importance_score': 0.69, 'published': t}
        b = {'importance': 4, 'importance_score': 0.55, 'published': t}
        c = {'importance': 5, 'importance_score': 0.71, 'published': t}
        ranked = sorted([b, c, a], key=render._rank_key, reverse=True)
        self.assertEqual(ranked, [c, a, b])

    def test_same_score_newer_first(self):
        old = {'importance_score': 0.5, 'published': datetime(2026, 9, 1, tzinfo=timezone.utc)}
        new = {'importance_score': 0.5, 'published': datetime(2026, 9, 2, tzinfo=timezone.utc)}
        self.assertEqual(sorted([old, new], key=render._rank_key, reverse=True), [new, old])


class SourceOptions(unittest.TestCase):
    def test_grouped_by_category_with_counts_and_escaped(self):
        items = [{'source': 'A & B', 'category': 'ai'}, {'source': 'A & B', 'category': 'ai'},
                 {'source': 'Zed', 'category': 'cloud'}]
        cats = [{'id': 'ai', 'title': 'AI'}, {'id': 'cloud', 'title': 'クラウド'}, {'id': 'gcp', 'title': 'GCP'}]
        html = render.source_options(items, cats)
        self.assertIn('<optgroup label="AI"><option value="A &amp; B">A &amp; B (2)</option></optgroup>', html)
        self.assertIn('label="クラウド"', html)
        self.assertNotIn('GCP', html)  # 記事のないカテゴリは出さない


if __name__ == '__main__':
    unittest.main()
