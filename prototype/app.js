/* =========================================================
   訴願智審臺 v3　應用邏輯（純前端・全部 mock）
   流程：上傳 → 歸戶確認 → 分析 → 工作畫面（5 分頁）→ 送審 → 結案歸檔 → 案件庫
   ========================================================= */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
const DAY = 86400000;
const isoT = (iso) => { const m = /^(\d{2,3})-(\d{1,2})-(\d{1,2})$/.exec(iso || ""); return m ? Date.UTC(+m[1] + 1911, +m[2] - 1, +m[3]) : null; };
const toMg = (t) => { const d = new Date(t); return `${d.getUTCFullYear() - 1911}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`; };
const cnDate = (t) => { const d = new Date(t); return `${d.getUTCFullYear() - 1911} 年 ${d.getUTCMonth() + 1} 月 ${d.getUTCDate()} 日`; };
const now = () => { const d = new Date(); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`; };
const today = () => toMg(Date.now());
const J = (ref, text) => ref ? `<span class="jump" data-jump="${ref}">${text}</span>` : text;
const plain = (h) => String(h ?? "").replace(/<[^>]+>/g, "");
const PN = { A: "甲", B: "乙", C: "丙", X: "甲" };
const TYPES = ["訴願書", "答辯書", "裁處書", "送達證書", "檢舉資料", "稽查紀錄", "採證照片", "影像放大", "車籍資料", "通知書", "陳述意見書", "係數計算", "簽呈", "影片", "卷證目錄", "調查筆錄", "決定書", "其他"];

/* ---------- 全域狀態 ---------- */
const S = { c: null, live: false, libId: null, status: "承辦中", served: null, recv: null, stances: {}, plan: null, paras: [], versions: [], audit: [], objections: [], doc: null, zoom: 1, final: null, court: null, finalDiff: null, labels: [] };
let LIB = [];
try { LIB = JSON.parse(localStorage.getItem("ssz.lib") || "[]"); } catch (e) { LIB = []; }
function saveLib() { try { localStorage.setItem("ssz.lib", JSON.stringify(LIB)); } catch (e) { /* 容量不足時略過 */ } }

/* ---------- 主題 ---------- */
function show(id) { $$(".screen").forEach((s) => s.classList.toggle("on", s.id === id)); window.scrollTo(0, 0); }
$$("[data-close]").forEach((b) => b.addEventListener("click", () => $("#" + b.dataset.close).classList.remove("on")));

/* =========================================================
   畫面 1：上傳
   ========================================================= */
let FILES = [];
function classifyByName(name) {
  const rules = [[/訴願書/, "appeal"], [/答辯/, "defense"], [/送達證書|送達/, "served"], [/裁處書|處分書/, "penalty"], [/檢舉/, "complaint"], [/稽查/, "insp"], [/放大/, "zoom"], [/照片|img_|photo/i, "ph1"], [/車籍|監理/, "vehicle"], [/通知書/, "notice"], [/陳述意見書|陳述/, "statement"], [/係數|計算/, "coef"], [/簽呈|簽/, "memo"], [/\.(mp4|mov)$/i, "video"], [/目錄/, "index"], [/筆錄/, "record"], [/決定書/, "final"]];
  for (const [re, d] of rules) if (re.test(name)) return d;
  return null;
}
function renderFiles() {
  const box = $("#fileList");
  box.innerHTML = FILES.map((f, i) => `<div class="filerow"><span class="fn" title="${esc(f.name)}">${esc(f.name)}</span><span class="sz num">${f.kb} KB</span><button class="rm" data-i="${i}" title="移除">×</button></div>`).join("");
  $$(".rm", box).forEach((b) => b.addEventListener("click", () => { FILES.splice(+b.dataset.i, 1); renderFiles(); }));
  const n = FILES.length, kb = FILES.reduce((a, f) => a + f.kb, 0);
  $("#runBtn").disabled = n === 0;
  $("#fileHint").textContent = n === 0 ? "尚未加入檔案" : `${n} 個檔案・${(kb / 1024).toFixed(1)} MB・由 Claude 判定類型與來源後直接分析`;
}
function addFiles(list) { Array.from(list).forEach((f) => { if (FILES.some((x) => x.name === f.name)) return; FILES.push({ name: f.name, kb: Math.max(1, Math.round((f.size || 0) / 1024)), docId: undefined, base: "B" }); }); renderFiles(); }
const drop = $("#drop"), fileInput = $("#file");
drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
fileInput.addEventListener("change", (e) => { addFiles(e.target.files); fileInput.value = ""; });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
function loadPack(messy) {
  FILES = CASE_B.files.map(([name, kb, tagName, docId]) => ({ name: messy ? (MESSY_NAMES[docId] || name) : name, kb, docId, base: "B" }));
  renderFiles();
}
$("#packBtn").addEventListener("click", () => loadPack(false));
$("#messyBtn").addEventListener("click", () => loadPack(true));
$("#clearBtn").addEventListener("click", () => { FILES = []; renderFiles(); });
$("#runBtn").addEventListener("click", () => runCase(autoClassify()));

/* ---------- 貼上文字 ---------- */
const pasteBox = $("#pasteBox"), parseBtn = $("#parseBtn"), pasteHint = $("#pasteHint");
function syncPaste() { const n = pasteBox.value.trim().length; parseBtn.disabled = n < 40; pasteHint.textContent = n === 0 ? "尚未輸入內容" : n < 40 ? `已輸入 ${n} 字，至少需 40 字` : `已輸入 ${n} 字，可解析`; }
pasteBox.addEventListener("input", syncPaste); syncPaste();
$("#sampleBtn").addEventListener("click", () => { pasteBox.value = SAMPLE_TEXT; syncPaste(); pasteBox.focus(); });
parseBtn.addEventListener("click", () => { const raw = pasteBox.value.trim(); if (raw.length >= 40) runCase(buildLive(parseAppeal(raw))); });

/* ---------- 示範案件卡與案件庫卡 ---------- */
$("#caseGrid").innerHTML = CASES.map((c, i) => `<button class="case-card" data-i="${i}"><span class="no num">案號 ${c.no}</span><h3>${c.cardTitle}</h3><p>${c.cardDesc}</p><div style="display:flex;flex-wrap:wrap;gap:6px">${c.cardTags.join("")}</div><div class="foot"><span>${c.name}</span><span class="go">開始分析 →</span></div></button>`).join("");
$$(".case-card").forEach((el) => el.addEventListener("click", () => runCase(structuredClone(CASES[+el.dataset.i]))));
function renderLibCard() {
  const n = (st) => LIB.filter((r) => r.status === st).length;
  const closed = LIB.filter((r) => r.status === "已結案").sort((a, b) => (b.closedAt || "").localeCompare(a.closedAt || ""));
  const court = LIB.filter((r) => r.court).sort((a, b) => (b.court.at || "").localeCompare(a.court.at || ""));
  $("#libCard").innerHTML = `<div><span class="v num">${n("承辦中")}</span><span class="k">承辦中</span></div><div><span class="v num">${n("已送審")}</span><span class="k">已送審</span></div><div><span class="v num">${n("已結案")}</span><span class="k">已結案</span></div><div><span class="v num" style="font-size:14px">${closed[0] ? closed[0].closedAt : "—"}</span><span class="k">最近結案</span></div><div><span class="v num" style="font-size:14px">${court[0] ? court[0].court.at : "—"}</span><span class="k">最近法院結果回填</span></div><div style="display:grid;place-items:center"><span class="btn" style="font-size:12px">開啟案件庫 →</span></div>`;
}
$("#libCard").addEventListener("click", openLibrary);
$("#libBtn").addEventListener("click", openLibrary);
$("#backBtn").addEventListener("click", () => { persist(); show("s-pick"); ["chip", "statusChip", "judgeChip"].forEach((id) => $("#" + id).classList.remove("on")); $("#backBtn").style.display = "none"; renderLibCard(); });
renderLibCard();

/* =========================================================
   自動歸戶（Claude 判定・mock）：不經人手，直接建案
   ========================================================= */
function autoClassify() {
  const base = CASE_B, c = structuredClone(base), seen = new Set(), docs = [];
  FILES.forEach((f, i) => {
    const ext = (f.name.match(/\.[a-z0-9]+$/i) || [""])[0].toLowerCase();
    const docId = f.docId !== undefined ? f.docId : classifyByName(f.name);
    const d0 = docId ? base.docs.find((x) => x.id === docId) : null;
    if (d0 && seen.has(docId)) { docs.push({ id: "dup-" + i, title: f.name, origName: f.name, stdName: f.name, tag: d0.tag, src: d0.src, kind: "missing", include: false, dup: true, summary: `與「${STD_NAME[docId] || d0.title}」內容相同，已排除`, note: "重複檔案，已自動排除。" }); return; }
    if (d0) { const d = structuredClone(d0); d.origName = f.name; d.stdName = (STD_NAME[docId] || d0.title) + ext; d.include = true; docs.push(d); seen.add(docId); }
    else docs.push({ id: "x-" + i, title: f.name, origName: f.name, stdName: f.name, tag: "其他", src: "原處分機關", kind: /\.(jpg|jpeg|png)$/.test(ext) ? "image" : "missing", file: null, include: true, unknown: true, summary: "無法辨識內容（mock：不在對照表）", note: "Claude 判定：無法辨識此文件內容，已列入卷宗但不進三方對照。" });
  });
  const order = base.docs.map((d) => d.id); docs.sort((a, b) => (order.indexOf(a.id) < 0 ? 99 : order.indexOf(a.id)) - (order.indexOf(b.id) < 0 ? 99 : order.indexOf(b.id)));
  c.docs = docs.length ? docs : base.docs.slice();
  c.autoCount = c.docs.filter((d) => d.include !== false).length;
  c.uploadNote = `Claude 判定 ${c.docs.length} 個檔案，${c.autoCount} 份納入分析`;
  return c;
}

/* =========================================================
   即時解析（貼上文字）
   ========================================================= */
function findDates(text) { const out = [], re = /(?:民國\s*)?(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/g; let m; while ((m = re.exec(text))) { const y = +m[1], mo = +m[2], d = +m[3]; if (y < 90 || y > 130 || mo < 1 || mo > 12 || d < 1 || d > 31) continue; out.push({ raw: m[0], idx: m.index, iso: `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`, t: Date.UTC(y + 1911, mo - 1, d) }); } return out; }
function dateNear(text, dates, keys, win = 60) { for (const k of keys) { let from = 0, i; while ((i = text.indexOf(k, from)) >= 0) { let best = null, bd = Infinity; for (const d of dates) { const dist = d.idx < i ? i - (d.idx + d.raw.length) : d.idx - i; if (dist <= win && dist < bd) { bd = dist; best = d; } } if (best) return best; from = i + k.length; } } return null; }
const firstMatch = (t, re) => { const m = t.match(re); return m ? (m[1] || m[0]).trim() : null; };
function classifySubject(text) { let best = null, bn = 0; for (const [s, ks] of SUBJ_KEYS) { const n = ks.reduce((a, k) => a + (text.includes(k) ? (k.length > 4 ? 2 : 1) : 0), 0); if (n > bn) { bn = n; best = s; } } return { subj: best, hits: bn }; }
const famOf = (s) => FAMILY.findIndex((f) => f.includes(s));
function searchDocs(subj, art, n = 5) { const fam = famOf(subj); return DOC_INDEX.map((d) => { let s = 8; if (subj && d.subj === subj) s += 46; else if (fam >= 0 && famOf(d.subj) === fam) s += 21; if (art && d.art.indexOf(art) >= 0) s += 33; s += Math.max(0, 10 - (114 - d.y) * 2.5); return { ...d, s: Math.min(97, Math.round(s)) }; }).sort((a, b) => b.s - a.s || b.y - a.y).slice(0, n); }
function whyDoc(d, q) { const b = []; if (d.subj === q.subj) b.push("案由完全相同"); else if (famOf(d.subj) >= 0 && famOf(d.subj) === famOf(q.subj)) b.push("同屬相近法規領域"); if (q.art && d.art.indexOf(q.art) >= 0) b.push(`同以訴願法 ${q.art} 作成決定`); if (d.y >= 113) b.push("近年決定書"); if (d.res.indexOf("撤銷") >= 0) b.push("結果為撤銷，建議作為反面對照"); return b.length ? b.join("；") + "。" : "案由與法條部分相符。"; }
function parseAppeal(raw) {
  const t0 = performance.now(), text = raw.replace(/\r/g, "").trim(), dates = findDates(text);
  const applicant = firstMatch(text, /訴願人[：:　\s]*([一-龥○Ｏ]{2,5})/), agent = firstMatch(text, /代理人[：:　\s]*([一-龥○Ｏ]{2,5})/);
  const agency = firstMatch(text, /(新北市政府[一-龥]{2,10}(?:分局|局|處))|(新北市[一-龥]{1,4}區公所)|(新北市政府)/);
  const orderNo = (firstMatch(text, /([一-龥]{2,8}字第?\s*[0-9A-Za-z][0-9A-Za-z\-]{3,}\s*號?)/) || "").replace(/^[日月年時分號第許起至]+/, "").trim() || null;
  const amount = firstMatch(text, /(?:新臺幣|新台幣)?\s*([\d,]{3,})\s*元/);
  const dServed = dateNear(text, dates, ["送達", "收受", "簽收", "收到"]), dReceived = dateNear(text, dates, ["收文", "提起本件訴願", "提起訴願", "遞狀"]);
  const dOrder = dateNear(text, dates, ["裁處書", "處分書", "告誡", "原處分", "所為之處分"]) || dates[0] || null;
  const { subj, hits } = classifySubject(text); const receiverOther = /配偶|同居|家人|代為簽收|代收|舍弟|舍妹|管理員/.test(text);
  return { text, dates, applicant, agent, agency, orderNo, amount, dServed, dReceived, dOrder, subj, hits, receiverOther, ms: Math.max(1, Math.round(performance.now() - t0)) };
}
function buildLive(p) {
  const Sj = p.subj || "未判定";
  const marks = [["ap-applicant", p.applicant], ["ap-agent", p.agent], ["ap-agency", p.agency], ["ap-orderno", p.orderNo], ["ap-amount", p.amount], ["ap-served", p.dServed && p.dServed.raw], ["ap-recv", p.dReceived && p.dReceived.raw], ["ap-orderdate", p.dOrder && p.dOrder.raw]];
  let html = esc(p.text); marks.forEach(([ref, v]) => { if (!v) return; const t = esc(v), i = html.indexOf(t); if (i < 0) return; html = html.slice(0, i) + `<mark data-ref="${ref}">` + t + "</mark>" + html.slice(i + t.length); });
  const doc = `<div class="doc-meta num">來源：貼上文字<br>字數：${p.text.length}　偵測日期：${p.dates.length} 處　解析耗時：${p.ms} ms</div>` + html.split(/\n+/).filter((s) => s.trim()).map((s) => `<p>${s}</p>`).join("");
  const refs = {}; marks.forEach(([r, v]) => { if (v) refs[r] = ["appeal", "mark"]; });
  const V = (v) => v || "未能自文本判定";
  const fields = [{ k: "訴願人", a: [V(p.applicant), p.applicant ? "ap-applicant" : null], d: ["—（尚無答辯書）", null], e: ["—", null] }, { k: "代理人", a: [V(p.agent), p.agent ? "ap-agent" : null], d: ["—", null], e: ["—", null] }, { k: "原處分機關", a: [V(p.agency), p.agency ? "ap-agency" : null], d: ["—", null], e: ["—", null] }, { k: "原處分文號", a: [V(p.orderNo), p.orderNo ? "ap-orderno" : null], d: ["—", null], e: ["—", null] }, { k: "送達日", a: [p.dServed ? p.dServed.iso + (p.receiverOther ? "（他人代收）" : "") : "未能自文本判定", p.dServed ? "ap-served" : null], d: ["—", null], e: ["須核對送達證書", null], conflict: p.dServed ? "訴願書自述送達日，須以卷附送達證書為準" : null }, { k: "機關收文日", a: [V(p.dReceived && p.dReceived.iso), p.dReceived ? "ap-recv" : null], d: ["—", null], e: ["收文戳", null] }, { k: "裁罰金額", a: [V(p.amount && p.amount + " 元"), p.amount ? "ap-amount" : null], d: ["—", null], e: ["—", null] }];
  const laws = PROC_LAWS.slice(); (SUBJ_LAWS[Sj] || []).forEach((l) => laws.push({ ...l, g: "實體法規" }));
  REFS.forEach((r) => { const hit = r.kw.filter((k) => p.text.includes(k)).length; if (hit) laws.push({ g: r.g, n: r.n, t: r.t, rel: Math.min(97, r.rel + hit * 2), badges: [tag("neutral", "資料集內文件"), tag("accent", `命中關鍵字 ${hit} 個`)] }); });
  const alert = (Sj === "洗錢防制法" && p.dOrder && p.dOrder.t < Date.UTC(2024, 7, 2)) ? { title: "法規時效性警示", text: `<b>洗錢防制法於 113 年 7 月 31 日全文修正公布、113 年 8 月 2 日施行。</b>本案偵測到之日期 <b>${p.dOrder.iso}</b> 落在修正施行日之前，請依行政罰法第 5 條為新舊法比較。` } : null;
  const simsRaw = searchDocs(Sj, "79I"), q = { subj: Sj, art: "79I" };
  const sims = simsRaw.map((d) => ({ fn: d.fn, s: d.s, why: whyDoc(d, q), chips: [d.res, d.art, d.subj].concat(d.res.indexOf("撤銷") >= 0 ? ["反面案例"] : []) }));
  const cnt = { 不受理: 0, 駁回: 0, 撤銷: 0 }; simsRaw.forEach((d) => { if (d.res.indexOf("不受理") >= 0) cnt.不受理++; else if (d.res.indexOf("駁回") >= 0) cnt.駁回++; else cnt.撤銷++; });
  const B = (v) => v ? esc(v) : '<span class="fill">（待補）</span>';
  const head = `訴願人　${B(p.applicant)}${p.agent ? "<br>代理人　" + esc(p.agent) : ""}<br>原處分機關　${B(p.agency)}`;
  const intro = `上列訴願人因${esc(Sj)}事件，不服原處分機關民國 ${p.dOrder ? p.dOrder.raw.replace(/民國\s*/, "") : '<span class="fill">（待補）</span>'} ${B(p.orderNo)}所為之處分，提起訴願一案，本府依法決定如下：`;
  const issue = p.receiverOther ? { id: "I1", title: "送達是否合法生效（他人代收）", a: ["訴願書自述由他人代收，主張未實際知悉。", "ap-served"], d: ["（尚無答辯書）", null], e: [["須核對送達證書", null]], law: ["行政程序法 §73 I", "訴願法 §14 I、III", "法務部 93 年函"], lead: { agency: ["A", "送達生效 → 依期間計算"], appellant: ["B", "送達不生效力 → 進入實體"] }, stance: "agency", objection: { result: "reject", plan: null, reply: "依行政程序法第 73 條第 1 項，付與同居人即生送達效力；訴願書未提出足以排除之事證。維持原判定。", evidence: ["ap-served"] } }
    : { id: "I1", title: "違規事證是否充足", a: ["訴願人主張舉證不足／否認違規。", null], d: ["（尚無答辯書）", null], e: [["須待原處分機關檢卷", null]], law: (SUBJ_LAWS[Sj] || []).map((l) => l.n), lead: { agency: ["A", "事證明確 → 駁回"], appellant: ["B", "舉證不足 → 撤銷"] }, stance: "open", objection: { result: "partial", plan: null, reply: "尚無答辯書與卷證可資重新引證；請於原處分機關檢卷後再提出異議。", evidence: [] } };
  return { id: "LIVE", no: "即時解析", name: `${Sj}　貼上文字`, outcome: "go", subj: Sj, art: "79I", live: true, judge: "A", files: [],
    docs: [{ id: "appeal", title: "訴願書（貼上文字）", tag: "訴願書", src: "訴願人", kind: "text", pages: 1, file: null, html: doc, include: true }], refs, fields,
    cls: [["案件類型", Sj], ["主要爭點", p.receiverOther ? "送達效力與訴願期間" : "違規事證與裁量適法性"], ["預判走向", "依期間計算與爭點表態決定"]],
    period: { served: p.dServed ? p.dServed.iso : null, recv: p.dReceived ? p.dReceived.iso : null, appealSays: null, servedRef: p.dServed ? "ap-served" : null, recvRef: p.dReceived ? "ap-recv" : null },
    checks: [["77(1)", "訴願書合法定程式", p.applicant && p.orderNo ? "pass" : "warn", p.applicant && p.orderNo ? "訴願人與原處分均可辨識" : "欄位不全，須通知補正"], ["77(2)", "於法定期間內提起", "auto", ""], ["77(3)", "當事人適格", "warn", "須核對"], ["77(4)", "具訴願能力", "warn", "須核對"], ["77(5)", "代理人合法", p.agent ? "warn" : "na", p.agent ? "須核對委任狀" : "未委任代理人"], ["77(6)", "行政處分仍存在", "warn", "須向原處分機關確認"], ["77(7)", "非重行提起", "warn", "須查系統"], ["77(8)", "屬訴願救濟範圍", p.orderNo ? "pass" : "warn", p.orderNo ? "已載處分文號" : "須確認"]],
    issues: [issue], objectionOther: CASE_B.objectionOther, citations: [], citationNote: "尚無答辯書可供查核。", laws, alert, sims, simDist: [["不受理", cnt.不受理, "#9C3A2E"], ["駁回", cnt.駁回, "#A8792A"], ["撤銷", cnt.撤銷, "#2E7D5B"]],
    plans: [{ id: "A", name: "甲案", verdict: "訴願駁回", art: "訴願法 §79 I", when: { I1: "agency" }, basis: ["訴願法 §79 I"], facts: ["爭點 1 採機關見解"], cases: sims.slice(0, 2).map((s) => s.fn), risk: ["mid", "尚無答辯書與卷證，風險待檢卷後評估。"] }, { id: "B", name: "乙案", verdict: "原處分撤銷", art: "訴願法 §81 I", when: { I1: "appellant" }, basis: ["訴願法 §81 I"], facts: ["爭點 1 採訴願人見解"], cases: [], risk: ["mid", "尚無卷證。"] }],
    drafts: { A: { tmpl: "79I 駁回（骨架）", head: "新北市政府訴願決定書", sub: "（即時解析草稿・待承辦人審核）", paras: [{ id: "meta", kind: "meta", text: head }, { id: "intro", kind: "p", text: intro }, { id: "h-main", kind: "h4", text: "主文" }, { id: "main", kind: "p", text: "訴願駁回。" }, { id: "h-fact", kind: "h4", text: "事實" }, { id: "fact", kind: "p", text: `緣<span class="fill">（違規事實請依卷證補實）</span>。訴願人不服，於 {{RECV}} 提起本件訴願。` }, { id: "h-reason", kind: "h4", text: "理由" }, { id: "r1", kind: "p", text: `一、按<span class="fill">（主管機關權限依據）</span>。` }, { id: "r2", kind: "p", text: `二、次按${esc(Sj)}相關規定……` }, { id: "r3", kind: "p", text: `三、卷查<span class="fill">（違規事證認定）</span>，其違規事證應堪認定。` }, { id: "r4", kind: "p", text: `四、至訴願人主張<span class="fill">（逐一回應）</span>等語。惟<span class="fill">（駁斥理由）</span>。是訴願人主張，尚難採據。` }, { id: "r5", kind: "p", text: "五、綜上論結，本件訴願為無理由，依訴願法第 79 條第 1 項規定，決定如主文。" }] }, B: { tmpl: "81I 撤銷（骨架）", head: "新北市政府訴願決定書", sub: "（即時解析草稿）", paras: [{ id: "meta", kind: "meta", text: head }, { id: "intro", kind: "p", text: intro }, { id: "h-main", kind: "h4", text: "主文" }, { id: "main", kind: "p", text: "原處分撤銷。" }, { id: "h-reason", kind: "h4", text: "理由" }, { id: "r1", kind: "p", text: `一、<span class="fill">（採訴願人見解之論述）</span>` }, { id: "r2", kind: "p", text: "二、綜上論結，本件訴願為有理由，依訴願法第 81 條第 1 項規定，決定如主文。" }] } },
    final: { verdict: "訴願駁回", date: "", no: "", file: null, paras: {} },
    gain: [[p.ms + " ms", "瀏覽器端解析耗時", "up"], [`${fields.filter((f) => f.a[0] !== "未能自文本判定").length} / ${fields.length}`, "欄位成功擷取", ""], ["101 件", "相似案例檢索範圍", ""], ["待人工", "程序期間審查", ""]] };
}

/* ---------- 逾期通用方案／草稿 ---------- */
function overduePlan() { return { id: "X", name: "甲案", verdict: "訴願不受理", art: "訴願法 §77 ②", when: {}, basis: ["訴願法 §14 I、III", "訴願法 §77 ②", "行政程序法 §72、§73"], facts: ["依承辦人修正之送達日／收文日，本件已逾 30 日法定不變期間"], cases: ["77(2) 類型 21 件皆為不受理"], risk: ["low", "期間計算為純規則運算；送達日之認定須以卷附送達證書為準。"] }; }
function overdueDraft(c) { const meta = (c.drafts.A || Object.values(c.drafts)[0]).paras.find((x) => x.id === "meta"); return { tmpl: "77(2) 不受理（期間重算）", head: "新北市政府訴願決定書", sub: `案號：${c.no} 號　（依修正後期間自動改判・待承辦人審核）`, paras: [meta ? { ...meta } : { id: "meta", kind: "meta", text: "" }, { id: "h-main", kind: "h4", text: "主文" }, { id: "main", kind: "p", text: "訴願不受理。" }, { id: "h-reason", kind: "h4", text: "理由" }, { id: "r1", kind: "p", text: "一、按訴願法第 14 條第 1 項及第 3 項規定：「訴願之提起，應自行政處分達到或公告期滿之次日起 30 日內為之。訴願之提起，以原行政處分機關或受理訴願機關收受訴願書之日期為準。」、第 77 條第 2 款規定：「訴願事件有左列各款情形之一者，應為不受理之決定：二、提起訴願逾法定期間者……。」", cite: "引自　相關法規／訴願法.pdf" }, { id: "r2", kind: "p", text: "二、本件系爭處分於 {{SERVED}} 送達訴願人<span class=\"fill\">（送達方式與受領人請依卷附送達證書補實）</span>，訴願期間應自 {{START}} 起算，至 {{DUE}} 屆滿。惟訴願人遲至 {{RECV}}（機關收文日）始提起本件訴願，已逾 30 日之法定不變期間 {{OVER}} 日，原處分業已確定。", cite: "日期由期間計算模組即時推導（未扣除在途期間）" }, { id: "r3", kind: "p", text: "三、綜上論結，本件訴願為程序不合，依訴願法第 77 條第 2 款規定，決定如主文。" }] }; }

/* =========================================================
   畫面 2：分析中
   ========================================================= */
function runCase(c, restore) {
  S.c = c; S.live = !!c.live;
  if (!restore) {
    S.served = c.period.served; S.recv = c.period.recv; S.stances = {}; c.issues.forEach((i) => { S.stances[i.id] = i.stance || "open"; });
    S.status = "承辦中"; S.plan = null; S.paras = []; S.versions = []; S.audit = []; S.objections = []; S.final = null; S.court = null; S.finalDiff = null; S.sel = null;
    const existing = LIB.find((r) => r.baseId === c.id && r.status === "承辦中" && !c.live);
    S.libId = existing ? existing.libId : `${c.id}-${Date.now().toString(36)}`;
  }
  S.doc = null; S.zoom = 1;
  $("#chip").classList.add("on"); $("#chipName").textContent = c.name; $("#chipNo").textContent = c.live ? c.no : "案號 " + c.no; $("#backBtn").style.display = "";
  if (restore) { render(); show("s-work"); return; }
  const steps = [["文件辨識（Claude 判定）", `${c.docs.length} 個檔案 → ${c.docs.filter((d) => d.include !== false).length} 份納入・${c.docs.filter((d) => d.dup).length} 份重複・${c.docs.filter((d) => d.unknown).length} 份無法辨識`, Math.min(2600, 700 + c.docs.length * 110), "classify"], ["欄位擷取（三方對照）", `${c.fields.length} 個欄位，${c.fields.filter((f) => f.conflict).length} 處衝突`, 700], ["爭點比對（訴願書 vs 答辯書 vs 卷證）", `識別 ${c.issues.length} 個爭點`, 760], ["法規檢索與引用查核", `推薦 ${c.laws.length} 筆；查核答辯書引用 ${c.citations.length} 則${c.citations.some((x) => x.status === "amended") ? "，1 則已修正" : ""}`, 840], ["AI 判定與草稿生成", `判定：${judgePlan(c).verdict}（${judgePlan(c).art}）`, 900]];
  $("#runSub").textContent = c.live ? c.name : `${c.name}　・　案號 ${c.no}${c.uploadNote ? "　・　" + c.uploadNote : ""}`;
  $("#stepList").innerHTML = steps.map((s, i) => `<div class="step" id="st${i}"><div class="idx">${i + 1}</div><div><div class="name">${s[0]}</div><div class="out" id="so${i}"></div>${s[3] ? `<div class="classify" id="cls${i}" style="flex-direction:column;gap:3px">${c.docs.map((d) => `<span style="display:flex;gap:8px;align-items:center;${d.include === false ? "opacity:.55" : ""}"><span class="num" style="color:var(--ink-3);min-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(d.origName || d.title)}</span><span>→</span><b style="white-space:nowrap">${d.tag}</b><span class="srct ${d.src}" style="flex:none">${d.src}</span><span style="color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0">${esc(d.summary || "")}</span></span>`).join("")}</div>` : ""}</div><div class="ms" id="sm${i}"></div></div>`).join("");
  $("#runBar").style.width = "0"; show("s-run");
  let t = 0;
  steps.forEach((s, i) => { setTimeout(() => { const el = $("#st" + i); if (!el) return; el.classList.add("active"); $("#runBar").style.width = ((i + 1) / steps.length * 100) + "%"; if (s[3]) $$("#cls" + i + " > span").forEach((sp, k) => setTimeout(() => sp.classList.add("in"), 80 + k * (1000 / Math.max(1, c.docs.length)))); }, t); t += s[2]; setTimeout(() => { const el = $("#st" + i); if (!el) return; el.classList.remove("active"); el.classList.add("done"); $("#so" + i).textContent = s[1]; $("#sm" + i).textContent = s[2] + " ms"; }, t); });
  setTimeout(() => { render(); show("s-work"); persist(); }, t + 500);
}

/* =========================================================
   期間、判定、草稿（狀態衍生）
   ========================================================= */
function period() { const st = isoT(S.served), rt = isoT(S.recv); if (!st) return null; const start = st + DAY, due = st + 30 * DAY; return { served: st, start, due, recv: rt, over: rt !== null ? rt > due : null, days: rt !== null ? Math.round((rt - due) / DAY) : null, left: rt !== null ? Math.round((due - rt) / DAY) : null }; }
const isOverdue = () => { const p = period(); return !!(p && p.over); };
function judgePlan(c) { c = c || S.c; if (isOverdue() && S.c === c) return c.plans.find((p) => p.art.includes("77")) || overduePlan(); return c.plans.find((p) => p.id === c.judge) || c.plans[0]; }
function currentPlan() { const c = S.c; if (S.plan === "X") return overduePlan(); return c.plans.find((p) => p.id === S.plan) || judgePlan(); }
function draftFor(id) { const c = S.c; if (id === "X") return overdueDraft(c); return c.drafts[id] || overdueDraft(c); }
function ensurePlan() { if (!S.plan) { S.plan = isOverdue() ? (S.c.plans.find((p) => p.art.includes("77")) || { id: "X" }).id : S.c.judge; loadDraft(true); } }
function loadDraft(fresh) { const d = draftFor(S.plan); S.paras = d.paras.map((p) => ({ ...p, tpl: p.text, src: "ai", refs: p.refs ? p.refs.slice() : [] })); if (fresh) { S.versions = []; } pushVersion("AI 生成草稿（" + d.tmpl + "）", "AI"); }
function fillDates(t) { const p = period(); return t.replace(/\{\{RECV\}\}/g, S.recv ? cnDate(isoT(S.recv)) : '<span class="fill">（待補收文日）</span>').replace(/\{\{SERVED\}\}/g, S.served ? cnDate(isoT(S.served)) : '<span class="fill">（待補送達日）</span>').replace(/\{\{START\}\}/g, p ? cnDate(p.start) : "—").replace(/\{\{DUE\}\}/g, p ? cnDate(p.due) : "—").replace(/\{\{OVER\}\}/g, p && p.days !== null ? p.days : "—"); }
function pushVersion(label, by) { S.versions.push({ ts: now(), label, by, snap: S.paras.map((p) => ({ ...p })) }); S.audit.push({ ts: now(), who: by === "AI" ? "ai" : "hu", para: "全文", action: label }); }
const editable = () => S.status === "承辦中";
const statusLabel = () => S.status === "已結案" && S.court ? `已結案・法院${S.court.res.startsWith("維持") ? "維持" : S.court.res.startsWith("撤銷") ? "撤銷" : "未訴"}` : S.status;

/* ---------- 持久化（案件庫） ---------- */
function persist() {
  if (!S.c) return;
  const c = S.c, jp = judgePlan();
  const rec = { libId: S.libId, baseId: c.id, name: c.name, no: c.no, subj: c.subj, art: currentPlan().art, verdict: S.final ? S.final.verdict : currentPlan().verdict, aiVerdict: jp.verdict, status: S.status, createdAt: (LIB.find((r) => r.libId === S.libId) || {}).createdAt || today(), closedAt: S.status === "已結案" ? ((LIB.find((r) => r.libId === S.libId) || {}).closedAt || today()) : null, final: S.final, court: S.court, updatedAt: today(),
    state: { served: S.served, recv: S.recv, stances: S.stances, plan: S.plan, paras: S.paras, versions: S.versions, audit: S.audit, objections: S.objections, finalDiff: S.finalDiff, docs: c.docs.map((d) => ({ id: d.id, tag: d.tag, src: d.src, include: d.include, origName: d.origName, stdName: d.stdName, kind: d.kind, title: d.title, note: d.note, file: d.file, summary: d.summary, dup: d.dup, unknown: d.unknown })), liveCase: c.live ? c : null } };
  const i = LIB.findIndex((r) => r.libId === S.libId); if (i >= 0) LIB[i] = rec; else LIB.push(rec);
  saveLib();
}
function openRecord(rec) {
  const base = rec.state.liveCase ? rec.state.liveCase : CASES.find((x) => x.id === rec.baseId); if (!base) return;
  const c = structuredClone(base);
  if (rec.state.docs && rec.state.docs.length) { const byId = Object.fromEntries(base.docs.map((d) => [d.id, d])); c.docs = rec.state.docs.map((sd) => { const d = byId[sd.id] ? structuredClone(byId[sd.id]) : { id: sd.id, title: sd.title, kind: sd.kind || "missing", note: sd.note, file: sd.file }; Object.assign(d, { tag: sd.tag || d.tag, src: sd.src || d.src, include: sd.include !== false, origName: sd.origName, stdName: sd.stdName, summary: sd.summary || d.summary, dup: sd.dup, unknown: sd.unknown }); if (sd.id === "final") { d.kind = "pdf"; d.file = sd.file; } return d; }); }
  Object.assign(S, { libId: rec.libId, status: rec.status, served: rec.state.served, recv: rec.state.recv, stances: rec.state.stances, plan: rec.state.plan, paras: rec.state.paras, versions: rec.state.versions, audit: rec.state.audit, objections: rec.state.objections || [], final: rec.final, court: rec.court, finalDiff: rec.state.finalDiff });
  runCase(c, true);
}

/* =========================================================
   畫面 3：渲染
   ========================================================= */
function render() { ensurePlan(); renderDocs(); renderExtract(); renderIssues(); renderLaws(); renderSims(); renderDraft(); updateChips(); $$(".tab")[0].click(); const first = S.c.docs.find((d) => d.kind !== "missing" && d.include !== false); if (first) openDoc(first.id); asstReset(); }
function updateChips() {
  const p = currentPlan();
  $("#judgeChip").classList.add("on"); $("#judgeText").textContent = `${p.verdict.length > 12 ? p.verdict.slice(0, 12) + "…" : p.verdict}（${p.art.replace("訴願法 ", "")}）・異議 ${S.objections.length} 次`;
  const sc = $("#statusChip"); sc.className = "chip status on " + S.status; $("#statusText").textContent = statusLabel();
  $$(".tab")[1].classList.toggle("warn", Object.values(S.stances).includes("open"));
  $$(".tab")[2].classList.toggle("warn", S.c.citations.some((x) => x.status !== "ok"));
}
function recompute() { renderExtract(); renderIssues(); renderDraft(); updateChips(); persist(); }
$$(".tab").forEach((b) => b.addEventListener("click", () => { $$(".tab").forEach((x) => x.classList.toggle("on", x === b)); $$(".tabpage").forEach((p, i) => p.classList.toggle("on", i === +b.dataset.t)); $("#panel").scrollTop = 0; }));

/* ---------- 分欄拖曳、展開卷宗 ---------- */
(function () {
  const work = $("#work"), h = $("#handle"); let drag = false;
  const saved = localStorage.getItem("ssz.leftw"); if (saved) work.style.setProperty("--leftw", saved);
  h.addEventListener("mousedown", (e) => { drag = true; h.classList.add("drag"); e.preventDefault(); });
  window.addEventListener("mousemove", (e) => { if (!drag) return; const r = work.getBoundingClientRect(); const w = Math.min(r.width - 300, Math.max(300, e.clientX - r.left)); work.style.setProperty("--leftw", w + "px"); });
  window.addEventListener("mouseup", () => { if (!drag) return; drag = false; h.classList.remove("drag"); localStorage.setItem("ssz.leftw", work.style.getPropertyValue("--leftw")); });
  $("#fullLeft").addEventListener("click", () => { const on = work.classList.toggle("fullleft"); $("#fullLeft").textContent = on ? "還原分欄" : "展開卷宗"; $("#fullLeft").classList.toggle("on", on); });
  $("#listToggle").addEventListener("click", () => { const on = $("#docPane").classList.toggle("listcollapsed"); $("#listToggle").textContent = on ? "展開清單" : "收合清單"; });
  $("#curDoc").addEventListener("click", () => { $("#docPane").classList.remove("listcollapsed"); $("#listToggle").textContent = "收合清單"; });
  document.addEventListener("keydown", (e) => { if (!$("#s-work").classList.contains("on")) return; if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.target.isContentEditable) return; if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return; const ids = S.c.docs.filter((d) => d.include !== false).map((d) => d.id); const i = ids.indexOf(S.doc); const n = e.key === "ArrowDown" ? Math.min(ids.length - 1, i + 1) : Math.max(0, i - 1); if (ids[n] && ids[n] !== S.doc) { e.preventDefault(); openDoc(ids[n]); } });
})();

