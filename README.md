# 📡 Tech News Digest

日本語テックサイトのRSSを毎日収集し、**Jev(TypeSafe AI)で重要度を判定**して、カテゴリ別・重要度順に表示する静的サイトです。
GitHub Actions で生成し、GitHub Pages(`gh-pages` ブランチ)で公開します。

**→ https://mazume-tech-club.github.io/tech-news-digest/**

## 特徴

- 🆕 **前回以降の新着** — 既定は未読だけ表示。「すべて既読にする」で片付け、読み終えたら「新着はすべて読みました」
- 🏷️ **重要な理由ラベル** — 「情報漏えい発生」「今すぐ対応」「料金改定」などを一覧に常に表示(スマホでも)。詳細に理由の 1 文
- 🎯 **重要度ランキング** — 記事ごとに Jev で「影響範囲・緊急性・新規性・宣伝度」を判定して合成。Lv5 はその日の上位 5 件まで(相対評価)
- 🧺 **同じ話題の束ね** — 同じ出来事を報じた記事を 1 行にまとめ「同じ話題 N件」
- 🔍 **ページの変化** — RSS のないステータス・料金・規約・発表ページの前日との差分(Treg)
- 📄 **本文から要約** — RSS に概要がない海外記事などは本文を取得して 2 行の日本語要約(Treg・1 日 20 件まで)
- ⭐ **フォロー / 見ない** — キーワードのフォロー、ソース・キーワードの非表示。既読と設定はブラウザの Cookie に保存(ログイン不要)
- 📱 **スマホはアプリ風** — 下部タブ(新着・注目・フォロー・設定)、絞り込みチップ、下から出る詳細シート。ホーム画面に追加可
- 📥 **RSS 中心** — 日本語サイトが中心。英語フィードは日本語タイトルに自動翻訳(原文も併記)
- 🛟 **フォールバック** — Jev / Treg 未設定・障害・低確信度のときはキーワード判定・RSS のみで動作
- 📂 **アーカイブ** — `YYYY/MM/YYYY-MM-DD.html` として日別に保存
- 🤝 **コントリビューション** — `feeds.yml` を編集する Pull Request をマージするだけで収集対象を追加可能

## 収集対象の追加(コントリビューター向け)

[`feeds.yml`](./feeds.yml) に1行追加して PR を出してください。手順は [CONTRIBUTING.md](./CONTRIBUTING.md) を参照。
PR では `feeds.yml` の自動検証(形式・重複・URL到達性)が走り、`main` にマージされると自動でサイトが再生成されます。

## 構成

```
feeds.yml                       収集するRSS/カテゴリ/設定(ここを編集)
generate_news.py                収集 → 翻訳 → Treg(ページの変化・本文) → 重要度判定 → 束ね・Lv5絞り込み → 出力
render.py                       閲覧UI(HTML/CSS/JS)。PC/スマホ1ページ・DADS参考・ダークモード・Cookie
jev_client.py                   Jev API クライアント・合成スコア・キャッシュ・フォールバック
treg_client.py                  Treg API クライアント・料金上限・1回の実行の予算管理
enrich.py                       本文の取得→要約 / ページの変化(差分)
curation.py                     記事ID・理由ラベル・同じ話題の束ね・Lv5の相対評価
docs/jev-design.md              Jev 連携の設計
docs/treg-design.md             Treg 連携の設計(エンドポイント・費用・動作確認の結果)
docs/reason-labels.md           重要な理由ラベル・束ね・既読Cookieの設計
tests/                          単体テスト
scripts/validate_feeds.py       feeds.yml の検証(PR時)
scripts/make_icons.py           アイコン(PNG/ICO)の再生成(デザイン変更時のみ。要 pillow)
assets/                         favicon.svg / favicon.ico / apple-touch-icon.png / icons/ / manifest.webmanifest(サイトのルートに公開)
.github/workflows/
  daily-news.yml                毎日19:05 JST / main への反映時 / 手動 → gh-pages へデプロイ
  validate-feeds.yml            PR で feeds.yml を検証
```

## セットアップ(管理者向け)

1. **Settings → Pages** → Source: `Deploy from a branch` / Branch: `gh-pages` `/ (root)`
   (`gh-pages` ブランチは初回の Actions 実行で自動作成されます。先に **Actions → Daily Tech News Digest → Run workflow** を実行してください)
2. **Settings → Secrets and variables → Actions** に登録
   - `JEV_API_KEY` — Jev API キー([typesafe.ai](https://typesafe.ai) で発行)
   - `TREG_API_KEY` — (任意) Treg の API キー。本文の要約・ページの変化に使う
   - `NTFY_TOPIC` — (任意) [ntfy.sh](https://ntfy.sh/) 通知用トピック
   - **Variables** タブに `TREG_API_URL` — (任意) Treg の呼び出し先 URL([docs/treg-design.md](./docs/treg-design.md) の「要確認」を参照)
   - Treg のキー/URL が未設定でもサイトは生成されます(本文の要約・ページの変化が出ないだけ)
3. **Settings → Actions → General → Workflow permissions** を `Read and write permissions` にする
4. (推奨) **Settings → Branches** で `main` を保護し、PR + レビュー必須にする

## Jev 連携について

記事 1 件ごとに Jev API を 1 回呼び、複数の観点(影響範囲・緊急性・新規性・宣伝度)を並列に判定して、コードで重み付き合成します。
設計・質問定義・閾値・コストは [docs/jev-design.md](./docs/jev-design.md) を参照してください。

## Treg 連携について

RSS に概要がない記事の本文取得と、RSS のないページの変更検知に Treg を使います。1 回の実行の費用は **$0.0065(約1円)以下** に制限し、
呼び出し回数と金額をログ・ジョブサマリーに出します。詳しくは [docs/treg-design.md](./docs/treg-design.md)。

## 個人設定(Cookie)

既読・フォロー・非表示・テーマはブラウザの Cookie に保存します(ログインなし・サーバーには送りません)。
既読は記事ID(URL ハッシュの先頭 7 文字)で直近 7 日分だけ保持します。詳しくは [docs/reason-labels.md](./docs/reason-labels.md)。

## ローカル実行

```bash
pip install -r requirements.txt
python generate_news.py        # dist/ に出力(JEV_API_KEY 未設定ならキーワード判定、TREG_* 未設定なら RSS のみ)
python scripts/validate_feeds.py
python -m unittest discover -s tests -t .
```
