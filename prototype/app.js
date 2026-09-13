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
/* 修正歸戶下拉用；與後端 doc_type 封閉清單一致（server/schemas/enums.json） */
const TYPES = ["訴願書", "訴願委任書", "補充理由書", "答辯書", "答辯書檢送函", "卷證目錄", "裁處書", "裁處書送達證書", "陳述意見通知書", "通知書送達證書", "陳述意見書", "檢舉資料", "稽查紀錄", "調查筆錄", "採證照片", "影像放大標註", "採證影片", "車籍資料", "係數計算表", "簽呈", "檢驗報告", "契約書", "委員會決定書", "閱覽卷宗申請書", "言詞辯論申請書", "言詞陳述申請書", "參加訴願申請書", "其他", "補正通知函"];

/* ---------- 全域狀態 ---------- */
const S = { c: null, live: false, libId: null, status: "承辦中", served: null, recv: null, stances: {}, plan: null, paras: [], versions: [], audit: [], objections: [], doc: null, zoom: 1, final: null, court: null, finalDiff: null, labels: [] };
let LIB = [];
try { LIB = JSON.parse(localStorage.getItem("ssz.lib") || "[]").filter((r) => r && r.libId); } catch (e) { LIB = []; }   // 過濾舊版留下的 libId=null 殘留列
function saveLib() { try { localStorage.setItem("ssz.lib", JSON.stringify(LIB)); } catch (e) { /* 容量不足時略過 */ } }

/* ---------- 主題 ---------- */
function show(id) { $$(".screen").forEach((s) => s.classList.toggle("on", s.id === id)); window.scrollTo(0, 0); const inCase = id === "s-work"; $("#asstBtn").style.display = inCase ? "" : "none"; if (!inCase) $("#asst").classList.remove("on"); }
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
function addFiles(list) {
  // 保留原始 File 物件：接後端時要用 FormData 上傳，只有檔名是不夠的
  Array.from(list).forEach((f) => {
    if (FILES.some((x) => x.name === f.name && x.kb === Math.round((f.size || 0) / 1024))) return;
    FILES.push({ name: f.name, kb: Math.max(1, Math.round((f.size || 0) / 1024)), file: f, docId: undefined, base: "B" });
  });
  renderFiles();
}
const drop = $("#drop"), fileInput = $("#file");
drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
fileInput.addEventListener("change", (e) => { addFiles(e.target.files); fileInput.value = ""; });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
$("#clearBtn").addEventListener("click", (e) => { e.preventDefault(); FILES = []; renderFiles(); });
$("#runBtn").addEventListener("click", () => startUpload());

/* ---------- F8：真上傳 ---------- */
const newCaseId = () => { const d = new Date(), p = (n) => String(n).padStart(2, "0");
  return `c${String(d.getFullYear()).slice(2)}${p(d.getMonth() + 1)}${p(d.getDate())}-${Math.random().toString(36).slice(2, 6)}`; };

function uploadError(e) {
  // 沒有 fallback：後端壞了就說壞了，不拿假資料頂替
  $("#fileHint").innerHTML = `<span style="color:var(--seal)">${esc(e.code || "ERROR")}：${esc(e.message || "")}</span>`;
  $("#runBtn").disabled = false; $("#runBtn").textContent = "重試";
}

async function startUpload() {
  const files = FILES.map((f) => f.file).filter(Boolean);
  if (!files.length) return uploadError({ code: "NO_FILE", message: "沒有可上傳的檔案（請重新選擇）" });
  $("#runBtn").disabled = true; $("#runBtn").textContent = "上傳中…";
  try {
    const caseId = newCaseId();
    const r = await Api.upload(caseId, files);
    runLive(caseId, r);
  } catch (e) { uploadError(e); }
  finally { $("#runBtn").textContent = "開始分析"; }
}

/* ---------- 貼上文字 ---------- */
// v7：貼上訴願書文字的即時解析入口自首頁移除；parseAppeal／buildLive 保留供 pipeline 參考

/* ---------- 示範案件卡與案件庫卡 ---------- */
/* 示範案件卡是唯一的 demo 入口（v8：上傳區的小字連結移除）。
   「以亂檔名」保留在卡片上——它證明判定看內容不看檔名，是這套系統的重點之一。 */
/* 首頁只留一張示範案件卡：case02（唯一有 S3 卷宗包、能真跑的那案）。
   其餘案例仍在 CASES 內供案件庫與測試使用，只是不在首頁露出。 */
const DEMO_CASES = CASES.filter((c) => c.hasDemoPack);
$("#caseGrid").innerHTML = DEMO_CASES.map((c) => { const i = CASES.indexOf(c); return `<div class="case-card" data-i="${i}"><span class="no num">案號 ${c.no}</span><h3>${c.cardTitle}</h3><p class="cdesc">${esc(c.cardDesc || "")}</p><div style="display:flex;flex-wrap:wrap;gap:6px">${c.cardTags.slice(1, 2).join("")}</div><div class="foot"><span>${c.name}</span><span style="display:flex;gap:14px;align-items:center"><span class="alt" data-messy="${i}" title="檔名換成 IMG_3985.jpg／scan_0001.pdf，證明判定看內容不看檔名">以亂檔名 →</span><span class="go" data-run="${i}">開始分析 →</span></span></div></div>`; }).join("");
$$("#caseGrid .go").forEach((el) => el.addEventListener("click", () => startDemo(+el.dataset.run, false)));
$$("#caseGrid .alt").forEach((el) => el.addEventListener("click", (e) => { e.stopPropagation(); startDemo(+el.dataset.messy, true); }));
$$(".case-card").forEach((el) => el.addEventListener("click", (e) => { if (!e.target.closest(".go,.alt")) startDemo(+el.dataset.i, false); }));

/* 示範案件：打 POST /api/cases/{id}/demo，從 S3 預放的卷宗真跑一次（不是查表） */
async function startDemo(i, messy) {
  const c = CASES[i];
  if (!c.hasDemoPack) return;
  const card = $(`#caseGrid .case-card[data-i="${i}"]`) || $("#caseGrid .case-card"), go = card.querySelector(".go");
  const label = go.textContent; go.textContent = messy ? "亂檔名載入中…" : "載入中…";
  try {
    const caseId = newCaseId();
    const r = await Api.demo(caseId, { pack: c.pack || "case02", messy });
    runLive(caseId, r, { title: c.cardTitle, name: c.name, no: c.no, messy });
  } catch (e) {
    go.textContent = label;
    card.insertAdjacentHTML("beforeend", `<p class="cdesc" style="color:var(--seal)">${esc(e.code || "ERROR")}：${esc(e.message || "")}</p>`);
  }
}

function renderLibCard() {}

$("#libBtn").addEventListener("click", openLibrary);
$("#homeBtn").addEventListener("click", (e) => { e.preventDefault(); $("#backBtn").click(); });
/* 頂部列的位置提示：首頁不顯示；案件／法規庫／案件庫顯示所在 */
function setCrumb(text) { const el = $("#crumb"); if (!text) { el.classList.remove("on"); el.innerHTML = ""; } else { el.classList.add("on"); el.innerHTML = text; } $$(".topnav button").forEach((b) => b.classList.toggle("on", (b.id === "lawBtn" && text === "法規庫") || (b.id === "libBtn" && text === "案件庫"))); }
$("#backBtn").addEventListener("click", () => { setCrumb(""); persist(); $("#analysisNote").style.display = "none"; $$(".tab").forEach((b) => { b.disabled = false; b.style.opacity = ""; }); show("s-pick"); Router.set("/"); ["chip", "statusChip", "judgeChip"].forEach((id) => $("#" + id).classList.remove("on")); $("#backBtn").style.display = "none"; renderLibCard(); renderLawCard(); });
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
    : { id: "I1", title: "違規事證是否充足", a: ["訴願人主張舉證不足／否認違規。", null], d: ["（尚無答辯書）", null], e: [["須待原處分機關檢卷", null]], law: (SUBJ_LAWS[Sj] || []).map((l) => l.n), lead: { agency: ["A", "事證明確 → 駁回"], appellant: ["B", "舉證不足 → 撤銷"] }, stance: "open", objection: { result: "partial", plan: null, reply: "尚無答辯書與卷證可資重新引證；請於原處分機關檢卷後再提出修正意見。", evidence: [] } };
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
    S.libId = c.live ? c.caseId : existing ? existing.libId : `${c.id}-${Date.now().toString(36)}`;   // 真上傳案：網址與案件庫都用後端 caseId
  }
  S.doc = null; S.zoom = 1; S.docMode = {};
  $("#chip").classList.add("on"); setCrumb($("#s-run").classList.contains("on") ? "分析中" : "案件審理"); $("#chipName").textContent = c.name; $("#chipNo").textContent = c.live ? c.no : "案號 " + c.no; $("#backBtn").style.display = ""; setCrumb("案件審理");
  if (restore || c.analysis) { if (restore) { render(); show("s-work"); Router.set(`/case/${S.libId || c.caseId || c.id}`); } return; }
  const steps = [["文件辨識（Claude 判定）", `${c.docs.length} 個檔案 → ${c.docs.filter((d) => d.include !== false).length} 份納入・${c.docs.filter((d) => d.dup).length} 份重複・${c.docs.filter((d) => d.unknown).length} 份無法辨識`, Math.min(2600, 700 + c.docs.length * 110), "classify"], ["欄位擷取（三方對照）", `${c.fields.length} 個欄位，${c.fields.filter((f) => f.conflict).length} 處衝突`, 700], ["爭點比對（訴願書 vs 答辯書 vs 卷證）", `識別 ${c.issues.length} 個爭點`, 760], ["法規檢索與引用查核", `推薦 ${c.laws.length} 筆；查核答辯書引用 ${c.citations.length} 則${c.citations.some((x) => x.status === "amended") ? "，1 則已修正" : ""}`, 840], ["AI 判定與草稿生成", `判定：${judgePlan(c).verdict}（${judgePlan(c).art}）`, 900]];
  $("#runSub").textContent = c.live ? c.name : `${c.name}　・　案號 ${c.no}${c.uploadNote ? "　・　" + c.uploadNote : ""}`;
  $("#stepList").innerHTML = steps.map((s, i) => `<div class="step" id="st${i}"><div class="idx">${i + 1}</div><div><div class="name">${s[0]}</div><div class="out" id="so${i}"></div>${s[3] ? `<div class="classify" id="cls${i}" style="flex-direction:column;gap:3px">${c.docs.map((d) => `<span style="display:flex;gap:8px;align-items:center;${d.include === false ? "opacity:.55" : ""}"><span class="num" style="color:var(--ink-3);min-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(d.origName || d.title)}</span><span>→</span><b style="white-space:nowrap">${d.tag}</b><span class="srct ${d.src}" style="flex:none">${d.src}</span><span style="color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0">${esc(d.summary || "")}</span></span>`).join("")}</div>` : ""}</div><div class="ms" id="sm${i}"></div></div>`).join("");
  $("#runBar").style.width = "0"; show("s-run");
  let t = 0;
  steps.forEach((s, i) => { setTimeout(() => { const el = $("#st" + i); if (!el) return; el.classList.add("active"); $("#runBar").style.width = ((i + 1) / steps.length * 100) + "%"; if (s[3]) $$("#cls" + i + " > span").forEach((sp, k) => setTimeout(() => sp.classList.add("in"), 80 + k * (1000 / Math.max(1, c.docs.length)))); }, t); t += s[2]; setTimeout(() => { const el = $("#st" + i); if (!el) return; el.classList.remove("active"); el.classList.add("done"); $("#so" + i).textContent = s[1]; $("#sm" + i).textContent = s[2] + " ms"; }, t); });
  setTimeout(() => { render(); show("s-work"); persist(); Router.set(`/case/${S.libId}`); }, t + 500);
}

/* =========================================================
   F9／F10：真分析中畫面（吃 SSE）→ 工作畫面（吃 GET files）
   步驟一是真的；步驟 2–5 待分析階段 API（docs/API-分析階段.md）接線
   ========================================================= */
const LIVE_STEPS = [
  ["文件辨識（Claude 判定）", "classify"],
  ["欄位擷取（三方對照）", "pending"],
  ["爭點比對（訴願書 vs 答辯書 vs 卷證）", "pending"],
  ["法規檢索與引用查核", "pending"],
  ["AI 判定與草稿生成", "pending"],
];

function runLive(caseId, job, meta = {}) {
  S.liveCase = { caseId, jobId: job.jobId, total: job.files.length }; Router.set(`/run/${caseId}`);
  $("#chip").classList.add("on"); setCrumb($("#s-run").classList.contains("on") ? "分析中" : "案件審理"); $("#chipName").textContent = meta.name || "新上傳案件";
  $("#chipNo").textContent = `暫編 ${caseId}`; $("#backBtn").style.display = ""; setCrumb("分析中");
  $("#runSub").textContent = `${meta.title || `${job.files.length} 個檔案`}　・　${caseId}${meta.messy ? "　・　亂檔名（檔名不參與判定）" : ""}`;
  $("#stepList").innerHTML = LIVE_STEPS.map(([name, kind], i) => `<div class="step" id="st${i}"><div class="idx">${i + 1}</div><div><div class="name">${name}</div><div class="out" id="so${i}"></div>${kind === "classify" ? `<div class="classify" id="cls0" style="flex-direction:column;gap:3px"></div>` : ""}</div><div class="ms" id="sm${i}"></div></div>`).join("");
  $("#runBar").style.width = "0"; show("s-run");
  $("#st0").classList.add("active");
  const q = job.queue || { ahead: 0 };
  $("#so0").textContent = q.ahead
    ? `已收 ${job.files.length} 個檔案・排隊中：前面還有 ${q.ahead} 件，約 ${Math.ceil(q.etaMs / 1000)} 秒`
    : `已收 ${job.files.length} 個檔案，辨識中…`;

  const t0 = Date.now();
  const seen = new Map(job.files.map((f) => [f.fileId, f.originalName]));
  let done = 0, dup = 0, bad = 0;
  const queue = [];                       // result 是逐箱回來的，排隊演成逐檔浮現
  let draining = false;
  const drain = () => {
    if (draining || !queue.length) return;
    draining = true;
    const row = queue.shift();
    $("#cls0").insertAdjacentHTML("beforeend", row);
    const el = $("#cls0").lastElementChild;
    requestAnimationFrame(() => el.classList.add("in"));
    $("#so0").textContent = `${done} / ${S.liveCase.total} 份`;
    setTimeout(() => { draining = false; drain(); }, 70);
  };

  const row = (fid, name, tag, src, summary, cls = "") =>
    `<span data-fid="${esc(fid)}" style="display:flex;gap:8px;align-items:center;${cls}"><span class="num" style="color:var(--ink-3);min-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(name)}</span><span>→</span><b style="white-space:nowrap">${esc(tag)}</b><span class="srct ${src}" style="flex:none">${esc(src)}</span><span style="color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0">${esc(summary)}</span></span>`;

  // 正規化事件很早就到（每檔一筆），先佔位讓畫面立刻有東西；分類結果回來再就地替換
  const place = (fid, name, meta) => {
    if ($(`#cls0 [data-fid="${fid}"]`)) return;
    $("#cls0").insertAdjacentHTML("beforeend", row(fid, name, "辨識中…", "未知", meta, "opacity:.5"));
    requestAnimationFrame(() => $(`#cls0 [data-fid="${fid}"]`)?.classList.add("in"));
  };

  const push = (fid, name, tag, src, summary, cls = "") => {
    const held = fid && $(`#cls0 [data-fid="${fid}"]:not(.filled)`);
    if (held) { held.outerHTML = row(fid, name, tag, src, summary, cls); const el = $(`#cls0 [data-fid="${fid}"]`); el.classList.add("in", "filled"); }
    else queue.push(row(fid, name, tag, src, summary, cls));
    $("#so0").textContent = `${done} / ${S.liveCase.total} 份`;
    drain();
  };

  const stream = Api.streamJob(job.jobId, {
    onQueued: (d) => {
      $("#runTitle").textContent = "排隊中";
      $("#so0").textContent = `前面還有 ${d.ahead} 件處理中，約 ${Math.ceil((d.etaMs || 0) / 1000)} 秒後開始`;
    },
    onStarted: () => { $("#runTitle").textContent = "正在分析卷宗"; $("#so0").textContent = `開始辨識 ${S.liveCase.total} 個檔案…`; },
    onNormalized: (d) => {
      if (!seen.has(d.fileId)) seen.set(d.fileId, d.fileId);
      place(d.fileId, seen.get(d.fileId), `${KIND[d.kind] || d.kind}${d.pages ? `・${d.pages} 頁` : d.duration ? `・${d.duration}s` : ""}`);
    },
    onContainer: (d) => push(d.fileId, seen.get(d.fileId) || d.fileId, "壓縮檔", "未知", `已展開 ${d.childIds.length} 份`, "opacity:.6"),
    onResult: (d) => {
      const name = seen.get(d.fileId) || d.fileId;
      if (d.duplicate) { dup++; done++; return push(d.fileId, name, "重複", "未知", "與既有檔案內容相同，已排除", "opacity:.55"); }
      if (!d.ok) { bad++; done++; return push(d.fileId, name, "讀取失敗", "未知", d.error?.code || "NORMALIZE_FAILED", "opacity:.7;color:var(--seal)"); }
      done++;
      const segs = d.segments || [];
      segs.forEach((sg, i) => push(i === 0 ? d.fileId : null, segs.length > 1 ? `${name}（${i + 1}/${segs.length}）` : name, sg.doc_type, sg.source, sg.summary || ""));
      $("#runBar").style.width = Math.round((done / S.liveCase.total) * 100 * 0.6) + "%";
    },
    onDone: async (d) => {
      $("#st0").classList.remove("active"); $("#st0").classList.add("done");
      $("#so0").textContent = `${d.ok} 份完成・${d.duplicate} 份重複・${d.error} 份失敗`;
      $("#sm0").textContent = `${Math.round((d.ms || Date.now() - t0) / 1000)} s`;
      $("#runBar").style.width = "20%";
      try { await runAnalysis(caseId); } catch (e) { fail(e); }
    },
    onFatal: (e) => fail(e),
  });

  function fail(e) {
    $("#st0").classList.remove("active");
    $("#so0").innerHTML = `<span style="color:var(--seal)">${esc(e.code || "ERROR")}：${esc(e.message || "")}</span>`;
    $("#runTitle").textContent = "分析失敗";
    stream.close();
  }

  // 逾時：超過 3 分鐘視為異常（實測 20 檔約 60–90 秒）
  setTimeout(() => { if (!$("#st0").classList.contains("done")) fail({ code: "TIMEOUT", message: "超過 3 分鐘未完成，請重試或檢查後端日誌" }); }, 180000);
}

/* =========================================================
   步驟 2–5：POST analyze → 每 3 秒 GET analysis 驅動進度 → done 後把 output 轉成工作畫面的 case 物件
   契約：docs/API-分析階段.md
   ========================================================= */
const ANALYSIS_STEPS = ["s2", "s3", "s4", "s5", "s6"];   // 對應畫面 st1…st4（s5、s6 合併顯示在第 5 格：相似案例＋草稿）
const STEP_SLOT = { s2: 1, s3: 2, s4: 3, s5: 4, s6: 4 };
const STEP_OUT = {
  s2: (o) => `${(o.fields || []).length} 個欄位，${(o.fields || []).filter((f) => f.conflict).length} 處衝突；程序 ${(o.checks || []).filter((k) => k[2] === "pass").length}/8 通過`,
  s3: (o) => `識別 ${(o.issues || []).length} 個爭點`,
  s4: (o) => `推薦 ${(o.laws || []).length} 筆；查核引用 ${(o.citations || []).length} 則${(o.citations || []).some((x) => x.status === "gap") ? "，有漏引" : ""}${o.alert ? "；⚠ 時效警示" : ""}`,
  s5: (o) => `相似案例 ${(o.sims || []).length} 件`,
  s6: (o) => `判定：${o.judge?.verdict || ""}（${o.judge?.art || ""}）`,
};
async function runAnalysis(caseId, { post = true } = {}) {
  $("#runTitle").textContent = "正在分析卷宗";
  for (let i = 1; i < LIVE_STEPS.length; i++) { $("#st" + i).style.opacity = ""; $("#so" + i).textContent = ""; }
  if (post) {  // 分析服務重佈時會有幾秒 ECONNREFUSED（502 ANALYSIS_UNAVAILABLE）：等它起來再送，不要直接判失敗
    for (let k = 0; ; k++) {
      try { await Api.analyze(caseId); break; }
      catch (e) { if (!(e.status === 502 || e.code === "ANALYSIS_UNAVAILABLE" || e.code === "NETWORK") || k >= 8) throw e; $("#so1").textContent = `分析服務啟動中，${5 * (k + 1)} 秒後重試（${k + 1}/8）…`; await new Promise((r) => setTimeout(r, 5000)); }
    }
  }
  Router.set(`/run/${caseId}`);
  $("#st1").classList.add("active"); $("#so1").textContent = "欄位擷取中…";
  return new Promise((resolve, reject) => {
    const started = {};
    Api.pollAnalysis(caseId, (doc, e) => {
      if (e) return reject(e);
      const st = doc.status || {}, o = doc.output || {};
      let doneN = 0;
      for (const step of ANALYSIS_STEPS) {
        const slot = STEP_SLOT[step], el = $("#st" + slot), state = st.steps?.[step];
        if (state === "running") { el.classList.add("active"); if (!started[step]) { started[step] = 1; $("#so" + slot).textContent = { s2: "欄位擷取中…", s3: "比對爭點中…", s4: "檢索法規、查核引用中…", s5: "檢索相似案例中…", s6: "撰擬決定書草稿中…" }[step]; } }
        if (state === "done") { doneN++; $("#so" + slot).textContent = STEP_OUT[step](o); if (step !== "s5") { el.classList.remove("active"); el.classList.add("done"); $("#sm" + slot).textContent = `${Math.round((st.ms?.[step] || 0) / 1000)} s`; } }
      }
      $("#runBar").style.width = Math.round(20 + doneN / ANALYSIS_STEPS.length * 80) + "%";
      if (st.state === "failed") return reject(new ApiError(st.error?.code || "ANALYSIS_FAILED", st.error?.message || st.error || "分析失敗"));
      if (st.state === "done") enterWork(caseId, doc).then(resolve, reject);
    });
  });
}

