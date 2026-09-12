/* =========================================================
   ② 標籤：正規化結果 → 裝箱 → Bedrock Converse（強制 schema）→ 逐檔 segments
   ========================================================= */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";

const here = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0";
export const MODEL = process.env.MODEL || DEFAULT_MODEL;
const REGION = process.env.AWS_REGION || "us-east-1";

export const DOC_TYPES = ["訴願書", "訴願委任書", "答辯書", "答辯書檢送函", "卷證目錄", "裁處書", "裁處書送達證書", "陳述意見通知書", "通知書送達證書", "陳述意見書", "檢舉資料", "稽查紀錄", "調查筆錄", "採證照片", "影像放大標註", "採證影片", "車籍資料", "係數計算表", "簽呈", "檢驗報告", "契約書", "委員會決定書", "閱覽卷宗申請書", "言詞辯論申請書", "言詞陳述申請書", "參加訴願申請書", "其他"];
export const SOURCES = ["訴願人", "原處分機關", "第三方", "本局", "未知"];
export const FORMS = ["文字PDF", "掃描", "照片", "影片", "系統列印", "手寫"];

/* 裝箱預算：三者先到先開新箱 */
export const BOX = { files: +(process.env.BOX_FILES || 10), images: 20, chars: 120_000 };
const PAGE_CAP = 3000;           // 每頁文字上限（字）
const TEXT_CAP = 60_000;         // 每檔文字上限（字）；20 頁合併卷宗約 25k
const MAX_RETRY = 3;

const SEGMENT_SCHEMA = {
  type: "object",
  required: ["fromPage", "toPage", "doc_type", "source", "form", "date", "doc_no", "party_hint", "summary", "confidence", "evidence"],
  properties: {
    fromPage: { type: "integer", minimum: 1 }, toPage: { type: "integer", minimum: 1 },
    doc_type: { type: "string", enum: DOC_TYPES }, source: { type: "string", enum: SOURCES }, form: { type: "string", enum: FORMS },
    date: { type: ["string", "null"] }, doc_no: { type: ["string", "null"] }, party_hint: { type: ["string", "null"] },
    summary: { type: "string" }, confidence: { type: "number", minimum: 0, maximum: 1 }, evidence: { type: "string" },
  },
};
const TOOL = {
  toolSpec: {
    name: "submit_classification",
    description: "回傳每個檔案的歸戶判定。每個 fileId 恰好一筆。",
    inputSchema: { json: { type: "object", required: ["results"], properties: { results: { type: "array", items: {
      type: "object", required: ["fileId", "segments"],
      properties: { fileId: { type: "string" }, segments: { type: "array", minItems: 1, items: SEGMENT_SCHEMA } },
    } } } } },
  },
};

let SYSTEM;
async function systemPrompt() { return (SYSTEM ??= await fs.readFile(path.join(here, "prompts", "classify.md"), "utf8")); }

/* ---------- 裝箱 ---------- */
function cost(n) { return { images: n.images?.length ?? 0, chars: Math.min(n.text?.length ?? 0, TEXT_CAP) }; }

/** 同類型打散：依 kind 輪流取，避免連續多張相似照片相鄰 */
function interleave(items) {
  const groups = new Map();
  for (const it of items) { const k = it.kind; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(it); }
  const out = [];
  while (out.length < items.length) for (const g of groups.values()) if (g.length) out.push(g.shift());
  return out;
}

export function pack(normalized, box = BOX) {
  const usable = normalized.filter((n) => n.ok && n.kind !== "unsupported" && n.kind !== "zip");
  const boxes = [];
  let cur = null;
  for (const n of interleave(usable)) {
    const c = cost(n);
    if (c.images > box.images) { boxes.push({ items: [n], images: c.images, chars: c.chars, oversize: true }); continue; }   // 多頁掃描獨占一箱（可能超過 20 張，另切）
    if (!cur || cur.items.length >= box.files || cur.images + c.images > box.images || cur.chars + c.chars > box.chars) {
      cur = { items: [], images: 0, chars: 0 }; boxes.push(cur);
    }
    cur.items.push(n); cur.images += c.images; cur.chars += c.chars;
  }
  return boxes;
}

