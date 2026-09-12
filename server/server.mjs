/* =========================================================
   文件歸戶 API — 契約見 docs/API-文件歸戶.md
   沒有 fallback：失敗回錯誤碼，不回假資料。
   ========================================================= */
import express from "express";
import multer from "multer";
import { randomUUID, createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { EventEmitter } from "node:events";
import { normalize, flatten, hasTool, REQUIRED_TOOLS, OPTIONAL_TOOLS } from "./normalize.mjs";
import { classifyAll, DOC_TYPES, SOURCES, NATURE, suggestedName, trueExt, annotateTiming, MODEL } from "./classify.mjs";
import { ping, REGION } from "./bedrock.mjs";
import * as s3 from "./store/s3.mjs";
import * as ddb from "./store/ddb.mjs";
import { mountAnalysisProxy } from "./analysis-proxy.mjs";

const PORT = +(process.env.PORT || 8080);
const MAX_FILE = 100 * 1024 * 1024;
const MAX_BATCH = 500 * 1024 * 1024;

const app = express();

/* CORS：前端與 API 同源時用不到，但隊友在本機跑前端打這台時需要。
   存取控制靠 Security Group（IP 白名單），能連到這裡的本來就有完整權限，
   因此預設放行所有來源；要收緊就設 CORS_ORIGIN=http://a,http://b */
const CORS_ORIGIN = process.env.CORS_ORIGIN || "*";
const allowList = CORS_ORIGIN === "*" ? null : CORS_ORIGIN.split(",").map((s) => s.trim());
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && (!allowList || allowList.includes(origin))) {
    res.setHeader("Access-Control-Allow-Origin", allowList ? origin : "*");
    res.setHeader("Vary", "Origin");
  }
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,Last-Event-ID");
  res.setHeader("Access-Control-Expose-Headers", "Content-Type");
  res.setHeader("Access-Control-Max-Age", "86400");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

/* request log：每個請求一行（SSE 在關閉時才記，含持續秒數） */
app.use((req, res, next) => {
  const t0 = Date.now();
  res.on("close", () => { if (!req.path.startsWith("/api/")) return; console.log(`${req.method} ${req.originalUrl} → ${res.statusCode} ${Date.now() - t0}ms`); });
  next();
});
app.use(express.json({ limit: "1mb" }));
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: MAX_FILE, fieldSize: MAX_FILE } });

const err = (res, status, code, message, extra = {}) => res.status(status).json({ code, message, retryable: code === "BEDROCK_THROTTLED", ...extra });
const iso = () => new Date().toISOString();

/* =========================================================
   Job 佇列：案件之間序列（Bedrock 併發在 classifyAll 內部控制）
   ========================================================= */
const bus = new EventEmitter();
bus.setMaxListeners(0);
const queue = [];
let working = false;

function enqueue(job) {
  queue.push(job);
  job.queuePos = working ? queue.length : 0;     // 0 = 立刻開始
  if (!working) drain(); else announceQueue();
}

/** 讓排隊中的 job 知道自己排第幾、前面大概要多久（用最近幾次的實際耗時估） */
const recentMs = [];
const avgJobMs = () => (recentMs.length ? Math.round(recentMs.reduce((a, b) => a + b, 0) / recentMs.length) : 50000);
function announceQueue() {
  queue.forEach((j, i) => {
    const ahead = i + (working ? 1 : 0);
    if (j.announced === ahead) return;
    j.announced = ahead;
    emit(j, "queued", { ahead, etaMs: ahead * avgJobMs() }).catch(() => {});
  });
}
async function drain() {
  working = true;
  while (queue.length) {
    const job = queue.shift();
    announceQueue();
    try { await runJob(job); }
    catch (e) { console.error(`[job ${job.jobId}] 未捕捉例外`, e); }
  }
  working = false;
}

async function emit(job, event, data) {
  const seq = ++job.seq;
  await ddb.appendEvent(job.jobId, seq, event, data);
  if (process.env.DEBUG_SSE) console.log(`[emit] ${job.jobId} #${seq} ${event} listeners=${bus.listenerCount(job.jobId)}`);
  bus.emit(job.jobId, { seq, event, data });
}

