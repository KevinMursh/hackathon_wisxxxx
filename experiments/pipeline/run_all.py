"""固定 pipeline v2：
  ingest（隊友歸戶結果）→ s2 欄位＋三方對照 → 期間／程序（程式）→ s3 爭點 → s4 法規（KB 函釋判解 + 字典查核）
  → s5 相似案例（KB decisions + 規則重排 + 1 次說明）→ s6 草稿（串流）→ to_frontend
用法：python -m pipeline.run_all case02 [--from s3] [--no-images] [--api http://host]
每步落 runs/{case}/；--from 讀前面步驟快取續跑。"""
import json, re, sys, time
from datetime import date, timedelta

from . import casedb, lawdb, lawlib, to_frontend
from .anchors import locate
from .common import RUNS, call_json, prompt, stream_text
from .ingest import Doc, by_name, for_step, load_any, load_local, load_remote, prompt_block
from .retrieval import retrieve
from .schemas import Fields, Issues, Laws, Sims

SYS = prompt("system")


def _load(case, step):
    return json.loads((RUNS / case / f"{step}.json").read_text(encoding="utf-8"))["output"]


def _save(case, step, obj):
    (RUNS / case).mkdir(parents=True, exist_ok=True)
    (RUNS / case / f"{step}.json").write_text(json.dumps({"output": obj}, ensure_ascii=False, indent=2), encoding="utf-8")


def _roc(s):
    m = s and re.match(r"(\d{2,3})-(\d{1,2})-(\d{1,2})", s)
    return date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))) if m else None


def _imgs(docs: list[Doc]):
    return [p for d in docs for p in d.images if not isinstance(p, str) or not p.startswith("http")]


def _img_note(docs: list[Doc]):
    names = [d.name for d in docs if d.images]
    return ("\n\n（附圖依序對應：" + "、".join(f"圖{i+1}={n}" for i, n in enumerate(names)) + "）") if names else ""


# ---------- 程式步驟 ----------
def period_and_checks(f: dict) -> dict:
    served, recv = _roc(f["disposition_served_date"]), _roc(f["appeal_received_date"])
    out = {"served": f["disposition_served_date"], "recv": f["appeal_received_date"], "appellant_says": f["appellant_stated_received"],
           "deadline": None, "in_time": None, "checks": []}
    if served:
        dl = served + timedelta(days=30)
        out["deadline"] = f"{dl.year-1911}-{dl.month:02d}-{dl.day:02d}"
        out["in_time"] = (recv <= dl) if recv else None
    out["checks"] = [{"item": "訴願期間（§14）", "ok": out["in_time"],
                      "note": f"送達 {out['served']}，次日起 30 日至 {out['deadline']}，收文 {out['recv']}" if served else "缺送達證書，無法起算"}]
    return out


def verify_quotes(docs: list[Doc], issues: dict) -> int:
    """回查爭點引句是否真在該檔文字裡；找不到標 unverified（圖片檔無文字者不算）。"""
    names, bad = by_name(docs), 0
    for i in issues["issues"]:
        for q in i["evidence"]:
            d = names.get(q["file"])
            q["verified"] = bool(d and (not d.text.strip() or locate(d, q["quote"])))
            bad += not q["verified"]
    return bad


