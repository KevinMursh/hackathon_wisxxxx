/* =========================================================
   訴願智審臺 v2　應用邏輯（純前端）
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
const J = (ref, text) => ref ? `<span class="jump" data-jump="${ref}">${text}</span>` : text;

/* ---------- 全域狀態 ---------- */
const S = { c: null, served: null, recv: null, stances: {}, plan: null, paras: [], versions: [], audit: [], sel: null, doc: null, zoom: 1, live: false };

/* ---------- 主題 ---------- */
$("#themeBtn").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
  $("#themeBtn").textContent = dark ? "切換深色" : "切換淺色";
});

/* =========================================================
   畫面 1：多檔案上傳
   ========================================================= */
let FILES = []; // {name, kb, tag, docId, pending}

function classifyFile(name) {
  const n = name.toLowerCase();
  const rules = [
    [/訴願書/, "訴願書", "appeal"], [/答辯/, "答辯書", "defense"], [/送達證書|送達/, "送達證書", "served"],
    [/裁處書|處分書/, "裁處書", "penalty"], [/檢舉/, "檢舉資料", "complaint"], [/稽查/, "稽查紀錄", "insp"],
    [/放大/, "影像放大", "zoom"], [/照片|img_|photo/, "採證照片", "ph1"], [/車籍|監理/, "車籍資料", "vehicle"],
    [/通知書/, "通知書", "notice"], [/陳述意見書|陳述/, "陳述意見書", "statement"], [/係數|計算/, "係數計算", "coef"],
    [/簽呈|簽/, "簽呈", "memo"], [/\.(mp4|mov)$/, "影片", "video"], [/目錄/, "卷證目錄", "index"], [/筆錄/, "調查筆錄", "record"],
  ];
  for (const [re, t, d] of rules) if (re.test(n) || re.test(name)) return [t, d];
  return ["其他", null];
}

function renderFiles() {
  const box = $("#fileList");
  box.innerHTML = FILES.map((f, i) => `
    <div class="filerow ${f.pending ? "pending" : ""}">
      <span class="fn" title="${esc(f.name)}">${esc(f.name)}</span>
      <span class="sz num">${f.kb} KB</span>
      <span class="tag ${DOCTAG[f.tag] || "neutral"}">${f.pending ? "辨識中…" : f.tag}</span>
      <button class="rm" data-i="${i}" title="移除">×</button>
    </div>`).join("");
  $$(".rm", box).forEach((b) => b.addEventListener("click", () => { FILES.splice(+b.dataset.i, 1); renderFiles(); }));
  const n = FILES.length, kb = FILES.reduce((a, f) => a + f.kb, 0);
  const kinds = new Set(FILES.map((f) => f.tag));
  $("#runBtn").disabled = n === 0;
  $("#fileHint").textContent = n === 0 ? "尚未加入檔案" : `${n} 個檔案・${(kb / 1024).toFixed(1)} MB・${kinds.size} 種文件類型${kinds.has("訴願書") ? "" : "（缺訴願書）"}`;
}

