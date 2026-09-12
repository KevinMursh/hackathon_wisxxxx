"""歷史決定書索引（零 LLM）：解析 101 份檔名 → {year, event, clause, result}，
相似案例先用「同事件類型 → 同款次 → 年度近」規則排序；評測案對應的 3 份決定書永遠排除。"""
import json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEC_DIR = ROOT / "資料集/命題方提供/歷史訴願決定書"
TEXT_CACHE = Path(__file__).resolve().parents[1] / "inputs/decisions_text"

# 評測用（勿用於RAG）/README.md 三案清單：這三份是 case01–03 的標準答案，不得進 few-shot／相似案例
EVAL_EXCLUDE = {
    "04.111年-違反建築法事件-77(2)-訴願逾期-不受理",
    "17.114年-違反廢棄物清理法事件-79I-訴願無理由-駁回",
    "19.114年-違反建築法事件-81I-訴願有理由-原處分撤銷",
}
_NORM = str.maketrans({"汙": "污"})


def _parse(pdf: Path) -> dict | None:
    stem = pdf.name.replace(".pdf 的副本.pdf", "").replace(".pdf", "")
    parts = stem.split("-")
    if len(parts) < 4:
        return None
    seq_year, event, clause = parts[0], parts[1], parts[2]
    m = re.match(r"(\d+)\.(\d+)年", seq_year)
    return {"id": stem, "path": str(pdf), "year": int(m.group(2)) if m else 0,
            "event": event.translate(_NORM), "clause": clause,
            "result": parts[-1], "desc": "-".join(parts[3:-1]),
            "excluded": stem in EVAL_EXCLUDE}


def load() -> list[dict]:
    return [c for p in sorted(DEC_DIR.rglob("*.pdf")) if (c := _parse(p))]


def text_of(c: dict, max_chars: int = 12000) -> str:
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    f = TEXT_CACHE / (c["id"] + ".txt")
    if not f.exists():
        t = subprocess.run(["pdftotext", "-layout", c["path"], "-"], capture_output=True, text=True).stdout
        f.write_text(t, encoding="utf-8")
    return f.read_text(encoding="utf-8")[:max_chars]


def similar(law_name: str, clause_hint: str | None = None, k: int = 5, year: int | None = None) -> list[dict]:
    """law_name 例「廢棄物清理法」；clause_hint 例「79I」「77(2)」。"""
    key = law_name.translate(_NORM).replace("法", "")
    pool = [c for c in load() if not c["excluded"] and key in c["event"]]
    def score(c):
        s = 0
        if clause_hint and c["clause"].startswith(clause_hint):
            s += 100
        elif clause_hint and c["clause"][:2] == clause_hint[:2]:
            s += 30
        elif not clause_hint and c["clause"][:2] in ("79", "81"):
            s += 100  # 程序無礙 → 實體審查案優先
        s += c["year"]  # 越新越前
        return -s
    return sorted(pool, key=score)[:k]


if __name__ == "__main__":
    cs = load()
    print(len(cs), "份；排除", sum(c["excluded"] for c in cs), "份")
    for c in similar("廢棄物清理法", "79I"):
        print(" ", c["year"], c["clause"], c["result"], c["id"])
