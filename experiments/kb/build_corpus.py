"""把資料集整理成 KB 語料上傳 S3：每檔一個 .txt ＋ .txt.metadata.json（Bedrock KB 格式）。
四個 prefix：laws / rulings / letters / decisions。評測三案對應決定書永遠排除。
用法：python -m kb.build_corpus [--dry]"""
import json, re, subprocess, sys
from pathlib import Path

import boto3

from pipeline.casedb import EVAL_EXCLUDE, load as load_cases, _NORM
from pipeline.common import REGION

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "資料集"
BUCKET = "ntpc-law3-deploy-229004791954"
PREFIX = "kb/"
OUT = Path(__file__).resolve().parents[1] / "inputs/kb_corpus"


def pdf_text(p: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout


def clean_name(p: Path) -> str:
    return p.name.replace(".pdf 的副本.pdf", "").replace(".pdf", "").replace(".md", "")


def law_domain(title: str) -> str:
    for k in ("廢棄物清理法", "洗錢防制法", "空氣污染防制法", "噪音管制法", "建築法", "政府資訊公開法", "行政罰法", "訴願法", "行政程序法", "道路交通"):
        if k in title.translate(_NORM):
            return k
    return "其他"


def emit(items: list, kind: str, name: str, text: str, meta: dict):
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 50:
        print("  skip (empty):", name, file=sys.stderr)
        return
    meta = {k: v for k, v in meta.items() if v not in ("", None)}  # KB 不接受空字串
    items.append((f"{kind}/{name}.txt", text, {"metadataAttributes": {"kind": kind, **meta}}))


def build() -> list:
    items = []
    # laws：整部法一檔（KB 自己切 chunk），另加自行蒐集的政資法
    for p in sorted((DS / "命題方提供/相關法規").glob("*.pdf")):
        t = pdf_text(p); name = clean_name(p)
        emit(items, "laws", name, t, {"law": name, "title": name})
    p = DS / "自行蒐集/相關法規補充/政府資訊公開法.md"
    if p.exists():
        emit(items, "laws", "政府資訊公開法", p.read_text(encoding="utf-8"), {"law": "政府資訊公開法", "title": "政府資訊公開法"})
    # rulings
    for p in sorted((DS / "命題方提供/司法院釋字及行政判解").glob("*.pdf")):
        name = clean_name(p); emit(items, "rulings", name, pdf_text(p), {"law": law_domain(name), "title": name})
    # letters（命題方 + 自行蒐集）
    for p in sorted((DS / "命題方提供/行政函釋").glob("*.pdf")):
        name = clean_name(p); emit(items, "letters", name, pdf_text(p), {"law": law_domain(name), "title": name})
    for p in sorted((DS / "自行蒐集/判解函釋補充").iterdir()):
        if p.suffix not in (".pdf", ".md"):
            continue
        name = clean_name(p); t = pdf_text(p) if p.suffix == ".pdf" else p.read_text(encoding="utf-8")
        kind = "decisions" if "決定書" in name else "letters"
        emit(items, kind, name, t, {"law": law_domain(name), "title": name, "year": 114, "clause": "", "result": ""})
    # decisions（排除評測三案）
    for c in load_cases():
        if c["excluded"]:
            continue
        emit(items, "decisions", c["id"], pdf_text(Path(c["path"])),
             {"law": law_domain(c["event"]), "title": c["id"], "year": c["year"], "clause": c["clause"], "result": c["result"]})
    return items


if __name__ == "__main__":
    items = build()
    OUT.mkdir(parents=True, exist_ok=True)
    s3 = boto3.client("s3", region_name=REGION)
    from collections import Counter
    print(Counter(k.split("/")[0] for k, _, _ in items))
    for key, text, meta in items:
        (OUT / key).parent.mkdir(parents=True, exist_ok=True)
        (OUT / key).write_text(text, encoding="utf-8")
        (OUT / (key + ".metadata.json")).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        if "--dry" not in sys.argv:
            s3.put_object(Bucket=BUCKET, Key=PREFIX + key, Body=text.encode("utf-8"), ContentType="text/plain; charset=utf-8")
            s3.put_object(Bucket=BUCKET, Key=PREFIX + key + ".metadata.json", Body=json.dumps(meta, ensure_ascii=False).encode("utf-8"))
    assert not any(any(x in k for x in EVAL_EXCLUDE) for k, _, _ in items), "評測決定書混入語料！"
    print(f"{len(items)} 檔 → s3://{BUCKET}/{PREFIX}")
