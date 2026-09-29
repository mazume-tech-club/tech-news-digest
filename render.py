"""
HTML レンダリング(閲覧UI)。

設計方針
- デジタル庁デザインシステム(DADS)を参考: 装飾を抑えたフラットな見た目、
  リンク=青/訪問済み=紫、本文16px以上・行間1.5以上、フォーカスリングは黄+黒の2重、
  色だけに頼らずラベル文字でも重要度を示す(コントラスト 4.5:1 以上)
- 大量の記事を「探す」より「絞る」: 注目ニュース → カテゴリ → 検索/重要度フィルタ
- JS が無効でも全記事が読める(フィルタは JS による追加機能)
- ライト/ダーク: OS設定に追従し、ヘッダーのボタンで手動切替(localStorage に保存)
"""

import html as HL
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
EPOCH = datetime.min.replace(tzinfo=timezone.utc)

IMP_LABEL = {5: '最重要', 4: '重要', 3: '注目'}
FILTER_OPTIONS = [(0, 'すべての重要度'), (3, '注目以上'), (4, '重要以上'), (5, '最重要のみ')]
PICKUP_N = 5


def esc(x):
    return HL.escape(str(x or ''), quote=True)


CSS = """
:root{
  --bg:#fff;--bg-sub:#f2f2f2;--surface:#fff;--tx:#1a1a1a;--tx-mute:#4d4d4d;
  --line:#d9d9d9;--line-strong:#767676;
  --link:#0017c1;--link-hover:#00118f;--visited:#6f2a9e;
  --crit-bg:#d70000;--crit-tx:#fff;--high:#8a4400;--high-line:#b45800;--note:#4d4d4d;
  --focus:#ffd43d;--focus-2:#000;--primary:#0031d8;--primary-tx:#fff;
}
:root[data-theme="dark"]{
  --bg:#121212;--bg-sub:#1e1e1e;--surface:#171717;--tx:#f2f2f2;--tx-mute:#b8b8b8;
  --line:#333;--line-strong:#8a8a8a;
  --link:#8fa9ff;--link-hover:#b5c5ff;--visited:#c9a2f0;
  --crit-bg:#ff6b6b;--crit-tx:#1a0000;--high:#ffb066;--high-line:#c77a2a;--note:#b8b8b8;
  --focus:#ffd43d;--focus-2:#fff;--primary:#8fa9ff;--primary-tx:#0a0a23;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#121212;--bg-sub:#1e1e1e;--surface:#171717;--tx:#f2f2f2;--tx-mute:#b8b8b8;
    --line:#333;--line-strong:#8a8a8a;
    --link:#8fa9ff;--link-hover:#b5c5ff;--visited:#c9a2f0;
    --crit-bg:#ff6b6b;--crit-tx:#1a0000;--high:#ffb066;--high-line:#c77a2a;--note:#b8b8b8;
    --focus:#ffd43d;--focus-2:#fff;--primary:#8fa9ff;--primary-tx:#0a0a23;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--tx);
  font-family:'Noto Sans JP','Hiragino Sans','Hiragino Kaku Gothic ProN','Yu Gothic UI',Meiryo,system-ui,sans-serif;
  font-size:16px;line-height:1.7;letter-spacing:.02em}
a{color:var(--link);text-underline-offset:.2em}
a:visited{color:var(--visited)}
a:hover{color:var(--link-hover);text-decoration-thickness:2px}
:focus-visible{outline:4px solid var(--focus-2);outline-offset:2px;box-shadow:0 0 0 2px var(--focus-2),0 0 0 6px var(--focus)}
.wrap{max-width:880px;margin:0 auto;padding:0 16px}
.skip{position:absolute;left:8px;top:-60px;background:var(--bg);padding:8px 12px;z-index:100;border:2px solid var(--tx)}
.skip:focus{top:8px}

.site-header{border-bottom:1px solid var(--line)}
.site-header .wrap{display:flex;gap:16px;align-items:center;justify-content:space-between;padding-top:14px;padding-bottom:14px;flex-wrap:wrap}
.site-title{margin:0;font-size:1.25rem;line-height:1.4;font-weight:700}
.lead{margin:0;font-size:.875rem;color:var(--tx-mute);line-height:1.5}
.header-tools{display:flex;gap:8px;align-items:center}
.btn{font:inherit;font-size:.875rem;line-height:1.4;min-height:44px;padding:8px 14px;border:1px solid var(--line-strong);
  border-radius:8px;background:var(--bg);color:var(--tx);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}
.btn:visited{color:var(--tx)}
.btn:hover{background:var(--bg-sub);color:var(--tx)}
#theme{display:none}.js #theme{display:inline-flex}

.stamp{margin:16px 0 8px;font-size:.875rem;color:var(--tx-mute);line-height:1.6}
.stamp b{color:var(--tx);font-weight:700}

h2{font-size:1.25rem;line-height:1.4;margin:0}
.pickup{margin:16px 0 8px;padding:16px;background:var(--bg-sub);border-radius:8px}
.pickup h2{margin-bottom:4px}
.pickup .note{margin:0 0 8px;font-size:.875rem;color:var(--tx-mute);line-height:1.5}
.pickup .item{border-bottom-color:var(--line-strong)}
.pickup .item-desc{display:none}

.tools{display:none;gap:8px;margin:20px 0 4px;flex-wrap:wrap}
.js .tools{display:flex}
.tools input[type=search],.tools select{font:inherit;min-height:44px;padding:8px 12px;border:1px solid var(--line-strong);
  border-radius:8px;background:var(--bg);color:var(--tx)}
.tools input[type=search]{flex:1 1 220px;min-width:0}
.tools select{flex:0 1 auto}
.tools label.chk{display:inline-flex;align-items:center;gap:8px;min-height:44px;font-size:.875rem;cursor:pointer}
.tools label.chk input{width:20px;height:20px}

.tabs{margin:16px 0 0}
.tabs ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.tabs a{display:inline-flex;align-items:center;gap:6px;min-height:44px;padding:8px 16px;border:1px solid var(--line-strong);
  border-radius:22px;background:var(--bg);color:var(--tx);text-decoration:none;font-size:.9375rem;line-height:1.4}
.tabs a:visited{color:var(--tx)}
.tabs a:hover{background:var(--bg-sub);color:var(--tx)}
.tabs a[aria-current="true"]{background:var(--primary);border-color:var(--primary);color:var(--primary-tx);font-weight:700}
.tabs .n{color:var(--tx-mute);font-size:.8125rem}
.tabs a[aria-current="true"] .n{color:inherit}

.status{margin:12px 0 0;font-size:.875rem;color:var(--tx-mute);min-height:1.5em}
.cat{margin-top:32px;scroll-margin-top:16px}
.cat>h2{padding-bottom:8px;border-bottom:2px solid var(--tx);display:flex;align-items:baseline;gap:8px}
.cat>h2 .count{font-size:.875rem;color:var(--tx-mute);font-weight:400}

.list{list-style:none;margin:0;padding:0}
.item{padding:14px 0;border-bottom:1px solid var(--line)}
.item-title{margin:0;font-size:1rem;line-height:1.6;font-weight:700}
.item-title a{color:var(--link)}
.item-title a:visited{color:var(--visited)}
.item-en,.item-desc{margin:2px 0 0;font-size:.875rem;color:var(--tx-mute);line-height:1.6}
.item-desc{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.hide-desc .item-desc{display:none}
.item-meta{margin:6px 0 0;font-size:.875rem;color:var(--tx-mute);line-height:1.5;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}
.badge{display:inline-block;font-size:.8125rem;font-weight:700;line-height:1.4;padding:1px 8px;border-radius:4px;margin-right:8px;vertical-align:1px;border:1px solid}
.b5{background:var(--crit-bg);color:var(--crit-tx);border-color:var(--crit-bg)}
.b4{color:var(--high);border-color:var(--high-line);background:transparent}
.b3{color:var(--note);border-color:var(--line-strong);background:transparent}
.item[data-imp="5"]{border-left:4px solid var(--crit-bg);padding-left:12px}
.item[data-imp="4"]{border-left:4px solid var(--high-line);padding-left:12px}

details.more{margin-top:8px}
details.more summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--link);font-size:.9375rem}
.empty{padding:32px 0;color:var(--tx-mute);text-align:center}
[hidden]{display:none!important}

.site-footer{margin-top:48px;padding:24px 0 48px;border-top:1px solid var(--line);font-size:.875rem;color:var(--tx-mute);line-height:1.7}

.arch-month{margin-top:24px}
.arch-month h2{font-size:1rem;padding-bottom:6px;border-bottom:2px solid var(--tx)}
.arch-list a{display:block;padding:12px 4px;min-height:44px}

@media (max-width:640px){
  .wrap{padding:0 14px}.tabs a{padding:8px 14px}
  .header-tools{width:100%}
  .pickup{padding:14px 12px;margin-left:-4px;margin-right:-4px}
}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
"""