/* ---------- 組 Converse content（交錯：標頭 → 該檔內容 → 標頭 → …） ---------- */
async function fileBlocks(n, { imagesFrom = 0, imagesTo } = {}) {
  const blocks = [];
  const head = `=== FILE ${n.fileId} | 原檔名: ${n.originalName} | kind: ${n.kind}${n.pages ? ` | 頁數: ${n.pages}` : ""}${n.duration ? ` | 時長: ${n.duration}s` : ""}${n.exif?.takenAt ? ` | EXIF拍攝: ${n.exif.takenAt}` : ""} ===`;
  blocks.push({ text: head });
  if (n.kind === "pdf-text" || n.kind === "office" || n.kind === "text") {
    let acc = "", used = 0;
    for (const [i, t] of (n.textPerPage?.length ? n.textPerPage : [n.text]).entries()) {
      if (used >= TEXT_CAP) { acc += `\n[p${i + 1}] …（略）`; continue; }
      const piece = t.slice(0, Math.min(PAGE_CAP, TEXT_CAP - used)); used += piece.length;
      acc += `\n[p${i + 1}]\n${piece}`;
    }
    blocks.push({ text: acc || "（無文字）" });
  }
  const imgs = (n.images ?? []).slice(imagesFrom, imagesTo);
  if (n.kind === "pdf-text" || n.kind === "office") { /* 批次模式不送文字 PDF 的頁圖 */ }
  else for (const [i, p] of imgs.entries()) {
    const label = n.kind === "video" ? `[幀 ${i + 1}/${imgs.length} @${n.frameTimes?.[i] ?? "?"}s]` : n.kind === "pdf-scan" ? `[p${imagesFrom + i + 1}]` : "[圖]";
    blocks.push({ text: label });
    blocks.push({ image: { format: "jpeg", source: { bytes: await fs.readFile(p) } } });
  }
  return blocks;
}

/* ---------- 呼叫 ---------- */
const client = new BedrockRuntimeClient({ region: REGION });

async function converse(blocks, { model = MODEL } = {}) {
  const cmd = new ConverseCommand({
    modelId: model,
    system: [{ text: await systemPrompt() }],
    messages: [{ role: "user", content: blocks }],
    toolConfig: { tools: [TOOL], toolChoice: { tool: { name: "submit_classification" } } },
    inferenceConfig: { maxTokens: 8000, temperature: 0 },
  });
  let lastErr;
  for (let attempt = 0; attempt < MAX_RETRY; attempt++) {
    try {
      const t0 = Date.now();
      const res = await client.send(cmd);
      const use = res.output?.message?.content?.find((c) => c.toolUse)?.toolUse;
      if (!use) throw Object.assign(new Error("model returned no tool use"), { code: "SCHEMA_INVALID" });
      return { results: use.input.results, usage: res.usage, ms: Date.now() - t0, stopReason: res.stopReason };
    } catch (e) {
      lastErr = e;
      const throttled = e.name === "ThrottlingException" || e.$metadata?.httpStatusCode === 429;
      if (!throttled) break;
      await new Promise((r) => setTimeout(r, 1500 * 2 ** attempt));
    }
  }
  const code = lastErr.code || (lastErr.name === "ThrottlingException" ? "BEDROCK_THROTTLED" : /AccessDenied|UnrecognizedClient|ExpiredToken|ResourceNotFound/.test(lastErr.name) ? "BEDROCK_UNAVAILABLE" : "BEDROCK_ERROR");
  throw Object.assign(new Error(lastErr.message), { code, cause: lastErr });
}

