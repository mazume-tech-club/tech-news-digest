"""
Treg(API ゲートウェイ)クライアント。設計は docs/treg-design.md を参照。

- GitHub Actions から HTTP で呼ぶ。API キーは環境変数 TREG_API_KEY(Secrets)
- 呼び出し先は環境変数 TREG_API_URL(Actions の Variables)。`{endpoint}` を含めばそこにエンドポイントIDを入れ、
  含まなければ末尾に `/<エンドポイントID>` を付ける
- すべての呼び出しに料金上限(X-Treg-Route-Max-Cost)を付ける
- 1 回の実行の合計(見込み額で積算)が予算を超えそうなら、それ以降の呼び出しを止める
- キー/URL 未設定・認証エラー・失敗時は None を返す(呼び出し側は今まで通りの処理を続ける)
"""

import os
import sys
import threading

import requests

DEFAULT_BUDGET_USD = 0.0065   # 1 日 約1円
TIMEOUT = 95                  # litescrape の timeout(最大 90 秒)+ 余裕

# カタログ上の単価(USD/成功1回)。予算の積算はこの見込み額で行い、実費が返ってきたら実費で精算する。
PRICES = {
    'litescrape.web.fetch.post': 0.00015,
}


class TregClient:
    def __init__(self, key=None, base_url=None, budget_usd=None, session=None):
        self.key = (os.environ.get('TREG_API_KEY', '') if key is None else key).strip()
        self.base_url = (os.environ.get('TREG_API_URL', '') if base_url is None else base_url).strip()
        if budget_usd is None:
            budget_usd = float(os.environ.get('TREG_BUDGET_USD', '') or DEFAULT_BUDGET_USD)
        self.budget = budget_usd
        self.session = session or requests
        self.spent = 0.0          # 精算済みの金額
        self.reserved = 0.0       # 実行中の呼び出しの見込み額
        self.calls = 0            # 実際に送ったリクエスト数
        self.ok = 0
        self.failed = 0
        self.skipped_budget = 0   # 予算超過で送らなかった数
        self.auth_failed = False
        self._lock = threading.Lock()

    # ── 状態 ──────────────────────────────────────────────────────────────
    @property
    def enabled(self):
        return bool(self.key and self.base_url) and not self.auth_failed

    def reason_disabled(self):
        if not self.key:
            return 'TREG_API_KEY 未設定'
        if not self.base_url:
            return 'TREG_API_URL 未設定'
        if self.auth_failed:
            return '認証エラー'
        return ''

    def url_for(self, endpoint_id):
        if '{endpoint}' in self.base_url:
            return self.base_url.replace('{endpoint}', endpoint_id)
        return f"{self.base_url.rstrip('/')}/{endpoint_id}"

    # ── 予算 ──────────────────────────────────────────────────────────────
    def _reserve(self, price):
        with self._lock:
            if self.spent + self.reserved + price > self.budget + 1e-12:
                self.skipped_budget += 1
                return False
            self.reserved += price
            self.calls += 1
            return True

    def _settle(self, price, charged, ok):
        with self._lock:
            self.reserved -= price
            self.spent += charged
            if ok:
                self.ok += 1
            else:
                self.failed += 1

    def affordable(self, endpoint_id):
        """残りの予算で、あと何回 endpoint_id を呼べるか。"""
        if not self.enabled:
            return 0
        price = PRICES.get(endpoint_id, 0.0)
        if price <= 0:
            return 10 ** 6
        left = self.budget - self.spent - self.reserved
        return max(0, int(left / price + 1e-9))

    # ── 呼び出し ──────────────────────────────────────────────────────────
    def call(self, endpoint_id, body=None, query=None, price_usd=None):
        """1 回呼んで JSON(dict)を返す。未設定・予算超過・失敗は None。"""
        if not self.enabled:
            return None
        price = PRICES.get(endpoint_id, 0.0) if price_usd is None else price_usd
        if not self._reserve(price):
            return None
        headers = {
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json',
            # 見込み額より高い見積もりなら、課金前に 402 で断ってもらう
            'X-Treg-Route-Max-Cost': f'{price:.6f}',
        }
        charged, ok, data = 0.0, False, None
        try:
            resp = self.session.post(self.url_for(endpoint_id), json=body or {}, params=query,
                                     headers=headers, timeout=TIMEOUT)
            if resp.status_code in (401, 403):
                self.auth_failed = True
            elif 200 <= resp.status_code < 300:
                data = resp.json()
                ok = True
                charged = _charged(resp, data, price)
                if isinstance(data, dict) and isinstance(data.get('body'), dict) and 'status' in data:
                    data = data['body']  # ゲートウェイが {status, body, cost_usd} で包んで返す場合
        except Exception as e:  # キーやレスポンス本文は出力しない
            print(f'  [WARN] Treg {endpoint_id}: {type(e).__name__}', file=sys.stderr)
        finally:
            self._settle(price, charged, ok)
        return data

    def summary(self):
        return (f'Treg: 呼び出し {self.calls}回(成功 {self.ok} / 失敗 {self.failed} / '
                f'予算超過で中止 {self.skipped_budget})  合計 ${self.spent:.5f} / 上限 ${self.budget:.4f}')


def _charged(resp, data, price):
    """実費。ヘッダー → 本文の cost_usd → 見込み額 の順に採用する(成功課金なので成功時のみ)。"""
    for h in ('X-Treg-Cost', 'X-Treg-Cost-Usd', 'X-Treg-Charge-Usd'):
        v = resp.headers.get(h) if hasattr(resp, 'headers') else None
        if v:
            try:
                return float(v)
            except ValueError:
                pass
    if isinstance(data, dict) and isinstance(data.get('cost_usd'), (int, float)):
        return float(data['cost_usd'])
    return price


def fetch_page(client, url, max_tokens=2000):
    """litescrape でページ本文(Markdown)を取得する。失敗時は None。"""
    data = client.call('litescrape.web.fetch.post', query={'timeout': 60}, body={
        'url': url, 'respond_with': 'content', 'retain_images': 'none', 'retain_links': 'none',
        'remove_overlay': True, 'max_tokens': max_tokens,
    })
    if isinstance(data, dict):
        text = data.get('content') or data.get('text')
        if isinstance(text, str) and text.strip():
            return text
    return None
