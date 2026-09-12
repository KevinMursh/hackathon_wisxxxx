/* =========================================================
   文件歸戶 API — 契約見 docs/API-文件歸戶.md
   沒有 fallback：失敗回錯誤碼，不回假資料。
   ========================================================= */
import express from "express";
import multer from "multer";
import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { EventEmitter } from "node:events";
import { normalize, flatten, hasTool, REQUIRED_TOOLS, OPTIONAL_TOOLS } from "./normalize.mjs";
import { classifyAll, DOC_TYPES, SOURCES, NATURE, suggestedName, trueExt, annotateTiming, MODEL } from "./classify.mjs";
import { ping, REGION } from "./bedrock.mjs";
import * as s3 from "./store/s3.mjs";
import * as ddb from "./store/ddb.mjs";

const PORT = +(process.env.PORT || 8080);
const MAX_FILE = 100 * 1024 * 1024;
const MAX_BATCH = 500 * 1024 * 1024;

const app = express();
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

function enqueue(job) { queue.push(job); if (!working) drain(); }
async function drain() {
  working = true;
  while (queue.length) {
    const job = queue.shift();
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
  const counters = { ok: 0, error: 0, duplicate: job.duplicates.length };
  try {
    /* ① 正規化（逐檔推事件） */
    const normalized = [];
    for (const f of job.files) {
      const buf = await s3Body(f.rawKey);
      const r = await normalize(buf, f.originalName, { outDir, fileId: f.fileId });
      const isZip = r.ok && r.kind === "zip";
      const items = isZip ? flatten([r]) : [r];
      if (isZip) {
        // 壓縮檔本身沒有內容可分類：標成容器，子檔各自建紀錄（否則 updateFile 會產生沒有 originalName 的孤兒）
        await ddb.updateFile(caseId, r.fileId, { status: "container", kind: "zip", childIds: items.map((c) => c.fileId), warnings: r.warnings ?? [] });
        await emit(job, "container", { fileId: r.fileId, childIds: items.map((c) => c.fileId) });
        for (const c of items) {
          const rawKey = c.srcPath ? await s3.putRaw(caseId, c.fileId, c.originalName, await fs.readFile(c.srcPath)) : undefined;
          await ddb.putFile({ fileId: c.fileId, caseId, originalName: c.originalName, sha256: c.sha256, bytes: c.bytes,
            rawKey, status: "queued", jobId, parentFileId: r.fileId, createdAt: iso(), updatedAt: iso() });
        }
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
    const results = await classifyAll(normalized, {
      onBox: (done, total) => emit(job, "box", { done, total }).catch(() => {}),
    });
    annotateTiming(results);

    const byId = new Map(normalized.map((n) => [n.fileId, n]));
    for (const r of results) {
      const n = byId.get(r.fileId);
      if (r.ok) {
        counters.ok++;
        const patch = {
          status: "done", kind: n?.kind, pages: n?.pages, duration: n?.duration,
          mime: n?.mime, warnings: n?.warnings ?? [],
          imagePages: n?.imagePages ?? null, imageKeys: n?._keys?.imageKeys ?? [], metaKey: n?._keys?.metaKey,
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
  }
}

async function s3Body(key) {
  const { GetObjectCommand } = await import("@aws-sdk/client-s3");
  const { S3Client } = await import("@aws-sdk/client-s3");
  const c = new S3Client({ region: REGION });
  const r = await c.send(new GetObjectCommand({ Bucket: s3.BUCKET, Key: key }));
  return Buffer.from(await r.Body.transformToByteArray());
}

const JOBS = new Map();   // jobId → job（含 seq / finished），SSE live 推用

/* =========================================================
   Endpoints
   ========================================================= */

/* 上傳整批 */
app.post("/api/cases/:caseId/files", upload.array("files"), async (req, res) => {
  const { caseId } = req.params;
  const uploaded = req.files ?? [];
  if (!uploaded.length) return err(res, 400, "VALIDATION", "缺少 files");
  const total = uploaded.reduce((a, f) => a + f.size, 0);
  if (total > MAX_BATCH) return err(res, 413, "PAYLOAD_TOO_LARGE", `整批 ${(total / 1e6).toFixed(0)}MB 超過上限 500MB`);

  const jobId = `job_${randomUUID().slice(0, 12)}`;
  const existing = await ddb.listFiles(caseId);
  const seenSha = new Map(existing.map((f) => [f.sha256, f.fileId]));
  const files = [], duplicates = [], out = [];
  let dupSeq = 0;

  try {
    for (const u of uploaded) {
      const originalName = Buffer.from(u.originalname, "latin1").toString("utf8");   // multer 預設 latin1
      const { createHash } = await import("node:crypto");
      const sha256 = createHash("sha256").update(u.buffer).digest("hex");
      const fileId = sha256.slice(0, 12);
      if (seenSha.has(sha256)) {
        // 重複檔另給 id：fileId 取自 sha256，直接沿用會覆蓋正本那筆紀錄
        const dupId = `${fileId}-d${++dupSeq}`;
        const rec = { fileId: dupId, caseId, originalName, sha256, bytes: u.size, status: "duplicate", duplicateOf: seenSha.get(sha256), createdAt: iso(), updatedAt: iso() };
        await ddb.putFile(rec);
        duplicates.push(rec); out.push({ fileId: dupId, originalName, bytes: u.size, status: "duplicate", duplicateOf: rec.duplicateOf });
        continue;
      }
      seenSha.set(sha256, fileId);
      const rawKey = await s3.putRaw(caseId, fileId, originalName, u.buffer);
      const rec = { fileId, caseId, originalName, sha256, bytes: u.size, rawKey, status: "queued", jobId, createdAt: iso(), updatedAt: iso() };
      await ddb.putFile(rec);
      files.push(rec); out.push({ fileId, originalName, bytes: u.size, status: "queued" });
    }
  } catch (e) {
    return err(res, 500, "S3_WRITE_FAILED", e.message);
  }

  const job = { jobId, caseId, files, duplicates, seq: 0, finished: false };
  JOBS.set(jobId, job);
  await ddb.putJob({ jobId, caseId, status: "queued", total: uploaded.length, createdAt: iso() });
  enqueue(job);
  res.status(202).json({ jobId, caseId, files: out, eventsUrl: `/api/jobs/${jobId}/events` });
});

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
      f.rawUrl = await s3.presignGet(f.rawKey, { filename: seg?.suggestedName || f.originalName });
      f.pageImageUrls = await Promise.all((f.imageKeys ?? []).map((k) => s3.presignGet(k)));
    }
  }
  res.json({ caseId, cutoffDate, files, groups });
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
app.use(express.static(process.env.FRONTEND_DIR || path.join(path.dirname(new URL(import.meta.url).pathname), "..", "prototype")));

app.use((e, _req, res, _next) => {
  if (e instanceof multer.MulterError) return err(res, 413, "PAYLOAD_TOO_LARGE", e.message);
  console.error("未捕捉例外", e);
  err(res, 500, "INTERNAL", e.message);
});

app.listen(PORT, () => console.log(`listening :${PORT}  region=${REGION} bucket=${s3.BUCKET} table=${ddb.TABLE} prefix=${process.env.S3_PREFIX || "(none)"}`));
