"""
HTML レンダリング(閲覧UI)。デザイン案: PC版「トップページ(改修案)」/ スマホ版「スマホアプリ版」。

設計方針
- 毎日開く技術者向け。既定は「前回以降の新着」。読み終えたら「新着はすべて読みました」
- 1 件 = 2 段(1 段目: 未読の点・Lv・重要な理由ラベル・タイトル / 2 段目: 出典・時刻・同じ話題N件・フォロー一致)
- 「重要な理由」はマウスオーバーに頼らず、ラベルとして常に表示する(スマホでも見える)
- 詳細(重要な理由の文・要約 or 差分・関連記事・操作)は開いたときだけ表示
- デジタル庁デザインシステム(DADS)を参考: リンク=青/訪問済み=紫、フォーカスリングは黄+黒の2重、
  色だけに頼らずラベル文字でも重要度を示す(コントラスト 4.5:1 以上)、操作対象は 44px 以上
- PC とスマホで 1 ページ。幅 640px 以下 + JS 有効のときは、埋め込みデータからアプリ風の画面を組み立てる
- JS が無効でも全記事が読める(サーバー側で全記事の HTML を出す。既読・設定は JS による追加機能)
- 個人設定(既読・フォロー・非表示・テーマ)は Cookie に保存。ログインはない
"""

import html as HL
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from curation import article_id, extract_keyword, follow_keyword, reason_labels, topics_of, why_text

JST = timezone(timedelta(hours=9))
EPOCH = datetime.min.replace(tzinfo=timezone.utc)
PICKUP_N = 6
CHANGES_ID = '_changes'


def esc(x):
    return HL.escape(str(x or ''), quote=True)