async function runJob(job) {
  const { jobId, caseId } = job;
  const t0 = Date.now();
  const outDir = await fs.mkdtemp(path.join(os.tmpdir(), "job-"));
  await ddb.updateJob(jobId, { status: "running", startedAt: iso() });
  console.log(`[job ${jobId}] start case=${caseId} files=${job.files.length} dup=${job.duplicates.length} queue=${queue.length}`);
  await emit(job, "started", { total: job.files.length });
  const counters = { ok: 0, error: 0, duplicate: job.duplicates.length };
  try {
    /* ① 正規化（逐檔推事件） */
    const normalized = [];
    for (const f of job.files) {
      const buf = await s3.getBytes(f.rawKey);
      const r = await normalize(buf, f.originalName, { outDir, fileId: f.fileId });
      const isZip = r.ok && r.kind === "zip";
      let items = isZip ? flatten([r]) : [r];
      if (isZip) {
        // 壓縮檔本身沒有內容可分類：標成容器，子檔各自建紀錄（否則 updateFile 會產生沒有 originalName 的孤兒）
        await ddb.updateFile(caseId, r.fileId, { status: "container", kind: "zip", childIds: items.map((c) => c.fileId), warnings: r.warnings ?? [] });
        await emit(job, "container", { fileId: r.fileId, childIds: items.map((c) => c.fileId) });
        const kept = [];
        for (const c of items) {
          // 子檔內容可能與已上傳的檔相同（fileId 取自 sha256）：直接 putFile 會蓋掉正本的檔名，
          // 改標成重複、且不再送模型分類
          const existing = await ddb.getFile(caseId, c.fileId);
          if (existing && existing.originalName !== c.originalName) {
            await ddb.putFile({ fileId: `${c.fileId}-z${++job.dupSeq}`, caseId, originalName: c.originalName, sha256: c.sha256,
              bytes: c.bytes, status: "duplicate", duplicateOf: c.fileId, parentFileId: r.fileId, jobId, createdAt: iso(), updatedAt: iso() });
            counters.duplicate++;
            await emit(job, "result", { fileId: `${c.fileId}-z${job.dupSeq}`, ok: true, duplicate: true, duplicateOf: c.fileId });
            continue;
          }
          const rawKey = c.srcPath ? await s3.putRaw(caseId, c.fileId, c.originalName, await fs.readFile(c.srcPath)) : undefined;
          await ddb.putFile({ fileId: c.fileId, caseId, originalName: c.originalName, sha256: c.sha256, bytes: c.bytes,
            rawKey, status: "queued", jobId, parentFileId: r.fileId, createdAt: iso(), updatedAt: iso() });
          kept.push(c);
        }
        items = kept;
      }
      for (const n of items) {
        if (n.ok) {
          const stored = await s3.putNormalized(caseId, n.fileId, n);
          n._keys = stored;
          normalized.push(n);
          await emit(job, "normalized", { fileId: n.fileId, kind: n.kind, pages: n.pages, duration: n.duration, warnings: n.warnings });
        } else {
          counters.error++;
          await ddb.updateFile(caseId, n.fileId, { status: "error", error: n.error });
          await emit(job, "result", { fileId: n.fileId, ok: false, error: n.error });
        }
      }
    }

    /* ② 分類（箱之間併發） */
    const byId = new Map(normalized.map((n) => [n.fileId, n]));
    const pushed = new Set();

    /** 一箱跑完就寫 DB、推事件，不等整批 */
    const flush = async (rs) => {
      for (const r of rs) {
        if (!r || pushed.has(r.fileId)) continue;
        pushed.add(r.fileId);
        const n = byId.get(r.fileId);
        if (r.ok) {
          counters.ok++;
          const patch = {
            status: "done", kind: n?.kind, pages: n?.pages, duration: n?.duration,
            mime: n?.mime, warnings: n?.warnings ?? [],
            imagePages: n?.imagePages ?? null, contentImagePages: n?.contentImagePages ?? null,
            imageKeys: n?._keys?.imageKeys ?? [], metaKey: n?._keys?.metaKey,
            segments: r.segments.map((s, i) => ({ segId: `${r.fileId}#${i}`, ...s })),
          };   // updatedAt 由 ddb.updateFile 自動加，這裡不能重複給
          await ddb.updateFile(caseId, r.fileId, patch);
          await emit(job, "result", { fileId: r.fileId, ok: true, segments: patch.segments });
        } else {
          counters.error++;
          await ddb.updateFile(caseId, r.fileId, { status: "error", error: r.error });
          await emit(job, "result", { fileId: r.fileId, ok: false, error: r.error });
        }
      }
    };

    const results = await classifyAll(normalized, {
      onBox: (done, total) => emit(job, "box", { done, total }).catch(() => {}),
      onBoxResults: flush,
    });
    annotateTiming(results);
    await flush(results);            // 補漏（單檔補跑等情況）

    console.log(`[job ${jobId}] done ok=${counters.ok} error=${counters.error} dup=${counters.duplicate} ${Date.now() - t0}ms`);
    await emit(job, "done", { jobId, total: job.files.length, ...counters, ms: Date.now() - t0 });
    await ddb.updateJob(jobId, { status: "done", finishedAt: iso(), counters });
  } catch (e) {
    const code = e.code || "INTERNAL";
    console.error(`[job ${jobId}] ${code}`, e.message);
    await emit(job, "fatal", { code, message: e.message });
    await ddb.updateJob(jobId, { status: "failed", finishedAt: iso(), error: { code, message: e.message } });
  } finally {
    await fs.rm(outDir, { recursive: true, force: true });
    job.finished = true;
    recentMs.push(Date.now() - t0); if (recentMs.length > 5) recentMs.shift();
  }
}

