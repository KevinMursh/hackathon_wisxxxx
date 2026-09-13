/* 把示範卷宗上傳到 S3 的 demo/{pack}/，供 POST /api/cases/{id}/demo 使用。
   跑一次即可（換卷宗內容才需重跑）。

   AWS_PROFILE=hackathon AWS_REGION=us-west-2 S3_BUCKET=… node scripts/upload-demo.mjs [pack]
*/
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";

const here = path.dirname(fileURLToPath(import.meta.url));
const REGION = process.env.AWS_REGION || "us-west-2";
const BUCKET = process.env.S3_BUCKET;
const PREFIX = (process.env.S3_PREFIX || "").replace(/^\/+|\/+$/g, "");
if (!BUCKET) { console.error("S3_BUCKET 未設定"); process.exit(1); }

const onlyDocs = (rel) => /^(01-訴願書|02-答辯書|03-卷證)\//.test(rel) && !/\/_build\//.test(rel) && !/\.DS_Store$/.test(rel);
const PACKS = {
  // 只收真正的卷宗檔；排除產製腳本、README 與合併檔（合併檔另行測試用，不進 demo）
  case02: { root: path.resolve(here, "../../資料集/評測用（勿用於RAG）/case02-廢清法79I駁回/卷宗包"), include: onlyDocs },
  case01: { root: path.resolve(here, "../../資料集/評測用（勿用於RAG）/case01-建築法77②逾期/卷宗包"), include: onlyDocs },
  case03: { root: path.resolve(here, "../../資料集/評測用（勿用於RAG）/case03-建築法81I撤銷/卷宗包"), include: onlyDocs },
};

const MIME = { pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", mp4: "video/mp4" };

async function walk(dir) {
  const out = [];
  for (const e of await fs.readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...(await walk(p)));
    else out.push(p);
  }
  return out;
}

const pack = process.argv[2] || "case02";
const spec = PACKS[pack];
if (!spec) { console.error(`未知的 pack：${pack}（可用：${Object.keys(PACKS).join(", ")}）`); process.exit(1); }

const s3 = new S3Client({ region: REGION });
const files = (await walk(spec.root))
  .map((abs) => ({ abs, rel: path.relative(spec.root, abs) }))
  .filter(({ rel }) => spec.include(rel) && !/\.DS_Store$/.test(rel))
  .sort((a, b) => a.rel.localeCompare(b.rel));

console.log(`pack=${pack} 共 ${files.length} 檔 → s3://${BUCKET}/${[PREFIX, `demo/${pack}/`].filter(Boolean).join("/")}`);
let n = 0;
for (const { abs, rel } of files) {
  const name = path.basename(abs);
  // 攤平成單層，並用序號保住卷證順序（ingest 依 key 排序讀取）
  const flat = `${String(++n).padStart(2, "0")}_${name}`;
  const key = [PREFIX, "demo", pack, flat].filter(Boolean).join("/");
  const body = await fs.readFile(abs);
  await s3.send(new PutObjectCommand({
    Bucket: BUCKET, Key: key, Body: body,
    ContentType: MIME[path.extname(name).slice(1).toLowerCase()] || "application/octet-stream",
  }));
  console.log(`  ✓ ${rel}  →  ${flat}  (${(body.length / 1024).toFixed(0)} KB)`);
}
console.log(`完成：${n} 檔`);