/* ---------- 卷宗瀏覽器 ---------- */
const KIND = { text: "文字", image: "掃描/照片", pdf: "PDF", video: "影片", missing: "—" };
S.docMode = {};
function renderDocs() {
  const c = S.c; $("#docCount").textContent = `${c.docs.length} 件`;
  const groups = SRC_ORDER.map((src) => [src, c.docs.filter((d) => (d.src || "原處分機關") === src)]).filter(([, l]) => l.length);
  $("#docList").innerHTML = groups.map(([src, list]) => `<div class="grp" data-g="${src}"><span class="tri">▾</span><span class="srct ${src}" style="margin:0">${src}</span><span>${src === "第三方" ? "獨立證據" : src === "本局" ? "受理機關" : ""}</span><span class="n">${list.length}</span></div><div class="items">${list.map((d) => `<div class="item ${d.include === false ? "skip" : ""}" data-doc="${d.id}" title="${esc(d.origName ? "原檔名：" + d.origName : d.title)}"><i></i><span class="t">${esc(d.stdName || d.title)}</span><span class="m">${d.pages || 1} 頁・${KIND[d.kind] || ""}</span><span class="tag neutral tagbtn" data-edit="${d.id}" title="修正類型／來源" style="font-size:10px">${d.tag} ✎</span><span class="sum">${esc(d.summary || "")}</span></div>`).join("")}</div>`).join("");
  $$("#docList .grp").forEach((g) => g.addEventListener("click", () => { g.classList.toggle("closed"); g.querySelector(".tri").textContent = g.classList.contains("closed") ? "▸" : "▾"; }));
  $$("#docList .item").forEach((b) => b.addEventListener("click", () => openDoc(b.dataset.doc)));
  $$("#docList .tagbtn").forEach((t) => t.addEventListener("click", (e) => { e.stopPropagation(); openTagPop(t.dataset.edit, t); }));
}
function openTagPop(id, anchor) {
  const d = S.c.docs.find((x) => x.id === id), pop = $("#tagPop"), pane = $("#docPane").getBoundingClientRect(), r = anchor.getBoundingClientRect();
  $("#tpType").innerHTML = TYPES.map((t) => `<option ${d.tag === t ? "selected" : ""}>${t}</option>`).join(""); $("#tpSrc").innerHTML = SRC_ORDER.map((t) => `<option ${d.src === t ? "selected" : ""}>${t}</option>`).join("");
  pop.style.left = Math.max(8, Math.min(pane.width - 230, r.left - pane.left - 120)) + "px"; pop.style.top = (r.bottom - pane.top + 4) + "px"; pop.classList.add("on");
  $("#tpCancel").onclick = () => pop.classList.remove("on");
  $("#tpSave").onclick = () => { const t = $("#tpType").value, sr = $("#tpSrc").value; if (t !== d.tag || sr !== d.src) { S.audit.push({ ts: now(), who: "hu", para: d.stdName || d.title, action: `修正歸戶：${d.tag}／${d.src} → ${t}／${sr}` }); d.tag = t; d.src = sr; renderDocs(); renderExtract(); renderIssues(); renderDraft(); persist(); openDoc(id); } pop.classList.remove("on"); };
}
function openDoc(id, after) {
  const c = S.c, d = c.docs.find((x) => x.id === id); if (!d) return;
  S.doc = id; S.zoom = 1; $("#tagPop").classList.remove("on");
  $$("#docList .item").forEach((b) => { const on = b.dataset.doc === id; b.classList.toggle("on", on); if (on) { const g = b.closest(".items").previousElementSibling; if (g.classList.contains("closed")) { g.classList.remove("closed"); g.querySelector(".tri").textContent = "▾"; } b.scrollIntoView({ block: "nearest" }); } });
  $("#curDocName").textContent = d.stdName || d.title;
  const view = $("#docView"), tools = $("#docTools"); tools.innerHTML = "";
  const missing = `<div class="doc-missing">找不到卷宗包檔案：<span class="num">${esc(d.file || "")}</span><br>請自 repo 根目錄開啟 prototype/index.html。</div>`;
  const head = `<div class="doc-meta num" style="margin-bottom:8px">${d.origName ? `原檔名：${esc(d.origName)}　→　` : ""}標籤：${esc(d.stdName || d.title)}<span class="srct ${d.src}">${d.src}</span>${d.srcNote ? `<span class="note">　${esc(d.srcNote)}</span>` : ""}${d.summary ? `<br><span class="note">Claude 判定：${esc(d.summary)}</span>` : ""}</div>`;
  if (d.include === false) { view.innerHTML = `<div class="doc-missing">${head}<b>${esc(d.stdName || d.title)}</b>　<span class="tag neutral">${d.tag}</span><br>${esc(d.note || "未納入分析。")}</div>`; }
  else if (d.kind === "text") {
    const mode = S.docMode[id] || (d.file ? "pdf" : "text");
    const paint = () => { const m = S.docMode[id] || (d.file ? "pdf" : "text"); if (d.file) tools.innerHTML = `<button class="ghost-btn ${m === "pdf" ? "on" : ""}" data-m="pdf">原始 PDF</button><button class="ghost-btn ${m === "text" ? "on" : ""}" data-m="text">擷取文字</button>`; view.innerHTML = m === "pdf" ? `<div style="padding:10px 12px 0">${head}</div><iframe class="doc-pdf" src="${d.file}#toolbar=0&view=FitH" title="${esc(d.title)}"></iframe>` : `<div class="doc-body">${head}${d.html}</div>`; if (m === "text") bindMarks(); $$("#docTools button").forEach((b) => b.addEventListener("click", () => { S.docMode[id] = b.dataset.m; paint(); })); };
    S.docMode[id] = mode; paint();
  } else if (d.kind === "image") {
    if (!d.file) { view.innerHTML = `<div class="doc-missing">${head}<b>${esc(d.stdName || d.title)}</b><br>${esc(d.note || "")}</div>`; }
    else {
    tools.innerHTML = `<button class="ghost-btn" data-z="-">－</button><button class="ghost-btn" data-z="+">＋</button><button class="ghost-btn" data-z="0">重設</button>`;
    view.innerHTML = `<div style="padding:10px 12px 0">${head}</div><div class="doc-img" id="docImg"><div class="imgwrap"><img src="${d.file}" alt="${esc(d.title)}">${(d.boxes || []).map((b) => `<div class="box" data-ref="${b.ref}" style="left:${b.x}%;top:${b.y}%;width:${b.w}%;height:${b.h}%"><span class="lb">${esc(b.label)}</span></div>`).join("")}</div></div>`;
    $("#docImg img").addEventListener("error", () => { view.innerHTML = missing; });
    const fit = () => { $("#docImg").style.setProperty("--imgw", Math.round((view.clientWidth - 24) * S.zoom) + "px"); }; fit();
    $$("#docTools button").forEach((b) => b.addEventListener("click", () => { S.zoom = b.dataset.z === "0" ? 1 : Math.min(4, Math.max(.5, S.zoom + (b.dataset.z === "+" ? .4 : -.4))); fit(); }));
    $("#docImg").addEventListener("dblclick", () => { S.zoom = S.zoom > 1.2 ? 1 : 2.2; fit(); });
    let drag = null; const el = $("#docImg"); el.addEventListener("mousedown", (e) => { drag = { x: e.clientX, y: e.clientY, sl: view.scrollLeft, st: view.scrollTop }; el.classList.add("drag"); });
    window.addEventListener("mousemove", (e) => { if (!drag) return; view.scrollLeft = drag.sl - (e.clientX - drag.x); view.scrollTop = drag.st - (e.clientY - drag.y); }); window.addEventListener("mouseup", () => { drag = null; el.classList.remove("drag"); });
    $$(".box", view).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); hitBox(b.dataset.ref); }));
    }
  } else if (d.kind === "pdf") { tools.innerHTML = `<a class="ghost-btn" href="${d.file}" target="_blank" style="text-decoration:none">新分頁開啟</a>`; view.innerHTML = `<div style="padding:10px 12px 0">${head}</div><iframe class="doc-pdf" src="${d.file}#toolbar=0&view=FitH" title="${esc(d.title)}"></iframe>`; }
  else if (d.kind === "video") { view.innerHTML = `<div class="doc-video">${head}<video id="vid" controls preload="metadata" src="${d.file}"></video><div class="cues">${(d.cues || []).map((q) => `<button class="ghost-btn" data-t="${q[1]}">${q[2]}</button>`).join("")}</div><p class="note" style="margin-top:8px">來源：${esc(d.srcNote || "檢舉人行車紀錄器")}；時間戳 2025/06/27 12:40:08–19。</p></div>`; $$(".cues button", view).forEach((b) => b.addEventListener("click", () => seek(+b.dataset.t))); $("#vid").addEventListener("error", () => { view.innerHTML = missing; }); }
  else view.innerHTML = `<div class="doc-missing">${head}<b>${esc(d.stdName || d.title)}</b>　<span class="tag neutral">${d.tag}</span><br>${esc(d.note || "")}</div>`;
  if (after) after();
}
function bindMarks() { $$("#docView mark[data-ref]").forEach((m) => m.addEventListener("click", () => { $$("#docView mark").forEach((x) => x.classList.remove("hit", "hit-seal")); m.classList.add("hit"); })); }
function hitBox(ref) { $$("#docView .box").forEach((b) => b.classList.toggle("hit", b.dataset.ref === ref)); const b = $(`#docView .box[data-ref="${ref}"]`); if (b) b.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }); }
function seek(t) { const v = $("#vid"); if (!v) return; const go = () => { v.currentTime = t; v.pause(); }; if (v.readyState >= 1) go(); else v.addEventListener("loadedmetadata", go, { once: true }); }
function jumpTo(ref) {
  const r = S.c.refs[ref]; if (!r) return; const [docId, kind] = r;
  if (kind === "mark") S.docMode[docId] = "text";
  const act = () => { if (kind === "mark") { $$("#docView mark").forEach((x) => x.classList.remove("hit", "hit-seal")); const m = $(`#docView mark[data-ref="${ref}"]`); if (m) { m.classList.add(/arg|served|receiver/.test(ref) ? "hit-seal" : "hit"); m.scrollIntoView({ block: "center", behavior: "smooth" }); } } else if (kind === "box") hitBox(ref); else if (kind === "time") { const d = S.c.docs.find((x) => x.id === docId); const cue = (d.cues || []).find((q) => q[0] === ref); if (cue) seek(cue[1]); } };
  if (S.doc !== docId || (kind === "mark" && !$("#docView mark"))) openDoc(docId, () => setTimeout(act, 60)); else act();
}
document.addEventListener("click", (e) => { const j = e.target.closest("[data-jump]"); if (j) { e.preventDefault(); jumpTo(j.dataset.jump); } if (!e.target.closest("#tagPop") && !e.target.closest(".tagbtn")) $("#tagPop")?.classList.remove("on"); });
function srcOf(ref) { const r = S.c.refs[ref]; if (!r) return ""; const d = S.c.docs.find((x) => x.id === r[0]); return d ? d.src : ""; }
const SJ = (ref, text) => ref ? `${J(ref, text)}<span class="srct ${srcOf(ref)}">${srcOf(ref)}</span>` : text;

