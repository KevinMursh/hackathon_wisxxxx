"""法規庫（v6 畫面的後端資料，零 LLM）：
- laws：資料集 12 部法規（名稱、修正日期、條數、來源）＋ 涉案數（101 決定書中引用次數）
- letters / rulings：KB 語料 metadata（名稱、主題、發文日、來源）
- version_check(law, dates)：三時點比對——修正日落在行為時之後 → 須依行政罰法 §5 比較
用法：python -m pipeline.lawlib  → runs/lawlib.json"""
import json, re
from pathlib import Path

from . import casedb, lawdb
from .common import RUNS

CORPUS = Path(__file__).resolve().parents[1] / "inputs/kb_corpus"
_ROC = re.compile(r"民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def roc(s: str | None) -> str | None:
    m = s and _ROC.search(s)
    return f"{int(m.group(1))}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def _letter_meta(title: str) -> dict:
    """從檔名抓發文機關、日期、主題：『法務部93年4月13日法律字第0930014628號函-寄存送達』"""
    m = re.match(r"(.+?)(\d{2,3})年(\d{1,2})月(\d{1,2})日(.+?)-(.+)$", title)
    if m:
        return {"n": f"{m.group(1)} {m.group(2)}.{m.group(3)}.{m.group(4)} {m.group(5)}", "topic": m.group(6),
                "date": f"{m.group(2)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"}
    m = re.match(r"(.+?)-(.+)$", title)
    return {"n": m.group(1) if m else title, "topic": m.group(2) if m else "", "date": "—"}


def build() -> dict:
    db = lawdb.load()
    # 涉案數：101 份決定書文字中引用該法的件數
    counts = {k: 0 for k in db}
    for c in casedb.load():
        t = casedb.text_of(c, 30000)
        for k in db:
            if k in t:
                counts[k] += 1
    sync = json.loads((RUNS / "lawsync.json").read_text(encoding="utf-8")) if (RUNS / "lawsync.json").exists() else None
    official = {r["n"]: r for r in (sync or {}).get("results", []) if r.get("officialDate")}
    laws = []
    for k, v in db.items():
        if k.endswith("（現行）"):
            continue  # 現行版併入資料集那一列的 official 欄
        o = official.get(k)
        laws.append({"n": k, "kind": "規則" if k.endswith("規則") or k.endswith("準則") else "法律", "date": roc(v["amended"]) or v["amended"],
                     "src": v.get("source", "命題方提供"), "arts": len(v["articles"]), "cases": counts[k],
                     "official": o["officialDate"] if o else None, "effective": (o or {}).get("effective"),
                     "status": (o or {}).get("status"), "currentArts": len(db.get(f"{k}（現行）", {}).get("articles", {})) or None})
    p = CORPUS / "laws/政府資訊公開法.txt"
    if p.exists():
        laws.append({"n": "政府資訊公開法", "kind": "法律", "date": roc(p.read_text(encoding="utf-8")[:300]) or "94-12-28", "src": "自行蒐集", "arts": 24, "cases": 0, "official": None, "effective": None, "status": None, "currentArts": None})
    lib = {"laws": laws, "letters": [], "rulings": [],
           "sync": {"checkedAt": sync["checkedAt"], "source": sync["source"], **sync["summary"]} if sync else None}
    for kind in ("letters", "rulings"):
        for mp in sorted((CORPUS / kind).glob("*.metadata.json")):
            meta = json.loads(mp.read_text(encoding="utf-8"))["metadataAttributes"]
            src = "自行蒐集" if any(x in meta["title"] for x in ("法務部114年2月11日", "環保署及環境部", "臺北市政府")) else "命題方提供"
            lib[kind].append({**_letter_meta(meta["title"]), "law": meta.get("law"), "src": src, "title": meta["title"]})
    return lib


def version_check(lib: dict, law_name: str, dates: dict) -> dict | None:
    """dates = {act, disp, decide}（民國 YYY-MM-DD）。回 {warn, amended, text}。"""
    L = next((x for x in lib["laws"] if x["n"] == law_name or law_name.startswith(x["n"])), None)
    if not L or not dates.get("act") or not L["date"]:
        return None
    if L["date"] > dates["act"]:
        return {"warn": True, "amended": L["date"], "text": f"修正 {L['date']} 落在行為時 {dates['act']} 之後 → 須依行政罰法 §5 為新舊法比較"}
    return {"warn": False, "amended": L["date"], "text": f"最新修正 {L['date']}，早於行為時 {dates['act']} → 三時點版本一致"}


if __name__ == "__main__":
    lib = build()
    RUNS.mkdir(exist_ok=True)
    (RUNS / "lawlib.json").write_text(json.dumps(lib, ensure_ascii=False, indent=2), encoding="utf-8")
    for l in lib["laws"]:
        print(f"  {l['date']:<10} {l['arts']:>5} 條  涉案 {l['cases']:>3}  {l['n']}")
    print(len(lib["letters"]), "函釋；", len(lib["rulings"]), "判解")
    for x in lib["letters"][:3]:
        print("  ", x["date"], x["n"], "｜", x["topic"])