const JOBS = new Map();   // jobId → job（含 seq / finished），SSE live 推用

/* 啟動時：上次程序中斷時仍在 running/queued 的 job 已不在記憶體佇列，標 failed 讓前端收到 fatal 而不是永遠等 */
async function recoverStaleJobs() {
  try {
    const stale = await ddb.listJobsByStatus?.(["running", "queued"]) ?? [];
    for (const j of stale) {
      console.warn(`[job ${j.jobId}] 上次程序重啟時未完成（${j.status}）→ failed`);
      await ddb.appendEvent(j.jobId, (j.seq ?? 9000) + 1, "fatal", { code: "SERVER_RESTARTED", message: "後端重新啟動，請重新上傳" });
      await ddb.updateJob(j.jobId, { status: "failed", finishedAt: iso(), error: { code: "SERVER_RESTARTED", message: "後端重新啟動" } });
    }
    if (stale.length) console.log(`[recover] ${stale.length} 個未完成 job 已標 failed`);
  } catch (e) { console.error("[recover] 失敗", e.message); }
}

/* =========================================================
   Endpoints
   ========================================================= */

/* 收件：上傳與 demo 共用同一條路（entries = [{originalName, buffer}]） */
async function ingest(caseId, entries) {
  const jobId = `job_${randomUUID().slice(0, 12)}`;
  const existing = await ddb.listFiles(caseId);
  const seenSha = new Map(existing.map((f) => [f.sha256, f.fileId]));
  const files = [], duplicates = [], out = [];
  let dupSeq = 0;

  // 先算 sha（純 CPU，快），再平行上傳 S3；重複判定仍依進來的順序，結果可預期
  const hashed = entries.map(({ originalName, buffer }) => ({ originalName, buffer, sha256: createHash("sha256").update(buffer).digest("hex") }));
  const toUpload = [];
  for (const h of hashed) if (!seenSha.has(h.sha256)) { seenSha.set(h.sha256, h.sha256.slice(0, 12)); toUpload.push(h); }
  const rawKeys = new Map();
  const CONCURRENCY = 6;
  for (let i = 0; i < toUpload.length; i += CONCURRENCY) {
    await Promise.all(toUpload.slice(i, i + CONCURRENCY).map(async (h) => {
      rawKeys.set(h.sha256, await s3.putRaw(caseId, h.sha256.slice(0, 12), h.originalName, h.buffer));
    }));
  }
  seenSha.clear();
  for (const f of existing) seenSha.set(f.sha256, f.fileId);

  const records = [];
  for (const { originalName, buffer, sha256 } of hashed) {
    const fileId = sha256.slice(0, 12);
    if (seenSha.has(sha256)) {
      // 重複檔另給 id：fileId 取自 sha256，直接沿用會覆蓋正本那筆紀錄
      const dupId = `${fileId}-d${++dupSeq}`;
      const rec = { fileId: dupId, caseId, originalName, sha256, bytes: buffer.length, status: "duplicate",
        duplicateOf: seenSha.get(sha256), jobId, createdAt: iso(), updatedAt: iso() };
      records.push(rec); duplicates.push(rec);
      out.push({ fileId: dupId, originalName, bytes: buffer.length, status: "duplicate", duplicateOf: rec.duplicateOf });
      continue;
    }
    seenSha.set(sha256, fileId);
    const rawKey = rawKeys.get(sha256) ?? await s3.putRaw(caseId, fileId, originalName, buffer);
    const rec = { fileId, caseId, originalName, sha256, bytes: buffer.length, rawKey, status: "queued", jobId, createdAt: iso(), updatedAt: iso() };
    records.push(rec); files.push(rec);
    out.push({ fileId, originalName, bytes: buffer.length, status: "queued" });
  }
  // DynamoDB 寫入平行化：20 次序列 round trip 會讓 202 慢十幾秒
  for (let i = 0; i < records.length; i += 10) await Promise.all(records.slice(i, i + 10).map((r) => ddb.putFile(r)));

  const job = { jobId, caseId, files, duplicates, seq: 0, dupSeq, finished: false };
  JOBS.set(jobId, job);
  await ddb.putJob({ jobId, caseId, status: "queued", total: entries.length, createdAt: iso() });
  enqueue(job);
  return { jobId, caseId, files: out, eventsUrl: `/api/jobs/${jobId}/events`,
    queue: { ahead: job.queuePos, etaMs: job.queuePos * avgJobMs() } };
}