/* ---------- Tab 1 ---------- */
const CHK_REF = { "77(1)": ["ap-claim", "訴願書"], "77(2)": ["sv-date", "送達證書"], "77(3)": ["doc-vehicle", "車籍查詢"], "77(4)": ["ap-applicant", "訴願書"], "77(5)": [null, ""], "77(6)": ["pn-amount", "裁處書"], "77(7)": [null, "案件系統"], "77(8)": ["pn-fact", "裁處書"] };
function addMonths(t, n) { const d = new Date(t); d.setUTCMonth(d.getUTCMonth() + n); return d.getTime(); }
function renderExtract() {
  const c = S.c, p = period();
  const rows = c.fields.map((f) => `<tr class="${f.conflict ? "conflict" : ""}"><td>${esc(f.k)}</td><td>${J(f.a[1], esc(f.a[0]))}</td><td>${J(f.d[1], esc(f.d[0]))}</td><td>${SJ(f.e[1], esc(f.e[0]))}${f.conflict ? `<span class="why">⚠ ${esc(f.conflict)}</span>` : ""}</td></tr>`).join("");
  const cls = c.cls.map(([l, v]) => `<div class="cls"><span class="lab">${l}</span><div class="val">${esc(v)}</div></div>`).join("");
  const over = !!(p && p.over);
  const items = c.checks.map((k) => { let st = k[2], note = k[3]; if (st === "auto") { if (!p) { st = "warn"; note = "卷內無送達證書，待補"; } else if (p.recv === null) { st = "warn"; note = "未有收文日"; } else if (p.over) { st = "fail"; note = `逾期 ${p.days} 日`; } else { st = "pass"; note = `未逾期（於屆滿前 ${p.left} 日提起）`; } } return { art: k[0], name: k[1], st, note }; });
  const n = (t) => items.filter((x) => x.st === t).length;
  const ICON = { pass: "☑", fail: "☒", na: "－", warn: "☐" }, STN = { pass: "通過", fail: "未通過", na: "不適用", warn: "待核" };
  const checklist = items.map((x) => { const r = CHK_REF[x.art] || [null, ""]; const src = r[0] && S.c.refs[r[0]] ? J(r[0], r[1] + " ↗") : (r[1] || ""); return `<div class="ck ${x.st}"><span class="ckbox">${ICON[x.st]}</span><span class="ckart num">${x.art}</span><span class="ckname">${x.name}</span><span class="ckst">${STN[x.st]}</span><span class="cknote">${esc(x.note)}</span><span class="cksrc">${src}</span></div>`; }).join("");
  const verdict = over ? { kind: "stop", big: "程序不合 → 應為不受理", text: `第 2 款未通過：依送達證書 ${S.served} 起算，法定期間至 ${toMg(p.due)} 屆滿，收文日 ${S.recv} 已逾期 ${p.days} 日。程序審查於此終結，毋庸進入實體審查。` } : n("fail") ? { kind: "stop", big: "程序不合 → 應為不受理", text: "有款次未通過，毋庸進入實體審查。" } : n("warn") ? { kind: "go", big: "待核", text: `有 ${n("warn")} 款待核，請補件或向原處分機關確認後再行判定。` } : { kind: "go", big: "程序合法 → 進入實體審查", text: `八款皆通過或不適用。實體爭點見「爭點」分頁（共 ${c.issues.length} 個）。` };
  let tl = "";
  if (p) { const anchor = [[p.served, "合法送達", "key"], [p.due, "期間屆滿", p.over ? "key" : ""]]; if (p.recv !== null) anchor.push([p.recv, "實際收文", p.over ? "bad" : "key"]); anchor.sort((a, b) => a[0] - b[0]); const min = anchor[0][0], max = anchor[anchor.length - 1][0], span = Math.max(1, max - min), pts = []; anchor.forEach(([t, lab, cl], i) => { let pos = Math.round((t - min) / span * 100); if (i > 0 && pos - pts[pts.length - 1].pos < 17) pos = Math.min(100, pts[pts.length - 1].pos + 17); pts.push({ d: toMg(t), lab, pos, cls: cl }); }); const recvPt = pts.find((x) => x.lab === "實際收文"); tl = `<div class="tl-track"><div class="tl-fill" style="width:${recvPt ? recvPt.pos : 100}%"></div>${pts.map((x) => `<div class="tl-pt ${x.cls}" style="left:${x.pos}%"><div class="up"><div class="d">${x.d}</div></div><div class="dot"></div><div class="lab">${x.lab}</div></div>`).join("")}</div><div class="tl-note">起算日 <b>${toMg(p.start)}</b>（送達之次日）＋ 30 日 ＝ 屆滿日 <b>${toMg(p.due)}</b>。${p.recv === null ? "尚無收文日。" : p.over ? `實際收文日 <b>${toMg(p.recv)}</b>，<span style="color:var(--seal);font-weight:600">逾法定不變期間 ${p.days} 日</span>。` : `實際收文日 <b>${toMg(p.recv)}</b>，<span style="color:var(--green);font-weight:600">未逾期，於屆滿前 ${p.left} 日提起</span>。`} 在途期間未扣除（訴願人住居所在本市）。</div>`; }
  else tl = `<div class="tl-note" style="margin-top:0;border:none">尚未取得送達日。</div>`;
  const ap = c.period.appealSays, due85 = p && p.recv !== null ? addMonths(p.recv, 3) : null;
  $("#p0").innerHTML = `
    <div class="sec"><div class="sec-head"><h3>案件分類</h3><span class="note">分類模型輸出</span></div><div class="box2 clsgrid">${cls}</div></div>
    <div class="sec"><div class="sec-head"><h3>訴願期間計算</h3><span class="note">訴願人是否於 30 日內提起（訴願法 §14）；依卷附送達證書與收文戳自動計算</span></div><div class="box2"><div class="period-edit">
      <div><label>送達日（卷證）</label><div class="val">${esc(S.served || "—")}</div><div class="src">${c.period.servedRef ? SJ(c.period.servedRef, "來源：送達證書 ↗") : "來源：訴願書自述／待補"}${ap && ap !== S.served ? `<span class="warnsrc">　⚠ 訴願書自述 ${ap}（發文日），已採卷證</span>` : ""}</div></div>
      <div><label>機關收文日</label><div class="val">${esc(S.recv || "—")}</div><div class="src">${c.period.recvRef ? J(c.period.recvRef, "來源：收文戳 ↗") : "來源：待補"}</div></div>
      <div><label>30 日期間屆滿</label><div class="val">${p ? toMg(p.due) : "—"}</div><div class="src">起算 ${p ? toMg(p.start) : "—"}（送達次日）</div></div>
      <div><label>是否逾期</label><div style="font-size:15px;font-weight:600;padding:4px 0;color:${over ? "var(--seal)" : "var(--green)"}">${p ? (p.recv === null ? "待補收文日" : over ? `逾期 ${p.days} 日` : `未逾期（於屆滿前 ${p.left} 日提起）`) : "待補送達日"}</div><div class="src">在途期間未扣除</div></div>
      <div style="border-top:1px solid var(--line)"><label>本局審理期限（訴願法 §85 I）</label><div class="val" style="color:var(--accent)">${due85 ? toMg(due85) : "—"}</div><div class="src">收受訴願書起 3 個月內作成決定；必要時得延長一次，最長 2 個月</div></div>
    </div><div class="timeline">${tl}</div></div></div>
    <div class="sec"><div class="sec-head"><h3>程序審查　訴願法第 77 條各款</h3><span class="note">通過 ${n("pass")}・不適用 ${n("na")}・待核 ${n("warn")}・未通過 ${n("fail")}</span></div>
      <div class="box2"><div class="cklist">${checklist}</div><div class="verdict ${verdict.kind}"><span class="big">${verdict.big}</span><p>${verdict.text}</p></div></div></div>
    <div class="sec"><div class="sec-head"><h3>三方對照</h3><span class="note">訴願人主張 ／ 機關答辯 ／ 卷證事實（標示來源，第三方證據優先）　點任一格跳至卷宗</span></div><div class="box2"><table class="cmp"><tr><th>欄位</th><th>訴願人主張（訴願人來源）</th><th>機關答辯（原處分機關來源）</th><th>卷證事實（第三方優先）</th></tr>${rows}</table></div></div>
    <p class="foot-note">程序審查為 AI 依卷面自動核對之結果，唯讀；任何一款未通過即應為不受理，毋庸進入實體。三方對照三欄之資料分別限於對應來源之文件，「卷證事實」欄優先採第三方證據；紅底列為主張與卷證不一致處，系統不自動裁決。不服請於草稿頁提出異議。</p>`;
}

