/* =========================================================
   後端接線層（文件歸戶 API v0.3）
   契約：docs/API-文件歸戶.md　　開發期指到雲端，正式版與前端同源
   原則：沒有 fallback——失敗就拋出可讀的錯誤，不回假資料
   ========================================================= */
"use strict";

const API_BASE = (() => {
  if (typeof location === "undefined") return "";          // Node 下只用 toDocs，不打 API
  const q = new URLSearchParams(location.search).get("api");
  if (q) return q.replace(/\/$/, "");
  if (location.protocol === "file:" || /^(localhost|127\.)/.test(location.hostname)) return "http://100.20.156.38/api";
  return "/api";                       // 與前端同源（正式部署）
})();

class ApiError extends Error {
  constructor(code, message, status) { super(message || code); this.code = code; this.status = status; }
  get text() { return `${this.code}：${this.message}`; }
}

async function req(path, opts = {}) {
  let res;
  try { res = await fetch(API_BASE + path, opts); }
  catch (e) { throw new ApiError("NETWORK", `連不到後端（${API_BASE}）。請確認服務是否運行、你的 IP 是否在允許清單內。`, 0); }
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("json") ? await res.json().catch(() => ({})) : {};
  if (!res.ok) throw new ApiError(body.code || `HTTP_${res.status}`, body.message || res.statusText, res.status);
  return body;
}