CSS = """
:root{
  --bg:#fff;--bg-sub:#f2f2f2;--card:#fff;--tx:#1a1a1a;--tx-mute:#4d4d4d;
  --line:#d9d9d9;--line-strong:#767676;
  --link:#0017c1;--link-hover:#00118f;--visited:#6f2a9e;
  --crit:#c00000;--crit-bg:#fdecec;--high:#8a4400;--high-bg:#fdf0e3;--info:#1a1a1a;--info-bg:#ececec;
  --new:#00676b;--new-bg:#e6f4f4;--add-bg:#e7f5ea;--scrim:rgba(0,0,0,.4);
  --focus:#ffd43d;--focus-2:#000;--primary:#0031d8;--primary-tx:#fff;
}
:root[data-theme="dark"]{
  --bg:#121212;--bg-sub:#1e1e1e;--card:#1a1a1a;--tx:#f2f2f2;--tx-mute:#b8b8b8;
  --line:#333;--line-strong:#8a8a8a;
  --link:#8fa9ff;--link-hover:#b5c5ff;--visited:#c9a2f0;
  --crit:#ff8a8a;--crit-bg:#3a1a1a;--high:#ffb066;--high-bg:#3a2612;--info:#e6e6e6;--info-bg:#2a2a2a;
  --new:#6fd3d6;--new-bg:#0f2a2b;--add-bg:#13301b;--scrim:rgba(0,0,0,.6);
  --focus:#ffd43d;--focus-2:#fff;--primary:#8fa9ff;--primary-tx:#0a0a23;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#121212;--bg-sub:#1e1e1e;--card:#1a1a1a;--tx:#f2f2f2;--tx-mute:#b8b8b8;
    --line:#333;--line-strong:#8a8a8a;
    --link:#8fa9ff;--link-hover:#b5c5ff;--visited:#c9a2f0;
    --crit:#ff8a8a;--crit-bg:#3a1a1a;--high:#ffb066;--high-bg:#3a2612;--info:#e6e6e6;--info-bg:#2a2a2a;
    --new:#6fd3d6;--new-bg:#0f2a2b;--add-bg:#13301b;--scrim:rgba(0,0,0,.6);
    --focus:#ffd43d;--focus-2:#fff;--primary:#8fa9ff;--primary-tx:#0a0a23;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--tx);
  font-family:'Noto Sans JP','Hiragino Sans','Hiragino Kaku Gothic ProN','Yu Gothic UI',Meiryo,system-ui,sans-serif;
  font-size:15px;line-height:1.6;letter-spacing:.02em}
a{color:var(--link);text-underline-offset:.2em}
a:visited{color:var(--visited)}
a:hover{color:var(--link-hover);text-decoration-thickness:2px}
button{font:inherit;cursor:pointer}
:focus-visible{outline:4px solid var(--focus-2);outline-offset:2px;box-shadow:0 0 0 2px var(--focus-2),0 0 0 6px var(--focus)}
.wrap{max-width:920px;margin:0 auto;padding:0 16px}
.skip{position:absolute;left:8px;top:-60px;background:var(--bg);padding:8px 12px;z-index:100;border:2px solid var(--tx)}
.skip:focus{top:8px}
.js-only{display:none!important}
.js .js-only:not([hidden]){display:revert!important}
.js .js-only.flex:not([hidden]){display:flex!important}
[hidden]{display:none!important}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

.site-header{border-bottom:1px solid var(--line)}
.site-header .wrap{display:flex;gap:12px;align-items:center;justify-content:space-between;padding-top:10px;padding-bottom:10px;flex-wrap:wrap}
.site-title{margin:0;font-size:1.125rem;line-height:1.4;font-weight:700}
.site-title .upd{font-size:.8125rem;font-weight:400;color:var(--tx-mute);margin-left:4px}
.header-tools{display:flex;gap:8px;flex-wrap:wrap}
.btn{font-size:.875rem;line-height:1.4;min-height:44px;padding:8px 14px;border:1px solid var(--line-strong);
  border-radius:8px;background:var(--bg);color:var(--tx);text-decoration:none;display:inline-flex;align-items:center}
.btn:visited{color:var(--tx)}
.btn:hover{background:var(--bg-sub);color:var(--tx)}
.btn.link{color:var(--link)}

.settings{margin-top:12px;padding:14px 16px;border:1px solid var(--line-strong);border-radius:8px;display:grid;gap:10px;font-size:.875rem}
.settings .grp{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.settings .grp>b{min-width:96px}
.settings .note{margin:0;color:var(--tx-mute);font-size:.8125rem}
.chipx{min-height:36px;padding:2px 10px;border:0;border-radius:18px;font-size:.8125rem}
.chipx.fol{background:var(--new-bg);color:var(--new);font-weight:700}
.chipx.mut{background:var(--info-bg);color:var(--info)}
.none-note{color:var(--tx-mute)}

.bar{margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.seg{display:inline-flex;border:1px solid var(--line-strong);border-radius:8px;overflow:hidden}
.seg button{min-height:44px;padding:8px 14px;border:0;background:var(--bg);color:var(--tx);font-size:.875rem;font-weight:700}
.seg button+button{border-left:1px solid var(--line-strong)}
.seg button[aria-pressed="true"]{background:var(--primary);color:var(--primary-tx)}
.bar .muted-n{font-size:.8125rem;color:var(--tx-mute)}
.status{margin:8px 0 0;font-size:.875rem;color:var(--tx-mute);min-height:1.5em}

.sec{margin-top:24px}
.sec.boxed{padding:14px 16px;background:var(--bg-sub);border-radius:8px}
.sec>h2{margin:0;padding-bottom:6px;border-bottom:2px solid var(--tx);font-size:1.0625rem;line-height:1.4;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.sec>h2 .note{font-size:.8125rem;color:var(--tx-mute);font-weight:400}
.sec .empty-note{margin:12px 0 0;color:var(--tx-mute);font-size:.875rem}
.cat-note{margin:8px 0 0;font-size:.8125rem;color:var(--tx-mute)}
.list{list-style:none;margin:0;padding:0}
.row{border-bottom:1px solid var(--line)}
.row-main{display:flex;gap:8px;align-items:flex-start;padding:8px 0}
.dot{flex:none;width:8px;height:8px;margin-top:9px;border-radius:50%;background:transparent}
.js .row.unread .dot{background:var(--primary)}
.row-body{flex:1;min-width:0}
.l1{display:flex;flex-wrap:wrap;gap:4px 6px;align-items:baseline}
.ttl{font-weight:700}
.js .row.read .ttl{font-weight:400;color:var(--visited)}
.l2{margin-top:2px;display:flex;flex-wrap:wrap;gap:2px 10px;font-size:.8125rem;color:var(--tx-mute)}
.fol-hit{color:var(--new);font-weight:700}
.lv{flex:none;font-size:.75rem;font-weight:700;padding:0 6px;border-radius:4px;line-height:1.6;letter-spacing:.04em}
.lv5{color:var(--crit);background:var(--crit-bg)}
.lv4{color:var(--high);background:var(--high-bg)}
.lv3{color:var(--info);background:var(--info-bg)}
.lv2,.lv1{color:var(--tx-mute);background:transparent;border:1px solid var(--line)}
.rs{flex:none;font-size:.75rem;font-weight:700;padding:0 6px;border-radius:4px;border:1px solid currentColor;line-height:1.5}
.rs.crit{color:var(--crit)}.rs.high{color:var(--high)}.rs.info{color:var(--tx-mute)}.rs.chg{color:var(--new)}
.likes{display:inline-flex;align-items:center;gap:4px}
.likes b{font-weight:700;color:var(--tx)}
.likes.hot,.likes.hot b{color:var(--crit)}
.detail{margin:8px 0 4px;padding:10px 12px;background:var(--bg-sub);border-radius:8px;font-size:.875rem;display:grid;gap:8px}
.sec.boxed .detail{background:var(--bg)}
.js .row:not(.open) .detail{display:none}
.detail p{margin:0}
.detail .sum{color:var(--tx-mute)}
.src-badge{display:inline-block;margin-right:6px;padding:0 6px;border-radius:4px;background:var(--new-bg);color:var(--new);font-size:.75rem;font-weight:700}
.diff{display:grid;gap:4px}
.diff div{padding:4px 8px;border-radius:4px}
.diff .bf{background:var(--crit-bg)}.diff .af{background:var(--add-bg)}
.rel{margin:0;padding-left:18px;color:var(--tx-mute)}
.orig{color:var(--tx-mute);font-size:.8125rem}
.ops{display:flex;flex-wrap:wrap;gap:6px}
.ops button{min-height:44px;padding:6px 12px;border:1px solid var(--line-strong);border-radius:8px;background:var(--bg);color:var(--tx);font-size:.8125rem}
.ops button.fo{border-color:var(--new);color:var(--new);font-weight:700}
.tog{flex:none;width:44px;height:44px;border:0;border-radius:8px;background:transparent;color:var(--tx-mute);display:grid;place-items:center}
.tog:hover{background:var(--bg-sub)}
.row.open .tog svg{transform:rotate(180deg)}
details.more{margin-top:8px}
details.more summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:var(--link);font-size:.9375rem}
.done{padding:48px 16px;text-align:center;color:var(--tx-mute)}
.done b{display:block;color:var(--tx)}
.site-footer{margin-top:40px;padding:20px 0 48px;border-top:1px solid var(--line);font-size:.8125rem;color:var(--tx-mute);line-height:1.7}
.site-footer p{margin:0 0 6px}

.arch-month{margin-top:24px}
.arch-month h2{font-size:1rem;padding-bottom:6px;border-bottom:2px solid var(--tx)}
.arch-list a{display:block;padding:12px 4px;min-height:44px}

/* ── スマホ(アプリ風)── */
#app{display:none}
@media (max-width:640px){
  .wrap{padding:0 14px}
  .js .pc-only{display:none!important}
  .js #app{display:block}
}
.app-head{padding:16px 16px 8px;display:flex;align-items:flex-end;justify-content:space-between;gap:8px}
.app-head p{margin:0;font-size:.75rem;color:var(--tx-mute)}
.head-btns{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.pill.sub{color:var(--tx);font-weight:400}
.pill.sub[aria-pressed="true"]{background:var(--tx);color:var(--bg);font-weight:700}
.done .pill{margin-top:16px}
.addf{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px}
.addf input{flex:1 1 160px;min-width:0;min-height:44px;padding:8px 12px;font:inherit;font-size:.875rem;border:1px solid var(--line-strong);border-radius:8px;background:var(--bg);color:var(--tx)}
.addf button{min-height:44px;padding:6px 14px;border:1px solid var(--new);border-radius:8px;background:var(--bg);color:var(--new);font-weight:700;font-size:.875rem}
.app-head h1{margin:0;font-size:1.75rem;line-height:1.25;font-weight:800}
.pill{min-height:44px;padding:6px 12px;border:0;border-radius:22px;background:var(--bg-sub);color:var(--link);font-size:.8125rem;font-weight:700}
.chips{display:flex;gap:6px;overflow-x:auto;padding:4px 16px 10px;scrollbar-width:none;position:sticky;top:0;z-index:5;background:var(--bg)}
.chips::-webkit-scrollbar{display:none}
.chips button{flex:none;min-height:44px;padding:0 14px;border:1px solid var(--line-strong);border-radius:22px;background:var(--bg);color:var(--tx);font-size:.8125rem;font-weight:700;white-space:nowrap}
.chips button[aria-pressed="true"]{background:var(--tx);color:var(--bg);border-color:var(--tx)}
.chips .n{margin-left:4px;font-weight:400;opacity:.8}
.app-main{padding:0 12px calc(96px + env(safe-area-inset-bottom))}
.cards{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.card{width:100%;text-align:left;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--tx);padding:10px 12px;display:grid;gap:4px}
.card .top{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.card .cdot{width:8px;height:8px;border-radius:50%;margin-right:2px;background:transparent}
.card.unread .cdot{background:var(--primary)}
.card .lv,.card .rs{font-size:.6875rem}
.card .ct{font-size:.9375rem;line-height:1.5;font-weight:700;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card.read .ct{font-weight:400;color:var(--tx-mute)}
.card .cm{font-size:.75rem;color:var(--tx-mute);display:flex;gap:8px;flex-wrap:wrap}
.app-set{display:grid;gap:16px;padding-top:4px}
.app-set section{border-radius:14px;background:var(--bg-sub);padding:12px 14px}
.app-set h2{margin:0 0 8px;font-size:.9375rem}
.app-set .chipx{min-height:44px;padding:0 12px;border-radius:22px}
.app-set label{min-height:52px;display:flex;align-items:center;justify-content:space-between;font-weight:700;font-size:.9375rem}
.app-set input[type=checkbox]{width:22px;height:22px}
.app-set .note{margin:0 4px;font-size:.8125rem;color:var(--tx-mute)}
.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:20;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-top:1px solid var(--line);background:var(--bg);padding:4px 0 calc(8px + env(safe-area-inset-bottom))}
.tabbar button{min-height:52px;border:0;background:transparent;color:var(--tx-mute);display:grid;justify-items:center;align-content:center;gap:2px;font-size:.6875rem;font-weight:700;position:relative}
.tabbar button[aria-current="page"]{color:var(--primary)}
.tabbar .badge{position:absolute;top:4px;left:54%;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:var(--crit);color:#fff;font-size:.6875rem;line-height:18px}
:root[data-theme="dark"] .tabbar .badge{color:#1a0000}
.sheet{position:fixed;inset:0;z-index:30;display:flex;flex-direction:column;justify-content:flex-end}
.sheet .scrim{flex:1;border:0;background:var(--scrim)}
.sheet section{max-height:78vh;overflow-y:auto;background:var(--bg);border-radius:20px 20px 0 0;padding:8px 16px calc(28px + env(safe-area-inset-bottom));display:grid;gap:10px}
.sheet .grab{justify-self:center;width:40px;height:5px;border-radius:3px;background:var(--line-strong);opacity:.5}
.sheet h2{margin:0;font-size:1.125rem;line-height:1.45}
.sheet .meta{margin:0;font-size:.8125rem;color:var(--tx-mute)}
.sheet .why{padding:10px 12px;border-radius:12px;background:var(--bg-sub);font-size:.875rem}
.sheet .sum{margin:0;font-size:.875rem;color:var(--tx-mute)}
.sheet .open-it{min-height:48px;border-radius:12px;background:var(--primary);color:var(--primary-tx);font-weight:700;display:flex;align-items:center;justify-content:center;text-decoration:none}
.sheet .open-it:visited{color:var(--primary-tx)}
.sheet .ops3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.sheet .ops3 button{min-height:48px;border:1px solid var(--line);border-radius:12px;background:var(--bg);color:var(--tx);font-size:.75rem}
.sheet .ops3 .fo{border-color:var(--new);color:var(--new);font-weight:700}
.sheet .rel{font-size:.8125rem}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
"""