/* ---------- Tab 2 ---------- */
function renderIssues() {
  const c = S.c, stN = { agency: "採機關", appellant: "採訴願人", open: "待議" };
  const verdictOf = (pid) => { const p = c.plans.find((x) => x.id === pid); return p ? p.verdict : "—"; };
  $("#p1").innerHTML = `<div class="sec"><div class="sec-head"><h3>雙方癥結點</h3><span class="note">訴願人主張 ／ 機關答辯 ／ 卷證顯示 ／ AI 認定與依據　不同意請點「對此有異議」</span></div>
    ${c.issues.map((it, i) => { const ai = it.stance || "open"; const cur = S.stances[it.id] || ai; const obj = S.objections.find((o) => o.issueId === it.id && o.result !== "reject"); return `
      <div class="issue" id="iss-${it.id}"><div class="issue-head"><span class="n">爭點 ${i + 1}</span><h3>${esc(it.title)}</h3>
        ${obj ? `<span class="ailab obj">異議後：${stN[cur]}</span><span class="note">原 AI 認定：${stN[ai]}</span>` : `<span class="ailab">AI 認定：${stN[ai]}</span>`}
        ${editable() ? `<span class="objlink" data-obj="${it.id}">對此有異議</span>` : ""}</div>
        <div class="issue-grid"><div><div class="lab">訴願人主張</div>${J(it.a[1], esc(it.a[0]))}</div><div><div class="lab">機關答辯</div>${J(it.d[1], esc(it.d[0]))}</div><div><div class="lab">卷證顯示</div><div class="ev">${it.e.map((e) => e[1] ? `<span class="tag accent jump" data-jump="${e[1]}">${esc(e[0])}<span class="srct ${srcOf(e[1])}">${srcOf(e[1])}</span></span>` : `<span class="tag neutral">${esc(e[0])}</span>`).join("")}</div></div></div>
        <div class="basis"><b>依據</b>${esc(it.ai || "")}</div>
        <div class="issue-foot"><span class="lab" style="font-size:10.5px;color:var(--ink-3)">法律素材</span>${it.law.map((l) => `<span>${esc(l)}</span>`).join("")}</div>
        <div class="lead"><span class="ai">→ 結論：${esc(verdictOf(obj && obj.plan ? obj.plan : c.judge))}</span><span class="note">採機關 → ${esc(verdictOf(it.lead.agency[0]))}　採訴願人 → ${esc(verdictOf(it.lead.appellant[0]))}</span></div></div>`; }).join("")}</div>
    <p class="foot-note">爭點由三方對照之衝突列與答辯書逐點回應段落配對產生；AI 認定僅附一句依據，不附信心度。承辦人的立場只透過「異議」表達：AI 重新引證後回覆採納／部分採納／無法採納。</p>`;
  $$("#p1 .objlink").forEach((l) => l.addEventListener("click", () => openObjection(l.dataset.obj)));
}

