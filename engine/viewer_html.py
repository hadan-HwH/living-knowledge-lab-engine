"""정본 뷰어 렌더 — 얇다. 분기 로직은 viewer.py에 있고 여기엔 없다.

★로직이 여기로 새면 테스트가 못 잡는다(설계 §3-1). 새면 되돌린다.
★템플릿은 str.format이 아니라 토큰 치환이다 — format을 쓰면 CSS·JS의 중괄호를
  전부 이중으로 써야 해서, 실수 하나가 문서 전체를 깨뜨린다.
"""
import json

_TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>Living Knowledge · __CORPUS__</title>
<style>
:root{--bd:#d8d8d8;--mut:#6b6b6b;--bg:#fff;--fg:#111;--hi:#f6f6f4;--acc:#8b1a1a}
@media(prefers-color-scheme:dark){:root{--bd:#3a3a3a;--mut:#9a9a9a;--bg:#151515;
--fg:#eee;--hi:#1f1f1f;--acc:#ff9a9a}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",
sans-serif;background:var(--bg);color:var(--fg)}
header{border-bottom:1px solid var(--bd);padding:10px 16px}
h1{font-size:14px;margin:0 0 8px;font-weight:600}
h2{font-size:16px;margin:0 0 4px}
h3{font-size:13px;margin:18px 0 4px;color:var(--mut);font-weight:600}
nav button{font:inherit;background:none;border:1px solid var(--bd);border-radius:4px;
padding:4px 12px;margin-right:6px;cursor:pointer;color:inherit}
nav button[aria-current=true]{background:var(--fg);color:var(--bg)}
.warn{background:#fdeaea;color:#7a1010;padding:8px 16px;font-size:13px}
@media(prefers-color-scheme:dark){.warn{background:#3a1414;color:#ffb4b4}}
.cov{padding:8px 16px;color:var(--mut);font-size:12px;border-bottom:1px solid var(--bd)}
main{display:flex;height:calc(100vh - 132px)}
#list{width:38%;overflow:auto;border-right:1px solid var(--bd)}
#detail{flex:1;overflow:auto;padding:16px}
.row{padding:8px 12px;border-bottom:1px solid var(--bd);cursor:pointer}
.row:hover{background:var(--hi)}
.filters{padding:8px 12px;border-bottom:1px solid var(--bd);position:sticky;top:0;
background:var(--bg)}
.filters input,.filters select{font:inherit;padding:3px 6px;margin:0 6px 4px 0}
.badge{font-size:11px;border:1px solid var(--bd);border-radius:3px;padding:0 5px;
color:var(--mut);margin-right:5px}
.frag{border-left:2px solid var(--bd);padding:4px 0 4px 10px;margin:8px 0}
.frag pre{white-space:pre-wrap;margin:4px 0;font:inherit}
details{margin:10px 0}
summary{cursor:pointer;color:var(--mut)}
table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid var(--bd);padding:6px 8px;text-align:left;
vertical-align:top;font-size:13px}
a{color:inherit}
.mut{color:var(--mut)}
.iss{color:var(--acc)}
#map{padding:14px 16px;overflow:auto;flex:1}
.note{color:var(--mut);font-size:12px;margin:0 0 12px}
.grp{border:1px solid var(--bd);border-radius:6px;margin:0 0 12px;overflow:hidden}
.grp>h3{margin:0;padding:6px 10px;background:var(--hi);color:var(--fg);font-size:13px;
display:flex;justify-content:space-between;border-bottom:1px solid var(--bd)}
.grp>h3 .n{color:var(--mut);font-weight:400}
.cells{display:flex;flex-wrap:wrap;gap:6px;padding:8px 10px}
.cell{border:1px solid var(--bd);border-radius:4px;padding:6px 8px;cursor:pointer;
min-width:96px;background:var(--bg);display:flex;flex-direction:column;justify-content:flex-end}
.cell:hover{border-color:var(--fg)}
.cell b{display:block;font-weight:600;font-size:12px}
.cell.more{width:96px!important;min-height:46px!important;justify-content:center;
align-items:center;color:var(--mut);border-style:dashed}
.cell .n{color:var(--mut);font-size:11px}
.bar{display:flex;height:3px;margin-top:5px;border-radius:2px;overflow:hidden}
.bar i{display:block}
.lk{font-size:12px;color:var(--mut);padding:2px 0}
.lk b{color:var(--fg);font-weight:600}
.leg{color:var(--mut);font-size:11px;margin:10px 0 0;line-height:1.9}
.leg i{display:inline-block;width:10px;height:10px;border-radius:2px;
vertical-align:-1px;margin-right:3px}
</style></head><body>
<header><h1>Living Knowledge · __CORPUS__ <span class="mut">@__SHA__</span></h1>
<nav><button data-page="지도" aria-current="true">지도</button>
<button data-page="개념">개념</button>
<button data-page="어긋남">어긋남</button>
<button data-page="현황">현황</button></nav></header>
<div id="warn"></div><div class="cov" id="cov"></div>
<main><div id="map" hidden></div><div id="list"></div><div id="detail"></div></main>
<script id="model" type="application/json">__PAYLOAD__</script>
<script>
const M = JSON.parse(document.getElementById("model").textContent);
const $ = (s) => document.querySelector(s);
function el(tag, cls, txt) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
}
const ISS = Object.fromEntries(M.issues.map(i => [i.id, i]));

if (M.warnings.length) {
  const w = $("#warn");
  w.className = "warn";
  w.textContent = "\\u26a0 " + M.warnings.join("  /  ");
}

// 커버리지 배너 — 안 잰 것은 0이 아니라 "안 쟀음"으로 뜬다.
const c = M.coverage;
const cv = (o, f) => o === null ? "안 쟀음" : f(o);
$("#cov").textContent = [
  "대조 " + cv(c.crosscheck, o => o.checked + "/" + o.total + " 개념"),
  "침식 " + cv(c.integrity, o => "참조 " + o.refs_checked + "건 스캔"),
  "낡음 " + cv(c.drift, o => (o.fresh ? "fresh" : "stale") + "(" + o.canon_sha + ")"),
  "앵커 미해소 " + c.unresolved_anchors,
  "기타 kind " + Object.keys(c.other_kinds).length
].join("   ·   ");

function anchorOf(k) { return (!k || k === "quote") ? null : k.split("|")[0]; }
function famOf(a) { const s = M.sources[a]; return s ? s.family : "미해소"; }
function linkOf(a) {
  const s = M.sources[a];
  if (!s || !s.file) return null;
  const root = M.meta.source_root;
  // 절대경로면 file:// 링크, 상대경로면 HTML 위치 기준 상대 링크(기계마다 같은 산출물).
  return (root.startsWith("/") ? "file://" + root : root) + "/" + s.file + "#L" + s.line;
}

function fragBox(f) {
  const a = anchorOf(f.key), b = el("div", "frag"), h = el("div");
  h.appendChild(el("span", "badge", a ? famOf(a) : "인용"));
  const u = linkOf(a), s = M.sources[a];
  if (u) { const x = el("a", null, f.key); x.href = u; h.appendChild(x); }
  else h.appendChild(el("span", "mut", f.key));
  // 링크가 브라우저 정책에 막혀도 경로·줄은 텍스트로 남는다(설계 3-1-2 완화책).
  if (s && s.file) h.appendChild(el("span", "mut", "  " + s.file + ":" + s.line));
  if (f.superseded_at) h.appendChild(el("span", "mut", "  대체 " + f.superseded_at));
  if (f.removed_at) h.appendChild(el("span", "mut", "  삭제 " + f.removed_at));
  b.appendChild(h);
  b.appendChild(el("pre", null, f.text || ""));
  return b;
}

function showConcept(x) {
  const d = $("#detail");
  d.innerHTML = "";
  d.appendChild(el("h2", null, x.name || x.anchor));
  d.appendChild(el("div", "mut",
    [x.anchor, x.scope, x.commitment, x.confidence, x.basis].filter(Boolean).join("  ·  ")));
  (x.issues || []).forEach(id => {
    const i = ISS[id];
    if (i) d.appendChild(el("div", "warn", "\\u26a0 " + i.kind + " — " + i.title));
  });
  d.appendChild(el("h3", null, "현행 " + x.fragments.current.length));
  x.fragments.current.forEach(f => d.appendChild(fragBox(f)));
  [["history", "이력"], ["removed", "삭제"]].forEach(pair => {
    const k = pair[0], label = pair[1];
    if (!x.fragments[k].length) return;
    const dt = el("details");
    dt.appendChild(el("summary", null, label + " " + x.fragments[k].length));
    x.fragments[k].forEach(f => dt.appendChild(fragBox(f)));
    d.appendChild(dt);
  });
  if (x.neighbors.length) {
    d.appendChild(el("h3", null, "관계 " + x.neighbors.length));
    x.neighbors.forEach(n => {
      const r = el("div", "frag");
      r.appendChild(el("span", "badge", n.dir === "out" ? "→" : "←"));
      const a = el("a", null, (n.canonical || "") + " " + n.other);
      a.href = "#";
      a.onclick = (e) => {
        e.preventDefault();
        const t = M.concepts.find(y => y.anchor === n.other);
        if (t) showConcept(t);
      };
      r.appendChild(a);
      if (n.quote) r.appendChild(el("pre", "mut", n.quote));
      d.appendChild(r);
    });
  }
}

function pageConcepts() {
  const L = $("#list");
  L.innerHTML = "";
  const f = el("div", "filters");
  const q = el("input");
  q.placeholder = "이름·anchor 검색";
  const sc = el("select");
  sc.appendChild(new Option("scope 전체", ""));
  Array.from(new Set(M.concepts.map(x => x.scope).filter(Boolean))).sort()
    .forEach(s => sc.appendChild(new Option(s, s)));
  const only = el("label");
  const cb = el("input");
  cb.type = "checkbox";
  only.appendChild(cb);
  only.appendChild(document.createTextNode(" 어긋남만"));
  f.appendChild(q); f.appendChild(sc); f.appendChild(only);
  L.appendChild(f);
  const rows = el("div");
  L.appendChild(rows);
  function draw() {
    rows.innerHTML = "";
    M.concepts.filter(x =>
      (!q.value || ((x.name || "") + x.anchor).includes(q.value)) &&
      (!sc.value || x.scope === sc.value) &&
      (!cb.checked || x.issues.length)
    ).forEach(x => {
      const r = el("div", "row");
      r.appendChild(el("div", null, x.name || x.anchor));
      const meta = x.anchor + "   조각 " + x.fragments.current.length +
        (x.fragments.history.length ? " · 이력 " + x.fragments.history.length : "");
      const m = el("div", "mut", meta);
      if (x.issues.length) m.appendChild(el("span", "iss", "   \\u26a0 " + x.issues.length));
      r.appendChild(m);
      r.onclick = () => showConcept(x);
      rows.appendChild(r);
    });
  }
  q.oninput = draw; sc.onchange = draw; cb.onchange = draw;
  draw();
  $("#detail").innerHTML = "";
}

function pageIssues() {
  $("#list").innerHTML = "";
  const d = $("#detail");
  d.innerHTML = "";
  d.appendChild(el("h2", null, "어긋남 " + M.issues.length + "건"));
  d.appendChild(el("div", "mut", "커버리지는 상단 배너 참조 — 안 잰 것은 0으로 보이지 않는다"));
  const t = el("table");
  const hd = el("tr");
  ["유형", "개념", "내용", "심각도"].forEach(h => hd.appendChild(el("th", null, h)));
  t.appendChild(hd);
  M.issues.forEach(i => {
    const r = el("tr");
    r.appendChild(el("td", null, i.kind));
    const cc = el("td");
    if (i.concept) {
      const a = el("a", null, i.concept);
      a.href = "#";
      a.onclick = (e) => {
        e.preventDefault();
        go("개념");
        const x = M.concepts.find(y => y.anchor === i.concept);
        if (x) showConcept(x);
      };
      cc.appendChild(a);
    } else cc.appendChild(el("span", "mut", "(개념 미연결)"));
    r.appendChild(cc);
    const dd = el("td");
    dd.appendChild(el("div", null, i.title));
    const det = JSON.stringify(i.detail);
    if (det && det !== "{}") dd.appendChild(el("div", "mut", det));
    r.appendChild(dd);
    r.appendChild(el("td", null, i.severity));
    t.appendChild(r);
  });
  d.appendChild(t);
}

function pageStatus() {
  $("#list").innerHTML = "";
  const d = $("#detail");
  d.innerHTML = "";
  d.appendChild(el("h2", null, "현황"));
  d.appendChild(el("div", "mut",
    "숫자는 metrics.yaml 원본 — 뷰어가 다시 세지 않는다"));
  d.appendChild(el("pre", null, JSON.stringify(M.metrics, null, 1)));
  d.appendChild(el("h3", null, "커버리지 — 무엇을 안 쟀나"));
  d.appendChild(el("pre", null, JSON.stringify(M.coverage, null, 1)));
}


const CMT = {frozen:"#3d6b4a", working:"#5b7fa6", hypothesis:"#a08040", exploratory:"#8a8a8a"};
function bar(cm){
  const total = Object.values(cm||{}).reduce((a,b)=>a+b,0);
  const b = el("span"); b.className = "bar";
  if(!total){ return b; }
  for(const [k,v] of Object.entries(cm)){
    const i = el("i"); i.style.width = (v/total*100)+"%";
    i.style.background = CMT[k] || "var(--bd)"; i.title = k+" "+v; b.appendChild(i);
  }
  return b;
}
function cell(node, onClick){
  const c = el("div"); c.className = "cell";
  // 무게 → 폭·높이. 크기가 눈에 안 들어오면 지도가 아니라 표다.
  const w = node.weight || 0.12;
  c.style.width = (96 + Math.round(w * 250)) + "px";
  c.style.minHeight = (46 + Math.round(w * 44)) + "px";
  c.appendChild(el("b", null, node.label || node.name));
  c.appendChild(el("span", "n", `개념 ${node.concepts ?? 1} · 조각 ${node.fragments}`));
  c.appendChild(bar(node.commitment));
  if(onClick){ c.onclick = onClick; }
  return c;
}
function pageMap(){
  $("#map").hidden = false; $("#list").hidden = true; $("#detail").hidden = true;
  const m = M.map || {groups:[], links:[], stats:{}}, d = $("#map");
  d.innerHTML = "";
  const s = m.stats || {};
  d.appendChild(el("p", "note",
    `${m.axis_note || ""}  —  무리 ${s.groups ?? 0} · 개념 ${s.concepts ?? 0} · `
    + `조각 ${s.fragments ?? 0} · 관계 안 ${s.relations_within ?? 0} / 관통 ${s.relations_across ?? 0}`));
  for(const g of m.groups){
    const box = el("div"); box.className = "grp";
    const h = el("h3"); h.appendChild(el("span", null, g.label || g.name));
    h.appendChild(el("span", "n", `개념 ${g.concepts} · 조각 ${g.fragments}`));
    box.appendChild(h);
    const cells = el("div"); cells.className = "cells";
    const kids = g.children || [];
    // 무리 하나가 화면을 다 먹으면 지도가 아니다 — 큰 것부터 CAP개만 펴 두고 나머지는 접는다.
    const CAP = 12;
    function fill(n){
      cells.innerHTML = "";
      for(const k of kids.slice(0, n)){
        const target = k.anchor ? M.concepts.find(c => c.anchor === k.anchor) : null;
        cells.appendChild(cell(k, target ? () => { go("개념"); showConcept(target); } : null));
      }
      if(kids.length > n){
        const more = el("div"); more.className = "cell more";
        more.appendChild(el("b", null, `+${kids.length - n}`));
        more.appendChild(el("span", "n", "더 보기"));
        more.onclick = () => fill(kids.length);
        cells.appendChild(more);
      }
    }
    fill(CAP);
    box.appendChild(cells);
    d.appendChild(box);
  }
  if((m.links||[]).length){
    const box = el("div"); box.className = "grp";
    box.appendChild(el("h3", null, `무리를 관통하는 관계 ${m.links.length}종`));
    const w = el("div"); w.style.padding = "8px 10px";
    for(const l of m.links.slice(0, 40)){
      const p = el("div", "lk");
      p.appendChild(el("b", null, l.from));
      p.appendChild(el("span", null, ` —${l.canonical || "?"}→ `));
      p.appendChild(el("b", null, l.to));
      if(l.count > 1){ p.appendChild(el("span", null, `  ×${l.count}`)); }
      w.appendChild(p);
    }
    if(m.links.length > 40){ w.appendChild(el("div","lk",`… 그리고 ${m.links.length-40}종 더`)); }
    box.appendChild(w); d.appendChild(box);
  }
  const leg = el("p", "leg");
  leg.innerHTML = "<b>읽는 법</b> — 칸 하나가 갈래(또는 개념), 아래 띠는 확정도 비율. "
    + "숫자는 개념 수와 <b>현행 조각 수</b>(두께)다. 조각이 적은 칸은 기획만 있고 근거가 얇다는 뜻. "
    + "칸을 누르면 개념 페이지로 간다.<br>"
    + Object.entries(CMT).map(([k,v]) => `<i style="background:${v}"></i>${k}`).join(" &nbsp; ");
  d.appendChild(leg);
}

const PAGES = { "지도": pageMap, "개념": pageConcepts, "어긋남": pageIssues, "현황": pageStatus };
function go(p) {
  document.querySelectorAll("nav button").forEach(b =>
    b.setAttribute("aria-current", String(b.dataset.page === p)));
  if(p !== "지도"){ $("#map").hidden = true; $("#list").hidden = false; $("#detail").hidden = false; }
  PAGES[p]();
}
document.querySelectorAll("nav button").forEach(b => {
  b.onclick = () => go(b.dataset.page);
});
go("지도");
</script></body></html>
"""


def render_html(model):
    """뷰 모델 → 자기 완결 HTML. 외부 요청 0(오프라인·CSP에서도 뜬다)."""
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    # 본문에 </script>가 있으면 문서가 거기서 끊긴다 — JSON 문자열 안에서 안전하게 깬다.
    payload = payload.replace("</", "<\\/")
    return (_TEMPLATE
            .replace("__PAYLOAD__", payload)
            .replace("__CORPUS__", str(model["meta"]["corpus"]))
            .replace("__SHA__", str(model["meta"].get("source_sha") or "?")))
