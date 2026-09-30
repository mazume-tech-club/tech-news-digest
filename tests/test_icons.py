import json
import os
import struct
import unittest

import render

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    assert head[:8] == b'\x89PNG\r\n\x1a\n', f'not a PNG: {path}'
    return struct.unpack('>II', head[16:24])


class Assets(unittest.TestCase):
    def test_png_sizes(self):
        self.assertEqual(png_size(os.path.join(ASSETS, 'apple-touch-icon.png')), (180, 180))
        self.assertEqual(png_size(os.path.join(ASSETS, 'icons', 'icon-192.png')), (192, 192))
        self.assertEqual(png_size(os.path.join(ASSETS, 'icons', 'icon-512.png')), (512, 512))
        self.assertEqual(png_size(os.path.join(ASSETS, 'icons', 'icon-maskable-512.png')), (512, 512))

    def test_favicons_exist(self):
        with open(os.path.join(ASSETS, 'favicon.ico'), 'rb') as f:
            self.assertEqual(f.read(4), b'\x00\x00\x01\x00')  # ICO ヘッダー
        self.assertTrue(os.path.getsize(os.path.join(ASSETS, 'favicon.svg')) > 0)

    def test_manifest_icons_exist_and_match_declared_size(self):
        with open(os.path.join(ASSETS, 'manifest.webmanifest'), encoding='utf-8') as f:
            m = json.load(f)
        self.assertLessEqual(len(m['short_name']), 12)
        self.assertEqual(m['display'], 'standalone')
        purposes = set()
        for icon in m['icons']:
            path = os.path.join(ASSETS, *icon['src'].split('/'))
            self.assertTrue(os.path.exists(path), icon['src'])
            if icon['type'] == 'image/png':
                w, h = icon['sizes'].split('x')
                self.assertEqual(png_size(path), (int(w), int(h)))
            purposes.add(icon['purpose'])
        self.assertEqual(purposes, {'any', 'maskable'})


class HeadTags(unittest.TestCase):
    def test_head_icons_use_absolute_urls_for_every_page_depth(self):
        html = render.head_icons('https://example.github.io/repo/')
        for needle in ('href="https://example.github.io/repo/favicon.svg"',
                       'href="https://example.github.io/repo/favicon.ico"',
                       'rel="apple-touch-icon" href="https://example.github.io/repo/apple-touch-icon.png"',
                       'rel="manifest" href="https://example.github.io/repo/manifest.webmanifest"',
                       'name="apple-mobile-web-app-title"', 'name="theme-color"'):
            self.assertIn(needle, html)

    def test_pages_include_icons(self):
        page = render.build_archive_index({'2026-09-30'}, 'https://example.github.io/repo')
        self.assertIn('apple-touch-icon', page)
        cats = [{'id': 'ai', 'title': 'AI'}]
        items = [{'title': 't', 'url': 'https://e.com', 'source': 's', 'category': 'ai', 'summary': '',
                  'published': None, 'importance': 3}]
        main = render.build_html(items, cats, {'show_per_category': 20}, 'https://example.github.io/repo/archive/')
        self.assertIn('href="https://example.github.io/repo/apple-touch-icon.png"', main)


if __name__ == '__main__':
    unittest.main()