/* ---------- Tab 3／4 ---------- */
function renderLaws() {
  const c = S.c, STN = { ok: "已驗證", amended: "該條已修正", missing: "查無此條", repealed: "已廢止", gap: "漏引" };
  const cites = c.citations.length ? `<table class="cite-check"><tr><th>引用</th><th>出現位置</th><th>狀態</th><th>說明</th></tr>${c.citations.map((x) => `<tr class="${x.status}"><td>${J(x.ref, esc(x.n))}</td><td>${esc(x.where)}</td><td><span class="st ${x.status}">${STN[x.status]}</span></td><td class="note" style="font-size:12px">${esc(x.note)}</td></tr>`).join("")}</table>` : `<div class="doc-missing" style="padding:14px">${esc(c.citationNote || "無引用可查核")}</div>`;
  const groups = {}; c.laws.forEach((l) => { (groups[l.g] = groups[l.g] || []).push(l); });
  $("#p2").innerHTML = `<div class="sec"><div class="sec-head"><h3>答辯書引用法條查核</h3><span class="note">逐條比對資料集法規全文與修正狀態</span></div><div class="box2">${cites}</div></div>${c.alert ? `<div class="sec"><div class="sec-head"><h3>${c.alert.title}</h3></div><div class="alert"><span class="mk">！</span><p>${c.alert.text}</p></div></div>` : ""}${Object.entries(groups).map(([g, list]) => `<div class="sec"><div class="sec-head"><h3>${g}</h3><span class="note">${list.length} 筆</span></div><div class="box2">${list.map((l) => `<div class="law"><div class="ttl"><span class="n">${esc(l.n)}</span></div><div class="rel">關聯 ${l.rel}%</div><div class="txt">${esc(l.t)}</div><div class="badges">${l.badges.join("")}</div></div>`).join("")}</div></div>`).join("")}`;
}
function renderSims() {
  const c = S.c, total = c.simDist.reduce((a, b) => a + b[1], 0), closed = LIB.filter((r) => r.status === "已結案").length;
  $("#p3").innerHTML = `<div class="sec"><div class="sec-head"><h3>Top ${c.sims.length} 相似歷史決定書</h3><span class="note">來源：資料集 101 件・本局案件庫已結案 ${closed} 件　點列展開決定書全文</span></div><div class="box2">${c.sims.map((s, i) => { const f = histFile(s.fn); return `<div class="sim ${f ? "exp" : ""}" data-i="${i}"><div class="sim-top"><span class="rank">${i + 1}</span><span class="fn">${esc(s.fn)}<span class="arrow">${f ? "▸ 展開" : ""}</span></span><span class="tag neutral" style="font-size:10px">資料集</span><span class="score">${s.s}%</span></div><div class="simbar"><i style="width:${s.s}%"></i></div><p class="why">${esc(s.why)}</p><div class="chips">${s.chips.map((x) => `<span class="tag ${x === "須注意" || x === "反面案例" ? "seal" : "neutral"}">${esc(x)}</span>`).join("")}</div>${f ? `<div class="body"><div style="display:flex;gap:8px;align-items:center;margin-bottom:8px"><span class="note num">${esc(f.split("/").pop())}</span><a class="ghost-btn" href="${f}" target="_blank" style="text-decoration:none;margin-left:auto">新分頁開啟</a></div><iframe data-src="${f}#toolbar=0&view=FitH" title="${esc(s.fn)}"></iframe></div>` : ""}</div>`; }).join("")}${closed ? LIB.filter((r) => r.status === "已結案" && r.libId !== S.libId).slice(0, 2).map((r) => `<div class="sim"><div class="sim-top"><span class="rank">庫</span><span class="fn">${esc(r.no)}　${esc(r.name)}</span><span class="tag accent" style="font-size:10px">本局案件庫</span><span class="score">—</span></div><p class="why">已結案案件：結論「${esc(r.verdict)}」，${r.court ? "法院結果：" + esc(r.court.res) : "尚無法院結果"}。</p></div>`).join("") : ""}</div></div>
    <div class="sec"><div class="sec-head"><h3>相似案例之決定結果分布</h3></div><div class="dist">${c.simDist.filter((d) => d[1] > 0).map((d) => `<div style="background:${d[2]};width:${d[1] / total * 100}%">${d[1]}</div>`).join("")}</div><div class="dist-key">${c.simDist.map((d) => `<span><i style="background:${d[2]}"></i>${d[0]} ${d[1]} 件</span>`).join("")}</div></div>
    <p class="foot-note">相似度綜合案由、援引法條、爭點類型與事實敘述四項計算；系統刻意納入結果相反之案例（反面案例）提醒撤銷風險。${esc(c.simsNote || "")}</p>`;
  $$("#p3 .sim.exp").forEach((el) => el.addEventListener("click", (e) => { if (e.target.closest("a")) return; const open = el.classList.toggle("open"); el.querySelector(".arrow").textContent = open ? "▾ 收合" : "▸ 展開"; const fr = el.querySelector("iframe"); if (open && fr && !fr.src) fr.src = fr.dataset.src; }));
}

