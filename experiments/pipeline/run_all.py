"""固定 pipeline：s2 欄位 → 期間／程序（程式）→ s3 爭點 → s4 法規＋引用查核（程式）→ s5 相似案例（規則＋1 次說明）→ s6 草稿（串流）
用法：python -m pipeline.run_all case02 [--from s3] [--no-images]
每步輸出落 runs/{case}/；--from 可從中間步驟續跑（讀前面步驟的 runs）。"""
import json, re, sys, time
from datetime import date, timedelta
from pathlib import Path

from . import casedb, lawdb
from .common import RUNS, call_json, docs_block, load_case, prompt, stream_text
from .schemas import Fields, Issues, Laws, Sims

SYS = prompt("system")


def _load(case: str, step: str):
    return json.loads((RUNS / case / f"{step}.json").read_text(encoding="utf-8"))["output"]


def _roc(s: str | None) -> date | None:
    m = s and re.match(r"(\d{2,3})-(\d{1,2})-(\d{1,2})", s)
    return date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))) if m else None


# ---------- 程式步驟（零 LLM） ----------
def period_and_checks(f: dict) -> dict:
    """訴願法 §14：處分達到之次日起 30 日內。"""
    served, recv = _roc(f["disposition_served_date"]), _roc(f["appeal_received_date"])
    out = {"served": f["disposition_served_date"], "recv": f["appeal_received_date"],
           "appellant_says": f["appellant_stated_received"], "deadline": None, "in_time": None, "checks": []}
    if served:
        dl = served + timedelta(days=30)
        out["deadline"] = f"{dl.year-1911}-{dl.month:02d}-{dl.day:02d}"
        if recv:
            out["in_time"] = recv <= dl
    out["checks"] = [
        {"item": "訴願期間（§14）", "ok": out["in_time"], "note": f"送達 {out['served']}，次日起 30 日至 {out['deadline']}，收文 {out['recv']}" if served else "缺送達證書，無法起算"},
        {"item": "自述收受日與送達證書", "ok": not (f["appellant_stated_received"] and f["appellant_stated_received"] != f["disposition_served_date"]),
         "note": f"自述 {f['appellant_stated_received']} vs 卷證 {f['disposition_served_date']}" if f["appellant_stated_received"] else "訴願書未自述"},
        {"item": "有無答辯書", "ok": bool(f["agency_replies"]), "note": f"{len(f['agency_replies'])} 點答辯"},
        {"item": "處分依據條文可查", "ok": None, "note": "見引用查核"},
    ]
    return out


def clause_hint(period: dict, issues: dict) -> str | None:
    if period["in_time"] is False:
        return "77(2)"
    return None  # 程序無礙 → 實體審查（79I／81I）


