# 📡 Tech News Digest

日本語テックサイトのRSSを毎日収集し、**JEV API で重要度を判定**して、カテゴリ別・重要度順に表示する静的サイトです。
GitHub Actions で生成し、GitHub Pages(`gh-pages` ブランチ)で公開します。

**→ https://mazume-tech-club.github.io/tech-news-digest/**

## 特徴

- 📥 **RSSのみ収集** — 日本語サイトが中心。英語フィードは日本語タイトルに自動翻訳(原文も併記)
- 🎯 **重要度ランキング** — JEV API が 1〜5 で判定。カテゴリごとに重要度の高い順に表示(🔴CRITICAL / 🟠HIGH / 🟡注目)
- 🛟 **フォールバック** — JEV API 未設定・障害時はキーワード判定で動作
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
jev_client.py                   JEV API クライアント + キーワード判定フォールバック
scripts/validate_feeds.py       feeds.yml の検証(PR時)
.github/workflows/
  daily-news.yml                毎日19:05 JST / main への反映時 / 手動 → gh-pages へデプロイ
  validate-feeds.yml            PR で feeds.yml を検証
```

## セットアップ(管理者向け)

1. **Settings → Pages** → Source: `Deploy from a branch` / Branch: `gh-pages` `/ (root)`
   (`gh-pages` ブランチは初回の Actions 実行で自動作成されます。先に **Actions → Daily Tech News Digest → Run workflow** を実行してください)
2. **Settings → Secrets and variables → Actions** に登録
   - `JEV_API_URL` — JEV API のエンドポイント
   - `JEV_API_KEY` — JEV API キー
   - `NTFY_TOPIC` — (任意) [ntfy.sh](https://ntfy.sh/) 通知用トピック
3. **Settings → Actions → General → Workflow permissions** を `Read and write permissions` にする
4. (推奨) **Settings → Branches** で `main` を保護し、PR + レビュー必須にする

## JEV API 連携について

JEV API の正式仕様が未確定のため、[`jev_client.py`](./jev_client.py) 冒頭に**仮定したリクエスト/レスポンス形式**を記載しています
(`POST` + `Authorization: Bearer`、記事のバッチを送り 1〜5 の重要度を受け取る)。
実際の仕様に合わせて `_call_jev()` / `_parse_results()` を修正してください。

## ローカル実行

```bash
pip install -r requirements.txt
python generate_news.py        # dist/ に出力(JEV_API_* 未設定ならキーワード判定)
python scripts/validate_feeds.py
```
