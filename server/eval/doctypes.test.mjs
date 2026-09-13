/* doc_type 清單同步驗證：零 LLM。node eval/doctypes.test.mjs
 *
 * doc_type 的值散落在 7 個地方各一份副本，任何一份漏改就會出事：
 * 前端下拉多出後端沒有的值 → server.mjs 的 DOC_TYPES.includes() 擋下來 → 400 VALIDATION。
 * 這個測試把 7 份副本抓出來互比，讓 drift 在 CI 就爆掉而不是在 demo 現場。
 */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DOC_TYPES, ORDER, NATURE } from "../classify.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (p) => fs.readFile(path.resolve(here, p), "utf8");
const readJson = async (p) => JSON.parse(await read(p));

/** 從 JS 原始碼取出某個字串陣列常數的內容 */
function arrayLiteral(src, name) {
  const m = src.match(new RegExp(`${name}\\s*=\\s*\\[([^\\]]*)\\]`));
  if (!m) throw new Error(`找不到 ${name}`);
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

const schema = await readJson("../schemas/classify.schema.json");
const enums = await readJson("../schemas/enums.json");
const promptMd = await read("../prompts/classify.md");
const appJs = await read("../../prototype/app.js");

/* prompt 的封閉清單是「、」分隔的一行純文字 */
const promptLine = promptMd.split("\n").find((l) => l.includes("訴願書、") && l.includes("其他"));
if (!promptLine) throw new Error("classify.md 找不到 doc_type 封閉清單那一行");

/** schema 裡 doc_type 的 enum（巢狀結構，直接遞迴找） */
function findDocTypeEnum(node) {
  if (!node || typeof node !== "object") return null;
  if (node.properties?.doc_type?.enum) return node.properties.doc_type.enum;
  for (const v of Object.values(node)) { const r = findDocTypeEnum(v); if (r) return r; }
  return null;
}

const sources = [
  ["classify.mjs DOC_TYPES", DOC_TYPES],
  ["classify.mjs ORDER", ORDER],
  ["classify.mjs NATURE keys", Object.keys(NATURE)],
  ["classify.schema.json enum", findDocTypeEnum(schema)],
  ["enums.json doc_type", enums.doc_type],
  ["prompts/classify.md 封閉清單", promptLine.split("、").map((s) => s.trim()).filter(Boolean)],
  ["prototype/app.js TYPES", arrayLiteral(appJs, "TYPES")],
];

const ref = new Set(DOC_TYPES);
let fail = 0;

for (const [label, list] of sources) {
  const errs = [];
  if (!list) { console.log(`✗ ${label}: 抓不到清單`); fail++; continue; }
  const got = new Set(list);
  const missing = [...ref].filter((t) => !got.has(t));
  const extra = [...got].filter((t) => !ref.has(t));
  if (missing.length) errs.push(`缺少：${missing.join("、")}`);
  if (extra.length) errs.push(`多出：${extra.join("、")}`);
  if (list.length !== new Set(list).size) errs.push("有重複值");

  if (errs.length) { fail++; console.log(`✗ ${label} (${list.length} 項)\n    ${errs.join("\n    ")}`); }
  else console.log(`✓ ${label} (${list.length} 項)`);
}

/* ORDER 決定 suggestedName 的序號前綴，eval 的正解寫死了這些數字（例如 27-其他）。
   新類別一律往「其他」後面加，才不會讓既有序號位移。 */
if (ORDER.indexOf("其他") !== 26) {
  console.log(`✗ ORDER: 「其他」序號應維持 27（index 26），目前 index ${ORDER.indexOf("其他")}——新類別請加在「其他」之後`);
  fail++;
} else console.log("✓ ORDER 既有序號未位移（其他 = 27）");

console.log(`\n${sources.length + 1 - fail} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
