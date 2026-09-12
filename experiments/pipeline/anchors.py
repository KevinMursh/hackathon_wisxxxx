"""quote → 文件內位置（頁、起迄）。模型只負責逐字引句，頁碼由程式定位；找不到就退成「開啟該檔」。"""
import re
from .ingest import Doc

_WS = re.compile(r"[\s　]+")


def _norm(s: str) -> tuple[str, list[int]]:
    """去空白後的字串 + 每個字元對應原始 index。"""
    out, idx = [], []
    for i, ch in enumerate(s):
        if not _WS.match(ch):
            out.append(ch); idx.append(i)
    return "".join(out), idx


def locate(doc: Doc, quote: str) -> dict | None:
    q, _ = _norm(quote)
    if len(q) < 4 or not doc.textPerPage:
        return None
    for pno, page in enumerate(doc.textPerPage, start=doc.fromPage):
        p, idx = _norm(page)
        j = p.find(q)
        if j < 0 and len(q) > 12:  # 退一步：取中段 12 字
            mid = q[len(q) // 2 - 6: len(q) // 2 + 6]
            j = p.find(mid)
            if j >= 0:
                j = max(0, j - (len(q) // 2 - 6))
        if j >= 0:
            end = min(j + len(q), len(idx)) - 1
            return {"page": pno, "start": idx[j], "end": idx[end] + 1}
    return None


class RefTable:
    """收集錨點：ref id → [fileId, type, payload]，型別對齊前端 refs（text / doc / time）。"""
    def __init__(self, docs: list[Doc], prefix: str = "q"):
        self.by_name = {d.name: d for d in docs}
        self.refs, self._n, self.unverified, self.prefix = {}, 0, [], prefix

    def add(self, q: dict | None) -> str | None:
        if not q or not q.get("file"):
            return None
        d = self.by_name.get(q["file"]) or next((x for x in self.by_name.values() if q["file"] in x.name or x.name in q["file"]), None)
        if not d:
            self.unverified.append(q); return None
        self._n += 1
        rid = f"{self.prefix}{self._n}"
        m = re.search(r"(\d{1,3})\s*秒", q.get("quote", "")) if d.doc_type == "採證影片" else None
        pos = locate(d, q.get("quote", ""))
        if pos:
            self.refs[rid] = [d.fileId, "text", pos]
        elif m:
            self.refs[rid] = [d.fileId, "time", int(m.group(1))]
        else:
            self.refs[rid] = [d.fileId, "doc", None]
            if d.text.strip() and q.get("quote"):  # 有引句卻找不到才算未定位；純〔檔名〕標記不算
                self.unverified.append(q)
        return rid