# テーマは Cookie(旧版の localStorage も読む)。描画前に適用してちらつきを防ぐ。
HEAD_JS = """
(function(){var d=document.documentElement;d.classList.add('js');var t='';
try{var m=document.cookie.match(/(?:^|; )tnd_theme=(light|dark)/);t=m?m[1]:(localStorage.getItem('theme')||'');}catch(e){}
if(t==='light'||t==='dark')d.setAttribute('data-theme',t);})();
"""

BODY_JS = r"""
(function(){
'use strict';
var D=JSON.parse(document.getElementById('tnd-data').textContent);
var $=function(s,r){return (r||document).querySelector(s)},$$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))};
var de=document.documentElement;
function h(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}

/* ── Cookie ─────────────────────────────────────────────── */
var PATH=location.pathname.indexOf(D.path)===0?D.path:'/';
var SECURE=location.protocol==='https:'?'; Secure':'';
function getC(n){var m=document.cookie.match(new RegExp('(?:^|; )'+n+'=([^;]*)'));return m?m[1]:''}
function setC(n,v){document.cookie=n+'='+v+'; Max-Age=34560000; Path='+PATH+'; SameSite=Lax'+SECURE}
function getList(n){try{var v=JSON.parse(decodeURIComponent(getC(n))||'[]');return Array.isArray(v)?v.filter(function(x){return typeof x==='string'}):[]}catch(e){return []}}
function setList(n,a){setC(n,encodeURIComponent(JSON.stringify(a)))}
var DAY=Math.floor(Date.now()/864e5);
// 既読: "日番号:id.id~日番号:id" 直近 7 日分だけ保持。4KB 上限の手前で古い日から捨てる
var groups={};
getC('tnd_r').split('~').forEach(function(g){var p=g.split(':');if(p.length===2&&/^\d+$/.test(p[0])&&DAY-(+p[0])<7){groups[p[0]]=p[1]?p[1].split('.'):[]}});
var readSet={};Object.keys(groups).forEach(function(k){groups[k].forEach(function(id){readSet[id]=1})});
var WM=parseInt(getC('tnd_w'),10)||0;   // 「すべて既読」にした時点(この時刻までに収集された記事は既読)
function saveRead(){
  var keys=Object.keys(groups).sort(),s='';
  for(;;){s=keys.map(function(k){return k+':'+groups[k].join('.')}).join('~');if(s.length<=3800||keys.length<=1)break;delete groups[keys.shift()]}
  if(s.length>3800){var g=groups[keys[0]];groups[keys[0]]=g.slice(g.length-400);s=keys[0]+':'+groups[keys[0]].join('.')}
  setC('tnd_r',s);
}
function isRead(it){return it.ts<=WM||!!readSet[it.id]}
function markRead(ids){var g=groups[DAY]||(groups[DAY]=[]);ids.forEach(function(id){if(!readSet[id]){readSet[id]=1;g.push(id)}});saveRead()}
function readAll(){WM=D.gen;setC('tnd_w',String(WM));groups={};readSet={};setC('tnd_r','');render()}
var follows=getList('tnd_follow'),muteS=getList('tnd_mute_src'),muteK=getList('tnd_mute_kw');

/* ── 判定 ───────────────────────────────────────────────── */
var BY={};D.items.forEach(function(it){BY[it.id]=it});
function muted(it){if(muteS.indexOf(it.s)>-1)return true;for(var i=0;i<muteK.length;i++){if(it.x.indexOf(muteK[i].toLowerCase())>-1)return true}return false}
// フォロー: 話題(別名を含む。例: 「マイナンバー」は「マイナアプリ」にも一致)または、タイトル・ソースの部分一致
function followHit(it){for(var i=0;i<follows.length;i++){var f=follows[i],fl=f.toLowerCase();
  if((it.tp||[]).some(function(t){return t.toLowerCase()===fl})||it.x.indexOf(fl)>-1)return f}return ''}
var keep={};   // この表示中に既読にした記事は、切り替えるまで一覧に残す(突然消えないように)
var unreadOnly=true,live=$('#status');
function say(t){if(live){live.textContent=t}}
function idsOf(it){return [it.id].concat((it.rel||[]).map(function(r){return r[3]}))}
function openArticle(it){markRead(idsOf(it));keep[it.id]=1}

/* ── テーマ ─────────────────────────────────────────────── */
var mq=window.matchMedia('(prefers-color-scheme: dark)');
function isDark(){var t=de.getAttribute('data-theme');return t?t==='dark':mq.matches}
function setTheme(dark){var n=dark?'dark':'light';de.setAttribute('data-theme',n);setC('tnd_theme',n);render()}

/* ── 操作(PC・スマホ共通)──────────────────────────────── */
function op(kind,it){
  if(kind==='mute-src'){if(muteS.indexOf(it.s)<0)muteS.push(it.s);setList('tnd_mute_src',muteS);say('「'+it.s+'」を表示しないようにしました。設定から解除できます。')}
  else if(kind==='mute-kw'){if(muteK.indexOf(it.kw)<0)muteK.push(it.kw);setList('tnd_mute_kw',muteK);say('「'+it.kw+'」を含む記事を表示しないようにしました。設定から解除できます。')}
  else if(kind==='follow-kw'){addFollow(it.fk)}
  render();
}
function addFollow(k){k=String(k||'').trim().slice(0,40);if(!k)return;
  if(!follows.some(function(x){return x.toLowerCase()===k.toLowerCase()})){follows.push(k);setList('tnd_follow',follows)}
  say('「'+k+'」をフォローしました。同じ話題の記事が「フォロー中」に出ます。')}
document.addEventListener('submit',function(e){var f=e.target.closest('.addf');if(!f)return;e.preventDefault();var i=$('input',f);addFollow(i.value);i.value='';render()});
function unfollow(k){follows=follows.filter(function(x){return x!==k});setList('tnd_follow',follows);render()}
function unmuteS(k){muteS=muteS.filter(function(x){return x!==k});setList('tnd_mute_src',muteS);render()}
function unmuteK(k){muteK=muteK.filter(function(x){return x!==k});setList('tnd_mute_kw',muteK);render()}
function chipsHTML(){
  var f=follows.map(function(k){return '<button type="button" class="chipx fol" data-unfollow="'+h(k)+'" aria-label="'+h(k)+' のフォローを外す">'+h(k)+' ×</button>'}).join('');
  var m=muteS.map(function(k){return '<button type="button" class="chipx mut" data-unmute-s="'+h(k)+'" aria-label="'+h(k)+' の非表示を解除">ソース: '+h(k)+' ×</button>'}).join('')
       +muteK.map(function(k){return '<button type="button" class="chipx mut" data-unmute-k="'+h(k)+'" aria-label="'+h(k)+' の非表示を解除">キーワード: '+h(k)+' ×</button>'}).join('');
  return {f:(f||'<span class="none-note">なし(記事の詳細の「フォロー」か、下の欄から追加できます)</span>'),m:m||'<span class="none-note">なし(記事の詳細の「見ない」から追加できます)</span>'};
}
document.addEventListener('click',function(e){
  var b=e.target.closest('[data-unfollow],[data-unmute-s],[data-unmute-k]');if(!b)return;
  if(b.dataset.unfollow!=null)unfollow(b.dataset.unfollow);else if(b.dataset.unmuteS!=null)unmuteS(b.dataset.unmuteS);else unmuteK(b.dataset.unmuteK);
});

/* ── PC ─────────────────────────────────────────────────── */
var rows=$$('.pc-only .row'),folSec=$('#sec-follow'),folList=$('#follow-list');
function renderPC(){
  var seen={},unread=0,total=0,hidden=0;
  D.items.forEach(function(it){if(it.lead){if(muted(it))hidden++;else{total++;if(!isRead(it))unread++}}});
  rows.forEach(function(li){
    var it=BY[li.dataset.id];if(!it)return;
    var r=isRead(it),fh=followHit(it);
    li.classList.toggle('read',r);li.classList.toggle('unread',!r);
    var dot=$('.dot',li);dot.setAttribute('aria-label',r?'既読':'未読');
    var fe=$('.fol-hit',li);fe.hidden=!fh;fe.textContent=fh?'フォロー: '+fh:'';
    li.hidden=muted(it)||(unreadOnly&&r&&!keep[it.id]);
  });
  // フォロー中: カテゴリ別の行を複製して並べる
  folList.innerHTML='';var nf=0;
  $$('.cat .row').forEach(function(li){var it=BY[li.dataset.id];if(!it||seen[it.id]||!followHit(it)||li.hidden)return;seen[it.id]=1;var c=li.cloneNode(true);c.classList.remove('open');fixIds(c,'f');folList.appendChild(c);nf++});
  folSec.hidden=follows.length===0;$('#follow-note').textContent=follows.join('・');
  $('#follow-empty').hidden=nf>0;
  $$('.pc-only .sec').forEach(function(s){if(s===folSec)return;var n=$$('.row:not([hidden])',s).length;var em=$('.empty-note',s);if(em)em.hidden=n>0;
    var dm=$('details.more',s);if(dm&&unreadOnly)dm.open=true});
  $('#cnt-unread').textContent=unread;$('#cnt-all').textContent=total;$('#cnt-muted').textContent=hidden;
  $('#seg-unread').setAttribute('aria-pressed',unreadOnly);$('#seg-all').setAttribute('aria-pressed',!unreadOnly);
  $('#done').hidden=!(unreadOnly&&unread===0&&!Object.keys(keep).length);
  var c=chipsHTML();$('#set-follow').innerHTML=c.f;$('#set-mute').innerHTML=c.m;
  var tb=$('#theme');tb.textContent=isDark()?'ライト表示':'ダーク表示';tb.setAttribute('aria-pressed',isDark());
}
function fixIds(li,p){var d=$('.detail',li),t=$('.tog',li);if(d&&t){d.id=p+'-'+d.id;t.setAttribute('aria-controls',d.id);t.setAttribute('aria-expanded','false')}}
document.addEventListener('click',function(e){
  var li=e.target.closest('.pc-only .row');if(!li)return;var it=BY[li.dataset.id];
  var t=e.target.closest('.tog');
  if(t){var o=!li.classList.contains('open');li.classList.toggle('open',o);t.setAttribute('aria-expanded',o);t.setAttribute('aria-label',o?'詳細を閉じる':'重要な理由と詳細を開く');return}
  var b=e.target.closest('[data-op]');if(b){op(b.dataset.op,it);return}
  var a=e.target.closest('a.ttl');if(a){openArticle(it);setTimeout(render,0)}
});
document.addEventListener('auxclick',function(e){var a=e.target.closest('.pc-only a.ttl');if(a){var it=BY[a.closest('.row').dataset.id];openArticle(it);setTimeout(render,0)}});
$('#seg-unread').addEventListener('click',function(){unreadOnly=true;keep={};render()});
$('#seg-all').addEventListener('click',function(){unreadOnly=false;render()});
$('#read-all').addEventListener('click',function(){readAll();say('すべて既読にしました。')});
$('#theme').addEventListener('click',function(){setTheme(!isDark())});
$('#settings-btn').addEventListener('click',function(){var p=$('#settings'),o=p.hidden;p.hidden=!o;this.setAttribute('aria-expanded',o)});

var ADDF='<form class="addf"><label class="vh" for="addf-m">フォローするキーワード</label><input id="addf-m" type="text" maxlength="40" placeholder="キーワードを追加(例: Rust、AWS)" autocomplete="off"><button type="submit">フォロー</button></form>';
/* ── スマホ(アプリ風)──────────────────────────────────── */
var app=$('#app'),tab='new',cat='all',sel=null,lastFocus=null,showRead=false,chipsReset=false;
var ICON={new:'M4 4h16v12H15l-3 3-3-3H4z',pick:'M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.5 6.7 19.4l1.2-6L3.4 9.3l6-.7z',follow:'M6 3h12v18l-6-4-6 4z',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM3 12h2M19 12h2M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4'};
var TABS=[['new','新着'],['pick','注目'],['follow','フォロー'],['settings','設定']];
function lvPill(it){return '<span class="lv lv'+it.lv+'" aria-label="'+(it.heat?'アツさ ':'重要レベル ')+it.lv+'(5段階)">'+(it.heat?'アツさ':'Lv')+it.lv+'</span>'}
function rsHTML(it){return it.rs.map(function(r){return '<span class="rs '+r[1]+'">'+h(r[0])+'</span>'}).join('')}
function renderApp(){
  var vis=D.items.filter(function(it){return it.lead&&!muted(it)});
  var unread=vis.filter(function(it){return !isRead(it)});
  var base=tab==='new'?(showRead?vis.slice():vis.filter(function(it){return !isRead(it)||keep[it.id]})):tab==='pick'?vis.filter(function(it){return it.lv>=4&&!it.heat}):tab==='follow'?vis.filter(followHit):[];
  base.sort(function(a,b){return (tab==='new'&&showRead?(isRead(a)-isRead(b)):0)||(b.lv-a.lv)||(b.sc-a.sc)||(b.ts-a.ts)});
  var cats=[['all','すべて']].concat(D.cats.filter(function(c){return base.some(function(it){return it.c===c[0]})}));
  if(!cats.some(function(c){return c[0]===cat}))cat='all';
  var list=cat==='all'?base:base.filter(function(it){return it.c===cat});
  var title={new:'新着 '+unread.length+'件',pick:'注目',follow:'フォロー中',settings:'設定'}[tab];
  var s='<header class="app-head"><div><p>'+h(D.updated)+' 更新</p><h1 id="app-title">'+h(title)+'</h1></div>'
    +(tab==='new'?'<div class="head-btns">'+(unread.length?'<button type="button" class="pill" id="m-readall">すべて既読</button>':'')
      +'<button type="button" class="pill sub" id="m-showread" aria-pressed="'+showRead+'">'+(showRead?'未読だけ':'既読も表示')+'</button></div>':'')+'</header>';
  if(tab!=='settings'){
    s+='<div class="chips" role="group" aria-label="絞り込み">'+cats.map(function(c){var n=c[0]==='all'?base.length:base.filter(function(it){return it.c===c[0]}).length;
      return '<button type="button" data-cat="'+h(c[0])+'" aria-pressed="'+(cat===c[0])+'">'+h(c[1])+'<span class="n">'+n+'</span></button>'}).join('')+'</div>';
    s+='<main class="app-main" id="m-main"><ul class="cards">'+list.map(function(it){var r=isRead(it),fh=followHit(it);
      return '<li><button type="button" class="card '+(r?'read':'unread')+'" data-id="'+it.id+'"><span class="top"><span class="cdot" role="img" aria-label="'+(r?'既読':'未読')+'"></span>'+lvPill(it)+rsHTML(it)+'</span>'
        +'<span class="ct">'+h(it.t)+'</span><span class="cm"><span>'+h(it.s)+'</span><span>'+h(it.tm)+'</span>'
        +(it.rel&&it.rel.length?'<span>同じ話題 '+it.rel.length+'件</span>':'')+(it.likes!=null?'<span>いいね '+it.likes+'</span>':'')
        +(fh?'<span class="fol-hit">フォロー: '+h(fh)+'</span>':'')+'</span></button></li>'}).join('')+'</ul>';
    if(!list.length){s+=tab==='new'?'<div class="done"><b>新着はすべて読みました</b>'+h(D.next)
        +'<p><button type="button" class="pill" id="m-showread2">読んだ記事も表示する</button></p></div>'
      :tab==='follow'&&!follows.length?'<div class="done"><b>フォロー中のキーワードはありません</b>記事の詳細から「フォロー」できます。</div>'
      :'<div class="done"><b>該当する記事はありません</b></div>'}
    s+='</main>';
  }else{
    var c=chipsHTML();
    s+='<main class="app-main"><div class="app-set"><section><h2>フォロー中</h2><div class="grp" style="display:flex;flex-wrap:wrap;gap:6px">'+c.f+'</div>'+ADDF+'</section>'
      +'<section><h2>見たくない</h2><div style="display:flex;flex-wrap:wrap;gap:6px">'+c.m+'</div></section>'
      +'<section style="padding:4px 14px"><label>ダーク表示<input type="checkbox" id="m-dark"'+(isDark()?' checked':'')+'></label></section>'
      +'<p class="note">設定と既読はこの端末のCookieに保存されます(既読は直近7日分)。ログインは不要です。ブラウザの共有メニューから「ホーム画面に追加」すると、アプリとして全画面で開けます。</p>'
      +'<p class="note"><a href="'+h(D.archive)+'">過去のニュース</a></p></div></main>';
  }
  s+='<nav class="tabbar" aria-label="メイン">'+TABS.map(function(t){var cur=tab===t[0];
    return '<button type="button" data-tab="'+t[0]+'"'+(cur?' aria-current="page"':'')+'><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+ICON[t[0]]+'"></path></svg>'+t[1]
      +(t[0]==='new'&&unread.length?'<span class="badge" aria-label="未読 '+unread.length+'件">'+unread.length+'</span>':'')+'</button>'}).join('')+'</nav>';
  if(sel&&BY[sel]){var it=BY[sel];
    s+='<div class="sheet"><button type="button" class="scrim" data-close aria-label="閉じる"></button><section role="dialog" aria-modal="true" aria-labelledby="sh-t" tabindex="-1">'
      +'<span class="grab" aria-hidden="true"></span><div class="top" style="display:flex;flex-wrap:wrap;gap:4px">'+lvPill(it)+rsHTML(it)+'</div>'
      +'<h2 id="sh-t">'+h(it.t)+'</h2><p class="meta">'+h(it.s)+'・'+h(it.tm)+'</p>'
      +'<div class="why"><b>重要な理由</b><br>'+(followHit(it)?'フォロー中の「'+h(followHit(it))+'」に一致。':'')+h(it.w)+'</div>'
      +(it.sm?'<p class="sum">'+(it.sb?'<span class="src-badge">本文から要約</span>':'')+h(it.sm)+'</p>':'')
      +(it.b!=null?'<div class="diff" style="font-size:.8125rem"><div class="bf"><b>変更前</b> <s>'+h(it.b)+'</s></div><div class="af"><b>変更後</b> '+h(it.a)+'</div></div>':'')
      +(it.rel&&it.rel.length?'<div class="rel-w" style="font-size:.8125rem"><b>同じ話題の記事</b><ul class="rel">'+it.rel.map(function(r){return '<li><a href="'+h(r[2])+'" target="_blank" rel="noopener noreferrer">'+h(r[0])+'</a>('+h(r[1])+')</li>'}).join('')+'</ul></div>':'')
      +'<a class="open-it" href="'+h(it.u)+'" target="_blank" rel="noopener noreferrer" data-open>記事を開く</a>'
      +'<div class="ops3"><button type="button" data-mop="mute-src">このソースを<br>見ない</button><button type="button" data-mop="mute-kw">「'+h(it.kw)+'」を<br>見ない</button><button type="button" class="fo" data-mop="follow-kw">「'+h(it.fk)+'」を<br>フォロー</button></div>'
      +'</section></div>';
  }
  // 描き直しでチップ列の横スクロールが左端に戻らないよう、位置を引き継ぐ(右側のカテゴリを選んでもその場に留まる)
  var oc=$('.chips',app),sx=oc?oc.scrollLeft:0,y=window.scrollY;
  app.innerHTML=s;window.scrollTo(0,y);
  var nc=$('.chips',app);if(nc){nc.scrollLeft=chipsReset?0:sx;chipsReset=false;
    var on=$('[aria-pressed="true"]',nc);if(on){var r=on.getBoundingClientRect(),w=nc.getBoundingClientRect();
      if(r.left<w.left+16||r.right>w.right-16)nc.scrollLeft+=r.left-w.left-(w.width-r.width)/2}}
  var sh=$('.sheet section',app);if(sh)sh.focus({preventScroll:true});
}
function closeSheet(markIt){var id=sel;sel=null;if(markIt&&id){openArticle(BY[id])}render();var c=id&&$('.card[data-id="'+id+'"]',app);(c||lastFocus||document.body).focus&&(c||lastFocus).focus()}
app.addEventListener('click',function(e){
  var t;
  if((t=e.target.closest('[data-tab]'))){tab=t.dataset.tab;cat='all';keep={};chipsReset=true;render();window.scrollTo(0,0);return}
  if((t=e.target.closest('[data-cat]'))){cat=t.dataset.cat;render();return}
  if((t=e.target.closest('.card'))){lastFocus=t;sel=t.dataset.id;render();return}
  if(e.target.closest('#m-readall')){readAll();return}
  if(e.target.closest('#m-showread,#m-showread2')){showRead=!showRead;keep={};render();return}
  if(e.target.closest('[data-close]')){closeSheet(false);return}
  if(e.target.closest('[data-open]')){setTimeout(function(){closeSheet(true)},0);return}
  if((t=e.target.closest('[data-mop]'))){var it=BY[sel];var k=t.dataset.mop;
    if(k!=='follow-kw'){openArticle(it)}sel=null;op(k,it);return}
});
app.addEventListener('change',function(e){if(e.target.id==='m-dark')setTheme(e.target.checked)});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&sel)closeSheet(false)});

var small=window.matchMedia('(max-width: 640px)');
function render(){renderPC();if(small.matches)renderApp();else app.innerHTML=''}
small.addEventListener&&small.addEventListener('change',render);
mq.addEventListener&&mq.addEventListener('change',render);
render();
})();
"""


