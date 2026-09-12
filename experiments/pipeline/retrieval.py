"""Bedrock Knowledge Base 檢索（語意找候選）。條號存在性查核仍由 lawdb 負責，兩層都要。"""
import json
from pathlib import Path

import boto3

_cfg = json.loads((Path(__file__).resolve().parents[1] / "kb/kb.json").read_text())
_rt = boto3.client("bedrock-agent-runtime", region_name=_cfg["region"])
KB_ID = _cfg["kbId"]


def retrieve(query: str, *, kinds: list[str] | None = None, law: str | None = None, k: int = 8,
             exclude_titles: set[str] | None = None) -> list[dict]:
    """回 [{title, kind, law, year, clause, result, text, score, uri}]，依分數排序。"""
    conds = []
    if kinds:
        conds.append({"in": {"key": "kind", "value": kinds}} if len(kinds) > 1 else {"equals": {"key": "kind", "value": kinds[0]}})
    if law:
        conds.append({"equals": {"key": "law", "value": law}})
    vs = {"numberOfResults": k * 2 if exclude_titles else k}
    if conds:
        vs["filter"] = conds[0] if len(conds) == 1 else {"andAll": conds}
    r = _rt.retrieve(knowledgeBaseId=KB_ID, retrievalQuery={"text": query[:1000]},
                     retrievalConfiguration={"vectorSearchConfiguration": vs})
    out = []
    for x in r["retrievalResults"]:
        m = x.get("metadata", {})
        t = m.get("title", "")
        if exclude_titles and any(e in t for e in exclude_titles):
            continue
        out.append({"title": t, "kind": m.get("kind"), "law": m.get("law"), "year": m.get("year"),
                    "clause": m.get("clause"), "result": m.get("result"), "text": x["content"]["text"],
                    "score": round(x.get("score", 0), 3), "uri": x["location"].get("s3Location", {}).get("uri", "")})
    return out[:k]


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "隨地拋棄煙蒂 稽查照片舉證 裁罰係數"
    for kinds in (["laws"], ["rulings", "letters"], ["decisions"]):
        print("==", kinds)
        for h in retrieve(q, kinds=kinds, k=4):
            print(f"  {h['score']:.3f} [{h['kind']}] {h['title'][:50]}  ← {h['text'][:60].replace(chr(10),' ')}")
