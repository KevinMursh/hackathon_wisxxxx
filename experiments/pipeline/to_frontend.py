"""pipeline 各步 JSON → 前端 case 物件（鍵名對齊 prototype/data.js）。純程式，零 LLM。"""
import re
from .anchors import RefTable
from .ingest import Doc

CHECK_LABELS = [("77(1)", "訴願書合法定程式"), ("77(2)", "於法定期間內提起"), ("77(3)", "當事人適格"), ("77(4)", "具訴願能力"),
                ("77(5)", "代理人合法"), ("77(6)", "行政處分仍存在"), ("77(7)", "非重行提起"), ("77(8)", "屬訴願救濟範圍")]
GROUP = {"機關權限": "實體法規", "處分依據": "實體法規", "裁罰額度": "裁罰基準", "裁量": "實體法規", "程序": "程序法規",
         "救濟期間": "程序法規", "判準": "判解", "政策說明": "行政函釋"}
HEADS = ("主文", "事實", "理由", "據上論結", "教示", "訴願決定書")


def _tri(t, rt: RefTable):
    if not t:
        return [None, None]
    return [t.get("value"), rt.add(t.get("quote"))]


def build(docs: list[Doc], fields: dict, period: dict, issues: dict, laws_verified: list, citations: list,
          laws_extra: dict, sims: list, sim_notes: dict, draft: str, draft_cites: list) -> dict:
    rt = RefTable(docs)
    out = {}
    out["files"] = [[d.name, d.fileId, d.doc_type, d.source, d.originalName] for d in docs]

    # Tab 1
    out["fields"] = [{"k": r["k"], "a": _tri(r.get("appellant"), rt), "d": _tri(r.get("agency"), rt),
                      "e": _tri(r.get("evidence"), rt), "conflict": r.get("conflict")} for r in fields["compare"]]
    out["cls"] = [["案件類型", fields["case_type"]], ["主要爭點", fields["main_issue"]],
                  ["預判走向", "程序不受理" if period["in_time"] is False else "實體審查"]]
    out["period"] = {"served": period["served"], "recv": period["recv"], "appealSays": period["appellant_says"],
                     "deadline": period["deadline"], "inTime": period["in_time"],
                     "servedRef": rt.add(fields.get("served_source")), "recvRef": None}
    p = fields["procedural"]
    st = lambda b, ok="pass", bad="fail": "auto" if b is None else (ok if b else bad)
    out["checks"] = [
        ["77(1)", CHECK_LABELS[0][1], "pass", "訴願書齊備"],
        ["77(2)", CHECK_LABELS[1][1], st(period["in_time"]), period["checks"][0]["note"]],
        ["77(3)", CHECK_LABELS[2][1], st(p["is_penalized_party"]), p["note"]],
        ["77(4)", CHECK_LABELS[3][1], st(p["has_capacity"]), ""],
        ["77(5)", CHECK_LABELS[4][1], "na" if not p["has_agent"] else "pass", "未委任代理人" if not p["has_agent"] else "附委任書"],
        ["77(6)", CHECK_LABELS[5][1], st(p["disposition_exists"]), ""],
        ["77(7)", CHECK_LABELS[6][1], st(p["prior_appeal"], ok="fail", bad="pass"), ""],
        ["77(8)", CHECK_LABELS[7][1], st(p["is_admin_disposition"]), ""],
    ]

    # Tab 2
    out["issues"] = [{"id": i["id"], "title": i["title"],
                      "a": [i["appellant_claim"], None], "d": [i["agency_reply"], None],
                      "e": [[q["quote"][:40], rt.add(q)] for q in i["evidence"]],
                      "law": i["laws"], "finding": i["finding"], "reason": i["reason"]} for i in issues["issues"]]

    # Tab 3
    out["laws"] = []
    for r in laws_verified:
        badges = []
        if r["kind"] == "法規":
            badges.append(["green", "資料集內全文"] if r["status"] == "ok" else ["amber", "資料集無此條" if r["status"] == "no_article" else "不在資料集"])
            if r.get("amended"):
                badges.append(["neutral", f"修正 {r['amended']}"])
        else:
            badges.append(["neutral", "資料集內文件" if r["status"] == "ok" else "候選外"])
        name = f"{r['name']} 第 {r['article']} 條{r['paragraph'] or ''}" if r["kind"] == "法規" else r["name"]
        out["laws"].append({"g": GROUP.get(r["role"], "其他"), "n": name, "t": r.get("text", "")[:300], "rel": r["rel"], "badges": badges, "why": r["why"]})
    out["citations"] = [{"n": c["cite"], "where": c["source"], "ref": None,
                         "status": "ok" if c["status"] == "ok" else ("gap" if c["status"] == "no_article" else "unknown"),
                         "note": {"ok": "資料集內全文比對相符", "no_article": "資料集該法無此條", "not_in_dataset": "子法／準則不在資料集", "unknown_law": "查無此法規"}[c["status"]]}
                        for c in citations]
    for g in laws_extra.get("missing_in_defense", []):
        out["citations"].append({"n": g, "where": "答辯書未引用", "ref": None, "status": "gap", "note": "決定書慣例應引；草稿已列入"})
    out["alert"] = laws_extra.get("alert")

    # Tab 4
    notes = {n["id"]: n for n in sim_notes.get("notes", [])}
    out["sims"] = [{"fn": s["id"], "s": notes.get(s["id"], {}).get("score", 0), "why": notes.get(s["id"], {}).get("why_similar", ""),
                    "one": notes.get(s["id"], {}).get("one_liner", ""), "chips": notes.get(s["id"], {}).get("chips", []),
                    "path": s["path"], "result": s["result"], "clause": s["clause"]} for s in sims]
    dist = {"不受理": 0, "駁回": 0, "撤銷": 0}
    for s in sims:
        dist["不受理" if "不受理" in s["result"] else "駁回" if "駁回" in s["result"] else "撤銷"] += 1
    out["simDist"] = [[k, v] for k, v in dist.items()]

    # Tab 5
    paras, cur_kind = [], "p"
    for n, line in enumerate(l.strip() for l in draft.splitlines() if l.strip()):
        kind = "h4" if line in HEADS or (len(line) <= 6 and line.rstrip("：:") in HEADS) else "p"
        refs = [rt.add({"file": f, "quote": ""}) for f in re.findall(r"〔([^〕]+)〕", line)]
        paras.append({"id": f"p{n}", "kind": kind, "text": re.sub(r"〔[^〕]+〕", "", line), "refs": [r for r in refs if r]})
    m_main = re.search(r"主文\s*\n+\s*(.+)", draft)
    m_art = re.search(r"依訴願法第\s*(\d+)\s*條第\s*(\d+)\s*項", draft)
    verdict = (m_main.group(1).strip() if m_main else "").rstrip("。")
    art = f"{m_art.group(1)}{'I' if m_art.group(2) == '1' else 'II'}" if m_art else ""
    total = sum(dist.values()) or 1
    same = dist["駁回"] if "駁回" in verdict else dist["撤銷"] if "撤銷" in verdict else dist["不受理"]
    out["judge"] = {"verdict": verdict, "art": f"訴願法 §{art}" if art else "", "issues": [[i["title"], i["finding"]] for i in issues["issues"]],
                    "risk": "low" if same / total >= 0.6 else "mid" if same / total >= 0.4 else "high",
                    "riskNote": f"相似案例 {same}/{total} 件結論相同", "unknownCites": [c["cite"] for c in draft_cites if c["status"] == "unknown_law"]}
    out["drafts"] = {"A": {"tmpl": art, "head": "新北市政府訴願決定書", "sub": f"（AI 草稿・待承辦人審核）", "paras": paras}}
    out["refs"] = rt.refs
    out["unverifiedQuotes"] = rt.unverified
    return out