IMPORTANCE_LABELS = {'impact': '影響範囲', 'urgency': '緊急性', 'novelty': '新規性', 'noise': '宣伝度'}
HEAT_LABELS = {'curiosity': '面白さ', 'appeal': '共感の広がり', 'learning': '学び', 'noise': '宣伝度'}


def level_indicator(it):
    """重要レベル(1〜5)の「Lv」表示。人気記事は「アツさ」。title に Jev の内訳と確度(補助情報)。"""
    lv = max(1, min(5, int(it.get('importance', 2))))
    heat = it.get('profile') == 'heat'
    name, short = ('アツさ', 'アツさ') if heat else ('重要レベル', 'Lv')
    bd, conf = it.get('breakdown'), it.get('confidence')
    labels = HEAT_LABELS if heat else IMPORTANCE_LABELS
    parts = [f'{label} {bd[k]:.0%}' for k, label in labels.items() if bd and isinstance(bd.get(k), (int, float))]
    if it.get('kind') == 'change':
        tip = f'{name} {lv}/5(ページの変化の種類による)'
    elif parts:
        tip = f'{name} {lv}/5 ・ ' + ' / '.join(parts)
        if conf is not None:
            tip += f' ・ Jev 確度 {conf:.0%}'
    else:
        tip = f'{name} {lv}/5({"いいね数" if heat else "キーワード"}による簡易判定)'
    return (f'<span class="lv lv{lv}" role="img" aria-label="{name} {lv}(5段階)" title="{esc(tip)}">'
            f'{short}{lv}</span>')