# JS は任意機能(絞り込み・テーマ切替)。無効でも全記事を閲覧できる。
HEAD_JS = """
(function(){var d=document.documentElement;d.classList.add('js');
try{var t=localStorage.getItem('theme');if(t==='light'||t==='dark')d.setAttribute('data-theme',t);}catch(e){}})();
"""

BODY_JS = """
(function(){
var $=function(s,r){return (r||document).querySelector(s)},$$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))};
var d=document.documentElement,q=$('#q'),imp=$('#imp'),desc=$('#desc'),status=$('#status'),cat='all';
var items=$$('.cat .item'),cats=$$('.cat'),pick=$('#pickup'),tabs=$$('.tabs a');
var mq=window.matchMedia('(prefers-color-scheme: dark)');
function isDark(){var t=d.getAttribute('data-theme');return t?t==='dark':mq.matches}
var tb=$('#theme');
function label(){tb.textContent=isDark()?'ライト表示にする':'ダーク表示にする';tb.setAttribute('aria-pressed',isDark())}
tb.addEventListener('click',function(){var n=isDark()?'light':'dark';d.setAttribute('data-theme',n);try{localStorage.setItem('theme',n)}catch(e){}label()});
mq.addEventListener&&mq.addEventListener('change',label);label();
function apply(){
  var text=(q.value||'').trim().toLowerCase(),min=parseInt(imp.value,10)||0,shown=0,filtering=!!text||min>0||cat!=='all';
  items.forEach(function(li){
    var ok=(cat==='all'||li.dataset.cat===cat)&&(+li.dataset.imp>=min)&&(!text||li.dataset.text.indexOf(text)>-1);
    li.hidden=!ok;if(ok)shown++;
  });
  cats.forEach(function(s){
    var n=$$('.item:not([hidden])',s).length;s.hidden=(n===0)||(cat!=='all'&&s.id!==cat);
    $$('details.more',s).forEach(function(x){if(filtering)x.open=true});
    var c=$('.count',s);if(c)c.textContent=n+'件';
  });
  if(pick)pick.hidden=filtering;
  document.body.classList.toggle('hide-desc',!desc.checked);
  status.textContent=filtering?(shown+'件を表示中'):'';
  $('#empty').hidden=shown>0;
}
tabs.forEach(function(a){a.addEventListener('click',function(e){
  e.preventDefault();cat=a.dataset.cat;
  tabs.forEach(function(t){t.removeAttribute('aria-current')});a.setAttribute('aria-current','true');
  apply();
})});
[q,imp,desc].forEach(function(el){el.addEventListener('input',apply)});
$('#tools').addEventListener('submit',function(e){e.preventDefault()});
})();
"""