/** analysis.output（API 契約形狀）→ 工作畫面的 case 物件（data.js 形狀） */
const DIST_COLOR = { "不受理": "#9C3A2E", "駁回": "#A8792A", "撤銷": "#2E7D5B" };
function toCase(caseId, docs, doc) {
  const o = doc.output || {}, j = o.judge || {};
  const byFile = {}; docs.forEach((d) => { if (!byFile[d.fileId]) byFile[d.fileId] = d.id; });
  const refs = {};
  for (const [k, v] of Object.entries(o.refs || {})) { const id = byFile[v[0]]; if (id) refs[k] = [id, v[1], v[2]]; }
  const fixRef = (r) => (r && refs[r] ? r : null);
  const finding = (f) => /^採機關/.test(f || "") ? "agency" : /^採訴願人/.test(f || "") ? "appellant" : "open";
  const plan = { id: "A", name: "AI 判定", verdict: j.verdict || "—", art: j.art || "", when: {}, basis: [], facts: (j.issues || []).map((x) => `${x[0]}（${x[1]}）`), cases: [], risk: [j.risk || "mid", j.riskNote || ""] };
  let sect = "", n = 0;
  const dv = Object.keys(o.drafts || {}), latestDraft = dv.length ? o.drafts[dv[dv.length - 1]] : null;   // 修改提案後重產的 vN 是現行版
  const paras = (latestDraft?.paras || []).map((p) => {
    if (p.kind === "h4") { sect = p.text; n = 0; return { id: `h-${p.text}`, kind: "h4", text: p.text }; }
    n++;
    const id = sect === "主文" ? "main" : sect === "事實" ? `fact${n}` : sect === "理由" ? `r${n}` : `p${n}`;
    return { id, kind: "p", text: esc(p.text), refs: (p.refs || []).map(fixRef).filter(Boolean), borrow: p.borrow || null };
  });
  const files = o.files || [];
  return {
    id: caseId, no: caseId, name: docs.find((d) => d.party)?.party || "新上傳案件", live: true, caseId, analysisPending: false, docs,
    dates: o.dates || null,
    fields: (o.fields || []).map((f) => ({ k: f.k, a: [f.a[0] ?? "—", fixRef(f.a[1])], d: [f.d[0] ?? "—", fixRef(f.d[1])], e: [f.e[0] ?? "—", fixRef(f.e[1])], conflict: f.conflict })),
    cls: o.cls || [],
    period: { served: o.period?.served || null, recv: o.period?.recv || null, appealSays: o.period?.appealSays || null, servedRef: fixRef(o.period?.servedRef), recvRef: fixRef(o.period?.recvRef) },
    checks: (o.checks || []).map((k) => [k[0], k[1], k[0] === "77(2)" ? "auto" : k[2], k[3]]),
    issues: (o.issues || []).map((it) => ({ id: it.id, title: it.title, a: [it.a[0], fixRef(it.a[1])], d: [it.d[0], fixRef(it.d[1])], e: (it.e || []).map((x) => [x[0], fixRef(x[1])]), law: it.law || [], stance: finding(it.afterObjection || it.finding), ai: it.reason, lead: { agency: ["A", ""], appellant: ["A", ""] } })),
    citations: (o.citations || []).map((x) => ({ ...x, status: x.status === "unknown" ? "missing" : x.status, ref: fixRef(x.ref) })),
    laws: (o.laws || []).map((l) => ({ ...l, badges: (l.badges || []).map((b) => Array.isArray(b) ? tag(b[0], b[1]) : b) })),
    alert: o.alert || null,
    sims: (o.sims || []).map((s) => ({ ...s, chips: s.chips || [] })),
    simDist: (o.simDist || []).map((d) => [d[0], d[1], DIST_COLOR[d[0]] || "#888"]),
    simsNote: `相似案例來自 Bedrock Knowledge Base（101 決定書語意檢索，已排除本案自身）；${(o.sims || []).filter((s) => s.borrow).length} 件標示可借用理由段。`,
    plans: [plan], judge: "A",
    drafts: { A: { tmpl: (j.art || "").replace("訴願法 §", ""), head: o.drafts?.A?.head || "新北市政府訴願決定書", sub: `案號：${caseId}　（AI 草稿・待承辦人審核）`, paras } },
    refs, analysis: doc, lawlib: o.lawlib || null,
  };
}

/** 取回歸戶結果＋分析結果，進工作畫面 */
async function enterWork(caseId, analysis) {
  const payload = await Api.listFiles(caseId);
  const docs = toDocs(payload);
  if (!analysis) {  // 沒分析結果（舊流程／分析失敗）：只有卷宗瀏覽器
    S.c = { id: caseId, no: caseId, name: docs.find((d) => d.party)?.party || "新上傳案件", live: true, analysisPending: true, caseId, cutoffDate: payload.cutoffDate,
      docs, fields: [], cls: [], issues: [], laws: [], citations: [], sims: [], simDist: [], drafts: {}, refs: {}, period: { served: null, recv: null } };
    S.doc = null; S.zoom = 1; S.docMode = {}; S.audit = []; S.objections = []; S.paras = []; S.versions = [];
    S.status = "承辦中"; S.libId = `${caseId}`;
    renderDocs(); $("#analysisNote").style.display = "";
    $$(".tab").forEach((b, i) => { b.disabled = i > 0; b.style.opacity = i > 0 ? ".4" : ""; }); $$(".tab")[0].click();
    const first = docs.find((d) => d.include !== false); if (first) openDoc(first.id);
    show("s-work"); return;
  }
  const c = toCase(caseId, docs, analysis);
  c.cutoffDate = payload.cutoffDate;
  $("#analysisNote").style.display = "none";
  $$(".tab").forEach((b) => { b.disabled = false; b.style.opacity = ""; });
  runCase(c, false);          // 走與示範案相同的 render 路徑（S.served/S.recv/立場/草稿版本）
  render(); show("s-work"); persist(); Router.set(`/case/${caseId}`);
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
  if (!S.libId || !S.c) return;   // 尚未配到案件編號（分析中、路由還原中）不落地，避免產生 libId=null 的殘留列
  if (!S.c) return;
  const c = S.c;
  if (c.analysisPending) {      // 真上傳案件：只有卷宗是真的，判定／草稿尚未接線，不要去算
    const rec = { libId: S.libId, baseId: c.id, name: c.name, no: c.no, subj: null, art: null, verdict: null,
      aiVerdict: null, status: S.status, createdAt: today(), closedAt: null, final: null, court: null, updatedAt: today(),
      analysisPending: true, caseId: c.caseId,
      state: { docs: c.docs.map((d) => ({ id: d.id, fileId: d.fileId, tag: d.tag, src: d.src, include: d.include, origName: d.origName, stdName: d.stdName, kind: d.kind, title: d.title, summary: d.summary, dup: d.dup })), audit: S.audit } };
    const k = LIB.findIndex((r) => r.libId === S.libId); if (k >= 0) LIB[k] = rec; else LIB.push(rec);
    return saveLib();
  }
  const jp = judgePlan();
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
  if (c.live && c.caseId) refreshLiveUrls(c);   // 存在案件庫裡的 presigned URL 會過期（15 分鐘）且可能是舊簽法，重開時一律向後端換新
}
/** 真上傳案件：用 GET files 換新每份文件的 rawUrl／downloadUrl／pageImageUrls／textUrl */
async function refreshLiveUrls(c) {
  try {
    const fresh = toDocs(await Api.listFiles(c.caseId)), byId = Object.fromEntries(fresh.map((d) => [d.id, d]));
    c.docs.forEach((d) => { const f = byId[d.id] || fresh.find((x) => x.fileId === d.fileId); if (f) Object.assign(d, { file: f.file, downloadUrl: f.downloadUrl, pageImageUrls: f.pageImageUrls, textUrl: f.textUrl, thumb: f.thumb }); });
    if (S.doc) openDoc(S.doc);
  } catch (e) { console.warn("refreshLiveUrls", e.message); }
}

/* =========================================================
   畫面 3：渲染
   ========================================================= */
function render() { ensurePlan(); renderDocs(); renderExtract(); renderIssues(); renderLaws(); renderSims(); renderDraft(); updateChips(); $$(".tab")[0].click(); const first = S.c.docs.find((d) => d.kind !== "missing" && d.include !== false); if (first) openDoc(first.id); asstReset(); }
function updateChips() {
  if ($("#addBtn")) $("#addBtn").disabled = S.status !== "承辦中";
  if (S.c?.analysisPending) {     // 尚未有判定可顯示
    $("#judgeChip").classList.remove("on");
    const sc0 = $("#statusChip"); sc0.className = "chip status on " + S.status; $("#statusText").textContent = statusLabel();
    return;
  }
  const p = currentPlan();
  $("#judgeChip").classList.add("on"); $("#judgeText").textContent = `${p.verdict.length > 12 ? p.verdict.slice(0, 12) + "…" : p.verdict}${p.art ? `（${p.art.replace("訴願法 ", "")}）` : ""}・修改 ${S.objections.length} 次`;
  const sc = $("#statusChip"); sc.className = "chip status on " + S.status; $("#statusText").textContent = statusLabel();
  $$(".tab")[1].classList.toggle("warn", Object.values(S.stances).includes("open"));
  $$(".tab")[2].classList.toggle("warn", S.c.citations.some((x) => x.status !== "ok"));
}
function recompute() { renderExtract(); renderIssues(); renderDraft(); updateChips(); persist(); }
$$(".tab").forEach((b) => b.addEventListener("click", () => { $$(".tab").forEach((x) => x.classList.toggle("on", x === b)); $$(".tabpage").forEach((p, i) => p.classList.toggle("on", i === +b.dataset.t)); $("#panel").scrollTop = 0; if (S.c) { asstSuggest(); Router.set(`/case/${S.libId || S.c.caseId || S.c.id}/${+b.dataset.t + 1}`); } }));

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
/* 後端 kind（normalize 的判定）→ 畫面文字 */
const KIND = { "pdf-text": "文字 PDF", "pdf-scan": "掃描 PDF", image: "掃描/照片", video: "影片", office: "Office", text: "純文字", unsupported: "不支援",
               text_: "文字", pdf: "PDF", missing: "—" };
S.docMode = {};
function renderDocs() {
  const c = S.c; $("#docCount").textContent = `${c.docs.length} 件`;
  const groups = SRC_ORDER.map((src) => [src, c.docs.filter((d) => (d.src || "原處分機關") === src)]).filter(([, l]) => l.length);
  const GNOTE = { "第三方": "獨立證據", "本局": "受理機關", "未知": "內容無從判定提出方" };
  $("#docList").innerHTML = groups.map(([src, list]) => `<div class="grp" data-g="${src}"><span class="tri">▾</span><span class="srct ${src}" style="margin:0">${src}</span><span>${GNOTE[src] || ""}</span><span class="n">${list.length}</span></div><div class="items">${list.map((d) => {
    const bad = d.err ? "err" : d.dup ? "dup" : d.container ? "box" : d.pending ? "pend" : d.staged ? "staged" : "";
    const meta = d.partOf ? `第 ${d.fromPage}–${d.toPage} 頁・${d.partOf.n}/${d.partOf.total}`
      : d.duration ? `${d.duration}s・影片`
      : `${d.pages || 1} 頁・${KIND[d.kind] || ""}`;
    const badge = d.err ? `<span class="tag err" style="font-size:10px">讀取失敗</span>`
      : d.pending ? `<span class="tag amber" style="font-size:10px">辨識中…</span>`
      : d.staged ? `<span class="tag amber" style="font-size:10px">待匯入</span>`
      : d.dup ? `<span class="tag neutral" style="font-size:10px">重複</span>`
      : d.container ? `<span class="tag neutral" style="font-size:10px">壓縮檔</span>`
      : `${d.imported ? `<span class="tag green" style="font-size:10px" title="補件匯入 ${d.imported}">新</span>` : ""}<span class="tag ${DOCTAG[d.tag] || "neutral"} tagbtn" data-edit="${d.id}" title="修正類型／來源" style="font-size:10px">${esc(d.tag)} ✎</span>`;
    return `<div class="item ${d.include === false ? "skip" : ""} ${bad}" data-doc="${d.id}" title="${esc(d.origName ? "原檔名：" + d.origName : d.title)}"><i></i><span class="t">${esc(d.stdName || d.title)}</span><span class="m">${meta}</span>${badge}<span class="sum">${esc(d.summary || "")}</span></div>`;
  }).join("")}</div>`).join("");
  $$("#docList .grp").forEach((g) => g.addEventListener("click", () => { g.classList.toggle("closed"); g.querySelector(".tri").textContent = g.classList.contains("closed") ? "▸" : "▾"; }));
  $$("#docList .item").forEach((b) => b.addEventListener("click", () => { if (S.doc === b.dataset.doc) closeDoc(); else openDoc(b.dataset.doc); }));
  $$("#docList .tagbtn").forEach((t) => t.addEventListener("click", (e) => { e.stopPropagation(); openTagPop(t.dataset.edit, t); }));
  $("#addBtn").disabled = S.status !== "承辦中"; $("#addDemo").style.display = c.supplement && !c.docs.some((d) => d.staged || d.pending || d.imported) && S.status === "承辦中" ? "" : "none";
}
function openTagPop(id, anchor) {
  const d = S.c.docs.find((x) => x.id === id), pop = $("#tagPop"), pane = $("#docPane").getBoundingClientRect(), r = anchor.getBoundingClientRect();
  $("#tpType").innerHTML = TYPES.map((t) => `<option ${d.tag === t ? "selected" : ""}>${t}</option>`).join(""); $("#tpSrc").innerHTML = SRC_ORDER.map((t) => `<option ${d.src === t ? "selected" : ""}>${t}</option>`).join("");
  pop.style.left = Math.max(8, Math.min(pane.width - 230, r.left - pane.left - 120)) + "px"; pop.style.top = (r.bottom - pane.top + 4) + "px"; pop.classList.add("on");
  $("#tpCancel").onclick = () => pop.classList.remove("on");
  $("#tpSave").onclick = async () => {
    const t = $("#tpType").value, sr = $("#tpSrc").value;
    if (t === d.tag && sr === d.src) return pop.classList.remove("on");
    const prev = { tag: d.tag, src: d.src, stdName: d.stdName };
    d.tag = t; d.src = sr; renderDocs(); pop.classList.remove("on");           // 樂觀更新：先動畫面
    if (d.fileId && S.c.caseId) {
      try {
        const updated = await Api.patchFile(S.c.caseId, d.fileId, { segIndex: d.segIndex ?? 0, doc_type: t, source: sr, by: "承辦人" });
        const seg = updated.segments?.[d.segIndex ?? 0];
        if (seg) { d.stdName = seg.suggestedName; d.nature = seg.nature; d.manual = seg.manual; }
        S.audit.push({ ts: now(), who: "hu", para: d.stdName || d.title, action: `修正歸戶：${prev.tag}／${prev.src} → ${t}／${sr}` });
        renderDocs();
      } catch (e) {                                                             // 失敗回滾，不留下前端與後端不一致
        Object.assign(d, prev); renderDocs();
        alert(`修正未儲存：${e.code || "ERROR"}　${e.message || ""}`);
      }
    } else {
      S.audit.push({ ts: now(), who: "hu", para: d.stdName || d.title, action: `修正歸戶：${prev.tag}／${prev.src} → ${t}／${sr}` });
    }
    if (!S.c.analysisPending) { renderExtract(); renderIssues(); renderDraft(); }
    persist(); openDoc(id);
  };
}

/* =========================================================
   F12：真檔案檢視（後端給的 rawUrl／textUrl／pageImageUrls）
   mock 的 kind 只有 text/image/pdf/video，後端是 pdf-text/pdf-scan/image/video/office/text/unsupported
   ========================================================= */
const TEXT_CACHE = new Map();

async function withFreshUrl(d, fn) {
  try { return await fn(d); }
  catch (e) {                                  // presigned 15 分鐘過期 → 重取一次
    if (!S.c?.caseId) throw e;
    const fresh = toDocs(await Api.listFiles(S.c.caseId)).find((x) => x.id === d.id);
    if (!fresh) throw e;
    Object.assign(d, { file: fresh.file, pageImageUrls: fresh.pageImageUrls });
    return fn(d);
  }
}

function openLiveDoc(d, view, tools, head) {
  const page = d.fromPage && d.fromPage > 1 ? `page=${d.fromPage}&` : "";
  const pdfFrame = () => `<div style="padding:10px 12px 0">${head}</div><iframe class="doc-pdf" src="${d.file}#${page}toolbar=0&view=FitH" title="${esc(d.title)}"></iframe>`;

  const paintText = async () => {
    view.innerHTML = `<div class="doc-body">${head}<p class="note">讀取文字中…</p></div>`;
    try {
      if (!TEXT_CACHE.has(d.fileId)) TEXT_CACHE.set(d.fileId, await Api.fileText(S.c.caseId, d.fileId));
      const t = TEXT_CACHE.get(d.fileId);
      const from = d.fromPage || 1;
      const pages = (t.textPerPage || []).slice(from - 1, d.toPage || undefined);
      const hl = S.hl && S.hl.id === d.id ? S.hl : null;      // 由 cite 跳轉帶來的反白位置
      view.innerHTML = `<div class="doc-body">${head}${pages.length
        ? pages.map((txt, i) => {
            const pno = from + i;
            let body = esc(txt || "（本頁無文字）");
            if (hl && hl.page === pno && txt) {
              body = esc(txt.slice(0, hl.start)) + `<mark class="hit" id="liveHit">${esc(txt.slice(hl.start, hl.end))}</mark>` + esc(txt.slice(hl.end));
            }
            return `<h4>第 ${pno} 頁</h4><pre style="white-space:pre-wrap;font:12.5px/1.9 var(--mono);margin:0 0 14px">${body}</pre>`;
          }).join("")
        : `<p class="note">這份文件沒有文字層（掃描件／照片），請切換「頁面影像」檢視。</p>`}</div>`;
      if (hl) { $("#liveHit")?.scrollIntoView({ block: "center", behavior: "smooth" }); S.hl = null; }
    } catch (e) {
      view.innerHTML = `<div class="doc-body">${head}<p class="note" style="color:var(--seal)">讀取文字失敗：${esc(e.code || "")} ${esc(e.message || "")}</p></div>`;
    }
  };

  const paintImages = () => {
    const urls = d.pageImageUrls?.length ? d.pageImageUrls : d.file ? [d.file] : [];
    tools.innerHTML = `<button class="ghost-btn" data-z="-">－</button><button class="ghost-btn" data-z="+">＋</button><button class="ghost-btn" data-z="0">重設</button>` + tools.innerHTML;
    view.innerHTML = `<div style="padding:10px 12px 0">${head}</div>` + urls.map((u, i) =>
      `<div class="doc-img"><div class="imgwrap"><img src="${u}" alt="${esc(d.title)} 第 ${i + 1} 張" loading="lazy"></div></div>`).join("");
    const fit = () => $$(".doc-img", view).forEach((el) => el.style.setProperty("--imgw", Math.round((view.clientWidth - 24) * S.zoom) + "px"));
    fit();
    $$("#docTools button[data-z]").forEach((b) => b.addEventListener("click", () => {
      S.zoom = b.dataset.z === "0" ? 1 : Math.min(4, Math.max(.5, S.zoom + (b.dataset.z === "+" ? .4 : -.4))); fit();
    }));
    $$(".doc-img img", view).forEach((img) => img.addEventListener("error", () => withFreshUrl(d, () => openDoc(d.id)).catch(() => {})));
  };

  const modes = [];
  if (d.kind === "pdf-text" || d.kind === "office") modes.push(["pdf", "原始 PDF"], ["text", "擷取文字"], ["img", "頁面影像"]);
  else if (d.kind === "pdf-scan") modes.push(["pdf", "原始 PDF"], ["img", "頁面影像"]);
  else if (d.kind === "image") modes.push(["img", "影像"]);
  else if (d.kind === "text") modes.push(["text", "內容"]);

  if (d.kind === "video") {
    tools.innerHTML = `<a class="ghost-btn" href="${d.file}" target="_blank" style="text-decoration:none">新分頁開啟</a>`;
    view.innerHTML = `<div class="doc-video">${head}<video id="vid" controls preload="metadata" src="${d.file}"></video>
      <p class="note" style="margin-top:8px">${d.duration ? `時長 ${d.duration} 秒；` : ""}分類時取 ${d.pageImageUrls?.length || 3} 幀判定類型。</p></div>`;
    return;
  }
  if (!modes.length) {
    view.innerHTML = `<div class="doc-missing">${head}<b>${esc(d.stdName || d.title)}</b><br>${esc(d.summary || "此格式不支援預覽")}${d.err ? `<br><span style="color:var(--seal)">${esc(d.err.code)}：${esc(d.err.message || "")}</span>` : ""}</div>`;
    return;
  }

  const paint = () => {
    const m = S.docMode[d.id] || modes[0][0];
    tools.innerHTML = modes.map(([k, label]) => `<button class="ghost-btn ${m === k ? "on" : ""}" data-m="${k}">${label}</button>`).join("")
      + (d.file ? `<a class="ghost-btn" href="${d.downloadUrl || d.file}" style="text-decoration:none">下載</a>` : "")
;
    if (m === "pdf") view.innerHTML = pdfFrame();
    else if (m === "img") paintImages();
    else paintText();
    $$("#docTools button[data-m]").forEach((b) => b.addEventListener("click", () => { S.docMode[d.id] = b.dataset.m; S.zoom = 1; paint(); }));
    // 放大鈕疊在預覽區右上角（屬於這份文件，不屬於整個瀏覽器表頭）
    view.insertAdjacentHTML("beforeend", `<button class="doc-full" title="全螢幕檢視（Esc 關閉）">⤢ 放大</button>`);
    $(".doc-full", view)?.addEventListener("click", () => openViewer(d));
  };
  paint();
}

