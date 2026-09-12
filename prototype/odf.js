/* =========================================================
   ODF 公文輸出（純前端、零依賴）
   .odt ＝ ZIP：mimetype（第一個、不壓縮）＋ content.xml ＋ styles.xml ＋ META-INF/manifest.xml
   政府公文交換用 ODF；LibreOffice／Word 都能開。
   ========================================================= */
"use strict";

const ODF = (() => {
  const enc = new TextEncoder();
  const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = (u8) => { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  const dosTime = (d) => ({ time: (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1), date: ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate() });

  /** entries: [{name, data: Uint8Array}] → Uint8Array（全部 store，ODF 規定 mimetype 必須不壓縮且排第一） */
  function zip(entries) {
    const parts = [], central = []; let offset = 0; const now = dosTime(new Date());
    const u16 = (v) => [v & 255, (v >> 8) & 255], u32 = (v) => [v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >>> 24) & 255];
    for (const e of entries) {
      const name = enc.encode(e.name), crc = crc32(e.data), n = e.data.length;
      const local = new Uint8Array([...u32(0x04034b50), ...u16(20), ...u16(0x0800), ...u16(0), ...u16(now.time), ...u16(now.date), ...u32(crc), ...u32(n), ...u32(n), ...u16(name.length), ...u16(0), ...name]);
      parts.push(local, e.data);
      central.push(new Uint8Array([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0x0800), ...u16(0), ...u16(now.time), ...u16(now.date), ...u32(crc), ...u32(n), ...u32(n), ...u16(name.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(offset), ...name]));
      offset += local.length + n;
    }
    const cdStart = offset, cd = central.reduce((a, b) => a + b.length, 0);
    const end = new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(entries.length), ...u16(entries.length), ...u32(cd), ...u32(cdStart), ...u16(0)]);
    const all = [...parts, ...central, end], out = new Uint8Array(all.reduce((a, b) => a + b.length, 0)); let p = 0;
    for (const a of all) { out.set(a, p); p += a.length; }
    return out;
  }

  const x = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  /** paras: [{kind:"h4"|"p"|"meta", text}]；head 標題；sub 副標；meta {caseNo, verdict, date} */
  function makeOdt({ head = "新北市政府訴願決定書", sub = "", paras = [], meta = {} }) {
    const body = [
      `<text:p text:style-name="Title">${x(head)}</text:p>`,
      sub ? `<text:p text:style-name="Sub">${x(sub)}</text:p>` : "",
      ...paras.map((p) => {
        const t = String(p.text || "").replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "");
        if (p.kind === "h4") return `<text:h text:style-name="H" text:outline-level="1">${x(t)}</text:h>`;
        return t.split("\n").map((line) => `<text:p text:style-name="Body">${x(line)}</text:p>`).join("");
      }),
      `<text:p text:style-name="Foot">本文件由訴願智審臺依 AI 草稿輸出（${x(meta.exportedAt || "")}），供承辦人審核；一切法律見解與事實認定以訴願審議委員會決議為準。</text:p>`,
    ].join("");
    const content = `<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2">
<office:font-face-decls><style:font-face style:name="標楷體" svg:font-family="標楷體, BiauKaiTC, 'PMingLiU'" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"/></office:font-face-decls>
<office:automatic-styles>
<style:style style:name="Title" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:margin-bottom="0.4cm"/><style:text-properties style:font-name="標楷體" fo:font-size="20pt" fo:letter-spacing="0.3cm" fo:font-weight="bold"/></style:style>
<style:style style:name="Sub" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:margin-bottom="0.6cm"/><style:text-properties style:font-name="標楷體" fo:font-size="12pt" fo:color="#555555"/></style:style>
<style:style style:name="H" style:family="paragraph"><style:paragraph-properties fo:text-align="center" fo:margin-top="0.5cm" fo:margin-bottom="0.25cm"/><style:text-properties style:font-name="標楷體" fo:font-size="16pt" fo:letter-spacing="0.5cm" fo:font-weight="bold"/></style:style>
<style:style style:name="Body" style:family="paragraph"><style:paragraph-properties fo:text-indent="1.2cm" fo:line-height="180%" fo:margin-bottom="0.2cm" fo:text-align="justify"/><style:text-properties style:font-name="標楷體" fo:font-size="14pt"/></style:style>
<style:style style:name="Foot" style:family="paragraph"><style:paragraph-properties fo:margin-top="1cm"/><style:text-properties style:font-name="標楷體" fo:font-size="10pt" fo:color="#777777"/></style:style>
</office:automatic-styles>
<office:body><office:text>${body}</office:text></office:body></office:document-content>`;
    const styles = `<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2">
<office:automatic-styles><style:page-layout style:name="pm1"><style:page-layout-properties fo:page-width="21cm" fo:page-height="29.7cm" fo:margin-top="2.5cm" fo:margin-bottom="2.5cm" fo:margin-left="2.5cm" fo:margin-right="2.5cm"/></style:page-layout></office:automatic-styles>
<office:master-styles><style:master-page style:name="Standard" style:page-layout-name="pm1"/></office:master-styles></office:document-styles>`;
    const manifest = `<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
<manifest:file-entry manifest:full-path="/" manifest:version="1.2" manifest:media-type="application/vnd.oasis.opendocument.text"/>
<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
<manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>`;
    const meta_ = `<?xml version="1.0" encoding="UTF-8"?><office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" xmlns:dc="http://purl.org/dc/elements/1.1/" office:version="1.2"><office:meta><dc:title>${x(head)} ${x(meta.caseNo || "")}</dc:title><meta:generator>訴願智審臺</meta:generator></office:meta></office:document-meta>`;
    const bytes = zip([
      { name: "mimetype", data: enc.encode("application/vnd.oasis.opendocument.text") },
      { name: "content.xml", data: enc.encode(content) },
      { name: "styles.xml", data: enc.encode(styles) },
      { name: "meta.xml", data: enc.encode(meta_) },
      { name: "META-INF/manifest.xml", data: enc.encode(manifest) },
    ]);
    return new Blob([bytes], { type: "application/vnd.oasis.opendocument.text" });
  }

  function download(blob, filename) {
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  }

  return { makeOdt, download, zip, crc32 };
})();

if (typeof window !== "undefined") window.ODF = ODF;
if (typeof module !== "undefined") module.exports = ODF;