def item_li(it, show_cat=None):
    ja, en = it.get('title_ja') or it['title'], it['title']
    imp = it.get('importance', 2)
    badge = f'<span class="badge b{imp}">{IMP_LABEL[imp]}</span>' if imp in IMP_LABEL else ''
    pub = it.get('published')
    time_html = ''
    if pub:
        local = pub.astimezone(JST)
        time_html = f'<time datetime="{pub.isoformat()}">{local.month}/{local.day} {local:%H:%M}</time>'
    desc = it.get('summary', '')
    search_text = ' '.join([ja, en, it['source'], desc]).lower()
    meta = [f'<span>{esc(it["source"])}</span>']
    if show_cat:
        meta.append(f'<span>{esc(show_cat)}</span>')
    if time_html:
        meta.append(time_html)
    return (f'<li class="item" data-imp="{imp}" data-cat="{esc(it["category"])}" data-text="{esc(search_text)}">'
            f'<h3 class="item-title">{badge}<a href="{esc(it["url"])}" target="_blank" rel="noopener noreferrer">{esc(ja)}</a></h3>'
            + (f'<p class="item-en" lang="en">{esc(en)}</p>' if ja != en else '')
            + (f'<p class="item-desc">{esc(desc)}</p>' if desc else '')
            + f'<p class="item-meta">{"".join(meta)}</p></li>')


def _rank_key(it):
    return (it.get('importance', 2), it['published'] or EPOCH)


def category_section(cat, items, show_n):
    ranked = sorted(items, key=_rank_key, reverse=True)
    head, rest = ranked[:show_n], ranked[show_n:]
    body = f'<ul class="list">{"".join(item_li(i) for i in head)}</ul>'
    if rest:
        body += (f'<details class="more"><summary>残り {len(rest)} 件を表示</summary>'
                 f'<ul class="list">{"".join(item_li(i) for i in rest)}</ul></details>')
    return (f'<section class="cat" id="{esc(cat["id"])}" aria-labelledby="h-{esc(cat["id"])}">'
            f'<h2 id="h-{esc(cat["id"])}">{esc(cat["title"])}<span class="count">{len(items)}件</span></h2>{body}</section>')


