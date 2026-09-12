/* 正規化驗證：零 LLM。node eval/normalize.test.mjs [--keep] [filter] */
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { normalize } from "../normalize.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const spec = JSON.parse(await fs.readFile(path.join(here, "normalize.expected.json"), "utf8"));
const args = process.argv.slice(2);
const keep = args.includes("--keep");
const filter = args.find((a) => !a.startsWith("--"));
const outDir = await fs.mkdtemp(path.join(os.tmpdir(), "norm-test-"));

const resolve = (p) => path.resolve(here, p.replace("$pack", spec._pack).replace("$samples", spec._samples));
const SCAN_TEXT_MIN = 50;
let pass = 0, fail = 0;
const failures = [];

for (const c of spec.cases) {
  if (filter && !c.path.includes(filter)) continue;
  const file = resolve(c.path);
  const name = path.basename(c.path);
  const t0 = Date.now();
  let r;
  try { r = await normalize(await fs.readFile(file), name, { outDir }); }
  catch (e) { r = { ok: false, error: { code: "THREW", message: e.message } }; }
  const ms = Date.now() - t0;
  const errs = [];
  const eq = (label, got, want) => { if (got !== want) errs.push(`${label}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`); };
  const inRange = (label, got, want) => {
    if (Array.isArray(want)) { if (!(got >= want[0] && got <= want[1])) errs.push(`${label}: got ${got}, want ${want[0]}–${want[1]}`); }
    else eq(label, got, want);
  };

  if (c.ok === false) {
    eq("ok", r.ok, false);
    if (r.ok === false) eq("error.code", r.error.code, c.error);
  } else {
    eq("ok", r.ok, true);
    if (r.ok) {
      eq("kind", r.kind, c.kind);
      if (c.pages !== undefined) inRange("pages", r.pages, c.pages);
      if (c.images !== undefined) eq("images", r.images.length, c.images);
      if (c.duration !== undefined) inRange("duration", r.duration, c.duration);
      if (c.mustContain) for (const s of c.mustContain) if (!r.text.includes(s)) errs.push(`mustContain "${s}" missing`);
      if (c.textMax !== undefined && r.text.replace(/\s/g, "").length > c.textMax) errs.push(`text length ${r.text.length} > ${c.textMax}`);
      if (r.kind === "pdf-scan" && r.text.replace(/\s/g, "").length >= SCAN_TEXT_MIN * r.pages) errs.push("pdf-scan but text is substantial");
      if (c.warningsMatch && !r.warnings.some((w) => w.includes(c.warningsMatch))) errs.push(`no warning matching "${c.warningsMatch}" in ${JSON.stringify(r.warnings)}`);
      if (c.children !== undefined) {
        eq("children", r.children?.length, c.children);
        if (c.childKinds) {
          const kinds = (r.children ?? []).map((x) => x.kind).sort();
          eq("childKinds", JSON.stringify(kinds), JSON.stringify([...c.childKinds].sort()));
        }
      }
      // 產出圖檔真的存在
      for (const img of r.images ?? []) await fs.access(img).catch(() => errs.push(`image missing: ${img}`));
    } else errs.push(`error: ${r.error.code} ${r.error.message}`);
  }

  if (errs.length) { fail++; failures.push({ name, errs }); console.log(`✗ ${name} (${ms}ms)\n    ${errs.join("\n    ")}`); }
  else { pass++; console.log(`✓ ${name} (${ms}ms) ${r.ok ? `${r.kind}${r.pages ? ` p${r.pages}` : ""}${r.duration ? ` ${r.duration}s` : ""} img${r.images?.length ?? 0}${r.warnings?.length ? " ⚠" + r.warnings.length : ""}` : r.error.code}`); }
}

console.log(`\n${pass} passed, ${fail} failed${keep ? `\noutput kept at ${outDir}` : ""}`);
if (!keep) await fs.rm(outDir, { recursive: true, force: true });
process.exit(fail ? 1 : 0);