/* ---------- 後處理 ---------- */
const ORDER = ["訴願書", "訴願委任書", "閱覽卷宗申請書", "言詞辯論申請書", "言詞陳述申請書", "參加訴願申請書", "答辯書檢送函", "答辯書", "卷證目錄", "裁處書", "裁處書送達證書", "檢舉資料", "稽查紀錄", "調查筆錄", "採證照片", "影像放大標註", "採證影片", "車籍資料", "陳述意見通知書", "通知書送達證書", "陳述意見書", "係數計算表", "簽呈", "檢驗報告", "契約書", "委員會決定書", "其他"];
const seq = (t) => String(Math.max(0, ORDER.indexOf(t)) + 1).padStart(2, "0");

/** 性質（主張／紀錄／證物）由 doc_type 查表，不問模型 */
export const NATURE = {
  "訴願書": "主張", "訴願委任書": "主張", "答辯書": "主張", "陳述意見書": "主張", "閱覽卷宗申請書": "主張", "言詞辯論申請書": "主張", "言詞陳述申請書": "主張", "參加訴願申請書": "主張", "檢舉資料": "主張",
  "答辯書檢送函": "紀錄", "卷證目錄": "紀錄", "裁處書": "紀錄", "裁處書送達證書": "紀錄", "陳述意見通知書": "紀錄", "通知書送達證書": "紀錄", "稽查紀錄": "紀錄", "調查筆錄": "紀錄", "車籍資料": "紀錄", "係數計算表": "紀錄", "簽呈": "紀錄", "委員會決定書": "紀錄", "契約書": "紀錄",
  "採證照片": "證物", "影像放大標註": "證物", "採證影片": "證物", "檢驗報告": "證物",
  "其他": "未知",
};

/** 時點：以該案裁處書日期為界（整案後處理，classifyAll 結束後呼叫） */
export function annotateTiming(results) {
  const dates = results.flatMap((r) => r.ok ? r.segments.filter((s) => s.doc_type === "裁處書" && s.date).map((s) => s.date) : []);
  const cut = dates.sort()[0] ?? null;
  for (const r of results) if (r.ok) for (const s of r.segments) {
    s.timing = !cut || !s.date ? "未知" : s.doc_type === "裁處書" ? "處分作成" : s.date <= cut ? "處分作成前" : "爭訟發生後";
  }
  return { cutoff: cut, results };
}

export function suggestedName(seg, ext) {
  const tail = seg.date?.replace(/-/g, "") || seg.doc_no?.match(/\d[\d-]*\d/)?.[0]?.slice(-8) || "";
  const src = seg.source && seg.source !== "未知" ? `_${seg.source}` : "";
  return `${seq(seg.doc_type)}-${seg.doc_type}${tail ? `_${tail}` : ""}${src}${ext ? `.${ext}` : ""}`;
}

function verifyEvidence(seg, n) {
  if (!seg.evidence || !n.text) return seg;
  // 取 evidence 中「」內字樣或連續 4 字以上片段，檢查是否真在該檔文字中
  const quotes = [...seg.evidence.matchAll(/「([^」]{2,})」/g)].map((m) => m[1].replace(/\s/g, ""));
  if (!quotes.length) return seg;
  const hay = n.text.replace(/\s/g, "");          // pdftotext -layout 會在標題字間塞空白
  const hit = quotes.some((q) => hay.includes(q));
  if (!hit) { seg.confidence = Math.round(seg.confidence * 0.6 * 100) / 100; seg.evidence_unverified = true; }
  return seg;
}

function postprocess(seg, n) {
  if (seg.doc_type === "其他") seg.summary = "無法辨識內容";
  seg.nature = NATURE[seg.doc_type] ?? "未知";
  if (["採證照片", "採證影片", "影像放大標註"].includes(seg.doc_type) && n.kind !== "pdf-text") { /* 來源由模型依證據回；規則層不覆寫 */ }
  verifyEvidence(seg, n);
  seg.suggestedName = suggestedName(seg, path.extname(n.originalName).replace(".", "").toLowerCase());
  return seg;
}

/* ---------- 主流程 ---------- */
/**
 * classifyAll(normalized, {perFile, model, onBox})
 *  → [{fileId, ok, segments | error, box, ms}]
 */
