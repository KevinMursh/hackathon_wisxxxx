/* 分類驗證：node eval/run.mjs [--group tune|final|all] [--per-file] [--box N] [--model ID] [--filter 字串] [--out file.json]
   需要 AWS 憑證（AWS_PROFILE=hackathon AWS_REGION=us-east-1）。 */
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { normalize } from "../normalize.mjs";

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const group = opt("--group", "tune");
const perFile = args.includes("--per-file");
const filter = opt("--filter", null);
const outFile = opt("--out", null);
if (opt("--box")) process.env.BOX_FILES = opt("--box");
if (opt("--model")) process.env.MODEL = opt("--model");
const { classifyAll, MODEL, BOX } = await import("../classify.mjs");

const here = path.dirname(fileURLToPath(import.meta.url));
const spec = JSON.parse(await fs.readFile(path.join(here, "manifest.json"), "utf8"));
const resolve = (p) => path.resolve(here, p.replace("$pack", spec._pack).replace("$samples", spec._samples).replace("$own", spec._own).replace("$dec", spec._dec));
const cases = spec.cases.filter((c) => (group === "all" || c.group === group) && (!filter || c.path.includes(filter)));
const outDir = await fs.mkdtemp(path.join(os.tmpdir(), "cls-"));

console.log(`model=${MODEL} mode=${perFile ? "per-file" : `batch(files≤${BOX.files})`} group=${group} n=${cases.length}\n`);

/* ① 正規化 */
const t0 = Date.now();
const normalized = [];
for (const c of cases) {
  const r = await normalize(await fs.readFile(resolve(c.path)), path.basename(c.path), { outDir });
  r._case = c;
  normalized.push(r);
}
console.log(`normalized ${normalized.length} in ${Date.now() - t0}ms`);

/* ② 分類 */
const t1 = Date.now();
let results;
try {
  results = await classifyAll(normalized, { perFile, onBox: (i, n) => console.log(`  box ${i + 1}/${n} done`) });
} catch (e) { console.error(`FATAL ${e.code}: ${e.message}`); process.exit(2); }
const totalMs = Date.now() - t1;
const byId = new Map(results.map((r) => [r.fileId, r]));

/* ③ 評分 */
const asArr = (x) => (Array.isArray(x) ? x : [x]);
const m = { n: 0, type: 0, source: 0, srcWrongIdentity: 0, noIdentityOk: 0, noIdentityN: 0, negOk: 0, negN: 0, segOk: 0, segN: 0, dateOk: 0, dateN: 0, docNoOk: 0, docNoN: 0, errors: 0, unverified: 0, nameOk: 0, nameN: 0 };
const confusion = {};
const rows = [];
let tokens = { in: 0, out: 0 };
for (const n of normalized) {
  const c = n._case, r = byId.get(n.fileId), name = path.basename(c.path);
  m.n++;
  if (!r?.ok) { m.errors++; rows.push(`✗ ${name}: ERROR ${r?.error?.code} ${r?.error?.message}`); continue; }
  tokens.in += r.usage?.inputTokens ?? 0; tokens.out += r.usage?.outputTokens ?? 0;
  const segs = r.segments, primary = segs[0];
  const types = segs.map((s) => s.doc_type);
  const typeOk = asArr(c.doc_type).some((t) => types.includes(t));
  const srcOk = asArr(c.source).includes(primary.source);
  if (typeOk) m.type++;
  if (srcOk) m.source++;
  if (!srcOk && primary.source !== "未知") m.srcWrongIdentity++;
  if (c.noIdentity) { m.noIdentityN++; if (primary.source === "未知") m.noIdentityOk++; }
  if (c.negative) { m.negN++; if (types.every((t) => t === "其他")) m.negOk++; }
  if (c.segmentsMin) { m.segN++; const have = c.segmentTypes ? c.segmentTypes.every((t) => types.includes(t)) : true; if (segs.length >= c.segmentsMin && have) m.segOk++; }
  if (c.date) { m.dateN++; if (segs.some((s) => s.date === c.date)) m.dateOk++; }
  if (c.doc_noContains) { m.docNoN++; if (segs.some((s) => (s.doc_no || "").includes(c.doc_noContains))) m.docNoOk++; }
  if (c.suggestedNameMatch) { m.nameN++; const re = new RegExp(c.suggestedNameMatch); if (re.test(primary.suggestedName)) m.nameOk++; else rows.push(`   ↳ name: got ${primary.suggestedName}, want /${c.suggestedNameMatch}/`); }
  if (segs.some((s) => s.evidence_unverified)) m.unverified++;
  const key = `${asArr(c.doc_type)[0]} → ${primary.doc_type}`;
  if (!typeOk) confusion[key] = (confusion[key] || 0) + 1;
  const flag = typeOk && srcOk ? "✓" : "✗";
  const detail = segs.length > 1 ? `${segs.length} segs: ${segs.map((s) => `${s.doc_type}@p${s.fromPage}-${s.toPage}`).join(", ")}` : `${primary.doc_type} / ${primary.source} / ${primary.date ?? "-"} / conf ${primary.confidence}${primary.evidence_unverified ? " ⚠unverified" : ""}`;
  rows.push(`${flag} ${name}  → ${primary.suggestedName}\n     ${detail}\n     ${primary.summary} ｜ ${primary.evidence}${!typeOk ? `\n     want type ${JSON.stringify(c.doc_type)}` : ""}${!srcOk ? `\n     want source ${JSON.stringify(c.source)}` : ""}`);
}
console.log(rows.join("\n"));
const pct = (a, b) => (b ? `${((100 * a) / b).toFixed(0)}% (${a}/${b})` : "n/a");
console.log(`
==== ${group} | ${perFile ? "per-file" : "batch"} | ${MODEL} ====
doc_type 準確率      ${pct(m.type, m.n - m.errors)}   目標 ≥90%
source 準確率        ${pct(m.source, m.n - m.errors)}   目標 ≥85%   （猜錯身分而非回未知：${m.srcWrongIdentity}）
無身分證據→未知      ${pct(m.noIdentityOk, m.noIdentityN)}   目標 100%
負樣本→其他          ${pct(m.negOk, m.negN)}   目標 100%
合併卷宗分段         ${pct(m.segOk, m.segN)}
date 命中            ${pct(m.dateOk, m.dateN)}
doc_no 命中          ${pct(m.docNoOk, m.docNoN)}\nsuggestedName 命中   ${pct(m.nameOk, m.nameN)}
evidence 回查失敗    ${m.unverified}
錯誤/未回            ${m.errors}
耗時 ${(totalMs / 1000).toFixed(1)}s   tokens in=${tokens.in} out=${tokens.out}`);
if (Object.keys(confusion).length) console.log("混淆：", confusion);
if (outFile) await fs.writeFile(outFile, JSON.stringify({ model: MODEL, perFile, group, metrics: m, totalMs, results }, null, 2));
await fs.rm(outDir, { recursive: true, force: true });