# ---------- 主流程 ----------
def run(case: str, start: str = "s2", images: bool = True):
    c = load_case(case)
    db = lawdb.load()
    order = ["s2", "s3", "s4", "s5", "s6"]
    todo = order[order.index(start):]
    t0 = time.monotonic()
    kw_docs = docs_block(c["docs"])
    imgs = list(c["images"].values()) if images else []

    # s2 欄位
    if "s2" in todo:
        fields = call_json("s2_fields", Fields, case=case, system=SYS + "\n\n" + prompt("s2_fields"),
                           user=kw_docs + "\n\n（附圖為掃描件與照片，檔名如圖片順序）\n" + "\n".join(f"圖 {i+1}: {p.name}" for i, p in enumerate(imgs)),
                           images=imgs).model_dump()
    else:
        fields = _load(case, "s2_fields")
    period = period_and_checks(fields)
    (RUNS / case / "s2_period.json").write_text(json.dumps({"output": period}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[s2] {fields['appellant_masked']} / {fields['disposition_no']} / 送達 {period['served']} 收文 {period['recv']} → 在期間內: {period['in_time']}", file=sys.stderr)

    # s3 爭點
    if "s3" in todo:
        issues = call_json("s3_issues", Issues, case=case, system=SYS + "\n\n" + prompt("s3_issues"),
                           user=kw_docs + "\n\n已擷取欄位：\n" + json.dumps(fields, ensure_ascii=False) +
                                "\n\n程序檢核：\n" + json.dumps(period, ensure_ascii=False) +
                                "\n\n（附圖為掃描件與照片）\n" + "\n".join(f"圖 {i+1}: {p.name}" for i, p in enumerate(imgs)),
                           images=imgs).model_dump()
    else:
        issues = _load(case, "s3_issues")
    for i in issues["issues"]:
        print(f"[s3] {i['title']} → {i['finding']}：{i['reason'][:40]}", file=sys.stderr)

    # s4 法規＋引用查核
    cites = []
    for fn, txt in c["docs"].items():
        if any(k in fn for k in ("答辯", "裁處書")):
            cites += lawdb.check_citations(db, txt, source=fn)
    if "s4" in todo:
        law_list = "\n".join(f"- {k}（{v['amended']}）" for k, v in db.items())
        laws = call_json("s4_laws", Laws, case=case, system=SYS + "\n\n" + prompt("s4_laws"),
                         user="可用法規清單：\n" + law_list + "\n\n本案欄位：\n" + json.dumps(fields, ensure_ascii=False) +
                              "\n\n本案爭點：\n" + json.dumps(issues, ensure_ascii=False) +
                              "\n\n答辯書／裁處書引用查核結果：\n" + json.dumps(cites, ensure_ascii=False)).model_dump()
    else:
        laws = _load(case, "s4_laws")
    verified = []
    for r in laws["recommended"]:
        hit = lawdb.lookup(db, r["law"], r["article"])
        verified.append({**r, "status": hit["status"], "text": hit["text"][:600], "amended": hit.get("amended", "")})
    (RUNS / case / "s4_verified.json").write_text(json.dumps({"output": {"laws": verified, "citations": cites}}, ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [v for v in verified if v["status"] != "ok"]
    print(f"[s4] 推薦 {len(verified)} 條（{len(bad)} 條查無）；答辯／裁處書引用 {len(cites)} 則，{sum(x['status']!='ok' for x in cites)} 則查無", file=sys.stderr)

    # s5 相似案例
    law_name = next((r["law"] for r in verified if r["role"].startswith("處分依據")), None) or (fields["law_basis"][0].split("第")[0] if fields["law_basis"] else "")
    cands = casedb.similar(law_name, clause_hint(period, issues), k=5)
    if "s5" in todo and cands:
        cand_txt = "\n\n".join(f"=== ID {x['id']} ===\n{casedb.text_of(x, 3000)}" for x in cands)
        sims = call_json("s5_sims", Sims, case=case, system=SYS + "\n\n" + prompt("s5_sims"),
                         user="本案欄位：\n" + json.dumps(fields, ensure_ascii=False) + "\n\n本案爭點：\n" +
                              json.dumps([i["title"] for i in issues["issues"]], ensure_ascii=False) + "\n\n候選決定書：\n" + cand_txt).model_dump()
    else:
        sims = _load(case, "s5_sims") if cands else {"notes": []}
    print(f"[s5] {law_name} → {len(cands)} 件：" + "；".join(x["id"][:22] for x in cands), file=sys.stderr)

    # s6 草稿
    if "s6" in todo:
        exemplars = "\n\n".join(f"=== 格式範例 {x['id']} ===\n{casedb.text_of(x, 6000)}" for x in cands[:2])
        user = ("本案卷宗：\n" + kw_docs + "\n\n本案欄位：\n" + json.dumps(fields, ensure_ascii=False) +
                "\n\n程序檢核：\n" + json.dumps(period, ensure_ascii=False) +
                "\n\n本案爭點：\n" + json.dumps(issues, ensure_ascii=False) +
                "\n\n推薦法條（含條文原文）：\n" + json.dumps(verified, ensure_ascii=False) +
                "\n\n" + exemplars + "\n\n請撰擬本案訴願決定書草稿。")
        draft = []
        for chunk in stream_text("s6_draft", case=case, system=SYS + "\n\n" + prompt("s6_draft"), user=user):
            draft.append(chunk); print(chunk, end="", flush=True)
        print()
        draft = "".join(draft)
    else:
        draft = _load(case, "s6_draft")
    draft_cites = lawdb.check_citations(db, draft, source="草稿")
    (RUNS / case / "s6_citations.json").write_text(json.dumps({"output": draft_cites}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[s6] 草稿 {len(draft)} 字；引用 {len(draft_cites)} 則，{sum(x['status']!='ok' for x in draft_cites)} 則查無；總耗時 {time.monotonic()-t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    args = sys.argv[1:]
    case = args[0] if args and not args[0].startswith("--") else "case02"
    start = args[args.index("--from") + 1] if "--from" in args else "s2"
    run(case, start, images="--no-images" not in args)