def reason_chips(it):
    out = []
    if it.get('kind') == 'change':
        out.append(f'<span class="rs chg">{esc(it.get("change_label", "変化"))}</span>')
        return ''.join(out)
    for r in reason_labels(it):
        out.append(f'<span class="rs {r["tone"]}">{esc(r["t"])}</span>')
    return ''.join(out)


def likes_chip(it):
    """いいね数(Zenn / Qiita)。取得できなかった記事・対象外の記事は空文字。"""
    n = it.get('likes')
    if n is None:
        return ''
    hot = ' hot' if n >= 50 else ''
    return f'<span class="likes{hot}" role="img" aria-label="いいね {n}件">♥ <b>{n:,}</b></span>'


def fmt_time(pub, now=None, short=False):
    """PC: 11/27 08:12 / スマホ(short): 今日=08:12・昨日=昨日 21:30・それ以前=11/25 10:00"""
    if not pub:
        return ''
    local = pub.astimezone(JST)
    if short and now:
        n = now.astimezone(JST).date()
        if local.date() == n:
            return f'{local:%H:%M}'
        if local.date() == n - timedelta(days=1):
            return f'昨日 {local:%H:%M}'
    return f'{local.month}/{local.day} {local:%H:%M}'


def _title(it):
    return it.get('title_ja') or it['title']