/* 上傳整批 */
app.post("/api/cases/:caseId/files", upload.array("files"), async (req, res) => {
  const { caseId } = req.params;
  const uploaded = req.files ?? [];
  if (!uploaded.length) return err(res, 400, "VALIDATION", "缺少 files");
  const total = uploaded.reduce((a, f) => a + f.size, 0);
  if (total > MAX_BATCH) return err(res, 413, "PAYLOAD_TOO_LARGE", `整批 ${(total / 1e6).toFixed(0)}MB 超過上限 500MB`);
  try {
    const r = await ingest(caseId, uploaded.map((u) => ({
      originalName: Buffer.from(u.originalname, "latin1").toString("utf8"),   // multer 預設 latin1
      buffer: u.buffer,
    })));
    res.status(202).json(r);
  } catch (e) { return err(res, 500, "S3_WRITE_FAILED", e.message); }
});

/* demo：從 S3 預放的示範卷宗真跑一次（不是查表）。body {pack:"case02", messy:false} */
const DEMO_PACKS = ["case02"];
app.post("/api/cases/:caseId/demo", async (req, res) => {
  const { caseId } = req.params;
  const { pack = "case02", messy = false } = req.body ?? {};
  if (!DEMO_PACKS.includes(pack)) return err(res, 400, "VALIDATION", `未知的示範卷宗：${pack}`);
  try {
    const keys = await s3.listKeys(`demo/${pack}/`, { shared: true });   // demo 不套 dev 前綴
    if (!keys.length) return err(res, 404, "DEMO_NOT_LOADED", `S3 尚無 demo/${pack}/，請先跑 server/scripts/upload-demo.mjs`);
    // 平行抓（原本 20 次序列 GET 讓使用者乾等 30 秒才拿到 202）
    const entries = await Promise.all(keys.map(async (k, i) => {
      const name = k.split("/").pop();
      return { originalName: messy ? messyName(name, i + 1) : name, buffer: await s3.getBytes(k) };
    }));
    const r = await ingest(caseId, entries);
    res.status(202).json({ ...r, pack, messy });
  } catch (e) { return err(res, 500, e.code || "S3_READ_FAILED", e.message); }
});

// 亂檔名 demo：證明判定看內容不看檔名
function messyName(name, n) {
  const ext = (name.match(/\.[a-z0-9]+$/i) || [""])[0].toLowerCase();
  if (/\.(jpe?g|png|heic)$/.test(ext)) return `IMG_${3980 + n}${ext}`;
  if (/\.(mp4|mov)$/.test(ext)) return `DASHCAM_${n}${ext}`;
  return n % 2 ? `scan_${String(n).padStart(4, "0")}${ext}` : `文件(${n})${ext}`;
}

