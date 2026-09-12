"""輸入層：把隊友歸戶 API 的 File[]/Segment[] 轉成 pipeline 用的 Doc 列表。
兩種來源：(1) 隊友 server 的 GET /cases/{id}/files JSON + S3 normalized/{fileId}/meta.json
        (2) 本機 inputs/{case}/files.json（同格式，text/images 指本機路徑；他 server 未上線前用）
規則：
- 顯示名用 suggestedName（人工修正後），錨點用 fileId；模型 quote 回 name，程式映回 fileId
- excluded / duplicate / source=本局 不進分析
- 合併卷宗多 segment → 各自一份 Doc，用 fromPage/toPage 從 textPerPage 切
- doc_type 決定進哪一步（STEP_DOCS）；source 決定三方對照落哪欄（COLUMN）"""
import json
from dataclasses import dataclass, field
from pathlib import Path

INPUTS = Path(__file__).resolve().parents[1] / "inputs"

# 隊友 classify.mjs 的 nature 查表（主張／紀錄／證物）
NATURE = {
    "訴願書": "主張", "訴願委任書": "主張", "答辯書": "主張", "答辯書檢送函": "紀錄", "陳述意見書": "主張",
    "卷證目錄": "紀錄", "裁處書": "紀錄", "裁處書送達證書": "紀錄", "陳述意見通知書": "紀錄", "通知書送達證書": "紀錄",
    "稽查紀錄": "紀錄", "調查筆錄": "紀錄", "簽呈": "紀錄", "係數計算表": "紀錄", "車籍資料": "紀錄", "委員會決定書": "紀錄",
    "檢舉資料": "證物", "採證照片": "證物", "影像放大標註": "證物", "採證影片": "證物", "檢驗報告": "證物", "契約書": "證物",
}
STEP_DOCS = {
    "s2": {"訴願書", "訴願委任書", "裁處書", "裁處書送達證書", "答辯書", "答辯書檢送函", "陳述意見通知書", "通知書送達證書"},
    "s3": None,  # 全部（主張＋紀錄＋證物）
}
COLUMN = {"訴願人": "a", "原處分機關": "d", "第三方": "e", "未知": "e"}


@dataclass
class Doc:
    fileId: str
    name: str            # suggestedName（顯示與 prompt 用）
    originalName: str
    doc_type: str
    source: str
    nature: str
    timing: str
    kind: str            # pdf-text / pdf-scan / image / video / text
    text: str = ""
    textPerPage: list = field(default_factory=list)
    images: list = field(default_factory=list)   # Path 或 bytes
    fromPage: int = 1
    toPage: int | None = None
    summary: str = ""
    segId: str = ""

    @property
    def column(self):
        return COLUMN.get(self.source)


def _read_text(entry: dict, base: Path) -> tuple[str, list]:
    """本機格式：entry 可帶 textPath / textPerPage；S3 格式由 loader 先填好 text/textPerPage。"""
    if "text" in entry:
        return entry["text"], entry.get("textPerPage") or [entry["text"]]
    if entry.get("textPath"):
        t = (base / entry["textPath"]).read_text(encoding="utf-8")
        return t, [t]
    return "", []


def from_files(files: list[dict], base: Path | None = None) -> list[Doc]:
    docs = []
    for f in files:
        if f.get("status") in ("duplicate", "error", "excluded") or f.get("excluded"):
            continue
        text, tpp = _read_text(f, base or Path("."))
        images = [(base / p) if base and not str(p).startswith("http") else p for p in f.get("images", [])]
        for i, seg in enumerate(f.get("segments") or [{}]):
            m = seg.get("manual") or {}
            doc_type = m.get("doc_type") or seg.get("doc_type", "其他")
            source = m.get("source") or seg.get("source", "未知")
            if source == "本局":
                continue
            a, b = seg.get("fromPage", 1), seg.get("toPage") or len(tpp) or 1
            seg_text = "\n\n".join(tpp[a - 1:b]) if tpp and len(f.get("segments") or []) > 1 else text
            docs.append(Doc(fileId=f["fileId"], name=m.get("suggestedName") or seg.get("suggestedName") or f["originalName"],
                            originalName=f["originalName"], doc_type=doc_type, source=source,
                            nature=NATURE.get(doc_type, "未知"), timing=seg.get("timing", "未知"), kind=f.get("kind", "text"),
                            text=seg_text, textPerPage=tpp[a - 1:b] if tpp else [], images=images,
                            fromPage=a, toPage=b, summary=seg.get("summary", ""), segId=seg.get("segId", f"{f['fileId']}#{i}")))
    # 同類型同日期會撞名（隊友模板已知問題）→ 加 -1/-2 保證 prompt 中檔名唯一
    seen = {}
    for d in docs:
        if d.name in seen:
            seen[d.name] += 1
            stem, _, ext = d.name.rpartition(".")
            d.name = f"{stem}-{seen[d.name]}.{ext}" if ext else f"{d.name}-{seen[d.name]}"
        else:
            seen[d.name] = 0
    return docs


def load_local(case: str) -> list[Doc]:
    base = INPUTS / case
    return from_files(json.loads((base / "files.json").read_text(encoding="utf-8"))["files"], base)


def load_remote(case_id: str, api_base: str) -> list[Doc]:
    """接隊友 server：GET files → 每檔拿 normalized meta.json（presigned 或 S3）。"""
    import urllib.request
    data = json.loads(urllib.request.urlopen(f"{api_base}/api/cases/{case_id}/files").read())
    files = []
    for f in data["files"]:
        meta = json.loads(urllib.request.urlopen(f["normalizedUrl"]).read()) if f.get("normalizedUrl") else {}
        files.append({**f, "text": meta.get("text", ""), "textPerPage": meta.get("textPerPage", []), "images": f.get("pageImageUrls", [])})
    return from_files(files)


def for_step(docs: list[Doc], step: str) -> list[Doc]:
    allow = STEP_DOCS.get(step)
    return [d for d in docs if allow is None or d.doc_type in allow]


def by_name(docs: list[Doc]) -> dict[str, Doc]:
    return {d.name: d for d in docs}


def prompt_block(docs: list[Doc], max_chars: int = 8000) -> str:
    parts = []
    for d in docs:
        head = f"=== FILE {d.name} | {d.doc_type} | 來源：{d.source} | {d.timing} ==="
        body = d.text[:max_chars] if d.text.strip() else f"（{d.kind}，無文字層，見附圖）"
        parts.append(head + "\n" + body)
    return "\n\n".join(parts)