def _id(it):
    return it.get('id') or article_id(it['url'])


def _ts(it, now):
    t = it.get('first_seen') or it.get('published') or now
    return int(min(t, now).timestamp()) if t else int(now.timestamp())


def _match_text(it):
    return ' '.join([_title(it), it['title'], it.get('source', '')]).lower()


TOG_SVG = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>')


def row_html(it, sec, now):
    """1 件 = 2 段。詳細は開いたときだけ(JS 無効時は常に表示)。"""
    aid = _id(it)
    kw = it.get('kw') or extract_keyword(_title(it))
    fk = it.get('fk') or follow_keyword(it)
    rel = it.get('related') or []
    pub = it.get('published')
    time_html = f'<time datetime="{pub.isoformat()}">{fmt_time(pub)}</time>' if pub else ''
    l2 = ['<span class="fol-hit js-only" hidden></span>', likes_chip(it), f'<span>{esc(it.get("source"))}</span>', time_html]
    if rel:
        l2.append(f'<span>同じ話題 {len(rel)}件</span>')
    detail = [f'<p><b>重要な理由:</b>{esc(why_text(it))}</p>']
    if it.get('kind') == 'change':
        detail.append(f'<div class="diff"><div class="bf"><b>変更前</b> <s>{esc(it.get("before"))}</s></div>'
                      f'<div class="af"><b>変更後</b> {esc(it.get("after"))}</div></div>')
    elif it.get('summary'):
        badge = '<span class="src-badge">本文から要約</span>' if it.get('summary_src') == 'body' else ''
        detail.append(f'<p class="sum">{badge}{esc(it["summary"])}</p>')
    if _title(it) != it['title']:
        detail.append(f'<p class="orig" lang="en">原題: {esc(it["title"])}</p>')
    if rel:
        lis = ''.join(f'<li><a href="{esc(r["url"])}" target="_blank" rel="noopener noreferrer">{esc(_title(r))}</a>'
                      f'({esc(r.get("source"))})</li>' for r in rel)
        detail.append(f'<ul class="rel" aria-label="同じ話題の記事">{lis}</ul>')
    detail.append('<div class="ops js-only flex">'
                  f'<button type="button" data-op="mute-src">「{esc(it.get("source"))}」を見ない</button>'
                  f'<button type="button" data-op="mute-kw">「{esc(kw)}」を見ない</button>'
                  f'<button type="button" class="fo" data-op="follow-kw">「{esc(fk)}」をフォロー</button></div>')
    did = f'd-{sec}-{aid}'
    return (f'<li class="row unread" data-id="{aid}">'
            f'<div class="row-main"><span class="dot" role="img" aria-label="未読"></span><div class="row-body">'
            f'<div class="l1">{level_indicator(it)}{reason_chips(it)}'
            f'<a class="ttl" href="{esc(it["url"])}" target="_blank" rel="noopener noreferrer">{esc(_title(it))}</a></div>'
            f'<div class="l2">{"".join(x for x in l2 if x)}</div>'
            f'<div class="detail" id="{did}">{"".join(detail)}</div></div>'
            f'<button type="button" class="tog js-only" aria-expanded="false" aria-controls="{did}" '
            f'aria-label="重要な理由と詳細を開く">{TOG_SVG}</button></div></li>')