/* SSE */
app.get("/api/jobs/:jobId/events", async (req, res) => {
  const { jobId } = req.params;
  const job = await ddb.getJob(jobId);
  if (!job) return err(res, 404, "JOB_NOT_FOUND", jobId);

  res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
  const after = Number.parseInt(req.headers["last-event-id"] ?? req.query.lastEventId ?? "0", 10) || 0;
  const send = (e) => { if (!e || e.seq == null) return; res.write(`id: ${e.seq}\nevent: ${e.event}\ndata: ${JSON.stringify(e.data ?? {})}\n\n`); };

  let maxSeq = after;
  for (const e of await ddb.listEvents(jobId, after)) { send(e); maxSeq = Math.max(maxSeq, Number(e.seq) || 0); }   // 回放

  if (process.env.DEBUG_SSE) console.log(`[sse] open ${jobId} replay=${maxSeq}`);
  const live = (e) => {
    if (process.env.DEBUG_SSE) console.log(`[sse] live #${e.seq} ${e.event} maxSeq=${maxSeq}`); if (e.seq > maxSeq) { maxSeq = e.seq; send(e); if (e.event === "done" || e.event === "fatal") res.end(); } };
  bus.on(jobId, live);

  const mem = JOBS.get(jobId);
  if ((mem?.finished || job.status === "done" || job.status === "failed") && maxSeq > 0) {
    const last = (await ddb.listEvents(jobId, 0)).at(-1);
    if (last && (last.event === "done" || last.event === "fatal")) res.end();
  }
  const ka = setInterval(() => res.write(": ka\n\n"), 15000);
  req.on("close", () => { clearInterval(ka); bus.off(jobId, live); });
});

/* 輪詢版 */
app.get("/api/jobs/:jobId", async (req, res) => {
  const job = await ddb.getJob(req.params.jobId);
  if (!job) return err(res, 404, "JOB_NOT_FOUND", req.params.jobId);
  const files = await ddb.listFiles(job.caseId);
  res.json({ ...job, files: files.filter((f) => f.jobId === job.jobId || f.status === "duplicate") });
});

/* 案件檔案清單 */
app.get("/api/cases/:caseId/files", async (req, res) => {
  const { caseId } = req.params;
  const all = await ddb.listFiles(caseId);
  if (!all.length) return err(res, 404, "CASE_NOT_FOUND", caseId);
  const files = req.query.includeExcluded === "true" ? all : all.filter((f) => f.status !== "excluded");
  const groups = Object.fromEntries(SOURCES.map((s) => [s, []]));
  const cutoffDate = all.flatMap((f) => (f.segments ?? []).filter((s) => s.doc_type === "裁處書" && s.date).map((s) => s.date)).sort()[0] ?? null;

  for (const f of files) {
    const seg = f.segments?.[0];
    if (seg) (groups[seg.source] ??= []).push(f.fileId);
    if (f.rawKey) {
      const name = seg?.suggestedName || f.originalName;
      f.rawUrl = await s3.presignGet(f.rawKey, { filename: name, inline: true });        // 檢視用（iframe/img）
      f.downloadUrl = await s3.presignGet(f.rawKey, { filename: name });                // 下載用（attachment，檔名＝標準檔名）
      f.pageImageUrls = await Promise.all((f.imageKeys ?? []).map((k) => s3.presignGet(k)));
    }
    if (f.metaKey) f.textUrl = `/api/cases/${encodeURIComponent(caseId)}/files/${f.fileId}/text`;
    // 每個 segment 配一張該段起始頁的圖（卷宗清單縮圖用）
    for (const s of f.segments ?? []) {
      const idx = (f.imagePages ?? []).indexOf(s.fromPage);
      s.pageImageUrl = idx >= 0 ? f.pageImageUrls?.[idx] ?? null : f.pageImageUrls?.[0] ?? null;
    }
  }
  res.json({ caseId, cutoffDate, files, groups });
});

/* 正規化後的逐頁文字：供「擷取文字」檢視與 refs 的 text 型錨點反白 */
app.get("/api/cases/:caseId/files/:fileId/text", async (req, res) => {
  const { caseId, fileId } = req.params;
  const file = await ddb.getFile(caseId, fileId);
  if (!file) return err(res, 404, "FILE_NOT_FOUND", fileId);
  if (!file.metaKey) return err(res, 404, "TEXT_NOT_AVAILABLE", `${file.kind ?? "?"} 沒有可用文字（掃描件請改用 pageImageUrls）`);
  try {
    const meta = await s3.getJson(file.metaKey);
    res.json({ fileId, kind: file.kind, pages: meta.pages ?? null,
      textPerPage: meta.textPerPage ?? (meta.text ? [meta.text] : []), warnings: meta.warnings ?? [] });
  } catch (e) { return err(res, 500, "S3_READ_FAILED", e.message); }
});

