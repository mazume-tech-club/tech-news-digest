import unittest

import render


class ConfidenceMeter(unittest.TestCase):
    def test_percentage_and_accessible_label(self):
        html = render.confidence_meter({'confidence': 0.876})
        self.assertIn('確度 88%', html)
        self.assertIn('aria-label="Jev の確度 88パーセント"', html)
        self.assertIn('width:88%', html)
        self.assertNotIn('low', html)

    def test_low_confidence_is_flagged(self):
        self.assertIn('conf low', render.confidence_meter({'confidence': 0.2}))

    def test_keyword_scored_item_shows_simple_label(self):
        self.assertIn('簡易判定', render.confidence_meter({'confidence': None}))
        self.assertIn('簡易判定', render.confidence_meter({}))

    def test_out_of_range_is_clamped(self):
        self.assertIn('width:100%', render.confidence_meter({'confidence': 1.7}))
        self.assertIn('width:0%', render.confidence_meter({'confidence': -0.3}))


if __name__ == '__main__':
    unittest.main()
