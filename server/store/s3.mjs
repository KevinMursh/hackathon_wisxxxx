/* S3：原檔、正規化產物、presigned 下載 */
import fs from "node:fs/promises";
import path from "node:path";
import { S3Client, PutObjectCommand, GetObjectCommand, HeadBucketCommand, ListObjectsV2Command } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const REGION = process.env.AWS_REGION || "us-west-2";
export const BUCKET = process.env.S3_BUCKET;
const PREFIX = (process.env.S3_PREFIX || "").replace(/^\/+|\/+$/g, "");
const PRESIGN_TTL = 15 * 60;
if (!BUCKET) { console.error("S3_BUCKET 未設定"); process.exit(1); }

const s3 = new S3Client({ region: REGION });
const key = (...parts) => [PREFIX, ...parts].filter(Boolean).join("/");

const MIME = { pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", mp4: "video/mp4", mov: "video/quicktime", json: "application/json", txt: "text/plain; charset=utf-8" };
const mimeOf = (name) => MIME[path.extname(name).slice(1).toLowerCase()] || "application/octet-stream";

export async function putRaw(caseId, fileId, originalName, body) {
  const ext = path.extname(originalName).slice(1).toLowerCase();
  const k = key("cases", caseId, "raw", ext ? `${fileId}.${ext}` : fileId);
  await s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: k, Body: body, ContentType: mimeOf(originalName), Metadata: { originalname: encodeURIComponent(originalName) } }));
  return k;
}

/** 正規化產物：meta.json + 頁圖／幀 */
export async function putNormalized(caseId, fileId, norm) {
  const base = key("cases", caseId, "normalized", fileId);
  const images = [];
  for (const p of norm.images ?? []) {
    const k = `${base}/${path.basename(p)}`;
    await s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: k, Body: await fs.readFile(p), ContentType: "image/jpeg" }));
    images.push(k);
  }
  const meta = { ...norm, images, dir: undefined, children: undefined };
  await s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: `${base}/meta.json`, Body: JSON.stringify(meta), ContentType: "application/json" }));
  return { metaKey: `${base}/meta.json`, imageKeys: images };
}

export async function presignGet(k, { filename } = {}) {
  const cmd = new GetObjectCommand({ Bucket: BUCKET, Key: k, ...(filename ? { ResponseContentDisposition: `attachment; filename*=UTF-8''${encodeURIComponent(filename)}` } : {}) });
  return getSignedUrl(s3, cmd, { expiresIn: PRESIGN_TTL });
}

export async function getJson(k) {
  const r = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: k }));
  return JSON.parse(await r.Body.transformToString());
}

/** 列出前綴下的所有 key（排序後回傳）。
    shared=true 時不套 S3_PREFIX：示範卷宗是 dev 與正式共用的內容，不該被開發前綴切開。 */
export async function listKeys(prefix, { shared = false } = {}) {
  const out = [];
  let token;
  do {
    const r = await s3.send(new ListObjectsV2Command({ Bucket: BUCKET, Prefix: shared ? prefix : key(prefix), ContinuationToken: token }));
    for (const o of r.Contents ?? []) if (!o.Key.endsWith("/")) out.push(o.Key);
    token = r.IsTruncated ? r.NextContinuationToken : undefined;
  } while (token);
  return out.sort();
}

export async function getBytes(k) {
  const r = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: k }));
  return Buffer.from(await r.Body.transformToByteArray());
}

export async function health() {
  try { await s3.send(new HeadBucketCommand({ Bucket: BUCKET })); return true; } catch { return false; }
}