/* ---------- Tab 5：判定列＋紙張文件＋紀錄 ---------- */
function paraLabel(p) { if (!p) return "全文"; if (p.kind === "h4") return p.text; if (p.kind === "meta") return "當事人欄"; const m = /^([一二三四五六七八九十]+)、/.exec(plain(p.text)); const sect = p.id.startsWith("r") ? "理由" : p.id.startsWith("fact") ? "事實" : p.id === "main" ? "主文" : "前言"; return m ? `${sect}${m[1]}` : sect; }
function refTitle(r) { const x = S.c.refs[r]; if (!x) return r; const d = S.c.docs.find((y) => y.id === x[0]); return d ? (d.stdName || d.title) : r; }
function renderDraft() {
  const c = S.c, jp = judgePlan(), cp = currentPlan(), d = draftFor(S.plan), ro = !editable();
  const RISK = { low: "低", mid: "中", high: "高" };
  const acts = S.status === "承辦中" ? `<button class="ghost-btn" id="objBtn">我有異議</button><button class="btn" id="submitBtn">送委員會審議</button>` : S.status === "已送審" ? `<button class="btn" id="closeBtn">登錄委員會結論並結案</button>` : `<button class="ghost-btn" id="courtBtn">登錄法院結果</button><button class="ghost-btn" id="forkBtn">另存為新草稿</button>`;
  const life = ["承辦中", "已送審", "已結案"], li = life.indexOf(S.status);
  const last = S.objections[S.objections.length - 1];
  const reply = last ? `<div class="reply"><div class="q">異議 ${S.objections.length}（${esc(last.issue)}）　${last.ts}　承辦人：${esc(last.text)}</div>AI：<b class="${last.result === "accept" ? "a" : last.result === "partial" ? "p" : "r"}">${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[last.result]}</b>　${esc(last.reply)}${last.evidence.length ? `<span class="note">　重新檢視：${last.evidence.map((r) => J(r, refTitle(r) + " ↗")).join("、")}</span>` : ""}</div>` : "";
  const body = S.paras.map((q) => { if (q.kind === "h4") return `<h4>${q.text}</h4>`; if (q.kind === "meta") return `<div class="meta">${fillDates(q.text)}</div>`; const tools = `<span class="tools" contenteditable="false">${(q.refs || []).map((r) => `<span class="jump" data-jump="${r}">↗ ${esc(refTitle(r))}</span>`).join("")}${q.cite ? `<span title="${esc(q.cite)}">來源</span>` : ""}${ro ? "" : "<span>點擊編輯</span>"}</span>`; return `<p class="para" data-pid="${q.id}" data-src="${q.src}" contenteditable="${ro ? "false" : "true"}" spellcheck="false">${fillDates(q.text)}${tools}</p>`; }).join("");
  $("#p4").innerHTML = `
    <div class="jbar"><span class="jv">AI 判定：${esc(jp.verdict)}</span><span class="jart">${esc(jp.art)}</span>${S.plan && S.plan !== jp.id ? tag("amber", `異議後改為：${esc(cp.verdict)}`) : ""}<span class="jrisk">撤銷風險：${RISK[cp.risk[0]]}　異議 ${S.objections.length} 次</span>
      <div class="acts">${acts}<div class="more"><button class="ghost-btn" id="moreBtn">⋯</button><div class="menu" id="moreMenu"><button id="exportOdf">匯出 ODF 公文格式</button><button id="copyAll">複製全文</button><button id="exportCmp">匯出比較表</button></div></div></div></div>
    <div class="lifeline">${life.map((s, i) => `<span class="${i < li ? "done" : i === li ? "on" : ""}">${s}</span>${i < 2 ? "→" : ""}`).join("")}${S.court ? `→<span class="on">法院：${esc(S.court.res)}</span>` : ""}${S.final ? `<span class="fin note">最終決定：${esc(S.final.verdict)}　${esc(S.final.date)}　${J("doc-final", "開啟 ↗")}</span>` : `<span class="fin note">${esc(cp.risk[1])}</span>`}</div>
    ${reply}
    <div class="paper ${ro ? "ro" : ""}" id="draftBody"><div class="pt">${esc(d.head)}</div><div class="ps">${esc(d.sub)}${ro ? "　・唯讀" : ""}</div>${body}<div class="tail">（訴願審議委員會委員名單、教示條款及發文日期由公文系統自動帶入）</div></div>
    <p class="foot-note" style="max-width:820px;margin:16px auto 0">草稿僅供承辦人參考，一切法律見解與事實認定仍以承辦人及訴願審議委員會之判斷為準。黃底標示處必須由承辦人補實後始得送審。</p>`;
  $("#moreBtn").addEventListener("click", (e) => { e.stopPropagation(); $("#moreMenu").classList.toggle("on"); }); document.addEventListener("click", () => $("#moreMenu")?.classList.remove("on"), { once: true });
  if (!ro) $$("#draftBody .para").forEach((el) => { el.addEventListener("input", () => { const q = S.paras.find((x) => x.id === el.dataset.pid); const clone = el.cloneNode(true); clone.querySelector(".tools")?.remove(); q.text = clone.innerHTML; q.src = "human"; el.dataset.src = "human"; el.dirty = true; }); el.addEventListener("blur", () => { if (!el.dirty) return; el.dirty = false; const q = S.paras.find((x) => x.id === el.dataset.pid); S.audit.push({ ts: now(), who: "hu", para: paraLabel(q), action: "人工直接編輯" }); S.versions.push({ ts: now(), label: `人工編輯 ${paraLabel(q)}`, by: "承辦人", snap: S.paras.map((x) => ({ ...x })) }); persist(); }); });
  $("#copyAll").addEventListener("click", () => { const clone = $("#draftBody").cloneNode(true); $$(".tools", clone).forEach((t) => t.remove()); navigator.clipboard?.writeText(clone.innerText); asstSay("已複製全文至剪貼簿。"); });
  $("#exportOdf").addEventListener("click", () => asstSay("原型未串接公文系統；正式版將以 ODF 範本輸出並帶入委員名單與教示條款。"));
  $("#exportCmp").addEventListener("click", exportCompare);
  $("#objBtn")?.addEventListener("click", () => openObjection());
  $("#submitBtn")?.addEventListener("click", () => { if (!confirm("定稿並送訴願審議委員會審議？送審後草稿將唯讀。")) return; S.status = "已送審"; pushVersion("定稿送審", "承辦人"); S.audit.push({ ts: now(), who: "hu", para: "案件", action: "送委員會審議" }); recompute(); renderIssues(); $$(".tab")[4].click(); });
  $("#closeBtn")?.addEventListener("click", openClose);
  $("#courtBtn")?.addEventListener("click", () => $("#courtModal").classList.add("on"));
  $("#forkBtn")?.addEventListener("click", () => { const c2 = structuredClone(S.c); c2.docs = c2.docs.filter((x) => x.id !== "final"); delete c2.refs["doc-final"]; const src = S.libId, paras = S.paras.map((x) => ({ ...x, src: "ai" })); Object.assign(S, { libId: `${c2.id}-${Date.now().toString(36)}`, status: "承辦中", paras, versions: [], audit: [], objections: [], final: null, court: null, finalDiff: null }); pushVersion(`自已結案案件 ${src} 另存為新草稿`, "承辦人"); runCase(c2, true); persist(); renderLibCard(); });
}
function diffParas(oldP, newP) { const out = []; oldP.forEach((q) => { if (q.kind === "h4") return; const cur = newP.find((x) => x.id === q.id); if (!cur) out.push({ label: paraLabel(q), html: `<del>${esc(plain(q.text))}</del>` }); else if (plain(cur.text) !== plain(q.text)) out.push({ label: paraLabel(q), html: diffHtml(plain(q.text), plain(cur.text)) }); }); newP.forEach((q) => { if (q.kind !== "h4" && !oldP.some((x) => x.id === q.id)) out.push({ label: paraLabel(q), html: `<ins>${esc(plain(q.text))}</ins>` }); }); return out; }