# ---------- 主流程 ----------
def run(case: str, start="s2", images=True, api: str | None = None, docs: list[Doc] | None = None, progress=None) -> dict:
    """progress(step, status, payload) 在每步開始／完成時呼叫（API 用）。回傳前端物件。"""
    docs = docs or (load_remote(case, api) if api else load_any(case))
    db = lawdb.load()
    order = ["s2", "s3", "s4", "s5", "s6"]
    todo = order[order.index(start):] if start in order else []  # --from fe：全部讀快取，只重做程式步驟與 adapter
    t0 = time.monotonic()
    log = lambda m: print(m, file=sys.stderr)
    emit = progress or (lambda *a: None)
    partial = {}  # 逐步累積給前端的鍵，每步完成就 emit 一次

    # s2
    emit("s2", "running", None)
    d2 = for_step(docs, "s2")
    if "s2" in todo:
        fields = call_json("s2_fields", Fields, case=case, system=SYS + "\n\n" + prompt("s2_fields"),
                           user=prompt_block(d2) + _img_note(d2), images=_imgs(d2) if images else []).model_dump()
    else:
        fields = _load(case, "s2_fields")
    period = period_and_checks(fields); _save(case, "s2_period", period)
    log(f"[s2] {fields['appellant_masked']} / {fields['disposition_no']} / 送達 {period['served']} 收文 {period['recv']} → 在期間內 {period['in_time']}；三方對照 {len(fields['compare'])} 列")
    emit("s2", "done", {"fields": fields, "period": period})
    emit("s3", "running", None)

    # s3
    if "s3" in todo:
        issues = call_json("s3_issues", Issues, case=case, system=SYS + "\n\n" + prompt("s3_issues"),
                           user=prompt_block(docs) + "\n\n已擷取欄位：\n" + json.dumps({k: fields[k] for k in ("appellant_claims", "agency_replies", "violation_fact", "law_basis")}, ensure_ascii=False)
                                + "\n\n程序檢核：\n" + json.dumps(period, ensure_ascii=False) + _img_note(docs),
                           images=_imgs(docs) if images else []).model_dump()
        bad = verify_quotes(docs, issues); _save(case, "s3_issues", issues)
    else:
        issues = _load(case, "s3_issues"); bad = sum(not q.get("verified", True) for i in issues["issues"] for q in i["evidence"])
    for i in issues["issues"]:
        log(f"[s3] {i['id']} {i['title']} → {i['finding']}：{i['reason'][:36]}")
    log(f"[s3] 引句回查失敗 {bad} 則")
    emit("s3", "done", {"issues": issues})
    emit("s4", "running", None)

    # s4：字典查核 + KB 候選（函釋／判解）+ 1 次挑選
    cites = []
    for d in docs:
        if d.doc_type in ("答辯書", "裁處書"):
            cites += lawdb.check_citations(db, d.text, source=d.name)
    q = fields["violation_fact"] + " " + " ".join(i["title"] for i in issues["issues"])
    cands = retrieve(q, kinds=["rulings", "letters"], k=8)
    seen, cand_list = set(), []
    for h in cands:
        if h["title"] not in seen:
            seen.add(h["title"]); cand_list.append(h)
    if "s4" in todo:
        law_list = "\n".join(f"- {k}｜最新修正 {v['amended']}" for k, v in db.items() if "（現行）" not in k)
        cand_txt = "\n\n".join(f"【{h['kind']}】{h['title']}\n{h['text'][:600]}" for h in cand_list)
        laws = call_json("s4_laws", Laws, case=case, system=SYS + "\n\n" + prompt("s4_laws"),
                         user="可用法規清單：\n" + law_list + "\n\n候選函釋判解（KB 檢索）：\n" + cand_txt +
                              "\n\n本案欄位：\n" + json.dumps({k: fields[k] for k in ("agency", "violation_fact", "violation_date", "disposition_date", "law_basis", "case_type")}, ensure_ascii=False) +
                              "\n\n本案爭點：\n" + json.dumps(issues, ensure_ascii=False) +
                              "\n\n答辯書／裁處書引用查核：\n" + json.dumps(cites, ensure_ascii=False)).model_dump()
    else:
        laws = _load(case, "s4_laws")
    verified = []
    def _canon(name: str) -> str:  # 模型可能把「（修正 …）」或全形括號一起抄進來
        base = re.split(r"[（(｜|]", name)[0].strip()
        if base in db:
            return base
        return next((k for k in sorted(db, key=len, reverse=True) if "（現行）" not in k and base.startswith(k)), base)
    for r in laws["recommended"]:
        if r["kind"] == "法規":
            r["name"] = _canon(r["name"])
            hit = lawdb.lookup(db, r["name"], r["article"] or "")
            verified.append({**r, "status": hit["status"], "text": hit["text"][:600], "amended": hit.get("amended", "")})
        else:
            hit = next((h for h in cand_list if h["title"] == r["name"] or r["name"] in h["title"]), None)
            verified.append({**r, "status": "ok" if hit else "unknown_law", "text": hit["text"][:600] if hit else "", "uri": hit["uri"] if hit else ""})
    _save(case, "s4_verified", {"laws": verified, "citations": cites, "kb_candidates": [h["title"] for h in cand_list]})
    emit("s4", "done", {"laws": verified, "citations": cites, "alert": laws.get("alert")})
    emit("s5", "running", None)
    log(f"[s4] 推薦 {len(verified)}（法規 {sum(v['kind']=='法規' for v in verified)}／函釋判解 {sum(v['kind']!='法規' for v in verified)}；查無 {sum(v['status']=='unknown_law' for v in verified)}）；答辯／裁處書引用 {len(cites)} 則；alert={bool(laws.get('alert'))}")

    # s5：KB decisions（同法）+ 規則重排
    law_name = next((r["name"] for r in verified if r["kind"] == "法規" and r["role"] == "處分依據"), None) or (fields["law_basis"][0].split("第")[0] if fields["law_basis"] else "")
    hits = retrieve(fields["violation_fact"] + " " + " ".join(i["title"] for i in issues["issues"]), kinds=["decisions"], law=law_name, k=12)
    kb_ids = []
    for h in hits:
        if h["title"] not in kb_ids:
            kb_ids.append(h["title"])
    allc = {c["id"]: c for c in casedb.load() if not c["excluded"]}
    hint = "77(2)" if period["in_time"] is False else None
    def score(cid):
        c = allc[cid]; s = 100 - kb_ids.index(cid) * 5
        if hint and c["clause"].startswith(hint): s += 40
        elif not hint and c["clause"][:2] in ("79", "81"): s += 40
        return -s
    sims = [allc[cid] for cid in sorted([i for i in kb_ids if i in allc], key=score)[:5]]
    if len(sims) < 5:
        sims += [c for c in casedb.similar(law_name, hint, k=5) if c not in sims][: 5 - len(sims)]
    if "s5" in todo and sims:
        sim_notes = call_json("s5_sims", Sims, case=case, system=SYS + "\n\n" + prompt("s5_sims"),
                              user="本案：\n" + json.dumps({"case_type": fields["case_type"], "violation_fact": fields["violation_fact"], "issues": [i["title"] for i in issues["issues"]]}, ensure_ascii=False) +
                                   "\n\n候選決定書：\n" + "\n\n".join(f"=== ID {x['id']} ===\n{casedb.text_of(x, 3000)}" for x in sims)).model_dump()
    else:
        sim_notes = _load(case, "s5_sims") if sims else {"notes": []}
    _save(case, "s5_list", sims)
    emit("s5", "done", {"sims": sims, "notes": sim_notes})
    emit("s6", "running", None)
    log(f"[s5] {law_name}（KB 命中 {len(kb_ids)}）→ " + "；".join(f"{x['year']} {x['clause']} {x['result']}" for x in sims))

    # s6
    if "s6" in todo:
        ex = "\n\n".join(f"=== 格式範例 {x['id']} ===\n{casedb.text_of(x, 5000)}" for x in sims[:2])
        borrow = [{"id": n["id"], "from": n["borrow_from"], "for": n["borrow_for"], "what": n["borrow_what"]} for n in sim_notes.get("notes", []) if n.get("borrow_from")]
        ex = "相似案例可借用段落（論理架構）：\n" + json.dumps(borrow, ensure_ascii=False) + "\n\n" + ex
        user = ("本案卷宗：\n" + prompt_block(docs, 6000) + "\n\n本案欄位：\n" + json.dumps({k: v for k, v in fields.items() if k != "compare"}, ensure_ascii=False) +
                "\n\n程序檢核：\n" + json.dumps(period, ensure_ascii=False) + "\n\n本案爭點：\n" + json.dumps(issues, ensure_ascii=False) +
                "\n\n推薦法條、函釋、判解（含原文）：\n" + json.dumps(verified, ensure_ascii=False) + "\n\n" + ex + "\n\n請撰擬本案訴願決定書草稿。")
        buf = []
        for ch in stream_text("s6_draft", case=case, system=SYS + "\n\n" + prompt("s6_draft"), user=user):
            buf.append(ch); print(ch, end="", flush=True)
        print(); draft = "".join(buf)
    else:
        draft = _load(case, "s6_draft")
    draft_cites = lawdb.check_citations(db, draft, source="草稿"); _save(case, "s6_citations", draft_cites)
    log(f"[s6] {len(draft)} 字；引用 {len(draft_cites)} 則，unknown {sum(c['status']=='unknown_law' for c in draft_cites)}")

    lib = lawlib.build()
    fe = to_frontend.build(docs, fields, period, issues, verified, cites, laws, sims, sim_notes, draft, draft_cites, lib)
    _save(case, "frontend", fe)
    emit("s6", "done", {"draft": draft})
    log(f"[fe] refs {len(fe['refs'])}（text {sum(v[1]=='text' for v in fe['refs'].values())}／doc {sum(v[1]=='doc' for v in fe['refs'].values())}／time {sum(v[1]=='time' for v in fe['refs'].values())}）；未定位引句 {len(fe['unverifiedQuotes'])}；判定 {fe['judge']['verdict']} {fe['judge']['art']} risk={fe['judge']['risk']}；總耗時 {time.monotonic()-t0:.0f}s")
    return fe


if __name__ == "__main__":
    a = sys.argv[1:]
    case = a[0] if a and not a[0].startswith("--") else "case02"
    run(case, a[a.index("--from") + 1] if "--from" in a else "s2", "--no-images" not in a, a[a.index("--api") + 1] if "--api" in a else None)