def _rank_key(it):
    return (it.get('importance_score', 0), it.get('published') or EPOCH)


def _likes_key(it):
    n = it.get('likes')
    return (-1 if n is None else n, it.get('published') or EPOCH)


def category_section(cat, items, show_n, now=None):
    now = now or datetime.now(JST)
    by_likes = cat.get('sort') == 'likes'
    ranked = sorted(items, key=_likes_key if by_likes else _rank_key, reverse=True)
    note = ''
    if by_likes:
        note = ('<p class="cat-note">いいね数の多い順に表示しています。'
                + ('「アツさ」は Jev が判定した、面白さ・共感の広がりです。' if cat.get('mode') == 'heat' else '')
                + '</p>')
    head, rest = ranked[:show_n], ranked[show_n:]
    body = f'<ul class="list">{"".join(row_html(i, cat["id"], now) for i in head)}</ul>'
    if rest:
        body += (f'<details class="more"><summary>残り {len(rest)} 件を表示</summary>'
                 f'<ul class="list">{"".join(row_html(i, cat["id"], now) for i in rest)}</ul></details>')
    return (f'<section class="sec cat" id="{esc(cat["id"])}" aria-labelledby="h-{esc(cat["id"])}">'
            f'<h2 id="h-{esc(cat["id"])}">{esc(cat["title"])}<span class="note">{len(items)}件</span></h2>{note}{body}'
            '<p class="empty-note js-only" hidden>新着はありません。</p></section>')


def head_icons(base):
    """アイコン・PWA関連の <head> タグ。base はサイトのルートURL(末尾スラッシュなし)。
    ページは /2026/09/x.html や /archive/ など階層が違うため、すべて絶対URLで指す。"""
    b = esc(base.rstrip('/'))
    return (f'<link rel="icon" href="{b}/favicon.svg" type="image/svg+xml">\n'
            f'<link rel="icon" href="{b}/favicon.ico" sizes="48x48">\n'
            f'<link rel="apple-touch-icon" href="{b}/apple-touch-icon.png">\n'
            f'<link rel="manifest" href="{b}/manifest.webmanifest">\n'
            '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">\n'
            '<meta name="theme-color" content="#121212" media="(prefers-color-scheme: dark)">\n'
            '<meta name="application-name" content="News Digest">\n'
            '<meta name="apple-mobile-web-app-title" content="News Digest">\n'
            '<meta name="mobile-web-app-capable" content="yes">\n'
            '<meta name="apple-mobile-web-app-capable" content="yes">')


def _page(title, body, script='', base=''):
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{head_icons(base)}
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
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


def next_update_text(now):
    """「次の更新は明日の朝です」など。更新時刻(=生成時刻)の時間帯から決める。"""
    h = now.astimezone(JST).hour
    part = '朝' if 4 <= h < 11 else '昼' if 11 <= h < 16 else '夜'
    return f'次の更新は明日の{part}です。'