/* ---------- 異議 ---------- */
function openObjection(preId) {
  const c = S.c;
  $("#objIssue").innerHTML = c.issues.map((it, i) => `<option value="${it.id}" ${preId === it.id ? "selected" : ""}>爭點 ${i + 1}：${esc(it.title)}</option>`).join("") + `<option value="other" ${preId === "other" ? "selected" : ""}>其他（未列爭點）</option>`;
  $("#objText").value = "";
  const fillEv = () => { const it = c.issues.find((x) => x.id === $("#objIssue").value); const evs = it ? it.e.filter((e) => e[1]) : []; $("#objEv").innerHTML = evs.length ? evs.map((e) => `<label><input type="checkbox" value="${e[1]}">${esc(e[0])}</label>`).join("") : '<span class="note">此項無可勾選之卷證</span>'; $$("#objEv input").forEach((cb) => cb.addEventListener("change", () => cb.parentElement.classList.toggle("on", cb.checked))); };
  $("#objIssue").onchange = fillEv; fillEv();
  $("#objText").oninput = () => { $("#objSend").disabled = $("#objText").value.trim().length < 6; }; $("#objSend").disabled = true;
  $("#objModal").classList.add("on");
}
$("#objSend").addEventListener("click", () => {
  const c = S.c, id = $("#objIssue").value, text = $("#objText").value.trim(), ev = $$("#objEv input:checked").map((x) => x.value);
  const it = c.issues.find((x) => x.id === id); const rule = it && it.objection ? it.objection : (c.objectionOther || CASE_B.objectionOther);
  const label = it ? `爭點 ${c.issues.indexOf(it) + 1}：${it.title}` : "其他";
  const o = { ts: now(), issue: label, issueId: id, text, ev, result: rule.result, reply: rule.reply, evidence: rule.evidence || [], plan: rule.plan, diff: null };
  S.audit.push({ ts: now(), who: "hu", para: label, action: `提出異議：${text}` });
  if ((rule.result === "accept" || rule.result === "partial") && rule.plan && c.drafts[rule.plan]) {
    const before = S.paras.map((x) => ({ ...x })); S.plan = rule.plan; const d = draftFor(rule.plan); S.paras = d.paras.map((p) => ({ ...p, tpl: p.text, src: "ai-edit", refs: p.refs ? p.refs.slice() : [] }));
    o.diff = diffParas(before, S.paras); pushVersion(`異議後重產（${d.tmpl}）`, "AI");
    if (it) S.stances[it.id] = "appellant";
  }
  S.audit.push({ ts: now(), who: "ai", para: label, action: `${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[rule.result]}：${rule.reply.slice(0, 40)}…` });
  S.objections.push(o); $("#objModal").classList.remove("on"); renderIssues(); renderDraft(); updateChips(); persist(); $$(".tab")[4].click(); $("#panel").scrollTop = 0;
});
function exportCompare() {
  const c = S.c, jp = judgePlan(), cp = currentPlan(), stN = { appellant: "採訴願人", agency: "採機關", open: "待議" };
  const cols = S.plan !== jp.id ? [["原判定", jp], ["異議後", cp]] : [["AI 判定", jp]];
  const w = window.open("", "_blank");
  w.document.write(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>方案比較表 ${c.no}</title><style>body{font-family:"BiauKaiTC","PingFang TC",serif;padding:28px;color:#111;font-size:13px}h1{font-size:18px;letter-spacing:.2em;text-align:center}table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border:1px solid #333;padding:6px 8px;vertical-align:top;text-align:left}th{background:#eee}ul{margin:0;padding-left:16px}.note{font-size:11px;color:#555;margin-top:14px}</style></head><body><h1>訴願案件審查結論比較表</h1><p>案號 ${esc(c.no)}　${esc(c.name)}　製表 ${new Date().toLocaleString("zh-TW")}</p>
    <h3>一、爭點表態</h3><table><tr><th>爭點</th><th>AI 判定</th><th>承辦人表態</th></tr>${c.issues.map((it, i) => `<tr><td>${i + 1}. ${esc(it.title)}</td><td>${stN[it.stance || "open"]}</td><td>${stN[S.stances[it.id]]}</td></tr>`).join("")}</table>
    <h3>二、結論比較</h3><table><tr><th></th>${cols.map(([n]) => `<th>${n}</th>`).join("")}</tr><tr><td>主文</td>${cols.map(([, p]) => `<td>${esc(p.verdict)}</td>`).join("")}</tr><tr><td>法條依據</td>${cols.map(([, p]) => `<td><ul>${p.basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></td>`).join("")}</tr><tr><td>事實認定</td>${cols.map(([, p]) => `<td><ul>${p.facts.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></td>`).join("")}</tr><tr><td>撤銷風險</td>${cols.map(([, p]) => `<td>${{ low: "低", mid: "中", high: "高" }[p.risk[0]]}　${esc(p.risk[1])}</td>`).join("")}</tr></table>
    ${S.objections.length ? `<h3>三、異議紀錄</h3><table><tr><th>爭點</th><th>承辦人理由</th><th>AI 回覆</th></tr>${S.objections.map((o) => `<tr><td>${esc(o.issue)}</td><td>${esc(o.text)}</td><td>${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[o.result]}：${esc(o.reply)}</td></tr>`).join("")}</table>` : ""}
    <p class="note">本表由訴願智審臺原型自動編製，僅供訴願審議委員會參考；一切法律見解與事實認定以委員會決議為準。</p><script>setTimeout(()=>window.print(),300)</script></body></html>`); w.document.close();
}

/* ---------- 結案歸檔 ---------- */
let finalPick = null;
function openClose() {
  const c = S.c, cp = currentPlan(); finalPick = null;
  $("#finalName").textContent = "尚未上傳"; $("#finalPrev").src = "about:blank"; $("#closeSend").disabled = true;
  const opts = $$("#finalVerdict option").map((o) => o.textContent); $("#finalVerdict").value = opts.includes(cp.verdict) ? cp.verdict : (cp.verdict.includes("撤銷") ? "原處分撤銷" : cp.verdict.includes("不受理") ? "訴願不受理" : "訴願駁回");
  $("#finalDate").value = c.final?.date || today(); $("#finalNo").value = c.final?.no || "";
  const stN = { appellant: "採訴願人", agency: "採機關", open: "待議" };
  $("#deid").innerHTML = [["訴願人", `${esc(c.fields[0]?.a[0] || "")} → <span class="m">［訴願人］</span>`], ["身分證／地址／電話", `<span class="m">全數移除</span>`], ["案由／條款", `${esc(c.subj)}／${esc(cp.art)}`], ["爭點與表態", c.issues.map((it, i) => `${i + 1}:${stN[S.stances[it.id]]}`).join("　")], ["證據組合", [...new Set(c.docs.filter((d) => d.include !== false).map((d) => d.tag))].join("、")], ["AI 判定／最終結論", `${esc(judgePlan().verdict)} → <span id="deidVerdict">${esc($("#finalVerdict").value)}</span>`], ["承辦人修改", `${S.paras.filter((p) => p.src === "human").length} 段人工編輯・${S.objections.length} 次異議`], ["歸戶標籤", `${(c.labelAudit || []).length} 筆人工修正`]].map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`).join("");
  $("#finalVerdict").onchange = () => { $("#deidVerdict").textContent = $("#finalVerdict").value; };
  $("#closeModal").classList.add("on");
}
$("#pickFinal").addEventListener("click", () => $("#finalFile").click());
$("#finalFile").addEventListener("change", (e) => { const f = e.target.files[0]; if (!f) return; const url = URL.createObjectURL(f); finalPick = { name: f.name, url, persist: null }; $("#finalName").textContent = `已上傳：${f.name}（${Math.round(f.size / 1024)} KB）`; $("#finalPrev").src = url; $("#closeSend").disabled = false; });
$("#useRealFinal").addEventListener("click", () => { const f = S.c.final?.file || CASE_B.final.file; finalPick = { name: "17.114年-違反廢棄物清理法事件-79I-訴願無理由-駁回.pdf", url: f, persist: f }; $("#finalName").textContent = `已選用：case02 真實決定書（demo）${S.c.final?.file ? "" : "　※ 本案無對應 PDF，以 case02 檔案示範"}`; $("#finalPrev").src = f + "#toolbar=0"; $("#closeSend").disabled = false; });
$("#closeSend").addEventListener("click", () => {
  if (!finalPick) return; const c = S.c;
  S.final = { verdict: $("#finalVerdict").value, date: $("#finalDate").value.trim(), no: $("#finalNo").value.trim(), fileName: finalPick.name, file: finalPick.persist || finalPick.url };
  S.status = "已結案";
  c.docs = c.docs.filter((d) => d.id !== "final"); c.docs.push({ id: "final", title: "訴願決定書（委員會結論）", stdName: `決定書_${S.final.date}`, tag: "決定書", src: "本局", kind: "pdf", pages: 3, file: S.final.file, include: true, origName: finalPick.name }); c.refs["doc-final"] = ["final", "doc"];
  const fp = c.final?.paras || {}; S.finalDiff = S.paras.filter((q) => fp[q.id] !== undefined && plain(q.text) !== plain(fp[q.id])).map((q) => ({ label: paraLabel(q), html: diffHtml(plain(fillDates(q.text)), plain(fp[q.id])) }));
  pushVersion(`結案歸檔（最終決定：${S.final.verdict}）`, "承辦人"); S.audit.push({ ts: now(), who: "hu", para: "案件", action: `登錄委員會結論 ${S.final.no || ""} 並結案歸檔` });
  $("#closeModal").classList.remove("on"); render(); persist(); openDoc("final"); $$(".tab")[4].click();
});
$("#courtSend").addEventListener("click", () => { const res = $("#courtRes").value, text = $("#courtText").value.trim(); if (res.startsWith("撤銷") && !text) return alert("撤銷時請填理由摘要"); S.court = { res, text, at: today() }; S.audit.push({ ts: now(), who: "hu", para: "案件", action: `登錄法院結果：${res}${text ? "／" + text : ""}` }); $("#courtModal").classList.remove("on"); renderDraft(); updateChips(); persist(); });

/* ---------- 案件庫 ---------- */
function openLibrary() {
  persist(); show("s-lib");
  const subj = [...new Set(LIB.map((r) => r.subj))], arts = [...new Set(LIB.map((r) => r.art))];
  $("#fSubj").innerHTML = '<option value="">案由：全部</option>' + subj.map((s) => `<option>${esc(s)}</option>`).join(""); $("#fArt").innerHTML = '<option value="">條款：全部</option>' + arts.map((s) => `<option>${esc(s)}</option>`).join("");
  renderLib(); $("#backBtn").style.display = "";
  $("#libClear").onclick = () => { if (!LIB.length) return; if (!confirm(`清空案件庫全部 ${LIB.length} 筆紀錄？此動作無法復原。`)) return; LIB = []; S.libId = null; saveLib(); renderLib(); renderLibCard(); };
}
function renderLib() {
  const f = { subj: $("#fSubj").value, art: $("#fArt").value, v: $("#fVerdict").value, st: $("#fStatus").value };
  const rows = LIB.filter((r) => (!f.subj || r.subj === f.subj) && (!f.art || r.art === f.art) && (!f.v || (r.verdict || "").startsWith(f.v)) && (!f.st || r.status === f.st)).sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""));
  $("#libStat").textContent = `共 ${LIB.length} 案・顯示 ${rows.length}`;
  $("#libTable").innerHTML = `<tr><th>案號</th><th>案由</th><th>條款</th><th>結論</th><th>狀態</th><th>結案日</th><th>法院結果</th><th>更新</th><th></th></tr>` + (rows.length ? rows.map((r) => `<tr data-id="${r.libId}"><td class="num">${esc(r.no)}</td><td>${esc(r.name)}</td><td class="num">${esc(r.art.replace("訴願法 ", ""))}</td><td>${esc(r.verdict)}${r.aiVerdict && r.aiVerdict !== r.verdict ? `<div class="note">AI 判定：${esc(r.aiVerdict)}</div>` : ""}</td><td><span class="chip status on ${r.status}" style="display:inline-flex;padding:1px 8px"><b>${r.status}${r.court ? "・法院" + (r.court.res.startsWith("維持") ? "維持" : r.court.res.startsWith("撤銷") ? "撤銷" : "未訴") : ""}</b></span></td><td class="num">${r.closedAt || "—"}</td><td>${r.court ? esc(r.court.res) : "—"}</td><td class="num">${r.updatedAt}</td><td><button class="ghost-btn del" data-del="${r.libId}" title="刪除此案件紀錄" style="padding:2px 8px;font-size:11px;color:var(--seal)">刪除</button></td></tr>`).join("") : `<tr><td colspan="9" class="empty">案件庫尚無案件；分析任一案件後即會出現。</td></tr>`);
  $$("#libTable .del").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); const r = LIB.find((x) => x.libId === b.dataset.del); if (!r) return; if (!confirm(`刪除案件紀錄「${r.no}　${r.name}」（${r.status}）？此動作無法復原。`)) return; LIB = LIB.filter((x) => x.libId !== r.libId); if (S.libId === r.libId) S.libId = null; saveLib(); renderLib(); renderLibCard(); }));
  $$("#libTable tr[data-id]").forEach((tr) => tr.addEventListener("click", (e) => { if (e.target.closest(".del")) return; const rec = LIB.find((r) => r.libId === tr.dataset.id); if (rec) openRecord(rec); }));
}
["#fSubj", "#fArt", "#fVerdict", "#fStatus"].forEach((s) => $(s).addEventListener("change", renderLib));