function addFiles(list) {
  Array.from(list).forEach((f) => {
    if (FILES.some((x) => x.name === f.name)) return;
    const [tag, docId] = classifyFile(f.name);
    const row = { name: f.name, kb: Math.max(1, Math.round((f.size || 0) / 1024)), tag, docId, pending: true };
    FILES.push(row);
    setTimeout(() => { row.pending = false; renderFiles(); }, 350 + Math.random() * 500);
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

$("#packBtn").addEventListener("click", () => {
  FILES = CASE_B.files.map(([name, kb, tag, docId]) => ({ name, kb, tag, docId, pending: true }));
  renderFiles();
  FILES.forEach((f, i) => setTimeout(() => { f.pending = false; renderFiles(); }, 120 + i * 90));
});
$("#clearBtn").addEventListener("click", () => { FILES = []; renderFiles(); });
$("#runBtn").addEventListener("click", () => {
  const has = (t) => FILES.some((f) => f.tag === t);
  const base = has("調查筆錄") ? CASE_C : CASE_B;
  const c = structuredClone(base);
  // 以上傳清單覆蓋卷宗瀏覽器：只顯示有對應文件者，其餘標示未納入
  const uploaded = FILES.map((f) => f.docId).filter(Boolean);
  const known = new Set(base.docs.map((d) => d.id));
  const extra = FILES.filter((f) => !f.docId || !known.has(f.docId)).map((f) => ({ id: "x-" + f.name, title: f.name, tag: f.tag, kind: "missing", note: "本原型未內建此類文件之解析，已列入卷宗但未納入分析。" }));
  const usePh = uploaded.includes("ph1");
  c.docs = base.docs.filter((d) => uploaded.includes(d.id) || (usePh && /^ph[23]$/.test(d.id))).concat(extra);
  if (!c.docs.length) c.docs = base.docs.slice();
  c.uploadNote = `使用者上傳 ${FILES.length} 個檔案；依檔名辨識類型後，以 ${base.id === "C" ? "洗錢防制法案" : "case02 卷宗包"}示範後續流程。`;
  runCase(c);
});

/* ---------- QR 手機上傳（示範） ---------- */
function drawQR() {
  const cv = $("#qrCanvas"), ctx = cv.getContext("2d"), N = 41;
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, N, N);
  let seed = Date.now() % 100000;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  ctx.fillStyle = "#000";
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) if (rnd() > 0.55) ctx.fillRect(x, y, 1, 1);
  const finder = (ox, oy) => { ctx.fillStyle = "#fff"; ctx.fillRect(ox - 1, oy - 1, 9, 9); ctx.fillStyle = "#000"; ctx.fillRect(ox, oy, 7, 7); ctx.fillStyle = "#fff"; ctx.fillRect(ox + 1, oy + 1, 5, 5); ctx.fillStyle = "#000"; ctx.fillRect(ox + 2, oy + 2, 3, 3); };
  finder(0, 0); finder(N - 7, 0); finder(0, N - 7);
  const code = Array.from({ length: 6 }, () => "ABCDEFGHJKMNPQRSTUVWXYZ23456789"[Math.floor(rnd() * 31)]).join("");
  $("#qrCode").textContent = code.slice(0, 3) + "-" + code.slice(3);
}
let phoneFiles = [];
$("#qrBtn").addEventListener("click", () => { drawQR(); phoneFiles = []; $("#phoneFeed").innerHTML = ""; $("#phoneState").textContent = "等待掃碼…"; $("#qrDone").disabled = true; $("#qrModal").classList.add("on"); });
$("#qrClose").addEventListener("click", () => $("#qrModal").classList.remove("on"));
$("#simScan").addEventListener("click", () => {
  const feed = $("#phoneFeed");
  $("#phoneState").textContent = "iPhone・已連線";
  const shots = [["送達證書（拍照）.jpg", 1840, "送達證書", "served"], ["稽查工作紀錄表（拍照）.jpg", 2110, "稽查紀錄", "insp"], ["陳述意見書（拍照）.jpg", 1970, "陳述意見書", "statement"]];
  let t = 0;
  shots.forEach(([name, kb, tag, docId], i) => {
    setTimeout(() => {
      const row = document.createElement("div");
      row.innerHTML = `<span class="prog">拍攝 ${esc(name)}　上傳中</span><div class="bar"><i style="width:0"></i></div>`;
      feed.appendChild(row); feed.scrollTop = feed.scrollHeight;
      const bar = $("i", row); let p = 0;
      const iv = setInterval(() => { p = Math.min(100, p + 9 + Math.random() * 14); bar.style.width = p + "%"; if (p >= 100) { clearInterval(iv); row.innerHTML = `<span class="ok">✓ ${esc(name)}　${kb} KB　已辨識為「${tag}」</span>`; phoneFiles.push({ name, kb, tag, docId, pending: false }); if (i === shots.length - 1) { $("#qrDone").disabled = false; $("#phoneState").textContent = "上傳完成"; } } }, 120);
    }, t);
    t += 1400;
  });
});
$("#qrDone").addEventListener("click", () => { phoneFiles.forEach((f) => { if (!FILES.some((x) => x.name === f.name)) FILES.push(f); }); renderFiles(); $("#qrModal").classList.remove("on"); });

/* ---------- 貼上文字（即時解析） ---------- */
const pasteBox = $("#pasteBox"), parseBtn = $("#parseBtn"), pasteHint = $("#pasteHint");
function syncPaste() { const n = pasteBox.value.trim().length; parseBtn.disabled = n < 40; pasteHint.textContent = n === 0 ? "尚未輸入內容" : n < 40 ? `已輸入 ${n} 字，至少需 40 字` : `已輸入 ${n} 字，可解析`; }
pasteBox.addEventListener("input", syncPaste); syncPaste();
$("#sampleBtn").addEventListener("click", () => { pasteBox.value = SAMPLE_TEXT; syncPaste(); pasteBox.focus(); });
parseBtn.addEventListener("click", () => { const raw = pasteBox.value.trim(); if (raw.length >= 40) runCase(buildLive(parseAppeal(raw))); });

/* ---------- 示範案件卡 ---------- */
$("#caseGrid").innerHTML = CASES.map((c, i) => `
  <button class="case-card" data-i="${i}">
    <span class="no num">案號 ${c.no}</span><h3>${c.cardTitle}</h3><p>${c.cardDesc}</p>
    <div style="display:flex;flex-wrap:wrap;gap:6px">${c.cardTags.join("")}</div>
    <div class="foot"><span>${c.name}</span><span class="go">開始分析 →</span></div>
  </button>`).join("");
$$(".case-card").forEach((el) => el.addEventListener("click", () => runCase(structuredClone(CASES[+el.dataset.i]))));

$("#backBtn").addEventListener("click", () => { show("s-pick"); $("#chip").classList.remove("on"); $("#planChip").classList.remove("on"); $("#backBtn").style.display = "none"; });
function show(id) { $$(".screen").forEach((s) => s.classList.toggle("on", s.id === id)); window.scrollTo(0, 0); }

/* =========================================================
   即時解析引擎（貼上文字路徑）
   ========================================================= */
function findDates(text) {
  const out = [], re = /(?:民國\s*)?(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日/g; let m;
  while ((m = re.exec(text))) { const y = +m[1], mo = +m[2], d = +m[3]; if (y < 90 || y > 130 || mo < 1 || mo > 12 || d < 1 || d > 31) continue; out.push({ raw: m[0], idx: m.index, iso: `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`, t: Date.UTC(y + 1911, mo - 1, d) }); }
  return out;
}
function dateNear(text, dates, keys, win = 60) {
  for (const k of keys) { let from = 0, i; while ((i = text.indexOf(k, from)) >= 0) { let best = null, bd = Infinity; for (const d of dates) { const dist = d.idx < i ? i - (d.idx + d.raw.length) : d.idx - i; if (dist <= win && dist < bd) { bd = dist; best = d; } } if (best) return best; from = i + k.length; } }
  return null;
}
const firstMatch = (t, re) => { const m = t.match(re); return m ? (m[1] || m[0]).trim() : null; };
function classifySubject(text) { let best = null, bn = 0; for (const [s, ks] of SUBJ_KEYS) { const n = ks.reduce((a, k) => a + (text.includes(k) ? (k.length > 4 ? 2 : 1) : 0), 0); if (n > bn) { bn = n; best = s; } } return { subj: best, hits: bn }; }
const famOf = (s) => FAMILY.findIndex((f) => f.includes(s));
function searchDocs(subj, art, n = 5) {
  const fam = famOf(subj);
  return DOC_INDEX.map((d) => { let s = 8; if (subj && d.subj === subj) s += 46; else if (fam >= 0 && famOf(d.subj) === fam) s += 21; if (art && d.art.indexOf(art) >= 0) s += 33; s += Math.max(0, 10 - (114 - d.y) * 2.5); return { ...d, s: Math.min(97, Math.round(s)) }; })
    .sort((a, b) => b.s - a.s || b.y - a.y).slice(0, n);
}
function whyDoc(d, q) { const b = []; if (d.subj === q.subj) b.push("案由完全相同"); else if (famOf(d.subj) >= 0 && famOf(d.subj) === famOf(q.subj)) b.push("同屬相近法規領域"); if (q.art && d.art.indexOf(q.art) >= 0) b.push(`同以訴願法 ${q.art} 作成決定`); if (d.y >= 113) b.push("近年決定書，格式為新版"); if (d.res.indexOf("撤銷") >= 0) b.push("結果為撤銷，建議作為反面對照"); return b.length ? b.join("；") + "。" : "案由與法條部分相符，可供文字結構參考。"; }

function parseAppeal(raw) {
  const t0 = performance.now(), text = raw.replace(/\r/g, "").trim(), dates = findDates(text);
  const applicant = firstMatch(text, /訴願人[：:　\s]*([一-龥○Ｏ]{2,5})/), agent = firstMatch(text, /代理人[：:　\s]*([一-龥○Ｏ]{2,5})/);
  const agency = firstMatch(text, /(新北市政府[一-龥]{2,10}(?:分局|局|處))|(新北市[一-龥]{1,4}區公所)|(新北市政府)/);
  const orderNo = (firstMatch(text, /([一-龥]{2,8}字第?\s*[0-9A-Za-z][0-9A-Za-z\-]{3,}\s*號?)/) || "").replace(/^[日月年時分號第許起至]+/, "").trim() || null;
  const amount = firstMatch(text, /(?:新臺幣|新台幣)?\s*([\d,]{3,})\s*元/);
  const dServed = dateNear(text, dates, ["送達", "收受", "簽收", "收到"]), dReceived = dateNear(text, dates, ["收文", "提起本件訴願", "提起訴願", "遞狀"]);
  const dOrder = dateNear(text, dates, ["裁處書", "處分書", "告誡", "原處分", "所為之處分"]) || dates[0] || null;
  const { subj, hits } = classifySubject(text);
  const receiverOther = /配偶|同居|家人|代為簽收|代收|舍弟|舍妹|管理員/.test(text);
  return { text, dates, applicant, agent, agency, orderNo, amount, dServed, dReceived, dOrder, subj, hits, receiverOther, ms: Math.max(1, Math.round(performance.now() - t0)) };
}

function buildLive(p) {
  const Sj = p.subj || "未判定";
  const marks = [["ap-applicant", p.applicant], ["ap-agent", p.agent], ["ap-agency", p.agency], ["ap-orderno", p.orderNo], ["ap-amount", p.amount], ["ap-served", p.dServed && p.dServed.raw], ["ap-recv", p.dReceived && p.dReceived.raw], ["ap-orderdate", p.dOrder && p.dOrder.raw]];
  let html = esc(p.text);
  marks.forEach(([ref, v]) => { if (!v) return; const t = esc(v), i = html.indexOf(t); if (i < 0) return; html = html.slice(0, i) + `<mark data-ref="${ref}">` + t + "</mark>" + html.slice(i + t.length); });
  const doc = `<div class="doc-meta num">來源：貼上文字<br>字數：${p.text.length}　偵測日期：${p.dates.length} 處　解析耗時：${p.ms} ms</div>` + html.split(/\n+/).filter((s) => s.trim()).map((s) => `<p>${s}</p>`).join("");
  const refs = {}; marks.forEach(([r, v]) => { if (v) refs[r] = ["appeal", "mark"]; });
  const V = (v) => v || "未能自文本判定";
  const fields = [
    { k: "訴願人", a: [V(p.applicant), p.applicant ? "ap-applicant" : null], d: ["—（尚無答辯書）", null], e: ["—", null] },
    { k: "代理人", a: [V(p.agent), p.agent ? "ap-agent" : null], d: ["—", null], e: ["—", null] },
    { k: "原處分機關", a: [V(p.agency), p.agency ? "ap-agency" : null], d: ["—", null], e: ["—", null] },
    { k: "原處分文號", a: [V(p.orderNo), p.orderNo ? "ap-orderno" : null], d: ["—", null], e: ["—", null] },
    { k: "送達日", a: [p.dServed ? p.dServed.iso + (p.receiverOther ? "（他人代收）" : "") : "未能自文本判定", p.dServed ? "ap-served" : null], d: ["—", null], e: ["須核對送達證書", null], conflict: p.dServed ? "訴願書自述送達日，須以卷附送達證書為準" : null },
    { k: "機關收文日", a: [V(p.dReceived && p.dReceived.iso), p.dReceived ? "ap-recv" : null], d: ["—", null], e: ["收文戳", null] },
    { k: "裁罰金額", a: [V(p.amount && p.amount + " 元"), p.amount ? "ap-amount" : null], d: ["—", null], e: ["—", null] },
  ];
  const laws = PROC_LAWS.slice(); (SUBJ_LAWS[Sj] || []).forEach((l) => laws.push({ ...l, g: "實體法規" }));
  REFS.forEach((r) => { const hit = r.kw.filter((k) => p.text.includes(k)).length; if (hit) laws.push({ g: r.g, n: r.n, t: r.t, rel: Math.min(97, r.rel + hit * 2), badges: [tag("neutral", "資料集內文件"), tag("accent", `命中關鍵字 ${hit} 個`)] }); });
  const alert = (Sj === "洗錢防制法" && p.dOrder && p.dOrder.t < Date.UTC(2024, 7, 2)) ? { title: "法規時效性警示", text: `<b>洗錢防制法於 113 年 7 月 31 日全文修正公布、113 年 8 月 2 日施行。</b>本案偵測到之日期 <b>${p.dOrder.iso}</b> 落在修正施行日之前，行為時應適用修正前條文，請依行政罰法第 5 條為新舊法比較。` } : null;
  const simsRaw = searchDocs(Sj, "79I"), q = { subj: Sj, art: "79I" };
  const sims = simsRaw.map((d) => ({ fn: d.fn, s: d.s, why: whyDoc(d, q), chips: [d.res, d.art, d.subj].concat(d.res.indexOf("撤銷") >= 0 ? ["反面案例"] : []) }));
  const cnt = { 不受理: 0, 駁回: 0, 撤銷: 0 }; simsRaw.forEach((d) => { if (d.res.indexOf("不受理") >= 0) cnt.不受理++; else if (d.res.indexOf("駁回") >= 0) cnt.駁回++; else cnt.撤銷++; });
  const B = (v) => v ? esc(v) : '<span class="fill">（待補）</span>';
  const head = `訴願人　${B(p.applicant)}${p.agent ? "<br>代理人　" + esc(p.agent) : ""}<br>原處分機關　${B(p.agency)}`;
  const intro = `上列訴願人因${esc(Sj)}事件，不服原處分機關民國 ${p.dOrder ? p.dOrder.raw.replace(/民國\s*/, "") : '<span class="fill">（待補）</span>'} ${B(p.orderNo)}所為之處分，提起訴願一案，本府依法決定如下：`;
  return {
    id: "LIVE", no: "即時解析", name: `${Sj}　貼上文字`, outcome: "go", subj: Sj, art: "79I", live: true,
    files: [], docs: [{ id: "appeal", title: "訴願書（貼上文字）", tag: "訴願書", kind: "text", pages: 1, file: null, html: doc }], refs, fields,
    cls: [["案件類型", Sj], ["主要爭點", p.receiverOther ? "送達效力與訴願期間" : "違規事證與裁量適法性"], ["預判走向", "依期間計算與爭點表態決定"]],
    period: { served: p.dServed ? p.dServed.iso : null, recv: p.dReceived ? p.dReceived.iso : null, appealSays: null, servedRef: p.dServed ? "ap-served" : null, recvRef: p.dReceived ? "ap-recv" : null },
    checks: [["77(1)", "訴願書合法定程式", p.applicant && p.orderNo ? "pass" : "warn", p.applicant && p.orderNo ? "訴願人與原處分均可辨識" : "欄位不全，須通知補正"], ["77(2)", "於法定期間內提起", "auto", ""], ["77(3)", "當事人適格", "warn", "須核對訴願人是否為處分相對人"], ["77(4)", "具訴願能力", "warn", "須核對年齡與行為能力"], ["77(5)", "代理人合法", p.agent ? "warn" : "na", p.agent ? "已載代理人，須核對委任狀" : "未委任代理人"], ["77(6)", "行政處分仍存在", "warn", "須向原處分機關確認"], ["77(7)", "非重行提起", "warn", "須查訴願案件管理系統"], ["77(8)", "屬訴願救濟範圍", p.orderNo ? "pass" : "warn", p.orderNo ? "已載處分文號" : "須確認是否為行政處分"]],
    issues: [
      p.receiverOther ? { id: "I1", title: "送達是否合法生效（他人代收）", a: ["訴願書自述由他人代收，主張未實際知悉。", "ap-served"], d: ["（尚無答辯書）", null], e: [["須核對送達證書", null]], law: ["行政程序法 §73 I", "訴願法 §14 I、III", "法務部 93 年函"], lead: { agency: ["A", "送達生效 → 依期間計算"], appellant: ["B", "送達不生效力 → 進入實體"] }, stance: "agency" }
        : { id: "I1", title: "違規事證是否充足", a: ["訴願人主張舉證不足／否認違規。", null], d: ["（尚無答辯書）", null], e: [["須待原處分機關檢卷", null]], law: (SUBJ_LAWS[Sj] || []).map((l) => l.n), lead: { agency: ["A", "事證明確 → 駁回"], appellant: ["B", "舉證不足 → 撤銷"] }, stance: "open" },
    ],
    citations: [], citationNote: "尚無答辯書可供查核；待原處分機關依訴願法第 58 條第 3 項檢卷答辯後，系統將逐條查核其引用法條。",
    laws, alert, sims, simDist: [["不受理", cnt.不受理, "#9C3A2E"], ["駁回", cnt.駁回, "#A8792A"], ["撤銷", cnt.撤銷, "#2E7D5B"]],
    plans: [
      { id: "A", name: "甲案", verdict: "訴願駁回", art: "訴願法 §79 I", when: { I1: "agency" }, basis: ["訴願法 §79 I"].concat((SUBJ_LAWS[Sj] || []).slice(0, 2).map((l) => l.n)), facts: ["爭點 1 採機關見解"], cases: sims.slice(0, 2).map((s) => s.fn), risk: ["mid", "尚無答辯書與卷證，風險待檢卷後評估。"] },
      { id: "B", name: "乙案", verdict: "原處分撤銷", art: "訴願法 §81 I", when: { I1: "appellant" }, basis: ["訴願法 §81 I"], facts: ["爭點 1 採訴願人見解"], cases: sims.filter((s) => s.fn.includes("撤銷")).map((s) => s.fn), risk: ["mid", "尚無卷證可資佐證訴願人主張。"] },
    ],
    drafts: {
      A: { tmpl: "79I 駁回（骨架）", head: "新北市政府訴願決定書", sub: "（即時解析草稿・待承辦人審核）", paras: [
        { id: "meta", kind: "meta", text: head }, { id: "intro", kind: "p", text: intro }, { id: "h-main", kind: "h4", text: "主文" }, { id: "main", kind: "p", text: "訴願駁回。" }, { id: "h-fact", kind: "h4", text: "事實" },
        { id: "fact", kind: "p", text: `緣<span class="fill">（違規事實：時間、地點、行為態樣，請依卷證補實）</span>。經原處分機關認訴願人違反${esc(Sj)}規定${p.amount ? "，裁處罰鍰新臺幣 " + esc(p.amount) + " 元" : ""}，以${B(p.orderNo)}裁處書處分。訴願人不服，於 {{RECV}} 提起本件訴願。` },
        { id: "fact-a", kind: "p", text: `一、訴願意旨略謂：<span class="fill">（自訴願書理由欄摘敘）</span>等語。` }, { id: "fact-d", kind: "p", text: `二、答辯意旨略謂：<span class="fill">（待原處分機關檢卷答辯後補入）</span>等語。` },
        { id: "h-reason", kind: "h4", text: "理由" },
        { id: "r1", kind: "p", text: `一、按<span class="fill">（主管機關權限依據與權限劃分公告）</span>。準此，本案原處分機關為有權限處分之機關。` },
        { id: "r2", kind: "p", text: `二、次按${esc(Sj)}相關規定……（法規推薦頁已備妥 ${(SUBJ_LAWS[Sj] || []).length} 條實體法條全文）。`, cite: "引自　相關法規資料夾" },
        { id: "r3", kind: "p", text: `三、卷查<span class="fill">（違規事證認定）</span>，其違規事證應堪認定。` },
        { id: "r4", kind: "p", text: `四、至訴願人主張<span class="fill">（逐一回應訴願主張）</span>等語。惟<span class="fill">（駁斥理由）</span>。是訴願人主張，尚難採據。` },
        { id: "r5", kind: "p", text: "五、綜上論結，本件訴願為無理由，依訴願法第 79 條第 1 項規定，決定如主文。" },
      ] },
      B: { tmpl: "81I 撤銷（骨架）", head: "新北市政府訴願決定書", sub: "（即時解析草稿・待承辦人審核）", paras: [
        { id: "meta", kind: "meta", text: head }, { id: "intro", kind: "p", text: intro }, { id: "h-main", kind: "h4", text: "主文" }, { id: "main", kind: "p", text: "原處分撤銷。" }, { id: "h-reason", kind: "h4", text: "理由" },
        { id: "r1", kind: "p", text: `一、<span class="fill">（採訴願人見解之事實與法律論述，請依卷證補實）</span>` },
        { id: "r2", kind: "p", text: "二、綜上論結，本件訴願為有理由，依訴願法第 81 條第 1 項規定，決定如主文。" },
      ] },
    },
    gain: [[p.ms + " ms", "瀏覽器端解析耗時", "up"], [`${fields.filter((f) => f.a[0] !== "未能自文本判定").length} / ${fields.length}`, "欄位成功擷取", ""], ["101 件", "相似案例檢索範圍", ""], ["待人工", "程序期間審查", ""]],
  };
}

/* =========================================================
   逾期時之通用不受理方案與草稿（供 B／C／LIVE 期間改為逾期時使用）
   ========================================================= */
function overduePlan() {
  return { id: "X", name: "甲案", verdict: "訴願不受理", art: "訴願法 §77 ②", when: {}, basis: ["訴願法 §14 I、III", "訴願法 §77 ②", "行政程序法 §72、§73"], facts: ["依承辦人修正之送達日／收文日，本件已逾 30 日法定不變期間"], cases: ["77(2) 類型 21 件皆為不受理"], risk: ["low", "期間計算為純規則運算；惟送達日之認定須以卷附送達證書為準。"], synthetic: true };
}
function overdueDraft(c) {
  const meta = (c.drafts.A || Object.values(c.drafts)[0]).paras.find((x) => x.id === "meta");
  return { tmpl: "77(2) 不受理（期間重算）", head: "新北市政府訴願決定書", sub: `案號：${c.no} 號　（依修正後期間自動改判・待承辦人審核）`, paras: [
    meta ? { ...meta } : { id: "meta", kind: "meta", text: "" },
    { id: "h-main", kind: "h4", text: "主文" }, { id: "main", kind: "p", text: "訴願不受理。" }, { id: "h-reason", kind: "h4", text: "理由" },
    { id: "r1", kind: "p", text: "一、按訴願法第 14 條第 1 項及第 3 項規定：「訴願之提起，應自行政處分達到或公告期滿之次日起 30 日內為之。訴願之提起，以原行政處分機關或受理訴願機關收受訴願書之日期為準。」、第 77 條第 2 款規定：「訴願事件有左列各款情形之一者，應為不受理之決定：二、提起訴願逾法定期間者……。」", cite: "引自　相關法規／訴願法.pdf" },
    { id: "r2", kind: "p", text: "二、本件系爭處分於 {{SERVED}} 送達訴願人<span class=\"fill\">（送達方式與受領人請依卷附送達證書補實）</span>，訴願期間應自 {{START}} 起算，至 {{DUE}} 屆滿。惟訴願人遲至 {{RECV}}（機關收文日）始提起本件訴願，已逾 30 日之法定不變期間 {{OVER}} 日，原處分業已確定。", cite: "日期由期間計算模組即時推導（未扣除在途期間）" },
    { id: "r3", kind: "p", text: "三、綜上論結，本件訴願為程序不合，依訴願法第 77 條第 2 款規定，決定如主文。" },
  ] };
}

/* =========================================================
   畫面 2：分析中（六階段＋文件歸戶動畫）
   ========================================================= */
function runCase(c) {
  S.c = c; S.live = !!c.live;
  S.served = c.period.served; S.recv = c.period.recv;
  S.stances = {}; c.issues.forEach((i) => { S.stances[i.id] = i.stance || "open"; });
  S.plan = null; S.paras = []; S.versions = []; S.audit = []; S.sel = null; S.doc = null; S.zoom = 1;

  $("#chip").classList.add("on"); $("#chipName").textContent = c.name; $("#chipNo").textContent = c.live ? c.no : "案號 " + c.no;
  $("#backBtn").style.display = "";
  const docs = c.docs.filter((d) => d.kind !== "missing");
  const steps = [
    ["文件辨識與歸戶", `${c.docs.length} 個檔案 → ${new Set(c.docs.map((d) => d.tag)).size} 種類型`, 1500, "classify"],
    ["欄位擷取（三方對照）", `${c.fields.length} 個欄位，${c.fields.filter((f) => f.conflict).length} 處衝突`, 700],
    ["爭點比對（訴願書 vs 答辯書 vs 卷證）", `識別 ${c.issues.length} 個爭點`, 760],
    ["法規檢索與引用查核", `推薦 ${c.laws.length} 筆；查核答辯書引用 ${c.citations.length} 則${c.citations.some((x) => x.status === "amended") ? "，1 則已修正" : ""}${c.alert ? "；1 則時效性警示" : ""}`, 840],
    ["方案研擬", `${c.plans.length} 個可行方案`, 700],
    ["決定書草稿生成", `套用「${(c.drafts.A || Object.values(c.drafts)[0]).tmpl}」模板`, 900],
  ];
  $("#runSub").textContent = c.live ? c.name : `${c.name}　・　案號 ${c.no}${c.uploadNote ? "　・　" + c.uploadNote : ""}`;
  $("#stepList").innerHTML = steps.map((s, i) => `<div class="step" id="st${i}"><div class="idx">${i + 1}</div><div><div class="name">${s[0]}</div><div class="out" id="so${i}"></div>${s[3] ? `<div class="classify" id="cls${i}">${c.docs.map((d) => `<span>${esc(d.title)}　<b>${d.tag}</b></span>`).join("")}</div>` : ""}</div><div class="ms" id="sm${i}"></div></div>`).join("");
  $("#runBar").style.width = "0"; show("s-run");
  let t = 0;
  steps.forEach((s, i) => {
    setTimeout(() => { const el = $("#st" + i); if (!el) return; el.classList.add("active"); $("#runBar").style.width = ((i + 1) / steps.length * 100) + "%"; if (s[3]) $$("#cls" + i + " span").forEach((sp, k) => setTimeout(() => sp.classList.add("in"), 80 + k * (1200 / Math.max(1, c.docs.length)))); }, t);
    t += s[2];
    setTimeout(() => { const el = $("#st" + i); if (!el) return; el.classList.remove("active"); el.classList.add("done"); $("#so" + i).textContent = s[1]; $("#sm" + i).textContent = s[2] + " ms"; }, t);
  });
  setTimeout(() => { render(); show("s-work"); }, t + 500);
}

/* =========================================================
   期間計算與方案推薦（狀態衍生）
   ========================================================= */
function period() {
  const st = isoT(S.served), rt = isoT(S.recv);
  if (!st) return null;
  const start = st + DAY, due = st + 30 * DAY;
  return { served: st, start, due, recv: rt, over: rt !== null ? rt > due : null, days: rt !== null ? Math.round((rt - due) / DAY) : null, left: rt !== null ? Math.round((due - rt) / DAY) : null };
}
const isOverdue = () => { const p = period(); return !!(p && p.over); };
function activePlans() {
  const c = S.c;
  if (isOverdue()) {
    const base77 = c.plans.some((p) => p.art.includes("77")) ? c.plans.filter((p) => p.art.includes("77")) : [overduePlan()];
    // 送達效力爭點改採訴願人 → 期間未起算，允許受理方案並列
    const contested = c.issues.some((i) => /送達/.test(i.title) && S.stances[i.id] === "appellant");
    if (contested) { const alt = c.plans.filter((p) => !p.art.includes("77") && Object.entries(p.when).every(([k, v]) => S.stances[k] === v)); if (alt.length) return base77.concat(alt); }
    return base77;
  }
  const base = c.plans.filter((p) => !p.art.includes("77 ②") || !c.singleReason);
  // 案例 A：預設僅一案；爭點改採訴願人才出現乙案
  if (c.singleReason) return c.plans.filter((p) => { const ok = Object.entries(p.when).every(([k, v]) => S.stances[k] === v); return p.id === "A" || ok; });
  return base;
}
function planFit(p) { const ks = Object.keys(p.when); const m = ks.filter((k) => S.stances[k] === p.when[k]).length; return { m, n: ks.length, all: ks.length === 0 || m === ks.length }; }
function recommended() { const ps = activePlans(); const full = ps.filter((p) => planFit(p).all); if (full.length) return full[0]; return null; }
function ensurePlan() {
  const ps = activePlans();
  if (!S.plan || !ps.some((p) => p.id === S.plan)) { const r = recommended(); S.plan = r ? r.id : ps[0].id; loadDraft(); }
}
function draftFor(id) { const c = S.c; if (id === "X" || (isOverdue() && !c.drafts[id])) return overdueDraft(c); return c.drafts[id] || overdueDraft(c); }
function loadDraft() {
  const d = draftFor(S.plan);
  S.paras = d.paras.map((p) => ({ ...p, tpl: p.text, src: "ai", refs: p.refs ? p.refs.slice() : [] }));
  S.sel = null; S.versions = []; S.audit = [];
  pushVersion("AI 生成草稿（" + d.tmpl + "）", "AI");
}
function fillDates(t) {
  const p = period();
  return t.replace(/\{\{RECV\}\}/g, S.recv ? cnDate(isoT(S.recv)) : '<span class="fill">（待補收文日）</span>')
    .replace(/\{\{SERVED\}\}/g, S.served ? cnDate(isoT(S.served)) : '<span class="fill">（待補送達日）</span>')
    .replace(/\{\{START\}\}/g, p ? cnDate(p.start) : "—").replace(/\{\{DUE\}\}/g, p ? cnDate(p.due) : "—")
    .replace(/\{\{OVER\}\}/g, p && p.days !== null ? p.days : "—");
}
function pushVersion(label, by) {
  S.versions.push({ ts: now(), label, by, snap: S.paras.map((p) => ({ ...p })) });
  S.audit.push({ ts: now(), who: by === "AI" ? "ai" : "hu", para: "全文", action: label });
}

/* =========================================================
   畫面 3：渲染
   ========================================================= */
function render() {
  ensurePlan();
  renderDocs();
  renderExtract(); renderIssues(); renderLaws(); renderSims(); renderPlans(); renderDraft();
  updateChips();
  $$(".tab")[0].click();
  const firstDoc = S.c.docs.find((d) => d.kind !== "missing");
  if (firstDoc) openDoc(firstDoc.id);
}
function updateChips() {
  const p = activePlans().find((x) => x.id === S.plan);
  $("#planChip").classList.add("on"); $("#planChipText").textContent = p ? `${p.name}・${p.verdict.length > 14 ? p.verdict.slice(0, 14) + "…" : p.verdict}` : "待選";
  $$(".tab")[1].classList.toggle("warn", Object.values(S.stances).includes("open"));
  $$(".tab")[2].classList.toggle("warn", S.c.citations.some((x) => x.status !== "ok"));
  $$(".tab")[0].classToggle = null;
}
function recompute(which) {
  ensurePlan();
  if (which !== "draft") { renderExtract(); renderIssues(); renderPlans(); }
  renderDraft(); updateChips();
}

/* --- 分頁切換 --- */
$$(".tab").forEach((b) => b.addEventListener("click", () => { $$(".tab").forEach((x) => x.classList.toggle("on", x === b)); $$(".tabpage").forEach((p, i) => p.classList.toggle("on", i === +b.dataset.t)); $("#panel").scrollTop = 0; }));

/* ---------- 卷宗瀏覽器 ---------- */
function renderDocs() {
  const c = S.c;
  $("#docCount").textContent = `${c.docs.length} 件`;
  $("#docStrip").innerHTML = c.docs.map((d) => `<button data-doc="${d.id}" title="${esc(d.title)}"><i style="background:var(--${{ accent: "accent", seal: "seal", amber: "amber", neutral: "line-strong", green: "green" }[DOCTAG[d.tag] || "neutral"]})"></i>${esc(d.title.length > 9 ? d.title.slice(0, 9) + "…" : d.title)}</button>`).join("");
  $$("#docStrip button").forEach((b) => b.addEventListener("click", () => openDoc(b.dataset.doc)));
}
function openDoc(id, after) {
  const c = S.c, d = c.docs.find((x) => x.id === id); if (!d) return;
  S.doc = id; S.zoom = 1;
  $$("#docStrip button").forEach((b) => { b.classList.toggle("on", b.dataset.doc === id); if (b.dataset.doc === id) b.scrollIntoView({ inline: "nearest", block: "nearest" }); });
  const view = $("#docView"), tools = $("#docTools");
  tools.innerHTML = "";
  const missing = `<div class="doc-missing">找不到卷宗包檔案：<span class="num">${esc(d.file || "")}</span><br>請自 repo 根目錄開啟 prototype/index.html，或確認「資料集/評測用（勿用於RAG）/case02-廢清法79I駁回/卷宗包/」存在。</div>`;
  if (d.kind === "text") {
    view.innerHTML = `<div class="doc-body">${d.html}</div>`;
    if (d.file) { tools.innerHTML = `<button class="ghost-btn" id="rawBtn">原始 PDF</button>`; $("#rawBtn").addEventListener("click", () => { const on = $("#rawBtn").classList.toggle("on"); view.innerHTML = on ? `<iframe class="doc-pdf" src="${d.file}#toolbar=0&view=FitH"></iframe>` : `<div class="doc-body">${d.html}</div>`; if (!on) bindMarks(); }); }
    bindMarks();
  } else if (d.kind === "image") {
    tools.innerHTML = `<button class="ghost-btn" data-z="-">－</button><button class="ghost-btn" data-z="+">＋</button><button class="ghost-btn" data-z="0">重設</button>`;
    view.innerHTML = `<div class="doc-img" id="docImg"><div class="imgwrap"><img src="${d.file}" alt="${esc(d.title)}">${(d.boxes || []).map((b) => `<div class="box" data-ref="${b.ref}" style="left:${b.x}%;top:${b.y}%;width:${b.w}%;height:${b.h}%"><span class="lb">${esc(b.label)}</span></div>`).join("")}</div></div>`;
    const img = $("#docImg img"); img.addEventListener("error", () => { view.innerHTML = missing; });
    const fit = () => { const w = view.clientWidth - 24; $("#docImg").style.setProperty("--imgw", Math.round(w * S.zoom) + "px"); };
    fit();
    $$("#docTools button").forEach((b) => b.addEventListener("click", () => { S.zoom = b.dataset.z === "0" ? 1 : Math.min(4, Math.max(.5, S.zoom + (b.dataset.z === "+" ? .4 : -.4))); fit(); }));
    $("#docImg").addEventListener("dblclick", () => { S.zoom = S.zoom > 1.2 ? 1 : 2.2; fit(); });
    let drag = null; const el = $("#docImg");
    el.addEventListener("mousedown", (e) => { drag = { x: e.clientX, y: e.clientY, sl: view.scrollLeft, st: view.scrollTop }; el.classList.add("drag"); });
    window.addEventListener("mousemove", (e) => { if (!drag) return; view.scrollLeft = drag.sl - (e.clientX - drag.x); view.scrollTop = drag.st - (e.clientY - drag.y); });
    window.addEventListener("mouseup", () => { drag = null; el.classList.remove("drag"); });
    $$(".box", view).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); hitBox(b.dataset.ref); }));
  } else if (d.kind === "pdf") {
    tools.innerHTML = `<a class="ghost-btn" href="${d.file}" target="_blank" style="text-decoration:none">新分頁開啟</a>`;
    view.innerHTML = `<iframe class="doc-pdf" src="${d.file}#toolbar=0&view=FitH" title="${esc(d.title)}"></iframe>`;
  } else if (d.kind === "video") {
    view.innerHTML = `<div class="doc-video"><video id="vid" controls preload="metadata" src="${d.file}"></video><div class="cues">${(d.cues || []).map((q) => `<button class="ghost-btn" data-t="${q[1]}">${q[2]}</button>`).join("")}</div><p class="note" style="margin-top:8px">來源：民眾檢舉行車紀錄器；時間戳 2025/06/27 12:40:08–19。點擊上方按鈕跳至關鍵幀。</p></div>`;
    $$(".cues button", view).forEach((b) => b.addEventListener("click", () => seek(+b.dataset.t)));
    $("#vid").addEventListener("error", () => { view.innerHTML = missing; });
  } else {
    view.innerHTML = `<div class="doc-missing"><b>${esc(d.title)}</b>　<span class="tag ${DOCTAG[d.tag] || "neutral"}">${d.tag}</span><br>${esc(d.note || "")}</div>`;
  }
  if (after) after();
}
function bindMarks() {
  $$("#docView mark[data-ref]").forEach((m) => m.addEventListener("click", () => {
    const ref = m.dataset.ref; $$("#docView mark").forEach((x) => x.classList.remove("hit", "hit-seal"));
    m.classList.add("hit");
    const row = $(`#p0 [data-jump="${ref}"]`); if (row) { $$(".tab")[0].click(); row.closest("tr")?.scrollIntoView({ block: "center", behavior: "smooth" }); }
  }));
}
function hitBox(ref) { $$("#docView .box").forEach((b) => b.classList.toggle("hit", b.dataset.ref === ref)); const b = $(`#docView .box[data-ref="${ref}"]`); if (b) b.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }); }
function seek(t) { const v = $("#vid"); if (!v) return; const go = () => { v.currentTime = t; v.pause(); }; if (v.readyState >= 1) go(); else v.addEventListener("loadedmetadata", go, { once: true }); }

