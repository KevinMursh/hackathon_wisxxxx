/* =========================================================
   ① 正規化：任意上傳檔 → LLM 可用的統一中間格式
   純工具，零 LLM。失敗回 {ok:false,error}，不拋、不假成功。
   ========================================================= */
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { fileTypeFromBuffer } from "file-type";
import sharp from "sharp";
import mammoth from "mammoth";

const run = promisify(execFile);
const SCAN_TEXT_MIN = 50;        // 每頁去空白後少於此字數 → 視為掃描
const IMG_MAX_EDGE = 1600;
const JPEG_Q = 85;
const VIDEO_FRAMES = 3;
const MAX_SCAN_PAGES = 200;      // 超過即拒絕（防止把整卷上百頁掃描件丟進來）

export const KINDS = ["pdf-text", "pdf-scan", "image", "video", "office", "text", "unsupported"];

const OFFICE_EXT = new Set(["doc", "docx", "odt", "rtf", "xls", "xlsx", "ods", "ppt", "pptx", "odp"]);
// file-type 對 OOXML 回這些 mime；一律交給 LibreOffice 轉 PDF
const OFFICE_MIME = new Set([
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.oasis.opendocument.text", "application/vnd.oasis.opendocument.spreadsheet", "application/vnd.oasis.opendocument.presentation",
  "application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint", "application/rtf",
]);
const TEXT_EXT = new Set(["txt", "md", "csv"]);
const IMAGE_MIME = new Set(["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "image/gif", "image/tiff", "image/bmp"]);
const VIDEO_MIME = new Set(["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/x-matroska"]);

/* 外部工具可用性：缺工具不讓整台服務掛掉，改為該格式回 unsupported（附原因） */
const toolCache = new Map();
export async function hasTool(bin) {
  if (!toolCache.has(bin)) toolCache.set(bin, run("which", [bin]).then(() => true).catch(() => false));
  return toolCache.get(bin);
}
export const REQUIRED_TOOLS = ["pdftotext", "pdftoppm", "pdfinfo", "file"];
export const OPTIONAL_TOOLS = { soffice: "Office 檔（doc/docx/odt/xls/xlsx/ppt/pptx）", ffmpeg: "影片", ffprobe: "影片", qpdf: "PDF 拆檔", unzip: "zip 解壓" };

class NormalizeError extends Error {
  constructor(code, message, cause) { super(message); this.code = code; this.cause = cause; }
}

/** 主入口：buffer + 原檔名 → 中間格式（含產出檔寫入 outDir） */
export async function normalize(buffer, originalName, { outDir, fileId } = {}) {
  const sha256 = createHash("sha256").update(buffer).digest("hex");
  fileId ??= sha256.slice(0, 12);
  outDir ??= await fs.mkdtemp(path.join(os.tmpdir(), "norm-"));
  const dir = path.join(outDir, fileId);
  await fs.mkdir(dir, { recursive: true });

  const base = { fileId, originalName, sha256, bytes: buffer.length, mime: null, kind: "unsupported",
    pages: null, duration: null, text: "", textPerPage: [], images: [], exif: {}, warnings: [], dir };
  try {
    const ext = path.extname(originalName).replace(".", "").toLowerCase();
    const ft = await fileTypeFromBuffer(buffer);        // magic bytes 優先於副檔名
    const mime = ft?.mime ?? (TEXT_EXT.has(ext) ? "text/plain" : null);
    base.mime = mime;
    if (ft && ext && ft.ext !== ext && !(ft.ext === "jpg" && ext === "jpeg"))
      base.warnings.push(`extension "${ext}" does not match content "${ft.ext}"`);

    if (mime === "application/pdf") return ok(await fromPdf(buffer, base, dir));
    if (mime && IMAGE_MIME.has(mime)) return ok(await fromImage(buffer, base, dir));
    if (mime && VIDEO_MIME.has(mime)) {
      if (!(await hasTool("ffprobe")) || !(await hasTool("ffmpeg"))) { base.warnings.push("ffmpeg/ffprobe 未安裝，影片未解析"); return ok(base); }
      return ok(await fromVideo(buffer, base, dir, ext || ft.ext));
    }
    if (isOffice(ft, ext)) {
      if (!(await hasTool("soffice"))) { base.warnings.push("LibreOffice 未安裝，Office 檔未解析"); return ok(base); }
      return ok(await fromOffice(buffer, base, dir, ft?.ext ?? ext));
    }
    if (mime === "application/zip" || ft?.ext === "zip") {
      if (!(await hasTool("unzip"))) { base.warnings.push("unzip 未安裝，壓縮檔未解開"); return ok(base); }
      return ok(await fromZip(buffer, base, dir));
    }
    if (mime === "text/plain" || (!ft && TEXT_EXT.has(ext)) || (!ft && looksLikeText(buffer))) return ok(fromText(buffer, base));
    base.warnings.push(`unsupported: mime=${mime ?? "?"} ext=${ext || "?"}`);
    return ok(base);                                     // unsupported 不是錯，是「不呼叫模型」
  } catch (e) {
    const code = e instanceof NormalizeError ? e.code : "NORMALIZE_FAILED";
    return { ok: false, fileId, originalName, sha256, bytes: buffer.length, error: { code, message: e.message } };
  }
}

const ok = (r) => ({ ok: true, ...r });

/* ---------- PDF ---------- */
async function fromPdf(buffer, base, dir) {
  const pdfPath = path.join(dir, "source.pdf");
  await fs.writeFile(pdfPath, buffer);
  const info = await pdfinfo(pdfPath);
  base.pages = info.pages;
  if (!base.pages) throw new NormalizeError("NORMALIZE_FAILED", "pdfinfo reports 0 pages");

  base.textPerPage = [];
  for (let p = 1; p <= base.pages; p++) {
    const { stdout } = await run("pdftotext", ["-layout", "-f", String(p), "-l", String(p), pdfPath, "-"]);
    base.textPerPage.push(stdout.replace(/\f/g, "").trimEnd());
  }
  base.text = base.textPerPage.join("\n\n");
  const noText = base.textPerPage.map((t, i) => (t.replace(/\s/g, "").length < SCAN_TEXT_MIN ? i + 1 : 0)).filter(Boolean);
  base.kind = noText.length > base.pages / 2 ? "pdf-scan" : "pdf-text";
  if (base.kind === "pdf-scan" && base.pages > MAX_SCAN_PAGES)
    throw new NormalizeError("TOO_MANY_PAGES", `scanned PDF has ${base.pages} pages (> ${MAX_SCAN_PAGES})`);
  if (base.kind === "pdf-text" && noText.length) base.warnings.push(`${noText.length} page(s) have no text layer`);

  // pdf-text 也要把「沒文字層的頁」出圖，否則混合卷宗裡的掃描頁模型看不到
  base.scanPages = base.kind === "pdf-text" ? noText : range(1, base.pages);
  const wanted = base.kind === "pdf-scan" ? range(1, base.pages) : uniq([1, ...noText, base.pages]).sort((a, b) => a - b);
  base.imagePages = wanted;
  for (const p of wanted) base.images.push(await pdfPage(pdfPath, p, dir));
  return base;
}

// -scale-to 讓長邊固定 1600px（不管頁面實際尺寸）；JPEG 而非 PNG：掃描/照片內容 PNG 編碼慢 50 倍以上
export async function pdfPage(pdfPath, page, dir) {
  const prefix = path.join(dir, `p${page}`);
  await run("pdftoppm", ["-scale-to", String(IMG_MAX_EDGE), "-jpeg", "-jpegopt", `quality=${JPEG_Q}`, "-f", String(page), "-l", String(page), "-singlefile", pdfPath, prefix]);
  return `${prefix}.jpg`;
}

async function pdfinfo(pdfPath) {
  const { stdout } = await run("pdfinfo", [pdfPath]);
  const m = /^Pages:\s+(\d+)/m.exec(stdout);
  return { pages: m ? +m[1] : 0 };
}

/* ---------- 圖片 ---------- */
async function fromImage(buffer, base, dir) {
  base.kind = "image";
  base.pages = 1;
  // 預建 sharp 無 HEVC 解碼器：HEIC 一律先用系統工具轉 JPEG（mac: sips；linux: heif-convert）
  if (base.mime === "image/heic" || base.mime === "image/heif") buffer = await heicToJpeg(buffer, dir);
  const img = sharp(buffer, { failOn: "none" });
  const meta = await img.metadata();
  if (meta.exif) base.exif = parseExif(meta.exif);
  const out = path.join(dir, "p1.jpg");
  await img.rotate().resize({ width: IMG_MAX_EDGE, height: IMG_MAX_EDGE, fit: "inside", withoutEnlargement: true }).jpeg({ quality: JPEG_Q }).toFile(out);
  base.images = [out];
  return base;
}

async function heicToJpeg(buffer, dir) {
  const src = path.join(dir, "source.heic"), dst = path.join(dir, "source.jpg");
  await fs.writeFile(src, buffer);
  if (process.platform === "darwin") await run("sips", ["-s", "format", "jpeg", src, "--out", dst]);
  else await run("heif-convert", [src, dst]);
  return fs.readFile(dst);
}

// 只抓 DateTimeOriginal，避免引入 exif 套件
function parseExif(buf) {
  const s = buf.toString("latin1");
  const m = /(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/.exec(s);
  return m ? { takenAt: `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}` } : {};
}

/* ---------- 影片 ---------- */
async function fromVideo(buffer, base, dir, ext) {
  base.kind = "video";
  const src = path.join(dir, `source.${ext || "mp4"}`);
  await fs.writeFile(src, buffer);
  const { stdout } = await run("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", src]);
  const d = parseFloat(stdout);
  if (!Number.isFinite(d) || d <= 0) throw new NormalizeError("NORMALIZE_FAILED", "ffprobe: no duration");
  base.duration = Math.round(d * 100) / 100;
  const ts = VIDEO_FRAMES === 1 ? [0] : Array.from({ length: VIDEO_FRAMES }, (_, i) => Math.min(d - 0.5, (d * i) / (VIDEO_FRAMES - 1)));
  for (const [i, t] of ts.entries()) {
    const out = path.join(dir, `f${i + 1}.jpg`);
    await run("ffmpeg", ["-v", "error", "-y", "-ss", String(Math.max(0, t)), "-i", src, "-frames:v", "1", "-vf", `scale='min(${IMG_MAX_EDGE},iw)':-2`, "-q:v", "3", out]);
    base.images.push(out);
  }
  base.frameTimes = ts.map((t) => Math.round(Math.max(0, t) * 100) / 100);
  return base;
}

/* ---------- Office ---------- */
function isOffice(ft, ext) {
  if (ft?.mime && OFFICE_MIME.has(ft.mime)) return true;
  if (ft?.ext && OFFICE_EXT.has(ft.ext)) return true;
  if (ft?.mime === "application/x-cfb" && OFFICE_EXT.has(ext)) return true;      // 舊版 doc/xls/ppt 是 CFB 容器
  if (ft?.mime === "application/zip" && OFFICE_EXT.has(ext)) return true;        // OOXML 有時只認得出 zip
  return !ft && OFFICE_EXT.has(ext);
}

async function fromOffice(buffer, base, dir, ext) {
  base.kind = "office";
  const src = path.join(dir, `source.${ext}`);
  await fs.writeFile(src, buffer);
  if (ext === "docx") {   // 純文字走 mammoth 較快；試算表／簡報只走 soffice
    try { base.text = (await mammoth.extractRawText({ buffer })).value.trim(); }
    catch (e) { base.warnings.push(`mammoth failed: ${e.message}`); }
  }
  const pdfPath = await sofficeToPdf(src, dir);
  const info = await pdfinfo(pdfPath);
  base.pages = info.pages;
  const per = [];
  for (let p = 1; p <= base.pages; p++) {
    const { stdout } = await run("pdftotext", ["-layout", "-f", String(p), "-l", String(p), pdfPath, "-"]);
    per.push(stdout.replace(/\f/g, "").trimEnd());
  }
  base.textPerPage = per;
  if (!base.text) base.text = per.join("\n\n");
  for (const p of uniq([1, base.pages])) base.images.push(await pdfPage(pdfPath, p, dir));
  base.convertedPdf = pdfPath;
  return base;
}

async function sofficeToPdf(src, dir) {
  const profile = path.join(dir, "lo-profile");     // 獨立 profile，避免同時多個 soffice 互鎖
  await run("soffice", ["--headless", `-env:UserInstallation=file://${profile}`, "--convert-to", "pdf", "--outdir", dir, src], { timeout: 120000 });
  const out = path.join(dir, path.basename(src, path.extname(src)) + ".pdf");
  await fs.access(out).catch(() => { throw new NormalizeError("NORMALIZE_FAILED", "soffice produced no PDF"); });
  return out;
}

/* ---------- 純文字 ---------- */
function fromText(buffer, base) {
  base.kind = "text";
  base.text = buffer.toString("utf8").replace(/^﻿/, "");
  base.textPerPage = [base.text];
  base.pages = 1;
  return base;
}

function looksLikeText(buffer) {
  const s = buffer.subarray(0, 4096);
  let bad = 0;
  for (const b of s) if (b === 0 || (b < 32 && b !== 9 && b !== 10 && b !== 13)) bad++;
  return bad === 0 && s.length > 0;
}

/* ---------- zip：展開後遞迴，回 children ---------- */
async function fromZip(buffer, base, dir) {
  base.kind = "zip";
  const src = path.join(dir, "source.zip"), out = path.join(dir, "unzipped");
  await fs.writeFile(src, buffer);
  await fs.mkdir(out, { recursive: true });
  await run("unzip", ["-qq", "-o", src, "-d", out]);
  const files = await walk(out);
  base.children = [];
  for (const f of files) {
    if (/(^|\/)(__MACOSX|\.DS_Store)/.test(f)) continue;
    const rel = path.relative(out, f);
    const child = await normalize(await fs.readFile(f), `${base.originalName}/${rel}`, { outDir: dir });
    base.children.push(child);
  }
  return base;
}

async function walk(d) {
  const out = [];
  for (const e of await fs.readdir(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) out.push(...(await walk(p))); else out.push(p);
  }
  return out;
}

/* ---------- utils ---------- */
const range = (a, b) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
const uniq = (xs) => [...new Set(xs)];

/** 展平：zip 的 children 拉平成一維，方便裝箱 */
export function flatten(results) {
  const out = [];
  for (const r of results) {
    if (r.ok && r.kind === "zip") out.push(...flatten(r.children));
    else out.push(r);
  }
  return out;
}
