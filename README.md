# 📡 Tech News Digest

日本語テックサイトのRSSを毎日収集し、**Jev(TypeSafe AI)で重要度を判定**して、カテゴリ別・重要度順に表示する静的サイトです。
GitHub Actions で生成し、GitHub Pages(`gh-pages` ブランチ)で公開します。

**→ https://mazume-tech-club.github.io/tech-news-digest/**

## 特徴

- 📥 **RSSのみ収集** — 日本語サイトが中心。英語フィードは日本語タイトルに自動翻訳(原文も併記)
- 🎯 **重要度ランキング** — 記事ごとに Jev で「影響範囲・緊急性・新規性・宣伝度」を判定して合成し、重要度(最重要 / 重要 / 注目)の高い順にカテゴリ別で表示
- 🛟 **フォールバック** — Jev 未設定・障害・低確信度のときはキーワード判定で動作
- 📂 **アーカイブ** — `YYYY/MM/YYYY-MM-DD.html` として日別に保存
- 🤝 **コントリビューション** — `feeds.yml` を編集する Pull Request をマージするだけで収集対象を追加可能

## 収集対象の追加(コントリビューター向け)

[`feeds.yml`](./feeds.yml) に1行追加して PR を出してください。手順は [CONTRIBUTING.md](./CONTRIBUTING.md) を参照。
PR では `feeds.yml` の自動検証(形式・重複・URL到達性)が走り、`main` にマージされると自動でサイトが再生成されます。

## 構成

```
feeds.yml                       収集するRSS/カテゴリ/設定(ここを編集)
generate_news.py                収集 → 翻訳 → 重要度判定 → 出力
render.py                       閲覧UI(HTML/CSS/JS)。DADS参考・ダークモード・絞り込み
jev_client.py                   Jev API クライアント・合成スコア・キャッシュ・フォールバック
docs/jev-design.md              Jev 連携の設計
tests/                          単体テスト
scripts/validate_feeds.py       feeds.yml の検証(PR時)
.github/workflows/
  daily-news.yml                毎日19:05 JST / main への反映時 / 手動 → gh-pages へデプロイ
  validate-feeds.yml            PR で feeds.yml を検証
```

## セットアップ(管理者向け)

1. **Settings → Pages** → Source: `Deploy from a branch` / Branch: `gh-pages` `/ (root)`
   (`gh-pages` ブランチは初回の Actions 実行で自動作成されます。先に **Actions → Daily Tech News Digest → Run workflow** を実行してください)
2. **Settings → Secrets and variables → Actions** に登録
   - `JEV_API_KEY` — Jev API キー([typesafe.ai](https://typesafe.ai) で発行)
   - `NTFY_TOPIC` — (任意) [ntfy.sh](https://ntfy.sh/) 通知用トピック
3. **Settings → Actions → General → Workflow permissions** を `Read and write permissions` にする
4. (推奨) **Settings → Branches** で `main` を保護し、PR + レビュー必須にする

## Jev 連携について

記事 1 件ごとに Jev API を 1 回呼び、複数の観点(影響範囲・緊急性・新規性・宣伝度)を並列に判定して、コードで重み付き合成します。
設計・質問定義・閾値・コストは [docs/jev-design.md](./docs/jev-design.md) を参照してください。

## ローカル実行

```bash
pip install -r requirements.txt
python generate_news.py        # dist/ に出力(JEV_API_KEY 未設定ならキーワード判定)
python scripts/validate_feeds.py
python -m unittest discover -s tests -t .
```
