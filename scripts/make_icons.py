#!/usr/bin/env python3
"""アプリアイコン(PNG/ICO)を生成する。assets/favicon.svg と同じ図形を Pillow で描く。

    pip install pillow
    python scripts/make_icons.py

生成物は assets/ にコミット済み。デザインを変えたときだけ再生成する(CIでは実行しない)。

  assets/apple-touch-icon.png        180x180  iOS のホーム画面(角丸は iOS が付けるので全面塗り)
  assets/icons/icon-192.png          192x192  Android / PWA(purpose: any・角丸)
  assets/icons/icon-512.png          512x512  同上
  assets/icons/icon-maskable-512.png 512x512  Android のマスク対応(全面塗り+中央の安全領域に図形)
  assets/favicon.ico                 16/32/48 古いブラウザ用
"""
import os

from PIL import Image, ImageDraw

BLUE = (0, 49, 216, 255)   # #0031d8
WHITE = (255, 255, 255, 255)
SS = 8                     # スーパーサンプリング(アンチエイリアス用)
# favicon.svg(viewBox 64)の図形。中心 (14,50) の円弧2本 + 点
CX0, CY0 = 14, 50
GLYPH_CENTER = (32.5, 30)  # 図形の外接ボックスの中心(SVG座標)


def draw_icon(size, rounded=True, glyph_scale=1.0):
    big = size * SS
    img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * 12 // 64, fill=BLUE)
    else:
        d.rectangle([0, 0, big, big], fill=BLUE)

    k = big / 64 * glyph_scale
    ox = big / 2 - GLYPH_CENTER[0] * k
    oy = big / 2 - GLYPH_CENTER[1] * k

    def P(x, y):
        return ox + x * k, oy + y * k

    stroke = 6 * k
    for r in (23, 37):
        cx, cy = P(CX0, CY0)
        half = r * k + stroke / 2  # Pillow は線を bbox の内側に描くので、中心線が半径 r になるよう外側へ広げる
        d.arc([cx - half, cy - half, cx + half, cy + half], start=270, end=360, width=round(stroke), fill=WHITE)
        for x, y in ((CX0, CY0 - r), (CX0 + r, CY0)):  # 丸い端
            px, py = P(x, y)
            d.ellipse([px - stroke / 2, py - stroke / 2, px + stroke / 2, py + stroke / 2], fill=WHITE)
    px, py = P(19, 45)
    d.ellipse([px - 5 * k, py - 5 * k, px + 5 * k, py + 5 * k], fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
    os.makedirs(os.path.join(root, 'icons'), exist_ok=True)
    draw_icon(180, rounded=False, glyph_scale=1.15).convert('RGB').save(os.path.join(root, 'apple-touch-icon.png'), optimize=True)
    draw_icon(192, rounded=True, glyph_scale=1.15).save(os.path.join(root, 'icons', 'icon-192.png'), optimize=True)
    draw_icon(512, rounded=True, glyph_scale=1.15).save(os.path.join(root, 'icons', 'icon-512.png'), optimize=True)
    # maskable: 中央 80% の円に収まるよう図形を小さめにする
    draw_icon(512, rounded=False, glyph_scale=0.95).save(os.path.join(root, 'icons', 'icon-maskable-512.png'), optimize=True)
    ico = draw_icon(256, rounded=True, glyph_scale=1.15)
    ico.save(os.path.join(root, 'favicon.ico'), sizes=[(16, 16), (32, 32), (48, 48)])
    print('generated icons in', os.path.normpath(root))


if __name__ == '__main__':
    main()
