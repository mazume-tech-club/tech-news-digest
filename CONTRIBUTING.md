# コントリビューションガイド

このリポジトリの収集対象は [`feeds.yml`](./feeds.yml) で管理しています。
**フィードの追加・修正・無効化は、`feeds.yml` を編集して Pull Request を出すだけ**です。

## フィードを追加する

1. リポジトリを Fork(または権限があればブランチを作成)
2. `feeds.yml` の `feeds:` に1行追加

   ```yaml
   - { name: サイト名, url: "https://example.com/feed", category: cloud }
   # 英語フィードは lang: en を付ける(日本語タイトルに自動翻訳されます)
   - { name: Example Blog, url: "https://example.com/en/feed", category: ai, lang: en }
   ```

3. Pull Request を作成(テンプレートのチェック項目を確認)
4. PR で走る **Validate feeds.yml** が緑になることを確認
5. レビュー後にマージ → 自動でサイトへ反映されます

### フィールド

| 項目 | 必須 | 説明 |
|------|------|------|
| `name` | ✅ | 表示名(他と重複不可) |
| `url` | ✅ | RSS/Atom/RDF の URL(重複不可) |
| `category` | ✅ | `feeds.yml` の `categories` の `id` |
| `lang` | | `ja`(既定) / `en` |
| `enabled` | | `false` で収集停止 |
| `max_items` | | このフィードの最大取り込み件数 |
| `likes` | | `zenn` / `qiita`。記事ごとのいいね数を各サイトのAPIから取得して表示する(RSSにはいいね数がないため) |

## 監視するページを追加する(ページの変化)

RSS のないステータスページ・料金ページ・利用規約・発表ページは、`feeds.yml` の `watches:` に追加すると
毎日 1 回取得して前日との差分を「ページの変化」に表示します。

```yaml
watches:
  - { name: Example Status, url: "https://status.example.com/", kind: status }
```

| 項目 | 必須 | 説明 |
|------|------|------|
| `name` | ✅ | 表示名 |
| `url` | ✅ | https の URL(feeds と重複不可) |
| `kind` | ✅ | `status`(障害) / `price`(料金) / `terms`(規約) / `news`(発表) |
| `enabled` | | `false` で監視停止 |

1 ページ 1 日 約 $0.00015 かかり、本文取得と 1 日の予算(約1円)を共有するため、10 ページ程度までにしてください。

### カテゴリの追加

`categories:` に `id / title` を追加すると新しいセクションが作られます(並び順=表示順)。

## ルール

- 無料で公開されているフィードのみ(有料・ログイン必須は不可)
- 日本語サイトを優先。英語は速報性・重要性が高いものに限る
- 取得できない URL は PR の検証で警告されます。恒久的に取得できない場合は `enabled: false` にしてください

## 変更のテスト

```bash
pip install -r requirements.txt
python scripts/validate_feeds.py    # 形式チェック + URL到達性
python generate_news.py             # dist/index.html を生成して確認
```