def page_data(leaders, followers, categories, now, archive_link, base_path):
    """スマホ版と既読管理用の埋め込みデータ(JSON)。"""
    cats = [[CHANGES_ID, 'ページの変化']] + [[c['id'], c['title']] for c in categories]
    out = []
    for it in leaders + followers:
        rel = it.get('related') or []
        d = {
            'id': _id(it), 'lead': not it.get('cluster_of'), 'lv': max(1, min(5, int(it.get('importance', 2)))),
            'sc': round(float(it.get('importance_score') or 0), 4), 'heat': it.get('profile') == 'heat',
            'rs': ([[it.get('change_label', '変化'), 'chg']] if it.get('kind') == 'change'
                   else [[r['t'], r['tone']] for r in reason_labels(it)]),
            't': _title(it), 'u': it['url'], 's': it.get('source', ''), 'tm': fmt_time(it.get('published'), now, short=True),
            'ts': _ts(it, now), 'c': it.get('category'), 'kw': it.get('kw') or extract_keyword(_title(it)),
            'fk': it.get('fk') or follow_keyword(it), 'tp': topics_of(it),
            'w': why_text(it), 'x': _match_text(it),
        }
        if it.get('kind') == 'change':
            d['b'], d['a'] = it.get('before', ''), it.get('after', '')
        elif it.get('summary') and d['lead']:
            d['sm'] = it['summary']
            if it.get('summary_src') == 'body':
                d['sb'] = 1
        if rel:
            d['rel'] = [[_title(r), r.get('source', ''), r['url'], _id(r)] for r in rel]
        if it.get('likes') is not None:
            d['likes'] = it['likes']
        out.append(d)
    data = {'gen': int(now.timestamp()), 'updated': f'{now.month}月{now.day}日 {now:%H:%M}',
            'next': next_update_text(now), 'path': base_path, 'archive': archive_link, 'cats': cats, 'items': out}
    # </script> を閉じさせないよう < をエスケープ
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def build_html(items, categories, settings, archive_link, changes=None, now=None):
    now = (now or datetime.now(JST)).astimezone(JST)
    changes = changes or []
    for it in items + changes:
        it.setdefault('id', article_id(it['url']))
        it.setdefault('kw', extract_keyword(_title(it)))
        it.setdefault('fk', follow_keyword(it))
    leaders = [i for i in items if not i.get('cluster_of')]
    followers = [i for i in items if i.get('cluster_of')]
    by_cat = {c['id']: [] for c in categories}
    for it in leaders:
        by_cat.setdefault(it['category'], []).append(it)
    shown = [c for c in categories if by_cat.get(c['id'])]

    news = [i for i in leaders if i.get('profile') != 'heat']  # 人気記事(アツさ)は注目の対象外
    n5 = sum(1 for i in news if i.get('importance') == 5)
    n4 = sum(1 for i in news if i.get('importance') == 4)
    picks = sorted([i for i in news if i.get('importance', 2) >= 4], key=_rank_key, reverse=True)[:PICKUP_N]
    pick_html = ''.join(row_html(i, 'pick', now) for i in picks)
    chg_html = ''.join(row_html(i, 'chg', now) for i in changes)
    sections = ''.join(category_section(c, by_cat[c['id']], settings['show_per_category'], now) for c in shown)

    base = archive_link.rstrip('/').removesuffix('/archive')
    base_path = (urlparse(base).path.rstrip('/') or '') + '/'
    data = page_data(leaders + changes, followers, categories, now, archive_link, base_path)

    body = f"""<a class="skip pc-only" href="#main">本文へ移動</a>
<div class="pc-only">
<header class="site-header"><div class="wrap">
  <h1 class="site-title">Tech News Digest <span class="upd">{now.month}月{now.day}日 {now:%H:%M} 更新</span></h1>
  <div class="header-tools">
    <button type="button" class="btn js-only" id="settings-btn" aria-expanded="false" aria-controls="settings">表示設定</button>
    <button type="button" class="btn js-only" id="theme" aria-pressed="false">ダーク表示</button>
    <a class="btn" href="{esc(archive_link)}">過去のニュース</a>
  </div>
</div></header>
<div class="wrap">
  <section class="settings" id="settings" aria-label="表示設定" hidden>
    <div class="grp"><b>フォロー中</b><span id="set-follow" style="display:contents"></span></div>
    <form class="addf grp"><label for="addf-pc" style="min-width:96px;font-weight:700">キーワードを追加</label><input id="addf-pc" type="text" maxlength="40" placeholder="例: Rust、AWS、脆弱性" autocomplete="off"><button type="submit">フォロー</button></form>
    <div class="grp"><b>見たくない</b><span id="set-mute" style="display:contents"></span></div>
    <p class="note">設定と既読はこのブラウザのCookieに保存されます(既読は直近7日分)。ログインは不要です。</p>
  </section>
  <div class="bar js-only flex">
    <div class="seg" role="group" aria-label="表示する記事">
      <button type="button" id="seg-unread" aria-pressed="true">前回以降の新着 <span id="cnt-unread">0</span>件</button>
      <button type="button" id="seg-all" aria-pressed="false">すべて <span id="cnt-all">{len(leaders) + len(changes)}</span>件</button>
    </div>
    <button type="button" class="btn link" id="read-all">すべて既読にする</button>
    <span class="muted-n">非表示 <span id="cnt-muted">0</span>件(見たくない設定)</span>
  </div>
  <p class="status" id="status" role="status" aria-live="polite">全{len(leaders) + len(changes)}件(Lv5 {n5}件・Lv4 {n4}件)</p>
  <main id="main">
    <div class="done" id="done" hidden><b>新着はすべて読みました</b>{esc(next_update_text(now))}</div>
    <section class="sec boxed" id="sec-pick" aria-labelledby="h-pick"><h2 id="h-pick">注目<span class="note">同じ話題はまとめて1行</span></h2>
      <ul class="list">{pick_html}</ul><p class="empty-note"{' hidden' if picks else ''}>新着はありません。</p></section>
    <section class="sec" id="sec-chg" aria-labelledby="h-chg"><h2 id="h-chg">ページの変化<span class="note">RSSのないページの前日との差分</span></h2>
      <ul class="list">{chg_html}</ul><p class="empty-note"{' hidden' if changes else ''}>{'新着はありません。' if changes else '前日からの変化はありません。'}</p></section>
    <section class="sec js-only" id="sec-follow" aria-labelledby="h-follow" hidden><h2 id="h-follow">フォロー中<span class="note" id="follow-note"></span></h2>
      <ul class="list" id="follow-list"></ul><p class="empty-note" id="follow-empty">新着はありません。</p></section>
    {sections}
  </main>
  <footer class="site-footer">
    <p>収集元は <a href="https://github.com/mazume-tech-club/tech-news-digest/blob/main/feeds.yml">feeds.yml</a> で管理しています。追加したいフィード・監視したいページがあれば Pull Request をお送りください。</p>
    <p>Lv と「重要な理由」は Jev の判定(影響範囲・緊急性・新規性・宣伝度)から作っています(利用できない場合はキーワード判定)。Lv5 はその日の上位数件だけに付きます。英語の見出しは自動翻訳です。</p>
  </footer>
</div>
</div>
<div id="app"></div>
<script type="application/json" id="tnd-data">{data}</script>"""
    return _page(f'Tech News Digest — {now.year}年{now.month}月{now.day}日', body, BODY_JS, base)


def build_archive_index(dates, pages_url):
    groups = {}
    for d in sorted(dates, reverse=True):
        groups.setdefault(d[:7], []).append(d)
    parts = []
    for ym, ds in groups.items():
        rows = ''.join(f'<li class="row"><a href="{esc(pages_url)}/{d[:4]}/{d[5:7]}/{d}.html">'
                       f'{int(d[:4])}年{int(d[5:7])}月{int(d[8:])}日</a></li>' for d in ds)
        parts.append(f'<section class="arch-month"><h2>{int(ym[:4])}年{int(ym[5:])}月</h2>'
                     f'<ul class="list arch-list">{rows}</ul></section>')
    content = ''.join(parts) or '<p class="done">アーカイブはまだありません。</p>'
    body = f"""<a class="skip" href="#main">本文へ移動</a>
<header class="site-header"><div class="wrap">
  <h1 class="site-title">Tech News Digest <span class="upd">過去のニュース(全{len(dates)}日分)</span></h1>
  <div class="header-tools"><a class="btn" href="{esc(pages_url)}/">最新のニュースへ</a></div>
</div></header>
<div class="wrap"><main id="main">{content}</main></div>"""
    return _page('過去のニュース — Tech News Digest', body, base=pages_url)