export async function classifyAll(normalized, { perFile = false, model = MODEL, onBox } = {}) {
  const results = new Map();
  for (const n of normalized) {
    if (!n.ok) results.set(n.fileId, { fileId: n.fileId, originalName: n.originalName, ok: false, error: n.error });
    else if (n.kind === "unsupported") results.set(n.fileId, { fileId: n.fileId, originalName: n.originalName, ok: true, skipped: true, segments: [{ fromPage: 1, toPage: 1, doc_type: "其他", source: "未知", form: "文字PDF", date: null, doc_no: null, party_hint: null, summary: "無法辨識內容", confidence: 1, evidence: "不支援的檔案格式，未送模型", suggestedName: suggestedName({ doc_type: "其他" }, path.extname(n.originalName).slice(1)) }] });
  }
  const boxes = perFile ? normalized.filter((n) => n.ok && n.kind !== "unsupported" && n.kind !== "zip").map((n) => ({ items: [n], images: n.images?.length ?? 0 })) : pack(normalized);

  for (const [bi, box] of boxes.entries()) {
    const byId = new Map(box.items.map((n) => [n.fileId, n]));
    const settle = (fileId, r) => results.set(fileId, { fileId, originalName: byId.get(fileId)?.originalName, box: bi, ...r });
    try {
      let out;
      if (box.oversize) out = await classifyOversize(box.items[0], model);
      else {
        const blocks = [];
        for (const n of box.items) blocks.push(...(await fileBlocks(n, perFile ? {} : {})));
        out = await converse(blocks, { model });
      }
      const seen = new Set();
      for (const r of out.results ?? []) {
        const n = byId.get(r.fileId);
        if (!n || seen.has(r.fileId)) continue;              // 多的丟
        seen.add(r.fileId);
        settle(r.fileId, { ok: true, segments: r.segments.map((s) => postprocess(s, n)), ms: out.ms, usage: seen.size === 1 ? out.usage : undefined });   // 用量只記在箱內第一筆，避免重複加總
      }
      for (const n of box.items) if (!seen.has(n.fileId)) {   // 少的：單檔補跑一次
        try {
          const one = await converse(await fileBlocks(n), { model });
          const r = one.results?.find((x) => x.fileId === n.fileId) ?? one.results?.[0];
          if (r) settle(n.fileId, { ok: true, segments: r.segments.map((s) => postprocess(s, n)), ms: one.ms, usage: one.usage, retried: true });
          else settle(n.fileId, { ok: false, error: { code: "MISSING_IN_RESPONSE", message: "model omitted this file twice" } });
        } catch (e) { settle(n.fileId, { ok: false, error: { code: e.code || "BEDROCK_ERROR", message: e.message } }); }
      }
    } catch (e) {
      for (const n of box.items) settle(n.fileId, { ok: false, error: { code: e.code || "BEDROCK_ERROR", message: e.message } });
      if (e.code === "BEDROCK_UNAVAILABLE") { onBox?.(bi, boxes.length, results); throw e; }   // 認證/模型不可用：整批停
    }
    onBox?.(bi, boxes.length, results);
  }
  const out = [...results.values()];
  annotateTiming(out);
  return out;
}

/** 掃描 PDF 超過 20 頁：每 20 頁一次，合併 segments 並平移頁碼 */
async function classifyOversize(n, model) {
  const segs = [];
  let ms = 0, usage = { inputTokens: 0, outputTokens: 0 };
  for (let from = 0; from < n.images.length; from += BOX.images) {
    const to = Math.min(n.images.length, from + BOX.images);
    const out = await converse(await fileBlocks(n, { imagesFrom: from, imagesTo: to }), { model });
    ms += out.ms; usage.inputTokens += out.usage?.inputTokens ?? 0; usage.outputTokens += out.usage?.outputTokens ?? 0;
    const r = out.results?.find((x) => x.fileId === n.fileId) ?? out.results?.[0];
    for (const s of r?.segments ?? []) segs.push({ ...s, fromPage: s.fromPage + from, toPage: s.toPage + from });
  }
  return { results: [{ fileId: n.fileId, segments: segs }], ms, usage };
}