def _page(title, body, script=''):
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<script>{HEAD_JS}</script>
<style>{CSS}</style>
</head>
<body>
{body}
{f'<script>{script}</script>' if script else ''}
</body>
</html>"""


def build_html(items, categories, settings, archive_link):
    now = datetime.now(JST)
    by_cat = {c['id']: [] for c in categories}
    for it in items:
        by_cat.setdefault(it['category'], []).append(it)
    shown = [c for c in categories if by_cat.get(c['id'])]
    titles = {c['id']: c['title'] for c in categories}

    n5 = sum(1 for i in items if i.get('importance') == 5)
    n4 = sum(1 for i in items if i.get('importance') == 4)

    picks = sorted([i for i in items if i.get('importance', 2) >= 4], key=_rank_key, reverse=True)[:PICKUP_N]
    pickup = ''
    if picks:
        pickup = ('<section class="pickup" id="pickup" aria-labelledby="h-pickup"><h2 id="h-pickup">注目ニュース</h2>'
                  '<p class="note">全カテゴリから、重要度の高い記事を抜き出しています。</p>'
                  f'<ul class="list">{"".join(item_li(i, titles.get(i["category"])) for i in picks)}</ul></section>')

    tabs = ['<li><a href="#main" data-cat="all" aria-current="true">すべて</a></li>']
    for c in shown:
        tabs.append(f'<li><a href="#{esc(c["id"])}" data-cat="{esc(c["id"])}">{esc(c["title"])}'
                    f'<span class="n">{len(by_cat[c["id"]])}</span></a></li>')

    options = ''.join(f'<option value="{v}">{l}</option>' for v, l in FILTER_OPTIONS)
    sections = ''.join(category_section(c, by_cat[c['id']], settings['show_per_category']) for c in shown)

    body = f"""<a class="skip" href="#main">本文へ移動</a>
<header class="site-header"><div class="wrap">
  <div><h1 class="site-title">Tech News Digest</h1>
  <p class="lead">日本語のテック系RSSを毎日集め、重要度の高い順に並べています。</p></div>
  <div class="header-tools"><button type="button" class="btn" id="theme" aria-pressed="false">ダーク表示にする</button>
  <a class="btn" href="{esc(archive_link)}">過去のニュース</a></div>
</div></header>
<div class="wrap">
  <p class="stamp"><b>{now.year}年{now.month}月{now.day}日 {now:%H:%M}</b> 更新 ／ 全{len(items)}件
  （最重要 {n5}件・重要 {n4}件）</p>
  {pickup}
  <form class="tools" id="tools" role="search" aria-label="記事の絞り込み">
    <input type="search" id="q" placeholder="キーワードで絞り込み" aria-label="キーワードで絞り込み" autocomplete="off">
    <select id="imp" aria-label="重要度">{options}</select>
    <label class="chk"><input type="checkbox" id="desc" checked>概要を表示</label>
  </form>
  <nav class="tabs" aria-label="カテゴリ"><ul>{''.join(tabs)}</ul></nav>
  <p class="status" id="status" role="status" aria-live="polite"></p>
  <main id="main">{sections}<p class="empty" id="empty" hidden>条件に合う記事がありません。条件を変えてください。</p></main>
  <footer class="site-footer">
    <p>収集元は <a href="https://github.com/mazume-tech-club/tech-news-digest/blob/main/feeds.yml">feeds.yml</a> で管理しています。
    追加したいフィードがあれば Pull Request をお送りください。</p>
    <p>重要度は JEV による判定(利用できない場合はキーワード判定)です。英語の見出しは自動翻訳で、原文を併記しています。</p>
  </footer>
</div>"""
    return _page(f'Tech News Digest — {now.year}年{now.month}月{now.day}日', body, BODY_JS)


def build_archive_index(dates, pages_url):
    groups = {}
    for d in sorted(dates, reverse=True):
        groups.setdefault(d[:7], []).append(d)
    parts = []
    for ym, ds in groups.items():
        rows = ''.join(f'<li class="item"><a href="{esc(pages_url)}/{d[:4]}/{d[5:7]}/{d}.html">'
                       f'{int(d[:4])}年{int(d[5:7])}月{int(d[8:])}日</a></li>' for d in ds)
        parts.append(f'<section class="arch-month"><h2>{int(ym[:4])}年{int(ym[5:])}月</h2>'
                     f'<ul class="list arch-list">{rows}</ul></section>')
    content = ''.join(parts) or '<p class="empty">アーカイブはまだありません。</p>'
    body = f"""<a class="skip" href="#main">本文へ移動</a>
<header class="site-header"><div class="wrap">
  <div><h1 class="site-title">Tech News Digest</h1><p class="lead">過去のニュース（全{len(dates)}日分）</p></div>
  <div class="header-tools"><a class="btn" href="{esc(pages_url)}/">最新のニュースへ</a></div>
</div></header>
<div class="wrap"><main id="main">{content}</main></div>"""
    return _page('過去のニュース — Tech News Digest', body)