/* 再點同一份文件 → 取消選取：清空檢視區 */
function closeDoc() {
  S.doc = null; $("#tagPop").classList.remove("on"); $$("#docList .item").forEach((b) => b.classList.remove("on")); $("#docPane").classList.add("nodoc");
  $("#curDocName").textContent = "未選取文件"; $("#docTools").innerHTML = "";
  $("#docView").innerHTML = `<div class="doc-empty" style="min-height:0;padding:10px"><span class="note">未選取文件——點選清單中的文件即可檢視；再點一次可取消選取</span></div>`;
}
/* 全螢幕檢視：把目前文件用同一組模式（PDF／文字／影像）放到置中浮層，背景暗化。 */
async function openViewer(d) {
  const vw = $("#viewer"), body = $("#vwBody"), tools = $("#vwTools");
  $("#vwName").textContent = d.stdName || d.title;
  $("#vwMeta").textContent = `${d.origName ? "原檔名 " + d.origName + "・" : ""}${d.pages || 1} 頁・${KIND[d.kind] || d.kind}`;
  const isLive = !!d.fileId;
  const modes = d.kind === "video" ? [] : isLive
    ? (d.kind === "pdf-text" || d.kind === "office" ? [["pdf", "原始 PDF"], ["text", "擷取文字"], ["img", "頁面影像"]]
       : d.kind === "pdf-scan" ? [["pdf", "原始 PDF"], ["img", "頁面影像"]]
       : d.kind === "image" ? [["img", "影像"]] : [["text", "內容"]])
    // mock 文件：kind 是 text/image/pdf/video，內容在 d.html、原檔在 d.file
    : (d.kind === "text" ? (d.file ? [["pdf", "原始 PDF"], ["text", "擷取文字"]] : [["text", "內容"]])
       : d.kind === "image" ? [["img", "影像"]] : d.kind === "pdf" ? [["pdf", "原始 PDF"]] : [["text", "內容"]]);
  let m = S.docMode[d.id] || modes[0]?.[0] || "pdf";

  const paint = async () => {
    tools.innerHTML = modes.map(([k, l]) => `<button class="${m === k ? "on" : ""}" data-vm="${k}">${l}</button>`).join("")
      + (d.file ? `<a href="${d.file}" target="_blank">下載</a>` : "");
    if (d.kind === "video") body.innerHTML = `<video controls preload="metadata" src="${d.file}"></video>`;
    else if (m === "pdf") body.innerHTML = `<iframe src="${d.file}#${d.fromPage > 1 ? `page=${d.fromPage}&` : ""}toolbar=1&view=FitH"></iframe>`;
    else if (m === "img") body.innerHTML = (d.pageImageUrls?.length ? d.pageImageUrls : [d.file]).map((u) => `<img src="${u}" loading="lazy">`).join("");
    else if (!isLive) body.innerHTML = `<div class="doc-body">${d.html || "<p class=\"note\">此文件沒有可顯示的文字內容</p>"}</div>`;
    else {
      body.innerHTML = `<div class="doc-body"><p class="note">讀取文字中…</p></div>`;
      try {
        if (!TEXT_CACHE.has(d.fileId)) TEXT_CACHE.set(d.fileId, await Api.fileText(S.c.caseId, d.fileId));
        const t = TEXT_CACHE.get(d.fileId), from = d.fromPage || 1;
        body.innerHTML = `<div class="doc-body">${(t.textPerPage || []).slice(from - 1, d.toPage || undefined)
          .map((txt, i) => `<h4>第 ${from + i} 頁</h4><pre style="white-space:pre-wrap;font:13px/1.9 var(--mono);margin:0 0 14px">${esc(txt || "（本頁無文字）")}</pre>`).join("") || "<p class=\"note\">沒有文字層</p>"}</div>`;
      } catch (e) { body.innerHTML = `<div class="doc-body"><p class="note" style="color:var(--seal)">讀取失敗：${esc(e.message || "")}</p></div>`; }
    }
    $$("#vwTools button[data-vm]").forEach((b) => b.addEventListener("click", () => { m = b.dataset.vm; S.docMode[d.id] = m; paint(); }));
  };
  await paint();
  vw.classList.add("on");
}
function closeViewer() { $("#viewer").classList.remove("on"); $("#vwBody").innerHTML = ""; }
$("#vwClose").addEventListener("click", closeViewer);
$("#viewer").addEventListener("click", (e) => { if (e.target.id === "viewer") closeViewer(); });   // 點暗處關閉
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#viewer").classList.contains("on")) closeViewer(); });