function jumpTo(ref) {
  const r = S.c.refs[ref]; if (!r) return;
  const [docId, kind] = r;
  const act = () => {
    if (kind === "mark") { $$("#docView mark").forEach((x) => x.classList.remove("hit", "hit-seal")); const m = $(`#docView mark[data-ref="${ref}"]`); if (m) { m.classList.add(/arg|served|receiver/.test(ref) ? "hit-seal" : "hit"); m.scrollIntoView({ block: "center", behavior: "smooth" }); } }
    else if (kind === "box") hitBox(ref);
    else if (kind === "time") { const d = S.c.docs.find((x) => x.id === docId); const cue = (d.cues || []).find((q) => q[0] === ref); if (cue) seek(cue[1]); }
  };
  if (S.doc !== docId) openDoc(docId, () => setTimeout(act, 60)); else act();
}
document.addEventListener("click", (e) => { const j = e.target.closest("[data-jump]"); if (j) { e.preventDefault(); jumpTo(j.dataset.jump); } });

/* ---------- Tab 1：案件擷取與分類 ---------- */
function renderExtract() {
  const c = S.c, p = period();
  const rows = c.fields.map((f) => `
    <tr class="${f.conflict ? "conflict" : ""}">
      <td>${esc(f.k)}</td>
      <td>${J(f.a[1], esc(f.a[0]))}</td><td>${J(f.d[1], esc(f.d[0]))}</td>
      <td>${J(f.e[1], esc(f.e[0]))}${f.conflict ? `<span class="why">⚠ ${esc(f.conflict)}</span>` : ""}</td>
    </tr>`).join("");
  const cls = c.cls.map(([l, v]) => `<div class="cls"><span class="lab">${l}</span><div class="val">${esc(v)}</div></div>`).join("");
  const marks = { pass: "✓", fail: "✕", na: "－", warn: "？" };
  const checks = c.checks.map((k) => {
    let st = k[2], note = k[3];
    if (st === "auto") { if (!p) { st = "warn"; note = "未有送達日，須人工核對送達證書"; } else if (p.recv === null) { st = "warn"; note = "未有收文日，須人工核對"; } else if (p.over) { st = "fail"; note = `逾期 ${p.days} 日`; } else { st = "pass"; note = `尚餘 ${p.left} 日`; } }
    return `<div class="chk ${st}"><span class="mk">${marks[st]}</span><div><span>${k[1]}</span><span class="art">訴願法 ${k[0]}　${esc(note)}</span></div></div>`;
  }).join("");
  const over = !!(p && p.over);
  const verdict = over
    ? { kind: "stop", big: "應為不受理", text: `依送達日 ${S.served} 起算，法定期間至 ${toMg(p.due)} 屆滿，機關收文日 ${S.recv} 已逾期 ${p.days} 日。程序審查於訴願法第 77 條第 2 款即告終結，毋庸進入實體審查；方案研擬已自動改為單一不受理方案。` }
    : p && p.recv !== null ? { kind: "go", big: "期間內提起", text: `收文日距屆滿尚餘 ${p.left} 日，未逾法定不變期間，進入實體審查。實體爭點見「爭點」分頁（共 ${c.issues.length} 個），方案研擬依承辦人對各爭點之表態連動。` }
    : { kind: "go", big: "待補程序資料", text: "尚未同時取得送達日與收文日，無法完成期間計算。請於下方欄位輸入（或自卷宗瀏覽器點選送達證書確認）。" };
  let tl = "";
  if (p) {
    const anchor = [[p.served, "合法送達", "key"], [p.due, "期間屆滿", p.over ? "key" : ""]];
    if (p.recv !== null) anchor.push([p.recv, "實際收文", p.over ? "bad" : "key"]);
    anchor.sort((a, b) => a[0] - b[0]);
    const min = anchor[0][0], max = anchor[anchor.length - 1][0], span = Math.max(1, max - min), pts = [];
    anchor.forEach(([t, lab, cl], i) => { let pos = Math.round((t - min) / span * 100); if (i > 0 && pos - pts[pts.length - 1].pos < 17) pos = Math.min(100, pts[pts.length - 1].pos + 17); pts.push({ d: toMg(t), lab, pos, cls: cl }); });
    const recvPt = pts.find((x) => x.lab === "實際收文");
    tl = `<div class="tl-track"><div class="tl-fill" style="width:${recvPt ? recvPt.pos : 100}%"></div>${pts.map((x) => `<div class="tl-pt ${x.cls}" style="left:${x.pos}%"><div class="up"><div class="d">${x.d}</div></div><div class="dot"></div><div class="lab">${x.lab}</div></div>`).join("")}</div>
      <div class="tl-note">起算日 <b>${toMg(p.start)}</b>（送達之次日）＋ 30 日 ＝ 屆滿日 <b>${toMg(p.due)}</b>。${p.recv === null ? "尚無收文日。" : p.over ? `實際收文日 <b>${toMg(p.recv)}</b>，<span style="color:var(--seal);font-weight:600">逾法定不變期間 ${p.days} 日</span>。` : `實際收文日 <b>${toMg(p.recv)}</b>，<span style="color:var(--green);font-weight:600">未逾期，距屆滿尚餘 ${p.left} 日</span>。`} 在途期間未扣除。</div>`;
  } else tl = `<div class="tl-note" style="margin-top:0;border:none">尚未取得送達日，無法繪製時間軸。</div>`;
  const ap = c.period.appealSays;
  $("#p0").innerHTML = `
    <div class="sec"><div class="sec-head"><h3>三方對照</h3><span class="note">訴願人主張 ／ 機關答辯 ／ 卷證事實　點任一格跳至卷宗來源</span></div>
      <div class="box2"><table class="cmp"><tr><th>欄位</th><th>訴願人主張（訴願書）</th><th>機關答辯（答辯書）</th><th>卷證事實</th></tr>${rows}</table></div></div>
    <div class="sec"><div class="sec-head"><h3>案件分類</h3><span class="note">分類模型輸出</span></div><div class="box2 clsgrid">${cls}</div></div>
    <div class="sec"><div class="sec-head"><h3>訴願期間計算（可修正，連動後續判斷）</h3><span class="note">送達日 ＋ 30 日；修正後程序審查、方案與草稿同步重算</span></div>
      <div class="box2"><div class="period-edit">
        <div><label>送達日（卷證）</label><input id="inServed" value="${esc(S.served || "")}" placeholder="114-09-18"><div class="src">${c.period.servedRef ? J(c.period.servedRef, "來源：送達證書 ↗") : "來源：訴願書自述／待補"}${ap && ap !== S.served ? `<span class="warnsrc">　⚠ 訴願書自述 ${ap}，與送達證書不符，已採卷證</span>` : ""}</div></div>
        <div><label>機關收文日</label><input id="inRecv" value="${esc(S.recv || "")}" placeholder="114-09-22"><div class="src">${c.period.recvRef ? J(c.period.recvRef, "來源：收文戳 ↗") : "來源：待補"}</div></div>
        <div><label>期間屆滿日</label><div class="num" style="font-size:15px;padding:4px 0">${p ? toMg(p.due) : "—"}</div><div class="src">起算 ${p ? toMg(p.start) : "—"}（送達次日）</div></div>
        <div><label>結果</label><div style="font-size:15px;font-weight:600;color:${over ? "var(--seal)" : "var(--green)"}">${p ? (p.recv === null ? "待補收文日" : over ? `逾期 ${p.days} 日` : `尚餘 ${p.left} 日`) : "待補送達日"}</div><div class="src"><button class="ghost-btn" id="applyPeriod" style="margin-top:4px">重算並連動</button></div></div>
      </div><div class="timeline">${tl}</div></div></div>
    <div class="sec"><div class="sec-head"><h3>程序審查　訴願法第 77 條各款</h3><span class="note">依卷面與期間計算自動檢核</span></div>
      <div class="box2"><div class="checks">${checks}</div><div class="verdict ${verdict.kind}"><span class="big">${verdict.big}</span><p>${verdict.text}</p></div></div></div>
    <p class="foot-note">三方對照之「卷證事實」欄由卷宗歸戶後之文件擷取；紅底列為訴願人主張與機關答辯或卷證不一致處，系統不自動裁決，僅指出證據位置供承辦人判斷。期間計算為純規則運算，送達日之認定以卷附送達證書為準。</p>`;
  const apply = () => { const s = $("#inServed").value.trim(), r = $("#inRecv").value.trim(); if (s && !isoT(s)) return alert("送達日格式須為 民國年-月-日，例如 114-09-18"); if (r && !isoT(r)) return alert("收文日格式須為 民國年-月-日"); const was = isOverdue(); S.served = s || null; S.recv = r || null; S.audit.push({ ts: now(), who: "hu", para: "期間", action: `修正送達日 ${s || "—"}／收文日 ${r || "—"}` }); const nowOver = isOverdue(); if (was !== nowOver) { S.plan = null; } else { S.paras.forEach((q) => { if (/\{\{/.test(q.tpl) && q.src !== "human") q.text = q.tpl; }); } recompute(); };
  $("#applyPeriod").addEventListener("click", apply);
  ["#inServed", "#inRecv"].forEach((s) => $(s).addEventListener("keydown", (e) => { if (e.key === "Enter") apply(); }));
}

/* ---------- Tab 2：爭點 ---------- */
function renderIssues() {
  const c = S.c;
  const st = (id, v) => S.stances[id] === v ? "on" : "";
  $("#p1").innerHTML = `
    <div class="sec"><div class="sec-head"><h3>雙方癥結點</h3><span class="note">每個爭點：訴願人主張 ／ 機關答辯 ／ 卷證顯示 ／ 法律素材 ／ 導向哪一案　承辦人表態後連動「方案研擬」</span></div>
    ${c.issues.map((it, i) => `
      <div class="issue" id="iss-${it.id}">
        <div class="issue-head"><span class="n">爭點 ${i + 1}</span><h3>${esc(it.title)}</h3>
          <div class="stance">
            <label class="${st(it.id, "appellant")}"><input type="radio" name="st-${it.id}" value="appellant" ${S.stances[it.id] === "appellant" ? "checked" : ""}>採訴願人</label>
            <label class="${st(it.id, "agency")}"><input type="radio" name="st-${it.id}" value="agency" ${S.stances[it.id] === "agency" ? "checked" : ""}>採機關</label>
            <label class="${st(it.id, "open")}"><input type="radio" name="st-${it.id}" value="open" ${S.stances[it.id] === "open" ? "checked" : ""}>待議</label>
          </div></div>
        <div class="issue-grid">
          <div><div class="lab">訴願人主張</div>${J(it.a[1], esc(it.a[0]))}</div>
          <div><div class="lab">機關答辯</div>${J(it.d[1], esc(it.d[0]))}</div>
          <div><div class="lab">卷證顯示</div><div class="ev">${it.e.map((e) => e[1] ? `<span class="tag accent jump" data-jump="${e[1]}">${esc(e[0])} ↗</span>` : `<span class="tag neutral">${esc(e[0])}</span>`).join("")}</div></div>
        </div>
        <div class="issue-foot"><div class="laws"><span class="lab" style="font-size:10.5px;color:var(--ink-3);margin-right:6px">法律素材</span>${it.law.map((l) => `<span>${esc(l)}</span>`).join("")}</div></div>
        <div class="lead"><span>採機關 → <b>${it.lead.agency[0] === "A" ? "甲" : it.lead.agency[0] === "B" ? "乙" : "丙"}案</b>　${esc(it.lead.agency[1])}</span><span>採訴願人 → <b>${it.lead.appellant[0] === "A" ? "甲" : it.lead.appellant[0] === "B" ? "乙" : "丙"}案</b>　${esc(it.lead.appellant[1])}</span></div>
      </div>`).join("")}</div>
    <p class="foot-note">爭點由三方對照之衝突列與答辯書「逐點回應」段落自動配對產生。表態僅改變方案推薦與草稿基礎，不會改寫卷證；「待議」之爭點會在方案研擬頁提示尚未表態。</p>`;
  $$("#p1 input[type=radio]").forEach((r) => r.addEventListener("change", () => { const id = r.name.slice(3); S.stances[id] = r.value; S.audit.push({ ts: now(), who: "hu", para: "爭點 " + id, action: `表態：${{ appellant: "採訴願人", agency: "採機關", open: "待議" }[r.value]}` }); S.plan = null; recompute(); $$(".tab")[1].click(); $("#iss-" + id)?.scrollIntoView({ block: "center" }); }));
}

/* ---------- Tab 3：法規推薦＋引用查核 ---------- */
function renderLaws() {
  const c = S.c, STN = { ok: "已驗證", amended: "該條已修正", missing: "查無此條", repealed: "已廢止", gap: "漏引" };
  const cites = c.citations.length ? `<table class="cite-check"><tr><th>引用</th><th>出現位置</th><th>狀態</th><th>說明</th></tr>${c.citations.map((x) => `<tr class="${x.status}"><td>${J(x.ref, esc(x.n))}</td><td>${esc(x.where)}</td><td><span class="st ${x.status}">${STN[x.status]}</span></td><td class="note" style="font-size:12px">${esc(x.note)}</td></tr>`).join("")}</table>` : `<div class="doc-missing" style="padding:14px">${esc(c.citationNote || "無引用可查核")}</div>`;
  const groups = {}; c.laws.forEach((l) => { (groups[l.g] = groups[l.g] || []).push(l); });
  const secs = Object.entries(groups).map(([g, list]) => `<div class="sec"><div class="sec-head"><h3>${g}</h3><span class="note">${list.length} 筆</span></div><div class="box2">${list.map((l) => `<div class="law"><div class="ttl"><span class="n">${esc(l.n)}</span></div><div class="rel">關聯 ${l.rel}%</div><div class="txt">${esc(l.t)}</div><div class="badges">${l.badges.join("")}</div></div>`).join("")}</div></div>`).join("");
  $("#p2").innerHTML = `
    <div class="sec"><div class="sec-head"><h3>答辯書引用法條查核</h3><span class="note">逐條比對資料集法規全文與修正狀態</span></div><div class="box2">${cites}</div></div>
    ${c.alert ? `<div class="sec"><div class="sec-head"><h3>${c.alert.title}</h3><span class="note">影響決定書合法性，請優先處理</span></div><div class="alert"><span class="mk">！</span><p>${c.alert.text}</p></div></div>` : ""}
    ${secs}
    <p class="foot-note">每則依據標示現行效力狀態；引用查核比對答辯書所引條號與資料集內法規全文（11 部法規、10 則函釋、19 則判解）。草稿經對話修改後若引入新引用，會自動重跑此查核並在對話中回報。</p>`;
}

/* ---------- Tab 4：相似案例（維持） ---------- */
function renderSims() {
  const c = S.c, total = c.simDist.reduce((a, b) => a + b[1], 0);
  $("#p3").innerHTML = `
    <div class="sec"><div class="sec-head"><h3>Top ${c.sims.length} 相似歷史決定書</h3><span class="note">比對範圍 110–114 年共 101 件</span></div>
      <div class="box2">${c.sims.map((s, i) => `<div class="sim"><div class="sim-top"><span class="rank">${i + 1}</span><span class="fn">${esc(s.fn)}</span><span class="score">${s.s}%</span></div><div class="simbar"><i style="width:${s.s}%"></i></div><p class="why">${esc(s.why)}</p><div class="chips">${s.chips.map((x) => `<span class="tag ${x === "須注意" || x === "反面案例" ? "seal" : "neutral"}">${esc(x)}</span>`).join("")}</div></div>`).join("")}</div></div>
    <div class="sec"><div class="sec-head"><h3>相似案例之決定結果分布</h3><span class="note">供預判走向參考</span></div>
      <div class="dist">${c.simDist.filter((d) => d[1] > 0).map((d) => `<div style="background:${d[2]};width:${d[1] / total * 100}%">${d[1]}</div>`).join("")}</div>
      <div class="dist-key">${c.simDist.map((d) => `<span><i style="background:${d[2]}"></i>${d[0]} ${d[1]} 件</span>`).join("")}</div></div>
    <p class="foot-note">相似度綜合案由、援引法條、爭點類型與事實敘述四項向量計算。系統會刻意納入結果相反之案例（標示為「反面案例」），提醒承辦人檢視本案是否存在相同的撤銷風險。</p>`;
}

/* ---------- Tab 5：方案研擬 ---------- */
const PN = { A: "甲", B: "乙", C: "丙", X: "甲" };
function renderPlans() {
  const c = S.c, ps = activePlans(), rec = recommended(), open = Object.entries(S.stances).filter(([, v]) => v === "open").map(([k]) => k);
  const single = ps.length === 1;
  const reason = isOverdue() ? `期間重算後本件已逾 30 日法定不變期間，訴願法第 77 條第 2 款為「應為不受理」之強制規定，無裁量空間，法律上僅此一結論。` : (single && c.singleReason) ? c.singleReason : null;
  const cards = ps.map((p) => {
    const f = planFit(p), isRec = rec && rec.id === p.id;
    return `<div class="plan ${isRec ? "rec" : ""} ${!isRec && f.n && !f.all ? "off" : ""}">
      <div class="plan-head"><h3>${p.name}</h3>${isRec ? tag("accent", "推薦") : ""}<span class="art">${esc(p.art)}</span></div>
      <div class="verdict-line">主文：${esc(p.verdict)}</div>
      <div class="sec2"><div class="lab">法條依據</div><ul>${p.basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></div>
      <div class="sec2"><div class="lab">事實認定（爭點表態）</div><ul>${p.facts.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>${f.n ? `<div class="fit" style="margin-top:4px;color:${f.all ? "var(--green)" : "var(--amber)"}">與目前表態相符 ${f.m}/${f.n}</div>` : ""}</div>
      <div class="sec2"><div class="lab">支持案例</div><ul>${p.cases.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></div>
      <div class="risk ${p.risk[0]}"><b>撤銷風險：${{ low: "低", mid: "中", high: "高" }[p.risk[0]]}</b>　${esc(p.risk[1])}</div>
      <div class="plan-foot"><label><input type="radio" name="plan" value="${p.id}" ${S.plan === p.id ? "checked" : ""}>採用此案作為草稿基礎</label></div>
    </div>`;
  }).join("");
  $("#p4").innerHTML = `
    ${reason ? `<div class="single"><b>本案法律上僅一結論</b>　${esc(reason)}</div>` : ""}
    ${open.length && !isOverdue() ? `<div class="alert" style="margin-bottom:14px"><span class="mk">！</span><p>尚有 ${open.length} 個爭點「待議」（${open.join("、")}）。方案推薦以已表態之爭點計算；請至「爭點」分頁完成表態，推薦結果會更明確。</p></div>` : ""}
    <div class="sec"><div class="sec-head"><h3>可行方案</h3><span class="note">依未定爭點推導；每案含法條依據／事實認定／支持案例／撤銷風險</span></div><div class="plans">${cards}</div></div>
    <div class="sec"><div class="sec-head"><h3>提送委員會</h3><span class="note">訴願為合議制，比較表供訴願審議委員會參考</span></div><div class="box2" style="padding:12px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button class="btn" id="exportCmp">匯出方案比較表</button><span class="note">開啟可列印之比較表（含爭點表態、法條、風險）</span></div></div>
    <p class="foot-note">方案不是憑空生成的：訴願法已將可能結論窮舉（77 不受理、79 駁回、81 撤銷／發回、82 命為處分、83 情況決定）。系統只在存在合理歧見的爭點上分支；沒有歧見時誠實給一案並說明理由。</p>`;
  $$("#p4 input[name=plan]").forEach((r) => r.addEventListener("change", () => { S.plan = r.value; loadDraft(); S.audit.push({ ts: now(), who: "hu", para: "方案", action: `採用${PN[r.value]}案作為草稿基礎` }); renderPlans(); renderDraft(); updateChips(); $$(".tab")[5].click(); }));
  $("#exportCmp").addEventListener("click", exportCompare);
}
function exportCompare() {
  const c = S.c, ps = activePlans(), rec = recommended();
  const stN = { appellant: "採訴願人", agency: "採機關", open: "待議" };
  const w = window.open("", "_blank");
  w.document.write(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>方案比較表 ${c.no}</title><style>body{font-family:"BiauKaiTC","PingFang TC",serif;padding:28px;color:#111;font-size:13px}h1{font-size:18px;letter-spacing:.2em;text-align:center}table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border:1px solid #333;padding:6px 8px;vertical-align:top;text-align:left}th{background:#eee}ul{margin:0;padding-left:16px}.rec{background:#eaf3ea}.note{font-size:11px;color:#555;margin-top:14px}</style></head><body>
    <h1>訴願案件方案比較表</h1><p>案號 ${esc(c.no)}　${esc(c.name)}　製表 ${new Date().toLocaleString("zh-TW")}　承辦人：＿＿＿</p>
    <h3>一、爭點表態</h3><table><tr><th>爭點</th><th>訴願人主張</th><th>機關答辯</th><th>承辦人表態</th></tr>${c.issues.map((it, i) => `<tr><td>${i + 1}. ${esc(it.title)}</td><td>${esc(it.a[0])}</td><td>${esc(it.d[0])}</td><td>${stN[S.stances[it.id]]}</td></tr>`).join("")}</table>
    <h3>二、方案比較</h3><table><tr><th></th>${ps.map((p) => `<th class="${rec && rec.id === p.id ? "rec" : ""}">${p.name}${rec && rec.id === p.id ? "（推薦）" : ""}</th>`).join("")}</tr>
      <tr><td>主文</td>${ps.map((p) => `<td>${esc(p.verdict)}</td>`).join("")}</tr><tr><td>法條依據</td>${ps.map((p) => `<td><ul>${p.basis.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></td>`).join("")}</tr>
      <tr><td>事實認定</td>${ps.map((p) => `<td><ul>${p.facts.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></td>`).join("")}</tr><tr><td>支持案例</td>${ps.map((p) => `<td><ul>${p.cases.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></td>`).join("")}</tr>
      <tr><td>撤銷風險</td>${ps.map((p) => `<td>${{ low: "低", mid: "中", high: "高" }[p.risk[0]]}　${esc(p.risk[1])}</td>`).join("")}</tr></table>
    <p class="note">本表由訴願智審臺原型依承辦人表態自動編製，僅供訴願審議委員會參考；一切法律見解與事實認定以委員會決議為準。</p><script>setTimeout(()=>window.print(),300)</script></body></html>`);
  w.document.close();
}

/* ---------- Tab 6：決定書草稿＋對話＋版本＋稽核 ---------- */
function paraLabel(p) { if (!p) return "全文"; if (p.kind === "h4") return p.text; if (p.kind === "meta") return "當事人欄"; const m = /^([一二三四五六七八九十]+)、/.exec(p.text.replace(/<[^>]+>/g, "")); const sect = p.id.startsWith("r") ? "理由" : p.id.startsWith("fact") ? "事實" : p.id === "main" ? "主文" : "前言"; return m ? `${sect}${m[1]}` : sect; }
function renderDraft() {
  const c = S.c, d = draftFor(S.plan), p = activePlans().find((x) => x.id === S.plan);
  if (S.sel && !S.paras.some((q) => q.id === S.sel)) S.sel = null;
  const body = S.paras.map((q) => {
    if (q.kind === "h4") return `<h4>${q.text}</h4>`;
    const html = fillDates(q.text);
    const cite = q.cite || (q.refs && q.refs.length) ? `<span class="cite">${q.refs && q.refs.length ? q.refs.map((r) => `<span class="jump" data-jump="${r}">↗ ${refTitle(r)}</span>`).join("") : ""}${q.cite ? esc(q.cite) : ""}</span>` : "";
    return `<p class="para ${S.sel === q.id ? "sel" : ""}" data-pid="${q.id}" data-src="${q.src}" contenteditable="true" spellcheck="false">${html}</p>${cite}`;
  }).join("");
  const fills = (S.paras.map((q) => q.text).join("").match(/class=\\?"fill/g) || []).length;
  $("#p5").innerHTML = `
    <div class="sec"><div class="sec-head"><h3>決定書草稿</h3><span class="note">套用「${esc(d.tmpl)}」模板　${p ? `・${p.name}` : ""}　・直接點段落即可編輯</span></div>
      <div class="box2">
        <div class="draft-bar"><button class="btn" id="exportOdf">匯出 ODF 公文格式</button><button class="ghost-btn" id="copyAll">複製全文</button><span class="tag amber">黃底待人工確認 ${fills} 處</span>
          <div class="legend"><span><i style="background:var(--accent-soft);border-left:3px solid var(--accent-soft)"></i>AI 生成</span><span><i style="background:var(--green)"></i>人工編輯</span><span><i style="background:var(--accent)"></i>AI 依指令修改</span><span><i style="background:var(--amber-soft);border-bottom:1px dashed var(--amber)"></i>待確認</span></div></div>
        <div class="draft" id="draftBody"><div class="draft-title">${esc(d.head)}</div><div class="draft-sub">${esc(d.sub)}</div>${body}<p style="color:var(--ink-3);font-size:12px;margin-top:20px">（訴願審議委員會委員名單、教示條款及發文日期由公文系統自動帶入）</p></div>
      </div>
      <div class="chat" id="chat">
        <div class="chat-head"><span class="eyebrow">承辦人助手</span><span>對草稿下指令；先點選段落可限定作用範圍</span><span class="scope">作用範圍：<b id="scopeTxt">${S.sel ? paraLabel(S.paras.find((q) => q.id === S.sel)) : "全文"}</b></span></div>
        <div class="chat-log" id="chatLog"></div>
        <div class="quick"><button class="ghost-btn" data-cmd="merge">合併其他方案論述</button><button class="ghost-btn" data-cmd="tone">改寫語氣（更嚴謹）</button><button class="ghost-btn" data-cmd="cite">補充依據</button><button class="ghost-btn" data-cmd="delete">刪除段落</button><button class="ghost-btn" data-cmd="dates">重算日期</button></div>
        <div class="chat-in"><input id="chatIn" placeholder="例如：把乙案的舉證論述併入理由六　／　理由三語氣再嚴謹一點"><button class="btn" id="chatSend">送出</button></div>
      </div></div>
    <div class="sec"><div class="sec-head"><h3>版本歷史與稽核軌跡</h3><span class="note">每段記錄生成來源、修改者、時間</span></div>
      <div class="hist"><div class="box2"><div class="chat-head" style="border-bottom:1px solid var(--line)"><span class="eyebrow">版本</span><span id="vcount"></span></div><div class="vlist" id="vlist"></div></div>
        <div class="box2"><div class="chat-head" style="border-bottom:1px solid var(--line)"><span class="eyebrow">稽核軌跡</span></div><div class="alist" id="alist" style="max-height:260px;overflow-y:auto"></div></div></div></div>
    <div class="sec"><div class="sec-head"><h3>本案效益</h3><span class="note">與同類案件人工作業比較</span></div><div class="box2 gain">${c.gain.map((g) => `<div><span class="v ${g[2]}">${esc(g[0])}</span><span class="k">${esc(g[1])}</span></div>`).join("")}</div></div>
    <p class="foot-note">草稿僅供承辦人參考，一切法律見解與事實認定仍以承辦人及訴願審議委員會之判斷為準。系統不會自動送出任何決定書；黃底標示處為模型無法自卷面確認之事項，必須由承辦人補實後始得送審。</p>`;
  // 編輯與選取
  $$("#draftBody .para").forEach((el) => {
    el.addEventListener("click", () => { S.sel = el.dataset.pid; $$("#draftBody .para").forEach((x) => x.classList.toggle("sel", x === el)); $("#scopeTxt").textContent = paraLabel(S.paras.find((q) => q.id === S.sel)); });
    el.addEventListener("input", () => { const q = S.paras.find((x) => x.id === el.dataset.pid); q.text = el.innerHTML; q.src = "human"; el.dataset.src = "human"; el.dirty = true; });
    el.addEventListener("blur", () => { if (!el.dirty) return; el.dirty = false; const q = S.paras.find((x) => x.id === el.dataset.pid); S.audit.push({ ts: now(), who: "hu", para: paraLabel(q), action: "人工直接編輯" }); S.versions.push({ ts: now(), label: `人工編輯 ${paraLabel(q)}`, by: "承辦人", snap: S.paras.map((x) => ({ ...x })) }); renderHist(); });
  });
  $("#copyAll").addEventListener("click", () => { navigator.clipboard?.writeText($("#draftBody").innerText); addMsg("a", "已複製全文至剪貼簿。"); });
  $("#exportOdf").addEventListener("click", () => addMsg("a", "原型未串接公文系統；正式版將以 ODF 範本輸出並帶入委員名單與教示條款。"));
  $$(".quick button").forEach((b) => b.addEventListener("click", () => runCommand(b.dataset.cmd)));
  $("#chatSend").addEventListener("click", sendChat); $("#chatIn").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
  if (!S.chatInit) { S.chatInit = true; }
  addMsg("a", `草稿已依${p ? p.name : "推薦方案"}生成，共 ${S.paras.filter((q) => q.kind !== "h4").length} 段。點選段落後可用下方指令修改；每次修改會顯示差異並記錄版本。`, true);
  renderHist();
}
function refTitle(r) { const x = S.c.refs[r]; if (!x) return r; const d = S.c.docs.find((y) => y.id === x[0]); return d ? d.title : r; }
function renderHist() {
  $("#vcount").textContent = `${S.versions.length} 版`;
  $("#vlist").innerHTML = S.versions.map((v, i) => `<div class="vrow ${i === S.versions.length - 1 ? "cur" : ""}"><span class="t">v${i + 1}・${v.ts}</span><span>${esc(v.label)}<span class="note">　${esc(v.by)}</span></span><button class="ghost-btn" data-v="${i}" data-a="diff">與現行比對</button><button class="ghost-btn" data-v="${i}" data-a="restore" ${i === S.versions.length - 1 ? "disabled" : ""}>還原</button></div>`).reverse().join("");
  $("#alist").innerHTML = S.audit.slice().reverse().map((a) => `<div class="arow"><span class="t">${a.ts}</span><span class="who ${a.who}">${a.who === "ai" ? "AI" : "承辦人"}</span><span>${esc(a.para)}：${esc(a.action)}</span></div>`).join("");
  $$("#vlist button").forEach((b) => b.addEventListener("click", () => {
    const v = S.versions[+b.dataset.v];
    if (b.dataset.a === "restore") { S.paras = v.snap.map((x) => ({ ...x })); S.versions.push({ ts: now(), label: `還原至 v${+b.dataset.v + 1}`, by: "承辦人", snap: S.paras.map((x) => ({ ...x })) }); S.audit.push({ ts: now(), who: "hu", para: "全文", action: `還原至 v${+b.dataset.v + 1}` }); renderDraft(); return; }
    const changed = [];
    v.snap.forEach((q) => { const cur = S.paras.find((x) => x.id === q.id); if (!cur) changed.push(`<div><b>${esc(paraLabel(q))}</b>（現行已刪除）<div class="diffbox"><del>${plain(q.text)}</del></div></div>`); else if (plain(cur.text) !== plain(q.text)) changed.push(`<div><b>${esc(paraLabel(q))}</b><div class="diffbox">${diffHtml(plain(q.text), plain(cur.text))}</div></div>`); });
    S.paras.forEach((q) => { if (!v.snap.some((x) => x.id === q.id)) changed.push(`<div><b>${esc(paraLabel(q))}</b>（v${+b.dataset.v + 1} 無此段）<div class="diffbox"><ins>${plain(q.text)}</ins></div></div>`); });
    addMsg("a", `<b>v${+b.dataset.v + 1} → 現行</b>　${changed.length ? changed.length + " 段有差異" : "無差異"}${changed.join("")}`);
    $("#chatLog").scrollIntoView({ block: "nearest", behavior: "smooth" });
  }));
}

/* ---------- 對話指令 ---------- */
const plain = (h) => String(h).replace(/<[^>]+>/g, "");
function addMsg(role, html, quiet) { const log = $("#chatLog"); if (!log) return; const el = document.createElement("div"); el.className = "msg " + role; el.innerHTML = html; log.appendChild(el); if (!quiet) log.scrollTop = log.scrollHeight; return el; }
function sendChat() {
  const inp = $("#chatIn"), t = inp.value.trim(); if (!t) return; inp.value = ""; addMsg("u", esc(t));
  const m = /(理由|事實)([一二三四五六七八九十]+)/.exec(t); if (m) { const q = S.paras.find((x) => paraLabel(x) === m[1] + m[2]); if (q) { S.sel = q.id; $$("#draftBody .para").forEach((x) => x.classList.toggle("sel", x.dataset.pid === q.id)); $("#scopeTxt").textContent = paraLabel(q); } }
  if (/合併|併入|納入|加入.*方案/.test(t)) runCommand("merge"); else if (/語氣|嚴謹|改寫|潤飾/.test(t)) runCommand("tone"); else if (/補充|依據|法條|引用|援引/.test(t)) runCommand("cite"); else if (/刪除|刪掉|移除/.test(t)) runCommand("delete"); else if (/日期|重算|期間/.test(t)) runCommand("dates");
  else addMsg("a", "本原型支援五類指令：<b>合併其他方案論述</b>、<b>改寫語氣</b>、<b>補充依據</b>、<b>刪除段落</b>、<b>重算日期</b>。可直接說「理由六合併乙案」「理由三語氣嚴謹一點」，或先點選段落再按下方按鈕。");
}
function runCommand(cmd) {
  const q = S.sel ? S.paras.find((x) => x.id === S.sel) : null;
  const needSel = () => { addMsg("a", "請先點選草稿中的一個段落（或在指令中指名，例如「理由六」），再執行此指令。"); };
  if (!q || q.kind === "h4") return needSel();
  const old = plain(q.text); let nw = null, note = "", newCite = null;
  if (cmd === "merge") { if (!q.merge) return addMsg("a", `${paraLabel(q)} 沒有其他方案的對應論述可併入。有對應論述的段落會在方案切換時保留關聯（例如甲案理由六 ↔ 乙案理由二）。`); nw = old + q.merge.text; note = `已將${PN[q.merge.from]}案之對應論述併入${paraLabel(q)}，主結論不變。`; }
  else if (cmd === "tone") { const R = [["尚難採據", "洵無可採"], ["應堪認定", "堪以認定"], ["洵屬有據", "於法有據"], ["並無不合", "尚無違誤"], ["並無違誤", "核無違誤"], ["等語。", "云云。"], ["惟查", "經查"], ["惟經", "然經"], ["復經", "並經"], ["不足採信", "委無足採"], ["容有誤會", "顯有誤解"]]; nw = old; R.forEach(([a, b]) => { nw = nw.split(a).join(b); }); if (nw === old) return addMsg("a", `${paraLabel(q)} 已為正式公文語氣，未找到可調整之慣用語。`); note = "已改寫為更嚴謹之公文用語，事實與引用未變動。"; }
  else if (cmd === "cite") {
    const norm = (s) => s.replace(/[\s　]/g, "");
    const cited = (l) => { const key = norm(l.n).replace(/（.*?）/g, ""); const short = key.split("第")[0] + "第" + (key.split("第")[1] || "").split("條")[0] + "條"; return norm(old).includes(key) || (short.length > 4 && norm(old).includes(short)); };
    const cand = S.c.laws.find((l) => !cited(l));
    if (!cand) return addMsg("a", "本段已涵蓋法規推薦頁之全部相關依據。"); nw = old + `（並參照${cand.n}）`; newCite = cand; note = `已補充「${cand.n}」為依據。`; }
  else if (cmd === "delete") { nw = ""; note = `將刪除${paraLabel(q)}；後續段落編號請於套用後自行調整。`; }
  else if (cmd === "dates") { if (!/\{\{/.test(q.tpl)) return addMsg("a", `${paraLabel(q)} 不含期間計算模組推導之日期，無需重算。`); const re = plain(fillDates(q.tpl)); if (re === old) return addMsg("a", `${paraLabel(q)} 之日期已與目前期間計算（送達 ${S.served || "—"}、收文 ${S.recv || "—"}）一致。`); nw = re; note = "已依目前期間計算結果重填日期。"; }
  const el = addMsg("a", `<b>${paraLabel(q)}</b>　${esc(note)}<div class="diffbox">${cmd === "delete" ? `<del>${esc(old)}</del>` : diffHtml(old, nw)}<div class="acts"><button class="btn" data-a="apply">套用</button><button class="ghost-btn" data-a="cancel">取消</button></div></div>`);
  el.querySelector('[data-a="cancel"]').addEventListener("click", () => { el.querySelector(".acts").innerHTML = '<span class="note">已取消</span>'; });
  el.querySelector('[data-a="apply"]').addEventListener("click", () => {
    if (cmd === "delete") { S.paras = S.paras.filter((x) => x.id !== q.id); S.sel = null; }
    else { q.text = cmd === "dates" ? fillDates(q.tpl) : (q.text.replace(/<[^>]+>/g, "") === old ? nw : nw); q.src = "ai-edit"; if (cmd === "cite" && newCite) { q.cite = (q.cite ? q.cite + "｜" : "") + "補充依據：" + newCite.n; } }
    const label = { merge: "合併方案論述", tone: "改寫語氣", cite: "補充依據", delete: "刪除段落", dates: "重算日期" }[cmd];
    S.audit.push({ ts: now(), who: "ai", para: paraLabel(q), action: label + "（承辦人核可套用）" });
    S.versions.push({ ts: now(), label: `${label}・${paraLabel(q)}`, by: "AI（承辦人核可）", snap: S.paras.map((x) => ({ ...x })) });
    el.querySelector(".acts").innerHTML = '<span class="note" style="color:var(--green)">✓ 已套用並記錄版本</span>';
    if (newCite) { const c = S.c.citations.find((x) => x.n === newCite.n); const amended = c && c.status === "amended" || /修正公布/.test(newCite.badges.join("")); setTimeout(() => addMsg("a", `<b>引用驗證</b>　《${esc(newCite.n)}》${amended ? '<span class="st amended">該條已修正</span>　請確認行為時適用版本' : '<span class="st ok">已驗證</span>　資料集內文件、現行有效'}`), 350); }
    renderDraftKeepLog();
  });
}
function renderDraftKeepLog() { const log = $("#chatLog").innerHTML; renderDraft(); $("#chatLog").innerHTML = log; $("#chatLog").scrollTop = $("#chatLog").scrollHeight; }

/* ---------- 字元級 diff（LCS） ---------- */
function diffHtml(a, b) {
  const n = a.length, m = b.length;
  if (n * m > 400000) return `<del>${esc(a)}</del><ins>${esc(b)}</ins>`;
  const dp = new Uint16Array((n + 1) * (m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i * (m + 1) + j] = a[i] === b[j] ? dp[(i + 1) * (m + 1) + j + 1] + 1 : Math.max(dp[(i + 1) * (m + 1) + j], dp[i * (m + 1) + j + 1]);
  let i = 0, j = 0, out = "", buf = { t: "", k: "" };
  const flush = () => { if (!buf.t) return; out += buf.k === "=" ? esc(buf.t) : buf.k === "-" ? `<del>${esc(buf.t)}</del>` : `<ins>${esc(buf.t)}</ins>`; buf = { t: "", k: "" }; };
  const push = (k, ch) => { if (buf.k !== k) { flush(); buf.k = k; } buf.t += ch; };
  while (i < n && j < m) { if (a[i] === b[j]) { push("=", a[i]); i++; j++; } else if (dp[(i + 1) * (m + 1) + j] >= dp[i * (m + 1) + j + 1]) { push("-", a[i]); i++; } else { push("+", b[j]); j++; } }
  while (i < n) { push("-", a[i++]); } while (j < m) { push("+", b[j++]); }
  flush(); return out;
}