/* ---------- 案件問答助手（只讀） ---------- */
$("#asstBtn").addEventListener("click", asstOpen); $("#asstClose").addEventListener("click", () => $("#asst").classList.remove("on"));
function asstOpen() { $("#asst").classList.add("on"); $("#asstIn").focus(); }
function asstAdd(role, html) { const log = $("#asstLog"); const el = document.createElement("div"); el.className = "msg " + role; el.innerHTML = html; log.appendChild(el); log.scrollTop = log.scrollHeight; return el; }
function asstSay(t) { asstOpen(); asstAdd("a", esc(t)); }
function asstReset() { $("#asstLog").innerHTML = ""; asstAdd("a", `我是本案的問答助手，只讀不改。可以問我「某個資料在哪份文件」「答辯書引了哪些法條」「本案爭點」。`); $("#asstSug").innerHTML = ["送達日在哪份文件？", "煙蒂的照片在哪？", "答辯書引了哪些法條？", "本案爭點有哪些？", "期間有沒有逾期？"].map((q) => `<button class="ghost-btn">${q}</button>`).join(""); $$("#asstSug button").forEach((b) => b.addEventListener("click", () => { $("#asstIn").value = b.textContent; asstSend(); })); }
function asstIndex() {
  const c = S.c, out = [];
  c.docs.forEach((d) => { if (d.include === false) return; const t = d.stdName || d.title, k = d.kind; if (d.html) { const re = /<mark data-ref="([^"]+)">([\s\S]*?)<\/mark>/g; let m; while ((m = re.exec(d.html))) out.push({ ref: m[1], doc: t, kind: k, tag: d.tag, text: plain(m[2]), where: "本文" }); } (d.boxes || []).forEach((b) => out.push({ ref: b.ref, doc: t, kind: k, tag: d.tag, text: b.label, where: "框選區" })); (d.cues || []).forEach((q) => out.push({ ref: q[0], doc: t, kind: k, tag: d.tag, text: q[2], where: "影片時間點" })); });
  return out;
}
const SYN = [["送達日", "送達日期"], ["收文", "收文"], ["煙蒂", "煙蒂"], ["照片", "採證"], ["影片", "12:40"], ["簽收", "簽章"], ["罰鍰", "3,600"], ["係數", "A=3"], ["車主", "車籍"], ["拋棄", "拋擲"]];
function asstSend() {
  const q = $("#asstIn").value.trim(); if (!q || !S.c) return; $("#asstIn").value = ""; asstAdd("u", esc(q));
  const c = S.c;
  if (/改|修改|幫我寫|重寫|刪|加一段|潤飾/.test(q)) return asstAdd("a", "助手不修改草稿或任何案件內容。請直接在草稿頁點段落編輯，或用「我有異議」請 AI 重新引證。");
  if (/法條|引用|法規|援引/.test(q)) return asstAdd("a", c.citations.length ? `答辯書引用 ${c.citations.length} 則：<br>${c.citations.map((x) => `・${J(x.ref, esc(x.n))}　<span class="st ${x.status}" style="font-size:10px">${{ ok: "已驗證", amended: "已修正", gap: "漏引" }[x.status] || x.status}</span>`).join("<br>")}<span class="src">來源：法規推薦分頁・引用查核</span>` : `本案尚無答辯書可查核。<span class="src">${esc(c.citationNote || "")}</span>`);
  if (/爭點|癥結/.test(q)) return asstAdd("a", `本案 ${c.issues.length} 個爭點：<br>${c.issues.map((it, i) => `・爭點 ${i + 1}：${esc(it.title)}（AI ${{ agency: "採機關", appellant: "採訴願人", open: "待議" }[it.stance || "open"]}）`).join("<br>")}<span class="src">來源：爭點分頁</span>`);
  if (/期間|逾期|幾天|屆滿/.test(q)) { const p = period(); return asstAdd("a", p ? `送達日 ${S.served}，起算 ${toMg(p.start)}，屆滿 ${toMg(p.due)}；收文日 ${S.recv || "—"}，${p.recv === null ? "尚無收文日" : p.over ? `<b style="color:var(--seal)">逾期 ${p.days} 日</b>` : `未逾期，尚餘 ${p.left} 日`}。${c.period.servedRef ? J(c.period.servedRef, "開啟送達證書 ↗") : ""}<span class="src">來源：期間計算模組（送達日以卷附送達證書為準）</span>` : "尚未取得送達日，無法計算期間。"); }
  if (/判定|結論|主文|風險/.test(q)) { const p = currentPlan(); return asstAdd("a", `AI 判定：<b>${esc(p.verdict)}</b>（${esc(p.art)}）。撤銷風險${{ low: "低", mid: "中", high: "高" }[p.risk[0]]}：${esc(p.risk[1])}<span class="src">來源：草稿分頁・AI 判定摘要</span>`); }
  const idx = asstIndex(); let terms = q.replace(/[？?，。、的在哪份哪個哪一裡面是什麼有沒有請問幫我找]/g, " ").split(/\s+/).filter((t) => t.length >= 2);
  SYN.forEach(([a, b]) => { if (q.includes(a)) terms.push(b); });
  const grams = new Set(); terms.forEach((t) => { for (let i = 0; i + 2 <= t.length; i++) grams.add(t.slice(i, i + 2)); });
  const GENERIC = ["訴願", "願人", "訴願人", "原處", "處分", "機關", "文件", "資料", "案件"];
  const wantPhoto = /照片|影像|圖/.test(q), wantVideo = /影片|錄影/.test(q), wantScan = /掃描|證書|紀錄表|簽呈/.test(q);
  const scored = idx.map((e) => { const hay = e.text + e.doc; let s = 0; grams.forEach((g) => { if (!GENERIC.includes(g) && hay.includes(g)) s++; }); terms.forEach((t) => { if (!GENERIC.includes(t) && hay.includes(t)) s += 3; }); if (wantPhoto && /照片|影像/.test(e.tag)) s += 4; if (wantVideo && e.kind === "video") s += 4; if (wantScan && e.kind === "image" && !/照片/.test(e.tag)) s += 2; return { ...e, s }; }).filter((e) => e.s >= 3).sort((a, b) => b.s - a.s);
  const seen = new Set(), top = scored.filter((e) => { const k = e.doc + e.text; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 3);
  if (!top.length) return asstAdd("a", `卷宗內無此資訊。<span class="src">已檢索 ${c.docs.filter((d) => d.include !== false).length} 份文件之 ${idx.length} 個定位點</span>`);
  asstAdd("a", `找到 ${top.length} 處：<br>${top.map((e) => `・《${esc(e.doc)}》第 1 頁・${e.where}：「${esc(e.text.length > 40 ? e.text.slice(0, 40) + "…" : e.text)}」<button class="ghost-btn open" data-jump="${e.ref}">開啟</button>`).join("<br>")}<span class="src">來源：卷宗歸戶後之定位索引</span>`);
}
$("#asstSend").addEventListener("click", asstSend); $("#asstIn").addEventListener("keydown", (e) => { if (e.key === "Enter") asstSend(); });

/* ---------- 字元級 diff ---------- */
function diffHtml(a, b) {
  const n = a.length, m = b.length; if (n * m > 400000) return `<del>${esc(a)}</del><ins>${esc(b)}</ins>`;
  const dp = new Uint16Array((n + 1) * (m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i * (m + 1) + j] = a[i] === b[j] ? dp[(i + 1) * (m + 1) + j + 1] + 1 : Math.max(dp[(i + 1) * (m + 1) + j], dp[i * (m + 1) + j + 1]);
  let i = 0, j = 0, out = "", buf = { t: "", k: "" };
  const flush = () => { if (!buf.t) return; out += buf.k === "=" ? esc(buf.t) : buf.k === "-" ? `<del>${esc(buf.t)}</del>` : `<ins>${esc(buf.t)}</ins>`; buf = { t: "", k: "" }; };
  const push = (k, ch) => { if (buf.k !== k) { flush(); buf.k = k; } buf.t += ch; };
  while (i < n && j < m) { if (a[i] === b[j]) { push("=", a[i]); i++; j++; } else if (dp[(i + 1) * (m + 1) + j] >= dp[i * (m + 1) + j + 1]) { push("-", a[i]); i++; } else { push("+", b[j]); j++; } }
  while (i < n) push("-", a[i++]); while (j < m) push("+", b[j++]); flush(); return out;
}