/* ---------- 端點 ---------- */
const Api = {
  base: API_BASE,
  ApiError,

  health: () => req("/health"),

  /** files：File 物件陣列（不是檔名）；回 {jobId, files[], eventsUrl} */
  upload(caseId, files) {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return req(`/cases/${encodeURIComponent(caseId)}/files`, { method: "POST", body: fd });
  },

  /** 用 S3 預放的示範卷宗真跑一次（非查表） */
  demo: (caseId, { pack = "case02", messy = false } = {}) =>
    req(`/cases/${encodeURIComponent(caseId)}/demo`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pack, messy }),
    }),

  listFiles: (caseId, { includeExcluded = false } = {}) =>
    req(`/cases/${encodeURIComponent(caseId)}/files${includeExcluded ? "?includeExcluded=true" : ""}`),

  fileText: (caseId, fileId) => req(`/cases/${encodeURIComponent(caseId)}/files/${fileId}/text`),

  patchFile: (caseId, fileId, patch) =>
    req(`/cases/${encodeURIComponent(caseId)}/files/${fileId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
    }),

  audit: (caseId) => req(`/cases/${encodeURIComponent(caseId)}/audit`),

  job: (jobId) => req(`/jobs/${jobId}`),

  /* ---- 分析階段（步驟 2–5／異議／法規庫）：docs/API-分析階段.md ---- */
  analyze: (caseId) => req(`/cases/${encodeURIComponent(caseId)}/analyze`, { method: "POST" }),
  analysis: (caseId) => req(`/cases/${encodeURIComponent(caseId)}/analysis`),
  objection: (caseId, body) => req(`/cases/${encodeURIComponent(caseId)}/objection`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  lawlib: () => req("/lawlib"),
  lawSync: () => req("/lawlib/sync", { method: "POST" }),
  /** 每 interval ms 輪詢 GET analysis，直到 done/failed；onTick(doc) 每次都叫 */
  pollAnalysis(caseId, onTick, { interval = 3000, timeout = 600000 } = {}) {
    let stop = false; const t0 = Date.now();
    const loop = async () => {
      if (stop) return;
      let doc = null;
      try { doc = await Api.analysis(caseId); } catch (e) { if (e.status !== 404) { onTick(null, e); return; } }
      if (doc) { onTick(doc); if (doc.status?.state === "done" || doc.status?.state === "failed") return; }
      if (Date.now() - t0 > timeout) return onTick(null, new ApiError("TIMEOUT", "分析超過 10 分鐘未完成"));
      setTimeout(loop, interval);
    };
    loop();
    return { stop: () => { stop = true; } };
  },

  /** SSE。回一個 {close()}；EventSource 不能帶標頭，重連走 ?lastEventId= */
  streamJob(jobId, handlers = {}, { lastEventId = 0 } = {}) {
    const url = `${API_BASE}/jobs/${jobId}/events${lastEventId ? `?lastEventId=${lastEventId}` : ""}`;
    const es = new EventSource(url);
    let maxSeq = lastEventId;
    const on = (name, fn) => es.addEventListener(name, (e) => {
      maxSeq = Math.max(maxSeq, +e.lastEventId || 0);
      let data = {};
      try { data = JSON.parse(e.data); } catch { /* 保持空物件 */ }
      fn?.(data, maxSeq);
    });
    on("queued", handlers.onQueued);
    on("started", handlers.onStarted);
    on("normalized", handlers.onNormalized);
    on("container", handlers.onContainer);
    on("box", handlers.onBox);
    on("result", handlers.onResult);
    on("done", (d) => { es.close(); handlers.onDone?.(d); });
    on("fatal", (d) => { es.close(); handlers.onFatal?.(new ApiError(d.code || "FATAL", d.message)); });
    es.onerror = () => {
      // 瀏覽器會自動重連，但補不了已錯過的事件；關掉自己用 lastEventId 重開
      if (es.readyState === EventSource.CLOSED) handlers.onFatal?.(new ApiError("SSE_CLOSED", "事件串流中斷", 0));
    };
    return { close: () => es.close(), get lastEventId() { return maxSeq; } };
  },
};

/* =========================================================
   後端 File[] → 前端 doc[]
   一個 segment 一列（合併卷宗 20 頁 17 段 = 17 列），同 fileId 共用原檔與頁圖
   ========================================================= */
function toDocs(payload) {
  const out = [];
  for (const f of payload.files || []) {
    const base = {
      fileId: f.fileId, origName: f.originalName, status: f.status,
      kind: f.kind, pages: f.pages, duration: f.duration,
      file: f.rawUrl || null, downloadUrl: f.downloadUrl || f.rawUrl || null, textUrl: f.textUrl || null,
      pageImageUrls: f.pageImageUrls || [], imagePages: f.imagePages || [],
      contentImagePages: f.contentImagePages || [], warnings: f.warnings || [],
    };

    // 沒有分類結果的狀態：各自一列，不進三方對照
    if (f.status !== "done" && f.status !== "excluded") {
      out.push({
        ...base, id: f.fileId, title: f.originalName, stdName: f.originalName,
        tag: "其他", src: "未知", include: false,
        dup: f.status === "duplicate", container: f.status === "container", err: f.error || null,
        summary: f.status === "duplicate" ? `與既有檔案內容相同，已排除`
          : f.status === "container" ? `壓縮檔，已展開 ${(f.childIds || []).length} 份`
          : f.status === "error" ? `無法讀取：${f.error?.code || "未知錯誤"}`
          : "處理中",
      });
      continue;
    }

    const segs = f.segments || [];
    segs.forEach((s, i) => {
      const multi = segs.length > 1;
      out.push({
        ...base,
        id: s.segId || `${f.fileId}#${i}`,
        segIndex: i,
        title: s.doc_type, tag: s.doc_type, src: s.source,
        nature: s.nature, timing: s.timing, date: s.date, docNo: s.doc_no, party: s.party_hint,
        stdName: s.suggestedName, summary: s.summary,
        confidence: s.confidence, evidence: s.evidence, unverified: !!s.evidence_unverified,
        fromPage: s.fromPage, toPage: s.toPage,
        pages: multi ? s.toPage - s.fromPage + 1 : f.pages,
        thumb: s.pageImageUrl || null,
        include: f.status !== "excluded",
        partOf: multi ? { name: f.originalName, total: segs.length, n: i + 1 } : null,
        manual: s.manual || null,
      });
    });
  }
  return out;
}

/** 依來源分組（五組，空組不顯示由呼叫端決定） */
function groupDocs(docs) {
  const order = typeof SRC_ORDER !== "undefined" ? SRC_ORDER : ["訴願人", "原處分機關", "第三方", "本局", "未知"];
  return order.map((src) => [src, docs.filter((d) => (d.src || "未知") === src)]);
}

if (typeof window !== "undefined") Object.assign(window, { Api, toDocs, groupDocs });
if (typeof module !== "undefined") module.exports = { toDocs, groupDocs };