/* 人工修正 */
app.patch("/api/cases/:caseId/files/:fileId", async (req, res) => {
  const { caseId, fileId } = req.params;
  const { segIndex = 0, doc_type, source, suggestedName: newName, excluded, by = "承辦人" } = req.body ?? {};
  const file = await ddb.getFile(caseId, fileId);
  if (!file) return err(res, 404, "FILE_NOT_FOUND", fileId);
  if (doc_type && !DOC_TYPES.includes(doc_type)) return err(res, 400, "VALIDATION", `doc_type 不在清單：${doc_type}`);
  if (source && !SOURCES.includes(source)) return err(res, 400, "VALIDATION", `source 不在清單：${source}`);

  const segments = structuredClone(file.segments ?? []);
  const seg = segments[segIndex];
  if (!seg && (doc_type || source || newName)) return err(res, 400, "VALIDATION", `segIndex ${segIndex} 不存在`);

  const audits = [];
  const note = (field, from, to) => { if (from !== to) audits.push({ fileId, segIndex, field, from, to, by, origin: "ai" }); };

  if (seg) {
    if (doc_type) { note("doc_type", seg.doc_type, doc_type); seg.doc_type = doc_type; seg.nature = NATURE[doc_type] ?? "未知"; }
    if (source) { note("source", seg.source, source); seg.source = source; }
    if (doc_type || source) { seg.manual = { ...(seg.manual ?? {}), by, at: iso() }; }
    const recomputed = newName ?? ((doc_type || source) ? suggestedName(seg, trueExt({ originalName: file.originalName, mime: file.mime, kind: file.kind })) : seg.suggestedName);
    note("suggestedName", seg.suggestedName, recomputed);
    seg.suggestedName = recomputed;
  }

  const patch = { segments };
  if (typeof excluded === "boolean") { note("status", file.status, excluded ? "excluded" : "done"); patch.status = excluded ? "excluded" : "done"; }
  const updated = await ddb.updateFile(caseId, fileId, patch);
  for (const a of audits) await ddb.appendAudit(caseId, a);
  res.json(updated);
});

app.get("/api/cases/:caseId/audit", async (req, res) => res.json({ entries: await ddb.listAudit(req.params.caseId) }));

/* 自檢 */
app.get("/api/health", async (_req, res) => {
  const names = [...REQUIRED_TOOLS, ...Object.keys(OPTIONAL_TOOLS)];
  const tools = Object.fromEntries(await Promise.all(names.map(async (t) => [t, await hasTool(t)])));
  const missingRequired = REQUIRED_TOOLS.filter((t) => !tools[t]);
  const degraded = Object.entries(OPTIONAL_TOOLS).filter(([t]) => !tools[t]).map(([t, what]) => `${t} 缺少 → ${what}無法處理`);
  const [bedrockOk, s3Ok, ddbOk] = await Promise.all([
    ping().then(() => true).catch((e) => { console.error("health bedrock", e.code, e.message); return false; }),
    s3.health(), ddb.health(),
  ]);
  const ok = bedrockOk && s3Ok && ddbOk && !missingRequired.length;
  res.status(ok ? 200 : 503).json({
    ok, version: "0.1.0", region: REGION,
    bedrock: { model: MODEL, reachable: bedrockOk, concurrency: +(process.env.BEDROCK_CONCURRENCY || 3), startInterval: +(process.env.BEDROCK_MIN_INTERVAL || 2) },
    s3: { bucket: s3.BUCKET, prefix: process.env.S3_PREFIX || "", ok: s3Ok },
    dynamodb: { table: ddb.TABLE, ok: ddbOk },
    tools, missingRequired, degraded,
  });
});

/* 靜態前端（與 API 同源；最後才掛） */
/* 分析階段（步驟 2–5／異議／法規庫）→ 同機 Python :8100；契約 docs/API-分析階段.md */
mountAnalysisProxy(app);

// 歷史決定書 PDF（相似案例展開用）：deploy/analysis 把 資料集/ 解到與 server/ 同層；只開放 命題方提供/，評測用資料夾不對外
app.use("/dataset", express.static(path.join(path.dirname(new URL(import.meta.url).pathname), "..", "資料集", "命題方提供"), { index: false, dotfiles: "deny" }));
app.use(express.static(process.env.FRONTEND_DIR || path.join(path.dirname(new URL(import.meta.url).pathname), "..", "prototype")));

app.use((e, _req, res, _next) => {
  if (e instanceof multer.MulterError) return err(res, 413, "PAYLOAD_TOO_LARGE", e.message);
  console.error("未捕捉例外", e);
  err(res, 500, "INTERNAL", e.message);
});

recoverStaleJobs();
app.listen(PORT, () => console.log(`listening :${PORT}  region=${REGION} bucket=${s3.BUCKET} table=${ddb.TABLE} prefix=${process.env.S3_PREFIX || "(none)"}`));
