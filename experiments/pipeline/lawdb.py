"""法規字典（零 LLM）：把 資料集/命題方提供/相關法規/*.pdf 解析成 {法規名: {條號: 條文}}，
提供 (1) 條號存在性查核 (2) 從任意文字抓出「○○法第○條」引用並逐一查核。"""
import json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAW_DIR = ROOT / "資料集/命題方提供/相關法規"
CACHE = Path(__file__).resolve().parents[1] / "inputs/laws.json"

_ART = re.compile(r"^\s*第\s*(\d+(?:-\d+)?)\s*條(?:之(\d+))?\s*(?:\d\s+)?(.*)$")  # 條號可與首行條文同列
CITE = re.compile(r"([一-龥]{2,20}?(?:法|條例|規則|準則|辦法))第\s*(\d+)\s*條(?:之\s*(\d+))?(?:第\s*(\d+)\s*項)?(?:第\s*(\d+)\s*款)?")


def _parse(pdf: Path) -> tuple[str, str, dict]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    name = re.search(r"法規名稱：\s*(\S+)", txt)
    amended = re.search(r"修正日期：\s*(\S.*?)\s*$", txt, re.M)
    arts, cur, buf = {}, None, []
    for line in txt.splitlines():
        m = _ART.match(line)
        if m:
            if cur:
                arts[cur] = "\n".join(buf).strip()
            cur = m.group(1) + (f"之{m.group(2)}" if m.group(2) else "")
            buf = [m.group(3).strip()] if m.group(3).strip() else []
        elif cur:
            buf.append(re.sub(r"^\s*\d?\s{0,3}", "", line).rstrip())
    if cur:
        arts[cur] = "\n".join(buf).strip()
    return (name.group(1) if name else pdf.stem), (amended.group(1) if amended else ""), arts


CURRENT_DIR = CACHE.parent / "kb_corpus/laws"
_CUR = re.compile(r"^第\s*(\S+?)\s*條\s*$")


def _parse_current(p: Path) -> tuple[str, str, dict]:
    """kb/sync_laws.py 產出的現行版：『法規名稱：…／修正日期：民國 YYY-MM-DD／第 N 條\n條文』"""
    txt = p.read_text(encoding="utf-8")
    name = re.search(r"法規名稱：\s*(\S+)", txt).group(1)
    amended = re.search(r"修正日期：民國\s*(\S+?)（", txt)
    arts, cur, buf = {}, None, []
    for line in txt.splitlines():
        m = _CUR.match(line)
        if m:
            if cur:
                arts[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur:
            buf.append(line)
    if cur:
        arts[cur] = "\n".join(buf).strip()
    return name, (amended.group(1) if amended else ""), arts


def load() -> dict:
    """資料集版本為主（行為時法）；同步下來的現行版以「{法規}（現行）」另存，資料集沒有的子法直接以本名加入。"""
    if CACHE.exists():
        db = json.loads(CACHE.read_text(encoding="utf-8"))
    else:
        db = {}
        for pdf in sorted(LAW_DIR.glob("*.pdf")):
            name, amended, arts = _parse(pdf)
            db[name] = {"amended": amended, "articles": arts, "source": "命題方提供"}
        CACHE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    for p in sorted(CURRENT_DIR.glob("*（現行 *）.txt")) if CURRENT_DIR.exists() else []:
        name, amended, arts = _parse_current(p)
        key = name if name not in db else f"{name}（現行）"
        y, mo, d = (amended.split("-") + ["", ""])[:3]
        db[key] = {"amended": f"民國 {y} 年 {mo} 月 {d} 日", "articles": arts, "source": "全國法規資料庫同步"}
    return db


def lookup(db: dict, law: str, art: str) -> dict:
    """回 {status, text}；status: ok / no_article / unknown_law"""
    hit = next((k for k in db if k == law or law.endswith(k) or (k.endswith(law) and "（現行）" not in k)), None)
    if not hit:
        return {"status": "unknown_law", "text": ""}
    t = db[hit]["articles"].get(art)
    return {"status": "ok" if t else "no_article", "law": hit, "text": t or "", "amended": db[hit]["amended"]}


_LEAD = "依按據照參違反適用及與暨和同之本前揭該上開查次另又並亦或及所稱定規定"
CITE_ANY = re.compile(r"([一-龥]{2,20}?(?:法|條例|規則|準則|辦法))?第\s*(\d+)\s*條(?:之\s*(\d+))?(?:第\s*(\d+)\s*項)?(?:第\s*(\d+)\s*款)?")


_SAME = {"同法", "本法", "法", "該法", "上開法", "前揭法"}
_SHORT = ("準則", "規則", "辦法", "條例")


def _clean_law(db: dict, law: str) -> tuple[str, str]:
    """回 (法規名, 類型)。類型：known / sublaw（含母法名但非母法，如裁罰準則）/ unknown。"""
    for k in sorted(db, key=len, reverse=True):
        if law.endswith(k):
            return k, "known"
    for k in sorted(db, key=len, reverse=True):
        i = law.find(k)
        if i >= 0:  # 子法：名稱通常為「違反○○法…準則」，「違反」屬名稱一部分
            start = i - 2 if law[max(0, i - 2):i] == "違反" else i
            return law[start:], "sublaw"
    return law.lstrip(_LEAD), "unknown"


def check_citations(db: dict, text: str, source: str = "") -> list[dict]:
    """抓出「○○法第○條（第○項第○款）」逐一查核。
    status：ok / no_article / not_in_dataset（真實子法，資料集未收）/ unknown_law。
    「同法」「及第○條」沿用前一法規；「裁罰準則」等簡稱接回前面出現過的全名。"""
    out, seen, last_law, last_end, fulls = [], set(), None, -99, {}
    for m in CITE_ANY.finditer(text):
        law, art, sub, para, item = m.groups()
        kind = "known"
        if law:
            raw = law
            if raw.endswith(("同法", "本法", "該法")):
                law = last_law
            else:
                law, kind = _clean_law(db, raw)
                if kind == "unknown":  # 簡稱（如「裁罰準則」）→ 接回前面出現過的全名或字典鍵
                    for full in list(fulls) + [k for k in db if "（現行）" not in k]:
                        L = next((n for n in range(len(raw), 3, -1) if full.endswith(raw[-n:])), 0)
                        if L:
                            law, kind = full, "sublaw"
                            break
                elif kind == "sublaw":
                    fulls[law] = True
        elif last_law and m.start() - last_end <= 4:
            law = last_law
        if not law:
            continue
        last_law, last_end = law, m.end()
        art_key = art + (f"之{sub}" if sub else "")
        key = (law, art_key, para, item)
        if key in seen:
            continue
        seen.add(key)
        r = lookup(db, law, art_key)
        status = r["status"]
        if status == "unknown_law" and (kind == "sublaw" or law in fulls):
            status = "not_in_dataset"
        cite = f"{law}第{art_key}條" + (f"第{para}項" if para else "") + (f"第{item}款" if item else "")
        out.append({"cite": cite, "law": law, "article": art_key, "status": status,
                    "source": source, "snippet": r["text"][:120]})
    return out


if __name__ == "__main__":
    db = load()
    for k, v in db.items():
        print(f"{len(v['articles']):>4} 條  {k}（{v['amended']}）")