function openDoc(id, after) {
  const c = S.c, d = findDoc(id); if (!d) return;
  id = d.id;
  S.doc = id; S.zoom = 1; $("#tagPop").classList.remove("on"); $("#docPane").classList.remove("nodoc");
  $$("#docList .item").forEach((b) => { const on = b.dataset.doc === id; b.classList.toggle("on", on); if (on) { const g = b.closest(".items").previousElementSibling; if (g.classList.contains("closed")) { g.classList.remove("closed"); g.querySelector(".tri").textContent = "▾"; } b.scrollIntoView({ block: "nearest" }); } });
  $("#curDocName").textContent = d.stdName || d.title;
  const view = $("#docView"), tools = $("#docTools"); tools.innerHTML = "";
  const missing = `<div class="doc-missing">找不到卷宗包檔案：<span class="num">${esc(d.file || "")}</span><br>請自 repo 根目錄開啟 prototype/index.html。</div>`;
  const head = `<div class="doc-meta num" style="margin-bottom:8px">${d.origName ? `原檔名：${esc(d.origName)}　→　` : ""}標籤：${esc(d.stdName || d.title)}<span class="srct ${d.src}">${d.src}</span>${d.srcNote ? `<span class="note">　${esc(d.srcNote)}</span>` : ""}${d.summary ? `<br><span class="note">Claude 判定：${esc(d.summary)}</span>` : ""}</div>`;
  if (d.fileId) { openLiveDoc(d, view, tools, head); if (after) after(); return; }   // 真上傳／demo 的檔案
  if (d.include === false) { view.innerHTML = `<div class="doc-missing">${head}<b>${esc(d.stdName || d.title)}</b>　<span class="tag neutral">${d.tag}</span><br>${esc(d.note || "未納入分析。")}</div>`; }
  else if (d.kind === "text") {
    const mode = d.file ? (S.docMode[id] || "pdf") : "text";
    const paint = () => { const m = d.file ? (S.docMode[id] || "pdf") : "text"; if (d.file) tools.innerHTML = `<button class="ghost-btn ${m === "pdf" ? "on" : ""}" data-m="pdf">原始 PDF</button><button class="ghost-btn ${m === "text" ? "on" : ""}" data-m="text">擷取文字</button>`; view.innerHTML = m === "pdf" ? `<div style="padding:10px 12px 0">${head}</div><iframe class="doc-pdf" src="${d.file}#toolbar=0&view=FitH" title="${esc(d.title)}"></iframe>` : `<div class="doc-body">${head}${d.html}</div>`; if (m === "text") bindMarks(); $$("#docTools button").forEach((b) => b.addEventListener("click", () => { S.docMode[id] = b.dataset.m; paint(); })); };
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
  if (d.kind !== "missing" && (d.file || d.html)) {      // mock 路徑也要有放大鈕
    view.insertAdjacentHTML("beforeend", `<button class="doc-full" title="全螢幕檢視（Esc 關閉）">⤢ 放大</button>`);
    $(".doc-full", view)?.addEventListener("click", () => openViewer(d));
  }
  if (after) after();
}
/** 真上傳案件的錨點：開檔並用 /text 反白 {page,start,end}；掃描件無文字則開頁圖 */
/* 分析階段的 refs 用 fileId，但卷宗清單一段一列、id 是 segId（fileId#n）。
   兩種 id 都要能解析，否則 cite 跳轉會靜默失敗（找不到文件就 return）。 */
function findDoc(id) {
  if (!S.c?.docs) return null;
  return S.c.docs.find((x) => x.id === id)
      || S.c.docs.find((x) => x.fileId === id)          // fileId → 該檔第一段
      || null;
}

/* 從右側 cite 跳到卷宗：不要自己畫內容——那會覆蓋掉 openLiveDoc 的工具列，
   導致「直接點檔案」與「點 cite 跳過來」看到的東西不一致（少了 原始PDF／擷取文字／頁面影像／下載）。
   改成：記下要反白的位置 → 交給 openDoc 正常渲染 → paintText 套用反白並捲到定位。 */
async function jumpLive(docId, range, second) {
  const d = findDoc(docId); if (!d) return;
  S.hl = range ? { id: d.id, ...range } : null;
  if (range) S.docMode[d.id] = "text";           // 文字錨點才強制切到擷取文字
  openDoc(d.id);
  if (second != null) {
    const go = () => { const v = $("#vid"); if (v) { v.currentTime = second; v.pause(); } };
    setTimeout(go, 300);
  }
}

function jumpTo(ref) {
  const r = S.c.refs[ref]; if (!r) return; const [docId, kind] = r;
  if (kind === "text" || (kind === "doc" && S.c.live)) return jumpLive(docId, kind === "text" ? r[2] : null);
  if (kind === "time" && S.c.live) return jumpLive(docId, null, r[2]);
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
/* 本局審理期限（§85 I）的狀態：只給日期看不出意義，要對照今天。
   注意這與「訴願人是否逾期」是兩件事——前者看提起日 vs 屆滿日（與今天無關），
   後者看今天 vs 應決定日。歷史案件（如 demo 的 114 年案）本來就會顯示已逾審理期限。 */
function due85Status(due) {
  const left = Math.round((due - Date.now()) / DAY);
  if (left >= 0) return `<span style="color:var(--green)">距今尚餘 ${left} 日</span>`;
  return `<span style="color:var(--seal)">已逾審理期限 ${-left} 日</span>（得依 §85 I 但書延長一次，最長 2 個月）`;
}

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
  const ap = c.period.appealSays, due85 = p && p.recv !== null ? addMonths(p.recv, 3) : null;
  /* 單軸時間軸：所有節點共用一個時間尺度，§14 與 §85 兩個區間以上下括號表示。
     兩者在時間上是**重疊**的（§85 從收文起算，而 §14 到屆滿才結束），畫成上下兩條會被讀成先後接續。
     收文日是樞紐：同時是一段的終點、另一段的起點。 */
  let tl = "";
  if (p) {
    const method = c.period.servedMethod || "";
    const servedLab = method.includes("寄存") ? "寄存生效（起算基準）" : method ? `處分送達（${method}）` : "處分送達";
    const now = Date.now();
    const decided = c.final?.at ? isoT(c.final.at) : null;
    const due58 = p.recv !== null ? p.recv + 20 * DAY : null;
    const ext85 = p.recv !== null ? addMonths(p.recv, 5) : null;

    const raw = [[p.served, servedLab, ""], [p.due, "30 日屆滿", ""]];
    if (p.recv !== null) {
      raw.push([p.recv, p.over ? "收文（逾期）" : "收文（訴願提起）", "pivot"],
               [due58, "答辯期限 §58 III", ""], [due85, "應決定 §85 I", ""], [ext85, "得延長至此 §85 I 但書", "opt"]);
      if (decided) raw.push([decided, "實際決定", "pivot"]);
    } else raw.push([p.due, "收文待補", "dim"]);

    const a = raw.filter((x) => x[0] != null).sort((x, y) => x[0] - y[0]);
    const min = a[0][0], max = a[a.length - 1][0], span = Math.max(1, max - min);
    const pos = (t) => Math.max(0, Math.min(100, ((t - min) / span) * 100));
    const laid = [];
    a.forEach(([t, lab, cl], i) => {                        // 節點過近時推開，避免標籤互疊
      let x = pos(t);
      if (i > 0 && x - laid[laid.length - 1].x < 15) x = Math.min(100, laid[laid.length - 1].x + 15);
      laid.push({ t, lab, cl, x });
    });
    const xOf = (t) => { const f = laid.find((z) => z.t === t); return f ? f.x : pos(t); };

    const a14 = xOf(p.served), b14 = xOf(p.due);
    const span14 = `<div class="tl-span up ${p.over ? "bad" : ""}" style="left:${a14}%;width:${Math.max(6, b14 - a14)}%">
      <span class="cap">§14 訴願人 30 日</span>
      <span class="res">${p.recv === null ? "收文待補" : p.over ? `逾期 ${p.days} 日` : `未逾期・餘 ${p.left} 日`}</span></div>`;

    let span85 = "", over85bar = "";
    if (p.recv !== null) {
      const over85 = !decided && now > due85;
      // 括號＝法定 3 個月（收文 → 應決定），延長是「必要時得延長一次」的例外，不算在裡面
      const a85 = xOf(p.recv), b85 = xOf(decided || due85);
      span85 = `<div class="tl-span dn ${over85 ? "bad" : ""}" style="left:${a85}%;width:${Math.max(6, b85 - a85)}%">
        <span class="cap">§85 I 法定審理 3 個月</span>
        <span class="res">${decided ? `歷時 ${Math.round((decided - p.recv) / DAY)} 日`
          : over85 ? `已逾期` : `尚餘 ${Math.round((due85 - now) / DAY)} 日`}</span></div>`;
      // 逾期段：從應決定畫到軸右端（今天多半已在軸外），末端箭頭表示仍在累積
      if (over85) over85bar = `<div class="tl-over" style="left:${xOf(due85)}%;width:${Math.max(4, 100 - xOf(due85))}%">
        <span class="arrow">▶</span><span class="lb">已逾 ${Math.round((now - due85) / DAY)} 日（至今）</span></div>`;
    }
    const nowMark = now >= min && now <= max ? `<div class="tl-now" style="left:${pos(now)}%"><span>今天</span></div>` : "";

    const track = `<div class="tl-track">${span14}${span85}${over85bar}${nowMark}${laid.map((z) =>
      `<div class="tl-pt ${z.cl}" style="left:${z.x}%"><div class="up"><div class="d">${toMg(z.t)}</div></div><div class="dot"></div><div class="lab">${esc(z.lab)}</div></div>`).join("")}</div>`;

    const note1 = `起算日 <b>${toMg(p.start)}</b>（送達之次日）＋ 30 日 ＝ 屆滿日 <b>${toMg(p.due)}</b>。${
      p.recv === null ? "<b>收文日待補</b>——無法判斷 §14 是否逾期，亦無法起算 §85 審理期限。"
      : p.over ? `實際收文日 <b>${toMg(p.recv)}</b>，<span style="color:var(--seal);font-weight:600">逾法定不變期間 ${p.days} 日</span>（§77②）。`
               : `實際收文日 <b>${toMg(p.recv)}</b>，<span style="color:var(--green);font-weight:600">未逾期，於屆滿前 ${p.left} 日提起</span>。`}
      在途期間未扣除（訴願人住居所在本市・§16）。`;
    const note2 = p.recv === null ? "" : decided
      ? `<br>本局自收文 <b>${toMg(p.recv)}</b> 起，於 <b>${toMg(decided)}</b> 作成決定，歷時 ${Math.round((decided - p.recv) / DAY)} 日。`
      : `<br>本局應於 <b>${toMg(due85)}</b> 前作成決定（§85 I），${due85Status(due85)}${
          now - due85 > 180 * DAY ? `；<span class="note">卷內收文日為 ${toMg(p.recv)}，本案卷宗為歷史案例</span>` : ""}。`;

    tl = `${track}<div class="tl-note">${note1}${note2}</div>`;
  }

  $("#p0").innerHTML = `
    <div class="sec"><div class="sec-head"><h3>案件分類</h3><span class="note">分類模型輸出</span></div><div class="box2 clsgrid">${cls}</div></div>
    <div class="sec"><div class="sec-head"><h3>期間計算</h3><span class="note">同一條時間軸：<b>上方括號</b>＝訴願人提起期間（§14，30 日）、<b>下方括號</b>＝本局審理期限（§85 I，3 個月）。兩者自收文日起重疊</span></div><div class="box2"><div class="period-edit">
      <div><label>送達日（卷證）</label><div class="val">${esc(S.served || "—")}</div><div class="src">${c.period.servedRef ? SJ(c.period.servedRef, "來源：送達證書 ↗") : "來源：訴願書自述／待補"}${ap && ap !== S.served ? `<span class="warnsrc">　⚠ 訴願書自述 ${ap}（發文日），已採卷證</span>` : ""}</div></div>
      <div><label>機關收文日</label><div class="val">${esc(S.recv || "—")}</div><div class="src">${c.period.recvRef ? J(c.period.recvRef, "來源：收文戳 ↗") : "來源：待補"}</div></div>
      <div><label>30 日期間屆滿</label><div class="val">${p ? toMg(p.due) : "—"}</div><div class="src">起算 ${p ? toMg(p.start) : "—"}（送達次日）</div></div>
      <div><label>訴願人是否逾期（§14）</label><div style="font-size:15px;font-weight:600;padding:4px 0;color:${over ? "var(--seal)" : "var(--green)"}">${p ? (p.recv === null ? "待補收文日" : over ? `逾期 ${p.days} 日` : `未逾期（於屆滿前 ${p.left} 日提起）`) : "待補送達日"}</div><div class="src">在途期間未扣除</div></div>
      <div style="border-top:1px solid var(--line)"><label>本局審理期限（§85 I）</label><div class="val" style="color:var(--accent)">${due85 ? toMg(due85) : "—"}</div><div class="src">${due85 ? `${due85Status(due85)}<br>` : ""}收受訴願書起 3 個月內作成決定；必要時得延長一次，最長 2 個月</div></div>
    </div><div class="timeline">${tl}</div></div></div>
    <div class="sec"><div class="sec-head"><h3>程序審查　訴願法第 77 條各款</h3><span class="note">通過 ${n("pass")}・不適用 ${n("na")}・待核 ${n("warn")}・未通過 ${n("fail")}</span></div>
      <div class="box2"><div class="cklist">${checklist}</div><div class="verdict ${verdict.kind}"><span class="big">${verdict.big}</span><p>${verdict.text}</p></div></div></div>
    <div class="sec"><div class="sec-head"><h3>三方對照</h3><span class="note">訴願人主張 ／ 機關答辯 ／ 卷證事實（標示來源，第三方證據優先）　點任一格跳至卷宗</span></div><div class="box2"><table class="cmp"><tr><th>欄位</th><th>訴願人主張（訴願人來源）</th><th>機關答辯（原處分機關來源）</th><th>卷證事實（第三方優先）</th></tr>${rows}</table></div></div>
    <p class="foot-note">程序審查為 AI 依卷面自動核對之結果，唯讀；任何一款未通過即應為不受理，毋庸進入實體。三方對照三欄之資料分別限於對應來源之文件，「卷證事實」欄優先採第三方證據；紅底列為主張與卷證不一致處，系統不自動裁決。不服請於草稿頁提出修正意見。</p>`;
}

/* ---------- Tab 2 ---------- */
function renderIssues() {
  const c = S.c, stN = { agency: "採機關", appellant: "採訴願人", open: "待議" };
  const verdictOf = (pid) => { const p = c.plans.find((x) => x.id === pid); return p ? p.verdict : "—"; };
  $("#p1").innerHTML = `<div class="sec"><div class="sec-head"><h3>雙方癥結點</h3><span class="note">訴願人主張 ／ 機關答辯 ／ 卷證顯示 ／ AI 認定與依據　不同意可在右下角問答助手說明要修改之處</span></div>
    ${c.issues.map((it, i) => { const ai = it.stance || "open"; const cur = S.stances[it.id] || ai; const obj = S.objections.find((o) => o.issueId === it.id && o.result !== "reject"); return `
      <div class="issue" id="iss-${it.id}"><div class="issue-head"><span class="n">爭點 ${i + 1}</span><h3>${esc(it.title)}</h3>
        ${obj ? `<span class="ailab obj v-${cur}">修正後：${stN[cur]}</span><span class="note">原 AI 認定：${stN[ai]}</span>` : `<span class="ailab v-${ai}">AI 認定：${stN[ai]}</span>`}
</div>
        <div class="issue-grid"><div class="col-a"><div class="lab a">訴願人主張</div>${J(it.a[1], esc(it.a[0]))}</div><div class="col-d"><div class="lab d">機關答辯</div>${J(it.d[1], esc(it.d[0]))}</div><div class="col-e"><div class="lab e">卷證顯示</div><div class="ev">${it.e.map((e) => e[1] ? `<span class="tag accent jump" data-jump="${e[1]}">${esc(e[0])}<span class="srct ${srcOf(e[1])}">${srcOf(e[1])}</span></span>` : `<span class="tag neutral">${esc(e[0])}</span>`).join("")}</div></div></div>
        <div class="basis"><b>依據</b>${esc(it.ai || "")}</div>
        <div class="issue-foot"><span class="lab" style="font-size:10.5px;color:var(--ink-3)">法律素材</span>${it.law.map((l) => `<span>${esc(l)}</span>`).join("")}</div>
        <div class="lead"><span class="ai v-${obj && obj.plan ? cur : ai}">→ 結論：${esc(verdictOf(obj && obj.plan ? obj.plan : c.judge))}</span><span class="note">採機關 → ${esc(verdictOf(it.lead.agency[0]))}　採訴願人 → ${esc(verdictOf(it.lead.appellant[0]))}</span></div></div>`; }).join("")}</div>
    <p class="foot-note">爭點由三方對照之衝突列與答辯書逐點回應段落配對產生；AI 認定僅附一句依據，不附信心度。承辦人的修正透過右下角問答助手提出：AI 先提案、承辦人確認後才重新產生，並逐項回覆採納／部分採納／無法採納。</p>`;
}

/* ---------- 三時點比對（零 AI） ---------- */
function versionCheck(libName) {
  const c = S.c, L = LAWLIB.find((x) => x.n === libName); if (!L || !c.dates) return null;
  const amend = isoT(L.effective || L.date), act = isoT(c.dates.act), dec = isoT(c.dates.decide);
  if (amend && act && amend > act) return { warn: true, text: `修正 ${L.date}${L.effective ? "（" + L.effective + " 施行）" : ""} 落在行為時 ${c.dates.act} 之後 → 須依行政罰法 §5 為新舊法比較` };
  return { warn: false, text: `最新修正 ${L.date}，早於行為時 ${c.dates.act} → 三時點版本一致` };
}
function pendingCites() { return (S.c.citations || []).filter((x) => x.status === "pending"); }

/* ---------- Tab 3／4 ---------- */
function renderLaws() {
  const c = S.c, STN = { ok: "已驗證", amended: "該條已修正", missing: "查無此條", repealed: "已廢止", gap: "漏引", pending: "未收錄" };
  const d = c.dates || {}; const tp = `<div class="tp"><div><span class="k">行為時</span><div class="v">${esc(d.act || "—")}</div></div><div><span class="k">裁處時</span><div class="v">${esc(d.disp || "—")}</div></div><div><span class="k">決定時（預定）</span><div class="v">${esc(d.decide || "—")}</div></div><div><span class="k">比對規則</span><div class="note">法規修正日落在行為時之後 → 行政罰法 §5 從新從輕比較</div></div></div>`;
  const anyWarn = c.laws.some((l) => { const v = versionCheck(l.lib); return v && v.warn; });
  const alert = c.alert || (anyWarn ? { title: "法規時效性警示（由三時點比對產生）", text: c.laws.filter((l) => versionCheck(l.lib)?.warn).map((l) => `<b>${esc(l.n)}</b>：${esc(versionCheck(l.lib).text)}`).join("<br>") } : null);
  const cites = c.citations.length ? `<table class="cite-check"><tr><th>引用</th><th>出現位置</th><th>狀態</th><th>說明</th></tr>${c.citations.map((x) => `<tr class="${x.status}"><td>${J(x.ref, esc(x.n))}</td><td>${esc(x.where)}</td><td><span class="st ${x.status}">${STN[x.status]}</span></td><td class="note" style="font-size:12px">${esc(x.note)}</td></tr>`).join("")}</table>` : `<div class="doc-missing" style="padding:14px">${esc(c.citationNote || "無引用可查核")}</div>`;
  const groups = {}; c.laws.forEach((l) => { (groups[l.g] = groups[l.g] || []).push(l); });
  const pend = pendingCites().length;
  $("#p2").innerHTML = `<div class="sec"><div class="sec-head"><h3>本案三時點</h3><span class="note">法規時效性依此比對</span></div>${tp}</div>
    <div class="sec"><div class="sec-head"><h3>答辯書引用法條查核</h3><span class="note">逐條比對法規庫（法規全文＋修正狀態）${pend ? `　・<span style="color:var(--seal)">${pend} 則未收錄</span>` : ""}</span></div><div class="box2">${cites}</div></div>
    ${alert ? `<div class="sec"><div class="sec-head"><h3>${alert.title}</h3><span class="note">影響決定書合法性，請優先處理</span></div><div class="alert"><span class="mk">！</span><p>${alert.text}</p></div></div>` : ""}
    ${Object.entries(groups).map(([g, list]) => `<div class="sec"><div class="sec-head"><h3>${g}</h3><span class="note">${list.length} 筆</span></div><div class="box2">${list.map((l) => { const v = versionCheck(l.lib); return `<div class="law"><div class="ttl"><span class="n">${esc(l.n)}</span></div><div class="rel">關聯 ${l.rel}%</div><div class="txt">${esc(l.t)}</div><div class="badges">${l.badges.join("")}</div>${v ? `<div class="ver ${v.warn ? "warn" : "ok"}">${v.warn ? "⚠ " : "✓ "}${esc(v.text)}</div>` : `<div class="ver note">版本：資料集未收錄此法規，無法比對</div>`}</div>`; }).join("")}</div></div>`).join("")}
    <p class="foot-note">「未收錄」表示決定書慣常援引但法規庫尚未收錄之函釋或裁量基準（如環保署函、裁罰準則）；函釋無統一 API，須由承辦人確認後人工入庫。</p>`;
}
function oldLaw(fn) { const y = parseInt(fn, 10); const L = LAWLIB.find((x) => fn.includes(x.n.replace("污", "汙")) || fn.includes(x.n)); if (!L) return null; const ay = parseInt(L.date, 10); if (!y || !ay) return null; if (y < ay) return `${L.n} ${L.date} 修正前`; if (y === ay) return `${L.n} 修法同年，援引前請確認該案決定日`; return null; }
/* 決定書 PDF 位置：真案 sims[].path 是伺服器絕對路徑 → /dataset/…（Node 對外）；mock 走 data.js 對照表（本機 ../資料集） */
function simUrl(s) {
  if (s.path) { const i = s.path.indexOf("命題方提供/"); if (i >= 0) return `${Api.base.replace(/\/api$/, "")}/dataset/${s.path.slice(i + "命題方提供/".length).split("/").map(encodeURIComponent).join("/")}`; }
  const f = histFile(s.fn) || histFile(s.fn.replace(/^\d+\./, "")); return f ? (S.c.live ? `${Api.base.replace(/\/api$/, "")}/dataset/${f.replace(/^\.\.\/資料集\/命題方提供\//, "").split("/").map(encodeURIComponent).join("/")}` : f) : null;
}
function renderSims() {
  const c = S.c, total = c.simDist.reduce((a, b) => a + b[1], 0), closed = LIB.filter((r) => r.status === "已結案").length;
  $("#p3").innerHTML = `<div class="sec"><div class="sec-head"><h3>Top ${c.sims.length} 相似歷史決定書</h3><span class="note">來源：資料集 101 件・本局案件庫已結案 ${closed} 件　點列展開決定書全文</span></div><div class="box2">${c.sims.map((s, i) => { const f = simUrl(s); return `<div class="sim ${f ? "exp" : ""}" data-i="${i}"><div class="sim-top"><span class="rank">${i + 1}</span><span class="fn">${esc(s.fn)}<span class="arrow">${f ? "▸ 展開" : ""}</span></span><span class="tag neutral" style="font-size:10px">資料集</span><span class="score">${s.s}%</span></div><div class="simbar"><i style="width:${s.s}%"></i></div><p class="why">${esc(s.why)}</p><div class="chips">${s.chips.map((x) => `<span class="tag ${x === "須注意" || x === "反面案例" ? "seal" : "neutral"}">${esc(x)}</span>`).join("")}${oldLaw(s.fn) ? `<span class="tag amber">舊法時期：${esc(oldLaw(s.fn))}</span>` : ""}</div>${s.borrow ? `<div class="borrow"><b>可借用</b>　該案${esc(s.borrow.from)} → 本案${esc(paraLabel(S.paras.find((q) => q.id === s.borrow.to)) || s.borrow.to)}：${esc(s.borrow.what)}</div>` : ""}${f ? `<div class="body"><div style="display:flex;gap:8px;align-items:center;margin-bottom:8px"><span class="note num">${esc(decodeURIComponent(f.split("/").pop()))}</span><a class="ghost-btn" href="${f}" target="_blank" style="text-decoration:none;margin-left:auto">新分頁開啟</a></div><iframe data-src="${f}#toolbar=0&view=FitH" title="${esc(s.fn)}"></iframe></div>` : ""}</div>`; }).join("")}${closed ? LIB.filter((r) => r.status === "已結案" && r.libId !== S.libId).slice(0, 2).map((r) => `<div class="sim"><div class="sim-top"><span class="rank">庫</span><span class="fn">${esc(r.no)}　${esc(r.name)}</span><span class="tag accent" style="font-size:10px">本局案件庫</span><span class="score">—</span></div><p class="why">已結案案件：結論「${esc(r.verdict)}」，${r.court ? "法院結果：" + esc(r.court.res) : "尚無法院結果"}。</p></div>`).join("") : ""}</div></div>
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
  const acts = S.status === "承辦中" ? `<button class="btn" id="submitBtn">送委員會審議</button>` : S.status === "已送審" ? `<button class="btn" id="closeBtn">登錄委員會結論並結案</button>` : `<button class="ghost-btn" id="courtBtn">登錄法院結果</button><button class="ghost-btn" id="forkBtn">另存為新草稿</button>`;
  const life = ["承辦中", "已送審", "已結案"], li = life.indexOf(S.status);
  const last = S.objections[S.objections.length - 1];
  const DN = { accept: "採納", partial: "部分採納", reject: "無法採納" }, cls = (r) => r === "accept" ? "a" : r === "partial" ? "p" : "r";
  const reply = last ? (last.items ? `<div class="reply"><div class="q">修改提案 ${S.objections.length}（${last.items.length} 項）　${last.ts}　重新產生 ${(last.scope || []).length} 步：${(last.scope || []).map((i) => RV_STEPS[i]).join("、") || "—"}</div><ul class="items">${last.items.map((it) => `<li><span class="q">${esc(it.label)}</span><br>AI：<b class="${cls(it.result)}">${DN[it.result]}</b>　${esc(it.reply)}${it.evidence.length ? `<span class="note">　重新檢視：${it.evidence.map((r) => J(r, refTitle(r) + " ↗")).join("、")}</span>` : ""}</li>`).join("")}</ul></div>` : `<div class="reply"><div class="q">修改提案 ${S.objections.length}（${esc(last.issue)}）　${last.ts}　承辦人：${esc(last.text)}</div>AI：<b class="${cls(last.result)}">${DN[last.result]}</b>　${esc(last.reply)}${last.evidence.length ? `<span class="note">　重新檢視：${last.evidence.map((r) => J(r, refTitle(r) + " ↗")).join("、")}</span>` : ""}</div>`) : "";
  const body = S.paras.map((q) => { if (q.kind === "h4") return `<h4>${q.text}</h4>`; if (q.kind === "meta") return `<div class="meta">${fillDates(q.text)}</div>`; const bfrom = (S.c.sims || []).filter((s) => s.borrow && s.borrow.to === q.id && !/反面/.test(s.borrow.what)); const tools = `<span class="tools" contenteditable="false">${bfrom.map((s) => `<span title="${esc(s.borrow.what)}">借自 ${esc(s.fn.slice(0, 4))}案${esc(s.borrow.from)}</span>`).join("")}${(q.refs || []).map((r) => `<span class="jump" data-jump="${r}">↗ ${esc(refTitle(r))}</span>`).join("")}${q.cite ? `<span title="${esc(q.cite)}">來源</span>` : ""}${ro ? "" : "<span>點擊編輯</span>"}</span>`; return `<p class="para" data-pid="${q.id}" data-src="${q.src}" contenteditable="${ro ? "false" : "true"}" spellcheck="false">${fillDates(q.text)}${tools}</p>`; }).join("");
  $("#p4").innerHTML = `
    <div class="jbar"><span class="jv">AI 判定：${esc(jp.verdict)}</span><span class="jart">${esc(jp.art)}</span>${S.plan && S.plan !== jp.id ? tag("amber", `修正後改為：${esc(cp.verdict)}`) : ""}<span class="jrisk">撤銷風險：${RISK[cp.risk[0]]}　修改 ${S.objections.length} 次</span>
      <div class="acts">${acts}<div class="more"><button class="ghost-btn" id="moreBtn">⋯</button><div class="menu" id="moreMenu"><button id="exportOdf">匯出 ODF 公文格式</button><button id="copyAll">複製全文</button><button id="exportCmp">匯出比較表</button></div></div></div></div>
    <div class="lifeline">${life.map((s, i) => `<span class="${i < li ? "done" : i === li ? "on" : ""}">${s}</span>${i < 2 ? "→" : ""}`).join("")}${S.court ? `→<span class="on">法院：${esc(S.court.res)}</span>` : ""}${S.final ? `<span class="fin note">最終決定：${esc(S.final.verdict)}　${esc(S.final.date)}　${J("doc-final", "開啟 ↗")}</span>` : `<span class="fin note">${esc(cp.risk[1])}</span>`}</div>
    ${reply}
    <div class="paper ${ro ? "ro" : ""}" id="draftBody"><div class="pt">${esc(d.head)}</div><div class="ps">${esc(d.sub)}${ro ? "　・唯讀" : ""}</div>${body}<div class="tail">（訴願審議委員會委員名單、教示條款及發文日期由公文系統自動帶入）</div></div>
    <p class="foot-note" style="max-width:820px;margin:16px auto 0">草稿僅供承辦人參考，一切法律見解與事實認定仍以承辦人及訴願審議委員會之判斷為準。黃底標示處必須由承辦人補實後始得送審。</p>`;
  $("#moreBtn").addEventListener("click", (e) => { e.stopPropagation(); $("#moreMenu").classList.toggle("on"); }); document.addEventListener("click", (e) => { if (!e.target.closest("#moreBtn")) $("#moreMenu")?.classList.remove("on"); });
  $$("#moreMenu button").forEach((b) => b.addEventListener("click", () => $("#moreMenu").classList.remove("on")));
  if (!ro) $$("#draftBody .para").forEach((el) => { el.addEventListener("input", () => { const q = S.paras.find((x) => x.id === el.dataset.pid); const clone = el.cloneNode(true); clone.querySelector(".tools")?.remove(); q.text = clone.innerHTML; q.src = "human"; el.dataset.src = "human"; el.dirty = true; }); el.addEventListener("blur", () => { if (!el.dirty) return; el.dirty = false; const q = S.paras.find((x) => x.id === el.dataset.pid); S.audit.push({ ts: now(), who: "hu", para: paraLabel(q), action: "人工直接編輯" }); S.versions.push({ ts: now(), label: `人工編輯 ${paraLabel(q)}`, by: "承辦人", snap: S.paras.map((x) => ({ ...x })) }); persist(); }); });
  $("#copyAll").addEventListener("click", async () => { const clone = $("#draftBody").cloneNode(true); $$(".tools", clone).forEach((t) => t.remove()); const ok = await copyText(clone.innerText); toast(ok ? `已複製全文（${clone.innerText.length} 字）至剪貼簿` : "複製失敗：瀏覽器不允許存取剪貼簿", ok ? "ok" : "err"); });
  $("#exportOdf").addEventListener("click", () => { try { const d = draftFor(S.plan), cp = currentPlan(); const paras = S.paras.map((q) => ({ kind: q.kind === "meta" ? "p" : q.kind, text: q.kind === "meta" ? fillDates(q.text) : q.text })); const name = `訴願決定書草稿_${S.c.no}_${today()}.odt`; ODF.download(ODF.makeOdt({ head: d.head, sub: `案號 ${S.c.no}　${cp.verdict}　（草稿・待承辦人審核）`, paras, meta: { caseNo: S.c.no, exportedAt: today() } }), name); toast(`已輸出 ODF：${name}（LibreOffice／Word 可開；委員名單與教示條款由公文系統帶入）`, "ok", 5000); } catch (e) { toast(`ODF 輸出失敗：${e.message}`, "err"); } });
  $("#exportCmp").addEventListener("click", () => { const w = exportCompare(); toast(w ? "比較表已在新分頁開啟並送列印" : "瀏覽器封鎖了新視窗，請允許彈出視窗後再試", w ? "ok" : "err"); });
  $("#submitBtn")?.addEventListener("click", () => { if (!confirm("定稿並送訴願審議委員會審議？送審後草稿將唯讀。")) return; S.status = "已送審"; pushVersion("定稿送審", "承辦人"); S.audit.push({ ts: now(), who: "hu", para: "案件", action: "送委員會審議" }); recompute(); renderIssues(); $$(".tab")[4].click(); });
  $("#closeBtn")?.addEventListener("click", openClose);
  $("#courtBtn")?.addEventListener("click", () => $("#courtModal").classList.add("on"));
  $("#forkBtn")?.addEventListener("click", () => { const c2 = structuredClone(S.c); c2.docs = c2.docs.filter((x) => x.id !== "final"); delete c2.refs["doc-final"]; const src = S.libId, paras = S.paras.map((x) => ({ ...x, src: "ai" })); Object.assign(S, { libId: `${c2.id}-${Date.now().toString(36)}`, status: "承辦中", paras, versions: [], audit: [], objections: [], final: null, court: null, finalDiff: null }); pushVersion(`自已結案案件 ${src} 另存為新草稿`, "承辦人"); runCase(c2, true); Object.assign(S, { status: "承辦中", final: null, court: null, finalDiff: null }); renderDraft(); updateChips(); persist(); renderLibCard(); });
}
function diffParas(oldP, newP) { const out = []; oldP.forEach((q) => { if (q.kind === "h4") return; const cur = newP.find((x) => x.id === q.id); if (!cur) out.push({ label: paraLabel(q), html: `<del>${esc(plain(q.text))}</del>` }); else if (plain(cur.text) !== plain(q.text)) out.push({ label: paraLabel(q), html: diffHtml(plain(q.text), plain(cur.text)) }); }); newP.forEach((q) => { if (q.kind !== "h4" && !oldP.some((x) => x.id === q.id)) out.push({ label: paraLabel(q), html: `<ins>${esc(plain(q.text))}</ins>` }); }); return out; }

/* ---------- 修正意見：v9 起改由問答助手以「提案 → 確認卡 → 局部重跑」處理；S.objections 結構保留供紀錄顯示 ---------- */
const RV_STEPS = ["案件擷取與分類", "訴願期間與程序審查", "爭點", "法規推薦", "相似案例", "決定書草稿"];
/* ---------- 真上傳案件：助手提案「確認執行」→ POST objection（逐爭點）→ 輪詢 → 更新爭點／草稿版本 ---------- */
/* 伺服器提案：POST confirm → 輪詢 job 事件（逐項進度寫在卡片）→ 重抓 analysis → 只重繪受影響分頁 */
async function applyServerProposal(p) {
  const c = S.c, D = { "採納": "accept", "部分採納": "partial", "無法採納": "reject" }, card = p.el, head = card ? card.querySelector(".pc-head span") : null, strip = card ? card.querySelector(".mini-steps") : null;
  const tabs = (p.server.affected_tabs && p.server.affected_tabs.length ? p.server.affected_tabs : [1, 4]).filter((t) => t >= 0 && t <= 4);
  tabs.forEach((t) => { $$(".tab")[t].classList.add("busy"); $("#p" + t).classList.add("busy"); });
  const before = S.paras.map((x) => ({ ...x }));
  try {
    const r = await Api.confirmProposal(c.caseId, p.id);
    if (head) head.textContent = "已送出，等待 AI 重新引證…";
    (p.scope || []).forEach((i) => { const sp = strip?.children[i]; if (sp) { sp.classList.add("run"); sp.textContent = `${i + 1} ${RV_STEPS[i]}…`; } });
    const STEP_IDX = { s2: [0, 1], s3: [2], s4: [3], s5: [4], s6: [5] }, lit = new Set();
    const done = await Api.waitProposal(c.caseId, p.id, (pd) => {
      const pg = pd.progress; if (!pg || !head) return;
      if (pg.phase === "objection") head.textContent = `AI 重新引證中 ${pg.i}/${pg.n}：${pg.label || ""}`;
      else if (pg.phase === "rerun") { head.textContent = `重新產生中：${RV_STEPS[STEP_IDX[pg.step]?.[0] ?? 5]}（從第 ${STEP_IDX[pg.step]?.[0] + 1} 步起，上游維持）`; (pg.steps || []).forEach((s) => { const cur = STEP_IDX[s] || []; cur.forEach((i) => { const sp = strip?.children[i]; if (!sp) return; if (s === pg.step) { sp.classList.add("run"); sp.classList.remove("ok"); sp.textContent = `${i + 1} ${RV_STEPS[i]}…`; } else if ((pg.steps || []).indexOf(s) < (pg.steps || []).indexOf(pg.step)) { sp.classList.remove("run"); sp.classList.add("ok"); sp.textContent = `✓ ${RV_STEPS[i]}`; lit.add(i); } }); }); }
    });
    const doc = await Api.analysis(c.caseId); c.analysis = doc;
    const replies = (done.replies || []).map((x) => ({ label: x.label, result: D[x.result] || "reject", reply: x.reply, evidence: (x.evidence || []).map((q) => q.file ? `${q.file}「${(q.quote || "").slice(0, 30)}」` : String(q)), revised: x.revised_finding, issueId: x.issueId }));
    replies.forEach((x) => { S.audit.push({ ts: now(), who: "hu", para: x.label.split("：")[0], action: `修改提案：${x.label}` }, { ts: now(), who: "ai", para: x.label.split("：")[0], action: `${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[x.result]}：${(x.reply || "").slice(0, 40)}…` }); if (x.revised && x.issueId) S.stances[x.issueId] = x.revised === "採機關" ? "agency" : x.revised === "採訴願人" ? "appellant" : "open"; });
    const nc = toCase(c.caseId, c.docs, doc); Object.assign(c, { issues: nc.issues, drafts: nc.drafts, refs: nc.refs, plans: nc.plans });
    const vers = Object.keys(doc.output.drafts || {}), latest = done.version || vers[vers.length - 1]; let diff = null;
    if (done.version) { S.paras = nc.drafts.A.paras.map((x) => ({ ...x, tpl: x.text, src: "ai-edit", refs: x.refs ? x.refs.slice() : [] })); diff = diffParas(before, S.paras); pushVersion(`修改提案後重產（${latest}・重跑 ${(done.rerun || []).length} 步）`, "AI"); }
    (done.rerun || []).forEach((s) => (STEP_IDX[s] || []).forEach((i) => { const sp = strip?.children[i]; if (sp) { sp.classList.remove("run"); sp.classList.add("ok"); sp.textContent = `✓ ${RV_STEPS[i]}`; } }));
    (p.scope || []).filter((i) => !(done.rerun || []).some((s) => (STEP_IDX[s] || []).includes(i))).forEach((i) => { const sp = strip?.children[i]; if (sp) { sp.classList.remove("run", "ok", "re"); sp.textContent = `${i + 1} ${RV_STEPS[i]}（維持）`; } });
    const worst = replies.every((x) => x.result === "accept") ? "accept" : replies.some((x) => x.result !== "reject") ? "partial" : "reject";
    S.objections.push({ ts: now(), issue: `${p.items.length} 項`, issueId: replies[0]?.issueId || "multi", text: p.q, ev: [], result: worst, reply: replies.map((x) => `${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[x.result]}：${x.reply}`).join(" "), evidence: [], plan: null, items: replies.map((x) => ({ label: x.label, result: x.result, reply: x.reply, evidence: [] })), scope: p.scope, diff, proposalId: p.id });
    renderTabs(tabs); if (done.rerun?.includes("s3") || done.rerun?.includes("s2")) renderExtract(); updateChips(); persist(); asstOpen();
    const anyAcc = replies.some((x) => x.result !== "reject");
    const rerunTxt = (done.rerun || []).length ? `重新產生 ${[...new Set((done.rerun || []).flatMap((s) => STEP_IDX[s] || []))].map((i) => RV_STEPS[i]).join("、")}；其餘維持` : "未重跑任何步驟";
    if (head) head.textContent = `已執行・${replies.length} 項${anyAcc ? "，" + rerunTxt : "，維持原認定"}`;
    CHAT_HIST.push({ role: "assistant", text: `（上述提案已執行：${replies.map((x) => `${x.label.split("：")[0]} ${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[x.result]}`).join("；")}。此提案已處理完畢，後續指示請視為新的修改。）` }); histSave();
    const el = asstAdd("a card rc", `<div class="pc-head"><b>已執行</b><span>${anyAcc ? rerunTxt : "AI 維持原認定，理由如下"}</span></div><div class="pc-body"><div>${replies.map((x) => `<div class="rc-item"><span class="note">${esc(x.label)}</span><br>AI：<b class="${x.result === "accept" ? "a" : x.result === "partial" ? "p" : "r"}">${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[x.result]}</b>　${esc(x.reply || "").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\n+/g, "<br>")}${x.evidence.length ? `<span class="note">　依據：${x.evidence.map(esc).join("、")}</span>` : ""}</div>`).join("")}</div></div><div class="pc-foot"><span class="note">${diff ? `草稿新版本 ${latest}，原版本可於版本紀錄回復` : "草稿未變動"}</span><button class="ghost-btn" data-tab="4">看草稿 ↗</button></div>`);
    el.querySelector("[data-tab]").addEventListener("click", () => $$(".tab")[4].click());
    tabs.forEach((t) => { const pg = $("#p" + t); pg.classList.add("flash"); setTimeout(() => pg.classList.remove("flash"), 1600); });
  } catch (e) { if (head) head.textContent = `執行失敗：${e.code || ""} ${e.message || ""}`; asstSay(`執行失敗：${e.message || e.code}`); }
  finally { tabs.forEach((t) => { $$(".tab")[t].classList.remove("busy"); $("#p" + t).classList.remove("busy"); }); }
}
async function applyLiveProposal(p) {
  if (p.server) return applyServerProposal(p);
  const c = S.c, D = { "採納": "accept", "部分採納": "partial", "無法採納": "reject" }, card = p.el, head = card ? card.querySelector(".pc-head span") : null;
  const issueItems = p.items.filter((it) => it.type === "issue" && it.id), others = p.items.filter((it) => !(it.type === "issue" && it.id));
  const reqs = issueItems.map((it) => ({ issueId: it.id, reason: `${{ appellant: "認定應改為採訴願人", agency: "認定應改為採機關", drop: "此爭點應刪除" }[it.to] || ""}${it.why ? "：" + it.why : ""}` }));
  if (others.length) reqs.push({ issueId: c.issues[0]?.id || "I1", reason: others.map((it) => it.label).join("；") });
  if (!reqs.length) return;
  const tabs = [1, 4]; tabs.forEach((t) => { $$(".tab")[t].classList.add("busy"); $("#p" + t).classList.add("busy"); });
  const before = S.paras.map((x) => ({ ...x })), replies = [];
  try {
    for (let i = 0; i < reqs.length; i++) {
      if (head) head.textContent = `AI 重新引證中 ${i + 1}/${reqs.length}：${c.issues.find((x) => x.id === reqs[i].issueId)?.title || ""}`;
      await Api.objection(c.caseId, { ...reqs[i], by: "承辦人" });
      const n0 = (c.analysis.objections || []).length;
      const doc = await new Promise((res, rej) => Api.pollAnalysis(c.caseId, (d, e) => { if (e) return rej(e); if ((d.objections || []).length > n0) res(d); }, { interval: 2500 }));
      c.analysis = doc; const ob = doc.objections[doc.objections.length - 1];
      replies.push({ label: ob.issueTitle, result: D[ob.result] || "reject", reply: ob.reply, evidence: (ob.evidence || []).map((q) => `${q.file}「${q.quote.slice(0, 30)}」`) });
      S.audit.push({ ts: now(), who: "hu", para: ob.issueTitle, action: `修改提案：${ob.reason}` }, { ts: now(), who: "ai", para: ob.issueTitle, action: `${ob.result}：${ob.reply.slice(0, 40)}…` });
      if (ob.revised_finding) S.stances[ob.issueId] = ob.revised_finding === "採機關" ? "agency" : ob.revised_finding === "採訴願人" ? "appellant" : "open";
    }
    const nc = toCase(c.caseId, c.docs, c.analysis); Object.assign(c, { issues: nc.issues, drafts: nc.drafts, refs: nc.refs, plans: nc.plans });
    const vers = Object.keys(c.analysis.output.drafts || {}), latest = vers[vers.length - 1]; let diff = null;
    if (latest && latest !== "A") { const nd = toCase(c.caseId, c.docs, { output: { ...c.analysis.output, drafts: { A: c.analysis.output.drafts[latest] } } }); c.drafts.A = nd.drafts.A; S.paras = nd.drafts.A.paras.map((x) => ({ ...x, tpl: x.text, src: "ai-edit", refs: x.refs || [] })); diff = diffParas(before, S.paras); pushVersion(`修改提案後重產（${latest}）`, "AI"); }
    const worst = replies.every((r) => r.result === "accept") ? "accept" : replies.some((r) => r.result !== "reject") ? "partial" : "reject";
    S.objections.push({ ts: now(), issue: `${reqs.length} 項`, issueId: reqs[0].issueId, text: p.q, ev: [], result: worst, reply: replies.map((r) => `${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[r.result]}：${r.reply}`).join(" "), evidence: [...new Set(replies.flatMap((r) => r.evidence))], plan: null, items: replies, scope: [2, 5], diff });
    renderTabs(tabs); updateChips(); persist(); asstOpen();
    if (head) head.textContent = `已執行・AI 重新引證 ${reqs.length} 項${diff ? "，草稿已重產" : "，結論不變"}`;
    const el = asstAdd("a card rc", `<div class="pc-head"><b>已執行</b><span>${diff ? "爭點認定與草稿已更新" : "AI 維持原認定，理由如下"}</span></div><div class="pc-body"><div>${replies.map((r) => `<div class="rc-item"><span class="note">${esc(r.label)}</span><br>AI：<b class="${r.result === "accept" ? "a" : r.result === "partial" ? "p" : "r"}">${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[r.result]}</b>　${esc(r.reply)}${r.evidence.length ? `<div class="note">依據：${r.evidence.map(esc).join("；")}</div>` : ""}</div>`).join("")}</div><button class="ghost-btn" data-tab="4">看草稿</button></div>`);
    el.querySelector("[data-tab]").addEventListener("click", () => $$(".tab")[4].click());
  } catch (e) { if (head) head.textContent = `重新引證失敗：${e.code || ""} ${e.message || ""}`; asstSay(`重新引證失敗：${e.message || e.code}`); }
  finally { tabs.forEach((t) => { $$(".tab")[t].classList.remove("busy"); $("#p" + t).classList.remove("busy"); }); }
}
function exportCompare() {
  const c = S.c, jp = judgePlan(), cp = currentPlan(), stN = { appellant: "採訴願人", agency: "採機關", open: "待議" };
  const cols = S.plan !== jp.id ? [["原判定", jp], ["修正後", cp]] : [["AI 判定", jp]];
  const w = window.open("", "_blank"); if (!w) return null;
  w.document.write(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>方案比較表 ${c.no}</title><style>body{font-family:"BiauKaiTC","PingFang TC",serif;padding:28px;color:#111;font-size:13px}h1{font-size:18px;letter-spacing:.2em;text-align:center}table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border:1px solid #333;padding:6px 8px;vertical-align:top;text-align:left}th{background:#eee}ul{margin:0;padding-left:16px}.note{font-size:11px;color:#555;margin-top:14px}</style></head><body><h1>訴願案件審查結論比較表</h1><p>案號 ${esc(c.no)}　${esc(c.name)}　製表 ${new Date().toLocaleString("zh-TW")}</p>
    <h3>一、爭點表態</h3><table><tr><th>爭點</th><th>AI 判定</th><th>承辦人表態</th></tr>${c.issues.map((it, i) => `<tr><td>${i + 1}. ${esc(it.title)}</td><td>${stN[it.stance || "open"]}</td><td>${stN[S.stances[it.id]]}</td></tr>`).join("")}</table>
    <h3>二、結論比較</h3><table><tr><th></th>${cols.map(([n]) => `<th>${n}</th>`).join("")}</tr><tr><td>主文</td>${cols.map(([, p]) => `<td>${esc(p.verdict)}</td>`).join("")}</tr><tr><td>法條依據</td>${cols.map(([, p]) => `<td><ul>${p.basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></td>`).join("")}</tr><tr><td>事實認定</td>${cols.map(([, p]) => `<td><ul>${p.facts.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></td>`).join("")}</tr><tr><td>撤銷風險</td>${cols.map(([, p]) => `<td>${{ low: "低", mid: "中", high: "高" }[p.risk[0]]}　${esc(p.risk[1])}</td>`).join("")}</tr></table>
    ${S.objections.length ? `<h3>三、修改提案紀錄</h3><table><tr><th>項目</th><th>承辦人意見</th><th>AI 回覆</th></tr>${S.objections.map((o) => `<tr><td>${esc(o.issue)}</td><td>${esc(o.text)}</td><td>${{ accept: "採納", partial: "部分採納", reject: "無法採納" }[o.result]}：${esc(o.reply)}</td></tr>`).join("")}</table>` : ""}
    <p class="note">本表由訴願智審臺原型自動編製，僅供訴願審議委員會參考；一切法律見解與事實認定以委員會決議為準。</p><script>setTimeout(()=>window.print(),300)</script></body></html>`); w.document.close(); return w;
}

/* ---------- 結案歸檔 ---------- */
let finalPick = null;
function openClose() {
  const c = S.c, cp = currentPlan(); finalPick = null;
  $("#finalName").textContent = "尚未上傳"; $("#finalPrev").src = "about:blank"; $("#closeSend").disabled = true;
  const opts = $$("#finalVerdict option").map((o) => o.textContent); $("#finalVerdict").value = opts.includes(cp.verdict) ? cp.verdict : (cp.verdict.includes("撤銷") ? "原處分撤銷" : cp.verdict.includes("不受理") ? "訴願不受理" : "訴願駁回");
  $("#finalDate").value = c.final?.date || today(); $("#finalNo").value = c.final?.no || "";
  const stN = { appellant: "採訴願人", agency: "採機關", open: "待議" };
  $("#deid").innerHTML = [["訴願人", `${esc(c.fields[0]?.a[0] || "")} → <span class="m">［訴願人］</span>`], ["身分證／地址／電話", `<span class="m">全數移除</span>`], ["案由／條款", `${esc(c.subj)}／${esc(cp.art)}`], ["爭點與表態", c.issues.map((it, i) => `${i + 1}:${stN[S.stances[it.id]]}`).join("　")], ["證據組合", [...new Set(c.docs.filter((d) => d.include !== false).map((d) => d.tag))].join("、")], ["AI 判定／最終結論", `${esc(judgePlan().verdict)} → <span id="deidVerdict">${esc($("#finalVerdict").value)}</span>`], ["承辦人修改", `${S.paras.filter((p) => p.src === "human").length} 段人工編輯・${S.objections.length} 次修改提案`], ["引用查核", pendingCites().length ? `${pendingCites().length} 則引用之函釋／準則未收錄於法規庫` : "全部已驗證"]].map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`).join("");
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
  persist(); show("s-lib"); Router.set("/lib");
  const subj = [...new Set(LIB.map((r) => r.subj))], arts = [...new Set(LIB.map((r) => r.art))];
  $("#fSubj").innerHTML = '<option value="">案由：全部</option>' + subj.map((s) => `<option>${esc(s)}</option>`).join(""); $("#fArt").innerHTML = '<option value="">條款：全部</option>' + arts.map((s) => `<option>${esc(s)}</option>`).join("");
  renderLib(); $("#backBtn").style.display = ""; setCrumb("案件庫");
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

/* ---------- 法規庫 ---------- */
/* 法規庫：真資料來自 GET /api/lawlib（lawdb＋lawsync 快照）；抓不到才退 data.js 常數 */
let LAWAPI = null;
async function loadLawlib() { try { LAWAPI = await Api.lawlib(); } catch (e) { LAWAPI = null; } renderLawCard(); if ($("#s-law").classList.contains("on")) renderLaw(); }
function lawRows() {
  if (LAWAPI) return { laws: LAWAPI.laws.map((l) => ({ n: l.n, kind: l.kind, date: l.date, arts: l.arts, cases: l.cases, src: l.src, official: l.official, effective: l.effective, status: l.status, currentArts: l.currentArts })),
                       ruls: [...(LAWAPI.rulings || []), ...(LAWAPI.judgments || [])], sync: LAWAPI.sync };
  return { laws: LAWLIB.map((l) => ({ ...l, official: l.official || null, status: /資料集 PDF 為/.test(l.src || "") ? "changed" : null })), ruls: RULINGS, sync: null };
}
function lawCounts() { const { laws, ruls, sync } = lawRows(); const recent = laws.filter((l) => { const t = isoT(l.official || l.date); return t && Date.now() - t < 366 * DAY * 3; }); return { laws: laws.length, rul: ruls.length, recent, sync: sync?.checkedAt || localStorage.getItem("ssz.lawsync") || "尚未同步", stale: laws.filter((l) => l.status === "changed").length }; }
function renderLawCard() { const k = lawCounts(); $("#lawCard").innerHTML = `<span><b>法規庫</b>　法規 <b class="num">${k.laws}</b> 部・函釋判解 <b class="num">${k.rul}</b> 則</span><span>上次同步全國法規資料庫 <b class="num">${esc(k.sync)}</b></span>${k.stale ? `<span class="warn">${k.stale} 部官方已有新修正</span>` : ""}<span class="go">開啟法規庫 →</span>`; }
$("#lawCard").addEventListener("click", openLawLib); $("#lawBtn").addEventListener("click", openLawLib);
let LAWTAB = "law";
/* 法規庫的狀態：這個畫面與任何案件無關，所以只能陳述法規本身的事實
   （有沒有新修正、生效了沒），不能判斷「哪一版才對」——那取決於個案的行為時與裁處時。
   案件層級的適用版本提示在 Tab 3 法規推薦（分析輸出的 laws[].version）。

   資料來源與限制（experiments/kb/sync_laws.py 解析 law.moj.gov.tw）：
   - officialDate：頁面「修正日期」（無則「公布日期」）——12 部全有
   - effective：頁面「最後生效日期」——**只有少數法規有**，沒有時不可假設已生效
   - pendingArticles：整頁比對有無「尚未生效」字樣，是粗篩，可能因附註誤判
   公布日 ≠ 施行日（中央法規標準法 §13：未特定施行日者自公布日起算至第三日生效），
   所以只有真的抓到 effective 才寫「起施行」，否則只寫「公布」。 */
function lawStatus(l) {
  const eff = isoT(l.effective), off = isoT(l.official || l.date);
  if (l.status === "changed") {
    if (eff && eff > Date.now())
      return { cls: "amended", text: `已修正・${l.effective} 起施行`, note: "新版尚未生效，現行案件仍適用資料集版本" };
    if (eff)
      return { cls: "gap", text: `已修正・${l.effective} 起施行`, note: "新版已生效，跨修正日之案件依行政罰法 §5 判斷適用版本" };
    if (l.pendingArticles)
      return { cls: "amended", text: "已修正・部分條文尚未生效", note: "施行日未載明；依全國法規資料庫頁面標示", title: "頁面出現「尚未生效」字樣，未取得明確施行日" };
    // 只知道公布日、不知道生效狀態：不要斷言「已生效」（/api/lawlib 目前未回 pendingArticles）
    return { cls: "gap", text: `已修正・${l.official} 公布`, note: "施行日未載明，生效狀態請查全國法規資料庫",
      title: "同步只取得修正公布日；公布日≠施行日（中央法規標準法 §13）" };
  }
  if (off && Date.now() - off < 366 * DAY * 3)
    return { cls: "amended", text: "一致・近期修正", note: "資料集即為最新版；此法近期修正過，審理舊案時注意行為時版本" };
  return { cls: "ok", text: "一致", note: "" };
}

function renderLaw() {
  const k = lawCounts(), { laws, ruls, sync } = lawRows(); $("#lawStat").textContent = `法規 ${k.laws}・函釋判解 ${k.rul}${LAWAPI ? "" : "（離線：資料集常數）"}`; $("#syncStat").textContent = `上次同步：${k.sync}`;
  $("#syncBtn").onclick = async () => {
    const b = $("#syncBtn"); b.disabled = true; b.textContent = "同步中…（逐部抓 law.moj.gov.tw，約 1–2 分鐘）"; $("#syncLog").innerHTML = `<span class="typing">連線全國法規資料庫，逐部比對修正日期…</span>`;
    const before = LAWAPI?.sync?.checkedAt;
    try {
      await Api.lawSync();
      for (let i = 0; i < 60; i++) { await new Promise((r) => setTimeout(r, 4000)); const d = await Api.lawlib(); if (d.sync?.checkedAt && d.sync.checkedAt !== before) { LAWAPI = d; break; } }
      const s = LAWAPI?.sync || {}; const ch = lawRows().laws.filter((l) => l.status === "changed");
      $("#syncLog").innerHTML = s.checkedAt === before ? `<span style="color:var(--seal)">逾時：同步仍在進行，稍後重新開啟法規庫即可看到結果。</span>` : `✓ ${esc(s.checkedAt)} 同步完成（${esc(s.source || "")}）・比對 ${s.checked} 部：<b>${s.changed} 部官方已有新修正</b>${ch.length ? "——" + ch.map((l) => `${esc(l.n)} ${l.date} → 官方 ${l.official}${l.effective ? `（${l.effective} 施行）` : ""}`).join("、") : ""}；其餘 ${s.same} 部與資料集一致。新舊版本均已收錄於法規庫，審理時依個案行為時／裁處時法律決定適用版本。`;
      renderLaw(); renderLawCard();
    } catch (e) { $("#syncLog").innerHTML = `<span style="color:var(--seal)">同步失敗：${esc(e.message || e.code)}</span>`; }
    b.disabled = false; b.textContent = "同步全國法規資料庫";
  };
  $$("#s-law .rtabs button").forEach((b) => { b.classList.toggle("on", b.dataset.l === LAWTAB); b.onclick = () => { LAWTAB = b.dataset.l; renderLaw(); }; });
  const involved = (n) => LIB.filter((r) => (r.state?.docs || []).length && r.subj && n.startsWith(r.subj.replace("違反", ""))).length;
  if (LAWTAB === "law") $("#lawTable").innerHTML = `<tr><th>法規</th><th>類型</th><th>資料集版本</th><th>官方最新修正</th><th>條數</th><th>狀態</th><th>涉案</th><th>來源</th></tr>` + laws.map((l) => `<tr><td>${esc(l.n)}</td><td>${esc(l.kind)}</td><td class="num">${esc(l.date)}</td><td class="num">${l.official ? esc(l.official) : "—"}${l.effective ? `<div class="note">${esc(l.effective)} 施行</div>` : ""}</td><td class="num">${l.arts}${l.currentArts && l.currentArts !== l.arts ? `<div class="note">現行 ${l.currentArts}</div>` : ""}</td><td>${(() => { const st = lawStatus(l); return `<span class="st ${st.cls}"${st.title ? ` title="${esc(st.title)}"` : ""}>${esc(st.text)}</span>${st.note ? `<div class="note">${esc(st.note)}</div>` : ""}`; })()}</td><td class="num">${l.cases ?? involved(l.n)}</td><td>${esc(l.src)}${l.official ? '<div class="note">全國法規資料庫同步</div>' : ""}</td></tr>`).join("");
  else $("#lawTable").innerHTML = `<tr><th>函釋／判解</th><th>主題</th><th>發文日</th><th>相關法規</th><th>來源</th></tr>` + ruls.map((r) => `<tr><td>${esc(r.n)}</td><td>${esc(r.topic || "")}</td><td class="num">${esc(r.date || "—")}</td><td>${esc(r.law || "")}</td><td>${esc(r.src)}<div class="note">人工確認入庫（各部會無統一 API）</div></td></tr>`).join("");
  if (!$("#syncLog").innerHTML && sync) $("#syncLog").innerHTML = `<span class="note">最近一次同步 ${esc(sync.checkedAt)}：比對 ${sync.checked} 部，${sync.changed} 部官方已有新修正、${sync.same} 部與資料集一致（${esc(sync.source || "")}）。法規庫同時保留資料集版本與官方現行版。</span>`;
}
function openLawLib() { persist(); show("s-law"); Router.set("/law"); $("#backBtn").style.display = ""; setCrumb("法規庫"); renderLaw(); }
renderLawCard();

/* ---------- 案件 AI 助理（問答唯讀；修改走提案確認） ---------- */
$("#asstBtn").addEventListener("click", asstOpen); $("#asstClose").addEventListener("click", () => $("#asst").classList.remove("on"));
$("#asstClear").addEventListener("click", async () => { if (!confirm("清除本案全部對話紀錄？（所有人看到的都會清掉；已執行的修改不受影響）")) return; if (isLiveCase()) { try { await Api.clearChat(S.c.caseId); } catch (e) { return toast(`清除失敗：${e.message || e.code}`, "err"); } } CHAT_HIST.length = 0; histSave(); asstReset(); toast("已清除本案對話紀錄"); });
$("#asstIn").addEventListener("input", () => { const t = $("#asstIn"); t.style.height = "auto"; t.style.height = Math.min(120, t.scrollHeight) + "px"; });
function asstOpen() { $("#asst").classList.add("on"); $("#asstIn").focus(); }
function asstAdd(role, html) { const log = $("#asstLog"); const el = document.createElement("div"); el.className = "msg " + role; el.innerHTML = html; log.appendChild(el); log.scrollTop = log.scrollHeight; return el; }
function asstSay(t) { asstOpen(); asstAdd("a", esc(t)); }
/* 系統通知走 toast，不進助手對話（助手只放與案件有關的問答與提案） */
function toast(msg, kind = "ok", ms = 3200) { let box = $("#toasts"); if (!box) { box = document.createElement("div"); box.id = "toasts"; document.body.appendChild(box); } const el = document.createElement("div"); el.className = `toast ${kind}`; el.textContent = msg; box.appendChild(el); requestAnimationFrame(() => el.classList.add("in")); setTimeout(() => { el.classList.remove("in"); setTimeout(() => el.remove(), 300); }, ms); return el; }
async function copyText(text) { try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; } } catch {} /* http 站台沒有 navigator.clipboard：退回 execCommand */ try { const ta = document.createElement("textarea"); ta.value = text; ta.style.cssText = "position:fixed;left:-9999px;top:0"; document.body.appendChild(ta); ta.focus(); ta.select(); const ok = document.execCommand("copy"); ta.remove(); return ok; } catch { return false; } }
function asstReset() {
  $("#asstLog").innerHTML = "";
  const ro = S.status !== "承辦中"; $("#asstState").textContent = ro ? `本案${S.status}・僅供查詢` : (isLiveCase() ? "已接後端・修改須確認" : "示範資料・修改須確認");
  $("#asstSub").textContent = ro ? "本案已送審或結案，僅能查詢；修改請先「另存為新草稿」" : "查詢卷宗、法規與分析結果；修改須經您確認才會執行";
  const w = document.createElement("div"); w.className = "asst-welcome";
  w.innerHTML = `<b>我是本案的 AI 助理。</b>回答一律附出處；任何修改都會先畫出「改完的樣子」，您按「確認執行」才會更新案件。<div class="two"><div><b>查詢</b><span class="note">　直接問</span><div class="ex"><button class="ghost-btn" data-q="送達日在哪份文件？">送達日在哪份文件？</button><button class="ghost-btn" data-q="行政罰法第 18 條第 1 項">行政罰法第 18 條第 1 項</button><button class="ghost-btn" data-q="本案判定與風險？">本案判定與風險？</button></div></div><div><b>修改</b><span class="note">　說要改什麼</span><div class="ex"><button class="ghost-btn" data-q="爭點 1 改採訴願人，因為">爭點 1 改採訴願人…</button><button class="ghost-btn" data-q="理由二精簡一點">理由二精簡一點</button><button class="ghost-btn" data-q="加引行政罰法第 18 條第 1 項">加引行政罰法 §18 I</button></div></div></div>`;
  w.querySelectorAll("[data-q]").forEach((b) => b.addEventListener("click", () => { $("#asstIn").value = b.dataset.q; if (/因為$/.test(b.dataset.q)) $("#asstIn").focus(); else asstSend(); }));
  $("#asstLog").appendChild(w);
  asstSuggest();
  if (isLiveCase()) histLoadLive(); else { histLoad(); renderHist(); }
}
/* 對話紀錄：真案存在後端（每案一份、所有人共用），重整、換電腦都在；mock 案存 sessionStorage */
const ST = { pending: "待確認", applied: "已執行", cancelled: "已取消", failed: "失敗" };
function renderHist() {
  CHAT_HIST.forEach((h) => {
    if (h.role === "user") return asstAdd("u", esc(h.text).replace(/\n/g, "<br>"));
    if (h.kind === "system") return asstAdd("a", `<span class="sysnote">${esc(h.text)}</span>`);
    const body = esc(h.text || "").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
    const pp = h.proposalId ? `<span class="src">修改提案 ${esc(h.proposalId)}・${ST[h.proposalState] || h.proposalState || ""}${(h.replies || []).length ? "：" + h.replies.map((r) => `${esc((r.label || "").split("：")[0])} ${esc(r.result || "")}`).join("；") : ""}</span>` : "";
    asstAdd("a", body + pp);
  });
  if (CHAT_HIST.length) asstAdd("a", `<span class="sysnote">以上為本案先前對話（${CHAT_HIST.length} 則；提案卡不重播）</span>`);
}
async function histLoadLive() {
  CHAT_HIST.length = 0;
  const wait = asstAdd("a", `<span class="sysnote">載入本案對話紀錄…</span>`);
  try { const r = await Api.chatLog(S.c.caseId); wait.remove(); (r.messages || []).forEach((m) => CHAT_HIST.push(m)); renderHist(); }
  catch (e) { wait.innerHTML = `<span class="sysnote">對話紀錄載入失敗：${esc(e.message || e.code)}</span>`; }
}
/* 建議句由本案狀態＋目前分頁即時產生（規則，零模型呼叫）；正式版可再加一次便宜的模型呼叫補充 */
function asstSuggest() {
  const c = S.c; if (!c) return; const tab = +($(".tab.on")?.dataset.t || 0), cp = currentPlan(), can = S.status === "承辦中", ask = [], edit = [];
  const other = (s) => s === "appellant" ? "採機關" : "採訴願人";
  const conflict = c.fields.find((f) => f.conflict), pend = pendingCites(), altPlan = c.plans.find((p) => p.id !== cp.id && p.id !== "X"), r2 = S.paras.find((p) => /^理由/.test(paraLabel(p)) && p.kind !== "h4"), hasNew = c.docs.some((d) => d.imported);
  if (tab === 0) { ask.push(`送達日在哪份文件？`, `期間有沒有逾期？`); if (can) { if (conflict) edit.push(`送達日改 ${(/(\d{3}-\d{2}-\d{2})/.exec(conflict.a[0]) || [])[1] || "114-09-16"}，因為`); edit.push(`應依 77(2) 逾期不受理，因為`); } }
  else if (tab === 1) { c.issues.slice(0, 2).forEach((it, i) => ask.push(`爭點 ${i + 1} 的卷證在哪？`)); if (can) { if (hasNew) edit.push(`依新補件重新審查爭點 1`); c.issues.slice(0, 2).forEach((it, i) => edit.push(`爭點 ${i + 1} 改${other(S.stances[it.id] || it.stance)}，因為`)); } }
  else if (tab === 2) { const l = c.laws.find((x) => /行政罰法|訴願法/.test(x.n)) || c.laws[0]; if (l) ask.push(l.n.replace(/ /g, "")); pend.slice(0, 1).forEach((x) => ask.push(`${x.n.replace(/（.*$/, "").slice(0, 14)}是什麼？`)); if (can) edit.push(`加引行政罰法第 5 條`, `加引裁罰準則第 9 條`); }
  else if (tab === 3) { ask.push(`相似案例的結論分布？`, `有沒有撤銷的案例？`); }
  else { ask.push(`本案判定與風險？`); if (can) { if (altPlan) edit.push(`結論改為${altPlan.verdict}，因為`); if (r2) edit.push(`${paraLabel(r2)}精簡一點`, `${paraLabel(r2)}語氣改平實`); edit.push(`從舉證責任分配的角度重寫理由`); } }
  const row = (cls, eb, list, fill) => list.length ? `<div class="sg ${cls}"><span class="eb">${eb}</span>${list.slice(0, 4).map((q) => `<button class="ghost-btn" data-fill="${fill ? 1 : 0}">${fill ? "✎ " : ""}${esc(q)}</button>`).join("")}</div>` : "";
  $("#asstSug").innerHTML = row("ask", "問", ask, false) + row("edit", "改", edit, true);
  $$("#asstSug button").forEach((b) => b.addEventListener("click", () => { const t = b.textContent.replace(/^✎ /, ""); $("#asstIn").value = t; if (b.dataset.fill === "1") { $("#asstIn").focus(); $("#asstIn").setSelectionRange(t.length, t.length); } else asstSend(); }));
}
function asstIndex() {
  const c = S.c, out = [];
  c.docs.forEach((d) => { if (d.include === false) return; const t = d.stdName || d.title, k = d.kind; if (d.html) { const re = /<mark data-ref="([^"]+)">([\s\S]*?)<\/mark>/g; let m; while ((m = re.exec(d.html))) out.push({ ref: m[1], doc: t, kind: k, tag: d.tag, text: plain(m[2]), where: "本文" }); } (d.boxes || []).forEach((b) => out.push({ ref: b.ref, doc: t, kind: k, tag: d.tag, text: b.label, where: "框選區" })); (d.cues || []).forEach((q) => out.push({ ref: q[0], doc: t, kind: k, tag: d.tag, text: q[2], where: "影片時間點" })); });
  return out;
}
const SYN = [["送達日", "送達日期"], ["收文", "收文"], ["煙蒂", "煙蒂"], ["照片", "採證"], ["影片", "12:40"], ["簽收", "簽章"], ["罰鍰", "3,600"], ["係數", "A=3"], ["車主", "車籍"], ["拋棄", "拋擲"]];

/* ---------- 助手：提案 → 確認 → 局部重跑 ---------- */
const EDIT_RE = /改|修改|加引|引用|援引|加入|新增|移除|刪除|重寫|改寫|潤飾|精簡|縮短|語氣|不受理|進入實體|撤銷|駁回|重新審查|重新認定|納入/;
const ART_TEXT = { "行政罰法 第 5 條": "行為後法律或自治條例有變更者，適用裁處時之法律或自治條例。但裁處前之法律或自治條例有利於受處罰者，適用最有利於受處罰者之規定。", "訴願法 第 14 條第 1 項": "訴願之提起，應自行政處分達到或公告期滿之次日起三十日內為之。", "行政程序法 第 73 條第 1 項": "於應送達處所不獲會晤應受送達人時，得將文書付與有辨別事理能力之同居人、受雇人或應送達處所之接收郵件人員。", "訴願法 第 77 條": "訴願事件有左列各款情形之一者，應為不受理之決定：一、訴願書不合法定程式不能補正或經通知補正逾期不補正者。二、提起訴願逾法定期間或未於第五十七條但書所定期間內補送訴願書者。……" };
const CN = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6 };
function lawName(raw) { const s = raw.replace(/^(請|幫我|另外|另|並|再|也|還要|加引|引用|援引|加入|新增|引|移除|刪除|不引|改|加|把)+/, ""); const inCase = (l) => (S.c.laws || []).some((x) => x.n.startsWith(l.n)) || (S.c.citations || []).some((x) => x.n.startsWith(l.n)); const hit = LAWLIB.filter((l) => s.includes(l.n) || (s.length >= 3 && l.n.includes(s))).sort((p, q) => (inCase(q) - inCase(p)) || (q.n.length - p.n.length))[0]; return hit ? hit.n : s; }
function parseIntent(q) {
  if (!EDIT_RE.test(q)) return null; const c = S.c, items = []; q = q.replace(/[，,]\s*因為\s*$/, "");
  const reI = /爭點\s*([一二三四五六\d])[^，。；,;]*?(改採訴願人|採訴願人|改採機關|採機關|刪除|移除)/g; let m;
  while ((m = reI.exec(q))) { const n = CN[m[1]] || +m[1], it = c.issues[n - 1]; if (!it) continue; const to = /訴願人/.test(m[2]) ? "appellant" : /機關/.test(m[2]) ? "agency" : "drop"; const seg = q.slice(m.index + m[0].length).split(/[；;。]|另外|另|並|加引|引用/)[0].replace(/^[，,、\s]+/, "").trim(); items.push({ type: "issue", id: it.id, to, why: /^(改|加|引)/.test(seg) ? "" : seg.slice(0, 60) }); }
  const reL = /(移除|刪除|不引|不再引用)?\s*(?:加引|引用|援引|加入|新增|引)?\s*([一-龥]{2,24}?(?:法|條例|準則|規則|辦法))\s*第?\s*(\d+)\s*條(?:\s*第?\s*(\d+)\s*項)?(?:\s*第?\s*(\d+)\s*款)?/g;
  while ((m = reL.exec(q))) { const name = lawName(m[2]), lib = LAWLIB.find((l) => l.n === name); items.push({ type: m[1] ? "law-rm" : "law", n: name, art: m[3], p: m[4], k: m[5], lib, ok: !!lib && !(lib.arts && +m[3] > lib.arts), msg: !lib ? "法規庫查無此法規" : lib.arts && +m[3] > lib.arts ? `${lib.n} 僅 ${lib.arts} 條，第 ${m[3]} 條不存在` : `法規庫有・${lib.date} 版` }); }
  m = /送達日?[^\d]{0,8}(\d{3})[-/.年](\d{1,2})[-/.月](\d{1,2})/.exec(q); if (m) items.push({ type: "served", v: `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}` });
  if (/進入實體/.test(q)) items.push({ type: "proc", v: "merit" }); else if ((m = /不受理[^。；]*?77\s*[(（第]?\s*(\d)/.exec(q) || /77\s*[(（第]?\s*(\d)[)）款]?[^。；]*?不受理/.exec(q))) items.push({ type: "proc", v: "77-" + m[1] }); else if (/不受理/.test(q) && !/採|爭點/.test(q)) items.push({ type: "proc", v: "77-?" });
  m = /(?:改|結論|判定)[^。；]*?(撤銷|駁回)/.exec(q); if (m && !items.some((i) => i.type === "issue")) { const p = c.plans.find((x) => x.verdict.includes(m[1]) && x.id !== currentPlan().id); if (p) items.push({ type: "verdict", plan: p.id }); }
  m = /(理由[一二三四五六]|主文|事實|前言)[^。；]*?(精簡|縮短|簡化|語氣|平實|潤飾|改寫|重寫|改)/.exec(q); if (m) { const p = S.paras.find((x) => paraLabel(x) === m[1] || (m[1] === "前言" && x.id === "intro") || (m[1] === "主文" && x.id === "main")); if (p) items.push({ type: "text", para: p.id, how: m[2] === "改" ? q.slice(m.index).slice(0, 40) : m[2] }); }
  m = /(?:依|依據|參酌|納入)(?:新)?(?:補件|補充理由書|新文件|新卷證)[^。；]*?爭點\s*([一二三四五六\d])/.exec(q) || /爭點\s*([一二三四五六\d])[^。；]*?(?:依|依據|參酌|納入)(?:新)?(?:補件|補充理由書|新文件|新卷證)/.exec(q);
  if (m) { const it = c.issues[(CN[m[1]] || +m[1]) - 1], newDocs = c.docs.filter((d) => d.imported); if (it) { if (!newDocs.length) return { clarify: "本案尚無補件；請先用左欄「＋ 補件」匯入新文件，再要求重新審查。" }; items.length = 0; items.push({ type: "reissue", id: it.id, docs: newDocs }); return { items }; } }
  m = /(?:從|以|用)([^，。；]{2,20}?)(?:的)?(?:角度|切入|觀點)/.exec(q); if (m && !items.some((i) => i.type === "text")) items.push({ type: "frame", angle: m[1] });
  if (!items.length) return { clarify: /好一點|更好|優化|順一點|完善/.test(q) ? "「改好一點」我無法判斷要動哪裡。請指定：哪個爭點要改認定？要加或移除哪條法規？還是哪一段理由要改寫、往哪個方向？" : "我看不出要改的具體對象。可以這樣說：「爭點 2 改採訴願人，因為…」「加引行政罰法第 18 條第 1 項」「送達日改 114-09-16」「理由二精簡一點」。" };
  return { items };
}
function periodFor(served) { const st = isoT(served), rt = isoT(S.recv); if (!st) return null; const due = st + 30 * DAY; return { due, over: rt !== null ? rt > due : null, left: rt !== null ? Math.round((due - rt) / DAY) : null }; }
function stepOf(it) { return { served: 0, proc: 1, issue: 2, reissue: 2, law: 3, "law-rm": 3, verdict: 4, frame: 5, text: 5 }[it.type]; }
function scopeOf(items) { const from = Math.min(...items.map(stepOf)); const s = []; for (let i = from; i < 6; i++) s.push(i); if (from === 3 && items.every((i) => stepOf(i) === 3)) return s.filter((i) => i !== 4); if (items.every((i) => i.type === "text")) return [5]; return s; }
function mockRewrite(text, how) { const t = plain(text); if (/精簡|縮短|簡化/.test(how)) { const ss = t.split(/(?<=。)/); return ss.slice(0, Math.max(1, Math.ceil(ss.length * 0.55))).join("").replace(/[，、]之[^。，]*?(，|。)/g, "$1"); } if (/語氣|平實|潤飾/.test(how)) return t.replace(/難認/g, "不能認為").replace(/洵屬/g, "確屬").replace(/尚非無據/g, "有其依據").replace(/核無違誤/g, "並無錯誤").replace(/殊難採憑/g, "難以採信").replace(/自屬/g, "應屬").replace(/要難/g, "難以"); return t; }
function buildProposal(items, q) {
  const c = S.c, stN = { agency: "採機關", appellant: "採訴願人", open: "待議", drop: "刪除" };
  const p = { id: "pp" + Date.now().toString(36), q, items: [], scope: scopeOf(items), planTo: null };
  items.forEach((it) => {
    if (it.type === "issue") { const is = c.issues.find((x) => x.id === it.id), from = S.stances[is.id] || is.stance || "open", leadPlan = it.to === "drop" ? null : (is.lead[it.to] || [])[0]; const pl = leadPlan ? (leadPlan === "X" ? overduePlan() : c.plans.find((x) => x.id === leadPlan)) : null; if (pl && pl.id !== currentPlan().id) p.planTo = pl.id; p.items.push({ ...it, n: c.issues.indexOf(is) + 1, title: is.title, from, label: `爭點 ${c.issues.indexOf(is) + 1}：${stN[from]} → ${stN[it.to]}`, verdictTo: pl ? pl.verdict : null }); }
    else if (it.type === "law" || it.type === "law-rm") { const key = `${it.n} 第 ${it.art} 條${it.p ? `第 ${it.p} 項` : ""}${it.k ? `第 ${it.k} 款` : ""}`; const dup = c.laws.some((l) => l.n.startsWith(`${it.n} 第 ${it.art} 條`)); p.items.push({ ...it, key, dup, label: `${it.type === "law-rm" ? "移除引用" : "加引"}：${key}` }); }
    else if (it.type === "served") { const np = periodFor(it.v); p.items.push({ ...it, from: S.served, due: np ? toMg(np.due) : "—", over: np && np.over, left: np ? np.left : null, label: `送達日：${S.served} → ${it.v}` }); }
    else if (it.type === "proc") p.items.push({ ...it, label: it.v === "merit" ? "程序：進入實體審查" : `程序：依訴願法 §77 (${it.v.slice(3)}) 不受理` });
    else if (it.type === "verdict") { const pl = c.plans.find((x) => x.id === it.plan); p.planTo = pl.id; p.items.push({ ...it, verdictTo: pl.verdict, artTo: pl.art, label: `結論：${currentPlan().verdict} → ${pl.verdict}` }); }
    else if (it.type === "text") { const pa = S.paras.find((x) => x.id === it.para); p.items.push({ ...it, lab: paraLabel(pa), before: plain(pa.text), after: mockRewrite(pa.text, it.how), label: `文字：${paraLabel(pa)}（${it.how}）` }); }
    else if (it.type === "reissue") { const is = c.issues.find((x) => x.id === it.id), sup = c.supplement, hit = sup && sup.issueId === is.id && it.docs.some((d) => sup.docs.some((x) => x.id === d.id)); p.items.push({ ...it, n: c.issues.indexOf(is) + 1, title: is.title, aFrom: is.a[0], aTo: hit ? sup.issueA[0] : is.a[0], eAdd: hit ? sup.issueE : it.docs.map((d) => [d.stdName, null]), note: hit ? sup.issueNote : "", label: `爭點 ${c.issues.indexOf(is) + 1}：納入補件重新審查（${it.docs.length} 份）` }); }
    else if (it.type === "frame") { const pa = S.paras.find((x) => x.id.startsWith("r") && x.kind !== "h4") || S.paras[2]; p.items.push({ ...it, lab: paraLabel(pa), before: plain(pa.text), after: `就${it.angle}而言，` + plain(pa.text), label: `論述角度：${it.angle}` }); }
  });
  if (p.planTo && c.drafts[p.planTo]) { const d = draftFor(p.planTo); p.diff = diffParas(S.paras, d.paras.map((x) => ({ ...x }))).sort((x, y) => (x.label === "主文" ? 0 : /^理由/.test(x.label) ? 1 : 2) - (y.label === "主文" ? 0 : /^理由/.test(y.label) ? 1 : 2)); p.draftTo = d; }
  return p;
}
const PENDING = {};
function renderProposal(p) {
  PENDING[p.id] = p; const c = S.c, jp = currentPlan();
  const item = (it) => {
    if (it.type === "issue") return `<div class="pc-item"><div class="lab">爭點認定<span class="jump" data-tab="1" data-el="iss-${it.id}">查看爭點 ↗</span></div><div class="bd"><div><span class="n" style="font-family:var(--mono);font-size:11px;border:1px solid var(--accent);color:var(--accent);padding:0 6px;margin-right:6px">爭點 ${it.n}</span><b>${esc(it.title)}</b></div><div><span class="ailab">AI 認定：${{ agency: "採機關", appellant: "採訴願人", open: "待議" }[it.from]}</span><span class="arw">→</span>${it.to === "drop" ? `<span class="ailab" style="border-color:var(--seal);color:var(--seal)">刪除此爭點</span>` : `<span class="ailab obj">修正後：${it.to === "appellant" ? "採訴願人" : "採機關"}</span>`}${it.why ? `<span class="note">　理由：${esc(it.why)}</span>` : ""}</div>${it.verdictTo && it.verdictTo !== jp.verdict ? `<div class="mini-jbar"><span class="note">結論</span><span class="jv">${esc(jp.verdict)}</span><span class="arw">→</span><span class="jv">${esc(it.verdictTo)}</span><span class="note">（依爭點導向；AI 重新引證後可能維持原判定）</span></div>` : ""}</div></div>`;
    if (it.type === "issue-new") return `<div class="pc-item"><div class="lab">新增爭點<span class="jump" data-tab="1">查看爭點 ↗</span></div><div class="bd"><div><span class="n" style="font-family:var(--mono);font-size:11px;border:1px solid var(--green);color:var(--green);padding:0 6px;margin-right:6px">＋ 爭點 ${it.n || c.issues.length + 1}</span><b>${esc(it.title || "")}</b></div>${it.why ? `<div class="note">理由：${esc(it.why)}</div>` : ""}<div class="note">AI 將依卷證就此爭點作認定，並重產法規推薦、相似案例與草稿</div></div></div>`;
    if (it.type === "reissue") return `<div class="pc-item"><div class="lab">爭點重新審查（納入補件）<span class="jump" data-tab="1" data-el="iss-${it.id}">查看爭點 ↗</span></div><div class="bd"><div><span class="n" style="font-family:var(--mono);font-size:11px;border:1px solid var(--accent);color:var(--accent);padding:0 6px;margin-right:6px">爭點 ${it.n}</span><b>${esc(it.title)}</b></div><div class="pc-diff diffbox"><span class="pl">訴願人主張（修改前 → 修改後）</span>${diffHtml(it.aFrom, it.aTo)}</div><div><span class="note">卷證顯示新增：</span>${it.eAdd.map((e) => `<span class="tag accent" style="font-size:10px">${esc(e[0])}</span>`).join(" ")}</div>${it.note ? `<div class="note">AI 將補充認定：${esc(it.note)}</div>` : `<div class="note">AI 將依新文件內容重新引證；本 mock 無對應示範資料，認定文字維持</div>`}</div></div>`;
    if (it.type === "law" || it.type === "law-rm") return `<div class="pc-item"><div class="lab">法規引用<span class="jump" data-tab="2">查看法規推薦 ↗</span></div><div class="bd"><div class="mini-law ${it.ok ? "" : "bad"}">${it.type === "law-rm" ? tag("seal", "移除") : it.ok ? tag("green", it.dup ? "已在清單" : "＋新增") : tag("seal", "無法引用")}<span class="nm">${esc(it.key)}</span>${it.lib ? `<span class="vd">${it.lib.date} 版</span>` : ""}<span class="${it.ok ? "st ok" : "st pending"}" style="font-size:10.5px">${esc(it.msg)}</span></div>${it.ok && it.type === "law" ? `<div class="note">條文原文將自法規庫帶入並於草稿理由引用${it.dup ? "（已在推薦清單，僅補入草稿引用）" : ""}</div>` : !it.ok ? `<div class="note" style="color:var(--seal)">此條不會寫入草稿</div>` : ""}</div></div>`;
    if (it.type === "served") return `<div class="pc-item"><div class="lab">訴願期間<span class="jump" data-tab="0">查看期間 ↗</span></div><div class="bd"><div class="mini-tp"><div><span class="k">送達日</span><del>${esc(it.from)}</del> → <b>${esc(it.v)}</b></div><div><span class="k">屆滿日</span><b>${esc(it.due)}</b></div><div><span class="k">結果</span>${it.over === null ? "—" : it.over ? `<b style="color:var(--seal)">逾期 → §77(2) 不受理</b>` : `<b style="color:var(--green)">在期間內，餘 ${it.left} 日</b>`}</div></div><div class="note">三方對照該列將標「承辦人更正」；期間與程序清單重算</div></div></div>`;
    if (it.type === "proc") return `<div class="pc-item"><div class="lab">程序審查<span class="jump" data-tab="0">查看程序清單 ↗</span></div><div class="bd"><div class="ck ${it.v === "merit" ? "pass" : "fail"}" style="padding:6px 0;border:none"><span class="ckbox">${it.v === "merit" ? "☑" : "☒"}</span><span class="ckart">${it.v === "merit" ? "§77 各款" : "§77 (" + it.v.slice(3) + ")"}</span><span class="ckname">${it.v === "merit" ? "全部通過 → 進入實體審查" : "改列不受理事由"}</span><span class="ckst">${it.v === "merit" ? "通過" : "不通過"}</span><span class="cknote">${it.v === "77-?" ? "未指明款次，AI 將反問" : "承辦人指示"}</span></div></div></div>`;
    if (it.type === "verdict") return `<div class="pc-item"><div class="lab">結論<span class="jump" data-tab="4">查看草稿 ↗</span></div><div class="bd"><div class="mini-jbar"><span class="jv">${esc(jp.verdict)}</span><span class="jart">${esc(jp.art)}</span><span class="arw">→</span><span class="jv">${esc(it.verdictTo)}</span><span class="jart">${esc(it.artTo)}</span></div></div></div>`;
    if (it.type === "text" || it.type === "frame") return `<div class="pc-item"><div class="lab">${it.type === "text" ? "文字表達" : "論述角度"}・${esc(it.lab)}<span class="jump" data-tab="4">查看草稿 ↗</span></div><div class="bd"><div class="pc-diff diffbox"><span class="pl">${it.previewLater ? "將改寫的段落（修改後內容於確認執行後產生）" : "修改前 → 修改後（預覽）"}</span>${fillDates(diffHtml(it.before, it.after))}</div></div></div>`;
  };
  const diff = p.diff && p.diff.length ? `<div class="pc-item"><div class="lab">草稿變動預覽（若採納・${p.draftTo.tmpl}）<span class="jump" data-tab="4">查看草稿 ↗</span></div><div class="bd">${p.diff.slice(0, 2).map((d) => `<div class="pc-diff diffbox"><span class="pl">${esc(d.label)}</span>${fillDates(d.html)}</div>`).join("")}${p.diff.length > 2 ? `<div class="note">…另 ${p.diff.length - 2} 段變動，確認後於草稿頁版本 diff 檢視</div>` : ""}</div></div>` : "";
  const steps = `<div class="pc-item"><div class="lab">影響範圍</div><div class="bd"><div class="mini-steps">${RV_STEPS.map((s, i) => `<span class="${p.scope.includes(i) ? "re" : ""}">${i + 1} ${s}</span>`).join("")}</div><div class="note">亮者重新產生（附您的意見）；其餘維持並作為下游 context</div></div></div>`;
  const el = asstAdd("a card", `<div class="pc-head"><b>修改提案</b><span>${p.items.length} 項・尚未執行，Tab1–5 未變</span></div><div class="pc-body">${p.items.map(item).join("")}${diff}${steps}</div><div class="pc-foot"><span class="note">按確認後才會更新；原版本保留可回復</span><button class="ghost-btn" data-no="${p.id}">取消</button><button class="btn" data-yes="${p.id}">確認執行</button></div>`);
  el.querySelectorAll("[data-tab]").forEach((j) => j.addEventListener("click", () => { $$(".tab")[+j.dataset.tab].click(); if (j.dataset.el) document.getElementById(j.dataset.el)?.scrollIntoView({ behavior: "smooth", block: "start" }); }));
  el.querySelector("[data-no]").addEventListener("click", () => { el.classList.add("off"); el.querySelector(".pc-head span").textContent = "已取消・內容未變動"; delete PENDING[p.id]; if (p.server && S.c?.caseId) { Api.cancelProposal(S.c.caseId, p.id).catch(() => {}); CHAT_HIST.push({ role: "assistant", text: "（上述提案已由承辦人取消，不再列入後續提案。）" }); histSave(); } asstAdd("a", "已取消。要調整提案的哪一部分？例如改另一個爭點、換一條法規，或換個說法。"); });
  el.querySelector("[data-yes]").addEventListener("click", () => { el.classList.add("busy"); el.querySelector(".pc-foot").remove(); delete PENDING[p.id]; p.el = el; applyProposal(p); });
  return el;
}
function aiReply(it) {
  const c = S.c;
  if (it.type === "reissue") { const is = c.issues.find((x) => x.id === it.id), sup = c.supplement; if (sup && sup.issueId === is.id && it.aTo !== it.aFrom) { Object.assign(c.refs, sup.refs); is.a = sup.issueA; is.e = [...is.e, ...sup.issueE.filter((e) => !is.e.some((x) => x[1] === e[1]))]; is.ai = (is.ai || "") + " 補件後：" + sup.issueNote; return { result: "partial", reply: `已納入補充理由書之主張與截圖為卷證；${sup.issueNote} 維持原認定。`, evidence: sup.issueE.map((e) => e[1]) }; } return { result: "partial", reply: `已將 ${it.docs.length} 份新文件納入爭點 ${it.n} 之卷證重新引證；未見足以推翻原認定之事證，維持原認定。`, evidence: [] }; }
  if (it.type === "issue") { const is = c.issues.find((x) => x.id === it.id); if (it.to === "drop") return { result: "partial", reply: "該爭點為訴願書與答辯書均有論及之事項，依訴願法第 67 條應予論斷；已於理由中併入相鄰爭點簡述，不另立標題。", evidence: [] }; if (it.to === it.from) return { result: "accept", reply: "與 AI 原認定一致，已將承辦人理由補入依據。", evidence: [] }; const r = is.objection || c.objectionOther || CASE_B.objectionOther; return { result: r.result, reply: r.reply.replace(/^(採納|部分採納|無法採納)。/, ""), evidence: r.evidence || [], plan: r.result !== "reject" ? r.plan : null, stance: r.result !== "reject" ? it.to : null }; }
  if (it.type === "law") return it.ok ? { result: "accept", reply: `${it.key} 已加入法規推薦，條文原文自法規庫帶入並於草稿理由引用。`, evidence: [] } : { result: "reject", reply: `${it.msg}。未寫入草稿，以免引用不存在之條文。`, evidence: [] };
  if (it.type === "law-rm") return { result: "accept", reply: `${it.key} 已自草稿引用移除；法規推薦清單保留供參。`, evidence: [] };
  if (it.type === "served") { S.served = it.v; return { result: "accept", reply: `送達日改為 ${it.v}，訴願期間已重算${isOverdue() ? "：已逾 30 日，程序審查改為不通過" : "，仍在期間內"}；三方對照該列標記「承辦人更正」。`, evidence: ["sv-date"] }; }
  if (it.type === "proc") { if (it.v === "merit") return { result: isOverdue() ? "reject" : "accept", reply: isOverdue() ? "依現有送達日與收文日，本件仍逾 30 日不變期間；程序審查為規則運算，除非更正送達日，否則無法進入實體。" : "程序各款均通過，維持進入實體審查。", evidence: [] }; if (it.v === "77-?") return { result: "reject", reply: "未指明訴願法第 77 條款次，無法改列；請說明是哪一款（例如「依 77(2) 逾期不受理」）。", evidence: [] }; return { result: "partial", reply: `程序判定屬承辦人職權，已依指示改列訴願法 §77 (${it.v.slice(3)})；惟卷面程序清單各款顯示通過，請於送審前補充該款事實依據。`, evidence: [] }; }
  if (it.type === "verdict") return { result: "accept", reply: `結論改為「${it.verdictTo}」，草稿依該方案重寫；相似案例改檢索同結論之決定書。`, evidence: [], plan: it.plan };
  if (it.type === "text") return { result: "accept", reply: `${it.lab}已依「${it.how}」改寫，其餘段落未動。`, evidence: [], para: it.para, after: it.after };
  return { result: "accept", reply: `理由已依「${it.angle}」角度重寫；事實、爭點與法規推薦不變。`, evidence: [], para: null, after: it.after, lab: it.lab };
}
/* 原地重跑：不切換畫面；提案卡的六步列逐步亮起，受影響分頁標「更新中」淡化，完成後只重繪那些分頁並短暫高亮 */
const STEP_TAB = [0, 0, 1, 2, 3, 4];
function rerunInPlace(scope, card, done) {
  const tabs = [...new Set(scope.map((i) => STEP_TAB[i]))], strip = card ? card.querySelector(".mini-steps") : null, head = card ? card.querySelector(".pc-head span") : null;
  tabs.forEach((t) => { $$(".tab")[t].classList.add("busy"); $("#p" + t).classList.add("busy"); });
  let t = 0, k = 0;
  scope.forEach((i) => { setTimeout(() => { if (strip) { const sp = strip.children[i]; sp.classList.add("run"); sp.textContent = `${i + 1} ${RV_STEPS[i]}…`; } if (head) head.textContent = `執行中 ${++k}/${scope.length}：${RV_STEPS[i]}`; }, t); t += 620; setTimeout(() => { if (strip) { const sp = strip.children[i]; sp.classList.remove("run"); sp.classList.add("ok"); sp.textContent = `✓ ${RV_STEPS[i]}`; } }, t); });
  setTimeout(() => { if (head) head.textContent = `已執行・重新產生 ${scope.length} 步，其餘維持`; done(tabs); tabs.forEach((t) => { $$(".tab")[t].classList.remove("busy"); const pg = $("#p" + t); pg.classList.remove("busy"); pg.classList.add("flash"); setTimeout(() => pg.classList.remove("flash"), 1600); }); }, t + 300);
}
function renderTabs(tabs) { const R = [renderExtract, renderIssues, renderLaws, renderSims, renderDraft]; tabs.forEach((t) => R[t]()); }
function applyProposal(p) {
  const c = S.c, D = { accept: "採納", partial: "部分採納", reject: "無法採納" }, before = S.paras.map((x) => ({ ...x }));
  if (c.live && c.analysis) return applyLiveProposal(p);
  const replies = p.items.map((it) => ({ ...it, ...aiReply(it) }));
  replies.forEach((r) => { S.audit.push({ ts: now(), who: "hu", para: r.label.split("：")[0], action: `修改提案：${r.label}` }); if (r.stance) S.stances[r.id] = r.stance; });
  const newPlan = replies.map((r) => r.plan).filter(Boolean).pop();
  if (newPlan && (c.drafts[newPlan] || newPlan === "X")) { S.plan = newPlan; const d = draftFor(newPlan); S.paras = d.paras.map((x) => ({ ...x, tpl: x.text, src: "ai-edit", refs: x.refs ? x.refs.slice() : [] })); }
  replies.filter((r) => r.after).forEach((r) => { const pa = r.para ? S.paras.find((x) => x.id === r.para) : S.paras.find((x) => paraLabel(x) === r.lab); if (pa) { pa.text = r.after; pa.src = "ai-edit"; } });
  if (p.scope.includes(5) && !newPlan) S.paras = S.paras.map((x) => x.kind === "h4" || x.kind === "meta" || replies.every((r) => r.type === "text" || r.type === "frame") ? x : { ...x, src: "ai-edit" });
  const worst = replies.every((r) => r.result === "accept") ? "accept" : replies.some((r) => r.result !== "reject") ? "partial" : "reject";
  const o = { ts: now(), issue: `${p.items.length} 項`, issueId: replies.find((r) => r.type === "issue")?.id || "multi", text: p.q, ev: [], result: worst, reply: replies.map((r) => `${D[r.result]}：${r.reply}`).join(" "), evidence: [...new Set(replies.flatMap((r) => r.evidence))], plan: newPlan || null, items: replies.map((r) => ({ label: r.label, result: r.result, reply: r.reply, evidence: r.evidence })), scope: p.scope, diff: null };
  replies.forEach((r) => S.audit.push({ ts: now(), who: "ai", para: r.label.split("：")[0], action: `${D[r.result]}：${r.reply.slice(0, 40)}…` }));
  rerunInPlace(p.scope, p.el, (tabs) => {
    if (p.scope.includes(5)) { o.diff = diffParas(before, S.paras); pushVersion(`修改提案後重產（${p.scope.length} 步）`, "AI"); }
    S.objections.push(o); renderTabs(tabs); if (p.scope.includes(0)) renderDocs(); updateChips(); persist(); asstOpen();
    const el = asstAdd("a card rc", `<div class="pc-head"><b>已執行</b><span>重新產生 ${p.scope.map((i) => RV_STEPS[i]).join("、")}；其餘維持</span></div><div class="pc-body"><div>${replies.map((r) => `<div class="rc-item"><span class="note">${esc(r.label)}</span><br>AI：<b class="${r.result === "accept" ? "a" : r.result === "partial" ? "p" : "r"}">${D[r.result]}</b>　${esc(r.reply)}${r.evidence.length ? `<span class="note">　重新檢視：${r.evidence.map((x) => J(x, refTitle(x) + " ↗")).join("、")}</span>` : ""}</div>`).join("")}</div></div><div class="pc-foot"><span class="note">草稿新版本已建立，原版本可於版本紀錄回復</span><button class="ghost-btn" data-tab="4">看草稿 ↗</button>${o.diff && o.diff.length ? `<span class="note">變動 ${o.diff.length} 段</span>` : ""}</div>`);
    el.querySelector("[data-tab]").addEventListener("click", () => $$(".tab")[4].click());
  });
}

/* ---------- 補件：只辨識新檔 → 助手提案 → 確認併入 → 局部重跑 ---------- */
const CORE_TAGS = ["訴願書", "訴願委任書", "答辯書", "答辯書檢送函", "卷證目錄", "裁處書", "裁處書送達證書"];
function docStep(d) { return CORE_TAGS.includes(d.tag) ? 0 : 2; }
function classifyNew(f) {
  const ext = (f.name.match(/\.[a-z0-9]+$/i) || [""])[0].toLowerCase(), kind = /\.(jpg|jpeg|png)$/.test(ext) ? "image" : /\.(mp4|mov)$/.test(ext) ? "video" : "pdf";
  if (f.mock) return { ...structuredClone(f.mock), include: false, staged: true };
  const id = classifyByName(f.name), ref = id ? CASE_B.docs.find((x) => x.id === id) : null;
  if (ref) return { id: "new-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), title: f.name, origName: f.name, stdName: (STD_NAME[id] || ref.title) + ext, tag: ref.tag, src: ref.src, kind, pages: 1, file: null, include: false, staged: true, summary: `Claude 判定：${ref.tag}（${ref.src}）・依內容辨識，非檔名` };
  return { id: "new-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), title: f.name, origName: f.name, stdName: f.name, tag: "其他", src: "未知", kind, pages: 1, file: null, include: false, staged: true, unknown: true, summary: "無法辨識內容，請點標籤指定類型／來源後再提出併入" };
}
/* 真案補件：POST files（同 caseId 累加）→ 輪詢 job → GET files → 新檔進結果視窗（類型／來源／標準檔名來自後端） */
async function addFilesLive(list) {
  const c = S.c, files = list.map((f) => f.file).filter(Boolean);
  if (!files.length) return alert("補件需要實際檔案（示範補件包僅供 mock 案）");
  const pend = files.map((f) => ({ id: "pend-" + Math.random().toString(36).slice(2, 8), title: f.name, origName: f.name, stdName: f.name, tag: "辨識中", src: "未知", kind: "missing", include: false, pending: true, summary: "上傳中…只送這些檔案辨識，既有文件不重跑" }));
  c.docs.push(...pend); renderDocs();
  try {
    const r = await Api.upload(c.caseId, files);
    const ids = new Set((r.files || []).map((x) => x.fileId));
    pend.forEach((p) => { p.summary = "Claude 辨識中…"; }); renderDocs();
    for (;;) { const j = await Api.job(r.jobId); if (j.status === "done" || j.status === "failed") { if (j.status === "failed") throw new Api.ApiError(j.error?.code || "JOB_FAILED", j.error?.message || "辨識失敗"); break; } await new Promise((res) => setTimeout(res, 2000)); }
    const all = toDocs(await Api.listFiles(c.caseId, { includeExcluded: true }));
    const fresh = all.filter((d) => ids.has(d.fileId));
    c.docs = c.docs.filter((d) => !d.pending);
    fresh.forEach((d) => { if (d.dup) { d._new = true; } else { d.staged = true; d.include = false; d.unknown = d.tag === "其他" && d.src === "未知"; } c.docs.push(d); });
    c._allDocs = all; renderDocs(); S.audit.push({ ts: now(), who: "hu", para: "卷宗", action: `補件上傳 ${files.length} 份（重複 ${fresh.filter((d) => d.dup).length}）` });
    openAddModal();
  } catch (e) { c.docs = c.docs.filter((d) => !d.pending); renderDocs(); alert(`補件失敗：${e.message || e.code}`); }
}
function addSupplement(list) {
  const c = S.c; if (!c) return; if (S.status !== "承辦中") return toast(`本案狀態為「${S.status}」，不可補件；請先「另存為新草稿」。`, "err");
  if (c.live && c.caseId) return addFilesLive(list);
  const pend = [];
  list.forEach((f) => {
    const dupOf = c.docs.find((d) => (d.origName || d.title) === f.name || (d.stdName === f.name));
    if (dupOf) { c.docs.push({ id: "dup-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 4), title: f.name, origName: f.name, stdName: f.name, tag: dupOf.tag, src: dupOf.src, kind: "missing", include: false, dup: true, _new: true, summary: `與「${dupOf.stdName || dupOf.title}」相同，已排除，不重跑` }); return; }
    const d = { id: "pend-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 4), title: f.name, origName: f.name, stdName: f.name, tag: "辨識中", src: "未知", kind: "missing", include: false, pending: true, summary: "Claude 辨識中…（只送這份，不重跑既有文件）", _f: f };
    c.docs.push(d); pend.push(d);
  });
  renderDocs(); S.audit.push({ ts: now(), who: "hu", para: "卷宗", action: `補件上傳 ${list.length} 份（重複 ${list.length - pend.length}）` });
  if (!pend.length) { openAddModal(); return; }
  setTimeout(() => {
    pend.forEach((p) => { const i = c.docs.indexOf(p); const d = classifyNew(p._f); c.docs[i] = d; });
    renderDocs(); openAddModal();
  }, 900 + pend.length * 450);
}
function openAddModal() {
  const c = S.c, staged = c.docs.filter((d) => d.staged && !d.include), dups = c.docs.filter((d) => d.dup && d._new); if (!staged.length && !dups.length) return;
  const rows = staged.map((d) => `<tr data-id="${d.id}" class="${d.unknown ? "unk" : ""}"><td class="num" style="color:var(--ink-3)">${esc(d.origName)}</td><td><b>${esc(d.stdName)}</b></td><td><select class="am-type">${TYPES.map((t) => `<option ${d.tag === t ? "selected" : ""}>${t}</option>`).join("")}</select></td><td><select class="am-src">${SRC_ORDER.map((t) => `<option ${d.src === t ? "selected" : ""}>${t}</option>`).join("")}</select></td><td>${KIND[d.kind] || d.kind}・${d.pages || 1} 頁</td><td class="note">${d.unknown ? `<span style="color:var(--seal)">無法辨識，請指定類型／來源</span>` : esc(d.summary || "")}</td></tr>`).join("")
    + dups.map((d) => `<tr class="dupr"><td class="num" style="color:var(--ink-3)">${esc(d.origName)}</td><td>—</td><td colspan="3"><span class="tag neutral" style="font-size:10px">重複</span></td><td class="note">${esc(d.summary)}</td></tr>`).join("");
  $("#amBody").innerHTML = rows; $("#amCount").textContent = `辨識 ${staged.length} 份・重複 ${dups.length} 份（僅新檔送 Claude 辨識，既有 ${c.docs.length - staged.length - dups.length} 份未重跑）`;
  $("#amImport").textContent = `匯入 ${staged.length} 份`; $("#amImport").disabled = !staged.length;
  $$("#amBody select").forEach((sel) => sel.addEventListener("change", async () => { const tr = sel.closest("tr"), d = c.docs.find((x) => x.id === tr.dataset.id); d.tag = tr.querySelector(".am-type").value; d.src = tr.querySelector(".am-src").value; if (d.unknown) { d.unknown = false; d.summary = `承辦人指定：${d.tag}（${d.src}）`; tr.classList.remove("unk"); tr.lastElementChild.textContent = d.summary; }
    if (c.live && c.caseId && d.fileId) { try { await Api.patchFile(c.caseId, d.fileId, { segIndex: d.segIndex ?? 0, doc_type: d.tag, source: d.src, by: "承辦人" }); } catch (e) { tr.lastElementChild.textContent = `後端更新失敗：${e.message || e.code}`; } } }));
  $("#addModal").classList.add("on");
}
$("#amX").addEventListener("click", () => $("#amCancel").click());
$("#amCancel").addEventListener("click", () => { const c = S.c; c.docs = c.docs.filter((d) => !(d.staged && !d.include) && !(d.dup && d._new)); renderDocs(); $("#addModal").classList.remove("on"); });
$("#amImport").addEventListener("click", () => {
  const c = S.c, staged = c.docs.filter((d) => d.staged && !d.include); c.docs.forEach((d) => { if (d.dup && d._new) delete d._new; });
  staged.forEach((d) => { d.include = true; d.staged = false; d.imported = today(); });
  if (c.live && c._allDocs) { c.docs = c._allDocs.map((d) => { const s = staged.find((x) => x.id === d.id); return s ? { ...d, tag: s.tag, src: s.src, imported: s.imported } : d; }).filter((d) => !d.dup || false); delete c._allDocs; }
  S.audit.push({ ts: now(), who: "hu", para: "卷宗", action: `補件匯入 ${staged.length} 份：${staged.map((d) => `${d.stdName}（${d.tag}／${d.src}）`).join("、")}` });
  $("#addModal").classList.remove("on"); renderDocs(); persist(); if (staged[0]) openDoc(staged[0].id); if (S.c.docs.some((d) => d.imported)) asstSuggest();
});
$("#addBtn").addEventListener("click", () => { if (S.status !== "承辦中") return alert(`本案狀態為「${S.status}」，不可補件；請先「另存為新草稿」。`); $("#addFile").click(); });
$("#addFile").addEventListener("change", () => { const fs = [...$("#addFile").files].map((f) => ({ name: f.name, size: f.size, file: f })); $("#addFile").value = ""; if (fs.length) addSupplement(fs); });
$("#addDemo").addEventListener("click", () => { const sup = S.c?.supplement; if (!sup) return; addSupplement(sup.files.map(([name, size], i) => ({ name, size, mock: sup.docs[i] }))); $("#addDemo").style.display = "none"; });
{ const pane = $("#docPane"); ["dragenter", "dragover"].forEach((ev) => pane.addEventListener(ev, (e) => { e.preventDefault(); pane.classList.add("over"); })); ["dragleave", "drop"].forEach((ev) => pane.addEventListener(ev, (e) => { e.preventDefault(); pane.classList.remove("over"); })); pane.addEventListener("drop", (e) => { const fs = [...(e.dataTransfer?.files || [])].map((f) => ({ name: f.name, size: f.size, file: f })); if (fs.length) addSupplement(fs); }); }
/* ---------- 助手：真案走後端 chat；mock 案走本機規則 ---------- */
const CHAT_HIST = [];   // 目前案件的對話（重整頁面自 sessionStorage 還原）
function histKey() { return "ssz.chat." + (S.c?.caseId || S.c?.id || ""); }
function histLoad() { CHAT_HIST.length = 0; try { (JSON.parse(sessionStorage.getItem(histKey()) || "[]")).forEach((h) => CHAT_HIST.push(h)); } catch {} }
function histSave() { if (isLiveCase()) return; try { sessionStorage.setItem(histKey(), JSON.stringify(CHAT_HIST.slice(-20))); } catch {} }
function isLiveCase() { const c = S.c; return !!(c && c.live && c.caseId && !c.analysisPending); }
let CHAT_BUSY = false;
async function asstSendLive(q) {
  const c = S.c, tab = +($(".tab.on")?.dataset.t || 0), t0 = Date.now();
  if (CHAT_BUSY) return asstAdd("a", `<span class="sysnote">上一則還在處理中，請稍候。</span>`);
  CHAT_BUSY = true; $("#asstSend").disabled = true; $("#asstSend").textContent = "處理中…";
  const wait = asstAdd("a", `<span class="typing">AI 查詢中…（一般 5–10 秒；提案含法條查核約 10–20 秒）</span>`);
  try {
    const res = await Api.chat(c.caseId, { message: q, tab, readonly: S.status !== "承辦中", history: CHAT_HIST.slice(-6) });
    console.info("[chat]", res.kind, Date.now() - t0, "ms", res.usage, res.tool_calls?.map((t) => t.name));
    wait.remove(); CHAT_HIST.push({ role: "user", text: q }, { role: "assistant", kind: res.kind, text: res.text || "", proposalId: res.proposal?.id, proposalState: res.proposal ? "pending" : null }); histSave();
    try { renderServerReply(res); } catch (e) { console.error("[chat] render failed", e, res); asstAdd("a", `回覆已收到但畫面無法呈現：${esc(e.message)}<span class="src">${esc((res.text || "").slice(0, 300))}</span>`); }
  } catch (e) { console.error("[chat] failed", e); wait.remove(); asstAdd("a", `助手暫時無法回應：${esc(e.message || e.code)}<span class="src">${esc(e.code || "")}　${Math.round((Date.now() - t0) / 1000)} 秒後放棄；可直接重送同一句</span>`); }
  finally { CHAT_BUSY = false; $("#asstSend").disabled = false; $("#asstSend").textContent = "送出"; }
}
/* 後端回覆 → 畫面；answer／clarify／refuse 是文字卡，proposal 走 renderProposal（同一套元件） */
function renderServerReply(res) {
  if (res.kind === "proposal" && res.proposal) { const p = fromServerProposal(res.proposal, res.text), el = renderProposal(p); loadPreview(p, el); return el; }
  const src = (res.sources || []).map((s) => {
    if (s.type === "doc" && s.fileId) { const d = S.c.docs.find((x) => x.fileId === s.fileId); return d ? `<span class="jump" data-doc="${d.id}">《${esc(s.title)}》${s.page ? " 第 " + s.page + " 頁" : ""} ↗</span>` : esc(s.title); }
    return `${{ law: "法規", decision: "決定書", state: "分析結果" }[s.type] || ""}：${esc(s.title)}${s.version ? `（${esc(s.version)} 版）` : ""}`;
  });
  const offer = res.kind === "answer" && res.cite_offer && S.status === "承辦中" ? `<button class="ghost-btn open" data-cite="1">以此提出修改 →</button>` : "";
  const el = asstAdd("a", `${esc(res.text || "").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/^#{1,4}\s*/gm, "").replace(/\n/g, "<br>")}${src.length ? `<span class="src">來源：${src.join("、")}</span>` : ""}${offer}`);
  el.querySelectorAll("[data-doc]").forEach((j) => j.addEventListener("click", () => openDoc(j.dataset.doc)));
  el.querySelector("[data-cite]")?.addEventListener("click", () => { const o = res.cite_offer; $("#asstIn").value = `請加引${o.law}第 ${o.article} 條${o.para ? `第 ${o.para} 項` : ""}`; asstSend(); });
  return el;
}
/* 提案預覽：後端只改寫受影響段落（≤3 段），回來後把卡片裡的「將改寫的段落」換成真 diff */
async function loadPreview(p, el) {
  const c = S.c; if (!(c && c.live && c.caseId && p.server)) return;
  const need = p.items.some((it) => ["text", "frame", "verdict"].includes(it.type) || (it.type === "law" && it.ok));
  if (!need) return;
  const body = el.querySelector(".pc-body"), note = document.createElement("div"); note.className = "pc-item"; note.innerHTML = `<div class="lab">草稿變動預覽</div><div class="bd"><span class="typing">AI 正在改寫受影響段落以供預覽（約 10–20 秒）…</span></div>`;
  body.insertBefore(note, body.lastElementChild);
  try {
    const r = await Api.previewProposal(c.caseId, p.id);
    if (!r.previews || !r.previews.length) { note.querySelector(".bd").innerHTML = `<span class="note">${r.busy ? "後端忙碌中，確認執行後仍會重產" : "此提案無段落級預覽；確認執行後於草稿頁版本 diff 檢視"}</span>`; return; }
    note.querySelector(".bd").innerHTML = r.previews.map((x) => `<div class="pc-diff diffbox"><span class="pl">${esc(x.para)}（修改前 → 修改後）</span>${fillDates(diffHtml(x.before, x.after))}</div>`).join("") + `<div class="note">預覽由 AI 改寫該段產生；確認執行後會依影響範圍重產整份草稿，最終文字可能略有不同。</div>`;
    el.querySelectorAll(".pc-item").forEach((it) => { if (it !== note && /將改寫的段落/.test(it.textContent)) it.remove(); });
  } catch (e) { note.querySelector(".bd").innerHTML = `<span class="note">預覽失敗：${esc(e.message || e.code)}</span>`; }
}
/* 伺服器提案（契約 §2）→ renderProposal 期望的欄位 */
function fromServerProposal(sp, text) {
  const c = S.c, code = (f) => f === "採機關" ? "agency" : f === "採訴願人" ? "appellant" : "open", jp = currentPlan();
  const items = sp.items.map((it) => {
    if (it.type === "issue") { const is = c.issues.find((x) => x.id === it.id); return { ...it, n: it.n || (is ? c.issues.indexOf(is) + 1 : "?"), title: it.title || is?.title || it.id, from: code(it.from), verdictTo: null, label: `爭點 ${it.n}：${{ appellant: "採訴願人", agency: "採機關", drop: "刪除" }[it.to] || it.to}` }; }
    if (it.type === "issue-new") return { ...it, label: `新增爭點：${it.title}` };
    if (it.type === "reissue") { const is = c.issues.find((x) => x.id === it.id); return { ...it, n: it.n || "?", title: it.title || is?.title || it.id, aFrom: is?.a?.[0] || "", aTo: is?.a?.[0] || "", eAdd: (it.docs || []).map((f) => [c.docs.find((d) => d.fileId === f)?.stdName || f, null]), note: "", label: `爭點 ${it.n}：納入補件重新審查` }; }
    if (it.type === "law" || it.type === "law-rm") return { ...it, lib: it.amended ? { date: it.amended } : null, label: `${it.type === "law-rm" ? "移除引用" : "加引"}：${it.key}` };
    if (it.type === "served") return { ...it, from: it.from || S.served, due: it.deadline || "—", over: it.inTime === null ? null : !it.inTime, left: it.daysLeft, label: `送達日：${it.from} → ${it.v}` };
    if (it.type === "proc") return { ...it, label: it.v === "merit" ? "程序：進入實體審查" : `程序：依訴願法 §77 (${String(it.v).split("-")[1] || "?"}) 不受理` };
    if (it.type === "verdict") return { ...it, verdictTo: it.to, artTo: "", label: `結論：${it.from || jp.verdict} → ${it.to}` };
    if (it.type === "text") { const pa = S.paras.find((x) => paraLabel(x) === it.para); return { ...it, lab: it.para, before: pa ? plain(pa.text) : "", after: pa ? plain(pa.text) : "", label: `文字：${it.para}（${it.how}）`, previewLater: true }; }
    if (it.type === "frame") { const pa = S.paras.find((x) => x.id.startsWith("r") && x.kind !== "h4"); return { ...it, lab: pa ? paraLabel(pa) : "理由", before: pa ? plain(pa.text) : "", after: pa ? plain(pa.text) : "", label: `論述角度：${it.angle}`, previewLater: true }; }
    return { ...it, label: JSON.stringify(it) };
  });
  return { id: sp.id, q: sp.message || text || "", items, scope: sp.scope || scopeOf(items), planTo: null, server: sp, summary: sp.summary };
}
function asstSend() {
  const q = $("#asstIn").value.trim(); if (!q || !S.c) return; $("#asstIn").value = ""; $("#asstIn").style.height = ""; asstAdd("u", esc(q).replace(/\n/g, "<br>"));
  const c = S.c;
  if (isLiveCase()) return asstSendLive(q);
  if (S.status !== "承辦中" && EDIT_RE.test(q)) return asstAdd("a", `本案狀態為「${S.status}」，不可修改。已結案案件請用「另存為新草稿」。`);
  const intent = /[?？]|有沒有|嗎|哪|是什麼/.test(q) ? null : parseIntent(q); if (intent) { if (intent.clarify) return asstAdd("a", intent.clarify); return renderProposal(buildProposal(intent.items, q)); }
  const lk = /([一-龥]{2,24}?(?:法|條例|準則|規則|辦法))\s*第?\s*(\d+)\s*條(?:\s*第?\s*(\d+)\s*項)?(?:\s*第?\s*(\d+)\s*款)?/.exec(q);
  if (lk) { const name = lawName(lk[1]), art = lk[2], para = lk[3], kuan = lk[4], lib = LAWLIB.find((l) => l.n === name), key = `${name} 第 ${art} 條${para ? `第 ${para} 項` : ""}${kuan ? `第 ${kuan} 款` : ""}`; const hit = c.laws.find((l) => l.n.startsWith(`${name} 第 ${art} 條`)) || (ART_TEXT[key] ? { n: key, t: ART_TEXT[key] } : null); if (!lib) return asstAdd("a", `法規庫查無「${esc(name)}」，無法提供條文；請確認法規名稱。<span class="src">來源：法規庫（${LAWLIB.length} 部）</span>`); if (lib.arts && +art > lib.arts) return asstAdd("a", `${esc(name)} 僅 ${lib.arts} 條，第 ${art} 條不存在。<span class="src">來源：法規庫・${lib.date} 版</span>`); const el = asstAdd("a", `<b>${esc(hit ? hit.n : key)}</b>（${lib.date} 版${lib.effective ? "，" + lib.effective + " 施行" : ""}）<br>${hit ? esc(hit.t) : "本條未在本案推薦清單內；正式版由後端法規字典帶入全文。"}<span class="src">來源：法規庫・全國法規資料庫同步</span><button class="ghost-btn open" data-cite="${esc(key)}">以此提出修改 →</button>`); el.querySelector("[data-cite]").addEventListener("click", () => { $("#asstIn").value = `請加引${key}`; asstSend(); }); return el; }
  if (/法條|引用|法規|援引/.test(q)) return asstAdd("a", c.citations.length ? `答辯書引用 ${c.citations.length} 則：<br>${c.citations.map((x) => `・${J(x.ref, esc(x.n))}　<span class="st ${x.status}" style="font-size:10px">${{ ok: "已驗證", amended: "已修正", gap: "漏引" }[x.status] || x.status}</span>`).join("<br>")}<span class="src">來源：法規推薦分頁・引用查核</span>` : `本案尚無答辯書可查核。<span class="src">${esc(c.citationNote || "")}</span>`);
  { const m = /爭點\s*([一二三四五六\d])[^。]*?(卷證|證據|在哪)/.exec(q); if (m) { const it = c.issues[(CN[m[1]] || +m[1]) - 1]; if (it) return asstAdd("a", `爭點 ${(CN[m[1]] || +m[1])}「${esc(it.title)}」的卷證：<br>${it.e.map((e) => e[1] ? `・${J(e[1], esc(e[0]) + " ↗")}` : `・${esc(e[0])}`).join("<br>")}<span class="src">來源：爭點分頁・卷證顯示欄</span>`); } }
  if (/相似|案例/.test(q) && /分布|結論|撤銷|駁回|不受理/.test(q)) { const sims = c.sims || [], want = /撤銷/.test(q) ? "撤銷" : /駁回/.test(q) ? "駁回" : /不受理/.test(q) ? "不受理" : null, hit = want ? sims.filter((s) => (s.fn || "").includes(want)) : sims; return asstAdd("a", hit.length ? `${want ? `結論為「${want}」的相似案例 ${hit.length} 件` : `相似案例 ${sims.length} 件，結論分布：${(c.simDist || []).map((d) => `${d[0]} ${d[1]}`).join("、")}`}：<br>${hit.slice(0, 5).map((s) => `・${esc(s.fn)}`).join("<br>")}<span class="src">來源：相似案例分頁（KB 檢索＋規則重排）</span>` : `相似案例中沒有結論為「${want}」者。<span class="src">來源：相似案例分頁</span>`); }
  if (/是什麼|內容|全文/.test(q) && /函|準則|釋字|判/.test(q)) { const p = pendingCites().find((x) => q.includes(x.n.replace(/（.*$/, "").slice(0, 14))); if (p) return asstAdd("a", `「${esc(p.n)}」法規庫未收錄，無法提供內容；${esc(p.note || "")}<span class="src">來源：法規推薦分頁・引用查核</span>`); }
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
$("#asstSend").addEventListener("click", asstSend);
/* 中文輸入法：組字中的 Enter 是選字不是送出。isComposing 為主；Safari 在 compositionend 那一下 keyCode 229 且 isComposing 已 false，用旗標多擋一拍 */
let composing = false, composedAt = 0;
$("#asstIn").addEventListener("compositionstart", () => { composing = true; });
$("#asstIn").addEventListener("compositionend", () => { composing = false; composedAt = Date.now(); });
function enterIsSend(e) { return e.key === "Enter" && !e.isComposing && !composing && e.keyCode !== 229 && Date.now() - composedAt > 60; }
$("#asstIn").addEventListener("keydown", (e) => { if (e.shiftKey) return; if (enterIsSend(e)) { e.preventDefault(); asstSend(); } });

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


/* =========================================================
   網址路由（hash）：#/ 首頁　#/lib 案件庫　#/law 法規庫　#/run/{caseId} 分析中　#/case/{id}[/{tab 1–5}]
   id 可為：案件庫 libId、示範案 id（A/B/C）、真上傳 caseId。程式內切換用 replaceState，不觸發 hashchange。
   ========================================================= */
const Router = {
  set(path) { const h = "#" + path; if (location.hash !== h) history.replaceState(null, "", h); },
  parse() { const m = /^#\/?([a-z]*)\/?([^/]*)\/?(\d)?/.exec(location.hash || "#/"); return { view: m?.[1] || "", id: m?.[2] ? decodeURIComponent(m[2]) : "", tab: m?.[3] ? +m[3] : 0 }; },
  async go() {
    const r = Router.parse();
    if (r.view === "lib") return openLibrary();
    if (r.view === "law") return openLawLib();
    if ((r.view === "case" || r.view === "run") && r.id) {
      const cur = S.c && (S.libId === r.id || S.c.caseId === r.id || S.c.id === r.id);
      if (!cur) {
        const rec = LIB.find((x) => x.libId === r.id);
        const mock = CASES.find((x) => x.id === r.id && !x.demoOnly);
        if (rec) openRecord(rec);
        else if (mock) runCase(structuredClone(mock), false);
        else await resumeLive(r.id);
      }
      if (r.tab && $$(".tab")[r.tab - 1] && !$$(".tab")[r.tab - 1].disabled) $$(".tab")[r.tab - 1].click();
      return;
    }
    if ($("#s-pick") && !$("#s-pick").classList.contains("on") && r.view === "") $("#backBtn").click();
  },
};
/** 直接開 #/case/{caseId}：有分析結果就進工作畫面；分析中就接上進度；只有歸戶結果就先分析 */
async function resumeLive(caseId) {
  let doc = null;
  try { doc = await Api.analysis(caseId); } catch (e) { if (e.status !== 404) return toast(`讀取案件失敗：${e.message}`, "err"); }
  if (doc && doc.status.state === "done") return enterWork(caseId, doc);
  let payload;
  try { payload = await Api.listFiles(caseId); } catch (e) { $("#runSub").textContent = ""; show("s-pick"); Router.set("/"); alert(`找不到案件 ${caseId}`); return; }
  $("#chip").classList.add("on"); setCrumb($("#s-run").classList.contains("on") ? "分析中" : "案件審理"); $("#chipName").textContent = payload.files.find((f) => f.segments?.[0]?.party_hint)?.segments[0].party_hint || "上傳案件"; $("#chipNo").textContent = `暫編 ${caseId}`; $("#backBtn").style.display = "";
  $("#runSub").textContent = `${payload.files.length} 個檔案　・　${caseId}`;
  $("#stepList").innerHTML = LIVE_STEPS.map(([name], i) => `<div class="step ${i === 0 ? "done" : ""}" id="st${i}"><div class="idx">${i + 1}</div><div><div class="name">${name}</div><div class="out" id="so${i}">${i === 0 ? `${payload.files.length} 份已辨識` : ""}</div></div><div class="ms" id="sm${i}"></div></div>`).join("");
  $("#runBar").style.width = "20%"; show("s-run");
  const pending = payload.files.some((f) => f.status === "queued" || f.status === "processing");
  if (pending) { $("#runTitle").textContent = "文件辨識進行中"; $("#so0").textContent = "辨識尚未完成，請稍後重新整理"; return; }
  try { await runAnalysis(caseId, { post: !(doc && doc.status.state === "running") }); }
  catch (e) { $("#runTitle").textContent = "分析失敗"; $("#so1").innerHTML = `<span style="color:var(--seal)">${esc(e.code || "ERROR")}：${esc(e.message || "")}</span>`; }
}
window.addEventListener("hashchange", () => Router.go());
Router.go();
loadLawlib();
