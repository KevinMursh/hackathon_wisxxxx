"""分析階段 API（步驟 2–5 ＋ 異議 ＋ 法規庫）。契約見 docs/API-分析階段.md。

    uvicorn api:app --host 0.0.0.0 --port 8100

- 一個 worker thread 序列跑 job（全帳號 Bedrock ≤ 1 RPS；再加上 common.py 的 1.1s 節流）
- 進度：記憶體 + DynamoDB（PK CASE#{id} / SK ANALYSIS#latest），重啟不丟
- 資料來源：本機 inputs/{case}/files.json（開發）或隊友的 DynamoDB+S3（雲上）
"""
import json, os, queue, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pipeline import assistant, lawlib, objection, run_all, to_frontend
from pipeline.anchors import RefTable
from pipeline.common import RUNS
from pipeline.ingest import load_any
from kb import sync_laws

REGION = os.getenv("AWS_REGION", "us-west-2")
TABLE = os.getenv("DDB_TABLE", "appeal-cases")
USE_DDB = os.getenv("ANALYSIS_DDB", "1") == "1"
_ddb = boto3.resource("dynamodb", region_name=REGION).Table(TABLE) if USE_DDB else None

app = FastAPI(title="訴願智審臺 分析階段 API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(HTTPException)
async def _flat_http_error(_req, exc):
    """錯誤格式與歸戶 API 一致：頂層 {code, message, retryable}，不是 FastAPI 預設的 {detail: {...}}。"""
    from fastapi.responses import JSONResponse
    d = exc.detail if isinstance(exc.detail, dict) else {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "retryable": False}
    return JSONResponse(status_code=exc.status_code, content=d)

STEPS = ["s2", "s3", "s4", "s5", "s6"]
_jobs: dict[str, dict] = {}          # jobId → {caseId, kind, state, events[], subscribers[]}
_analyses: dict[str, dict] = {}      # caseId → analysis 文件（同 GET 回應）
_q: queue.Queue = queue.Queue()
_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- 持久化 ----------
def _save(case_id: str, doc: dict):
    _analyses[case_id] = doc
    (RUNS / case_id).mkdir(parents=True, exist_ok=True)
    (RUNS / case_id / "analysis.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    if _ddb is not None:
        try:
            _ddb.put_item(Item={"PK": f"CASE#{case_id}", "SK": "ANALYSIS#latest", "json": json.dumps(doc, ensure_ascii=False), "updatedAt": _now()})
        except Exception as e:  # DDB 失敗不擋主流程
            print("ddb put failed:", str(e)[:80])


def _load(case_id: str) -> dict | None:
    if case_id in _analyses:
        return _analyses[case_id]
    p = RUNS / case_id / "analysis.json"
    if p.exists():
        return _analyses.setdefault(case_id, json.loads(p.read_text(encoding="utf-8")))
    if _ddb is not None:
        r = _ddb.get_item(Key={"PK": f"CASE#{case_id}", "SK": "ANALYSIS#latest"}).get("Item")
        if r:
            return _analyses.setdefault(case_id, json.loads(r["json"]))
    return None


# ---------- job ----------
def _emit(job: dict, ev: str, data: dict):
    e = {"seq": len(job["events"]) + 1, "event": ev, "data": data, "at": _now()}
    job["events"].append(e)
    for sub in list(job["subscribers"]):
        sub.put(e)


def _progress_for(job: dict, doc: dict, docs, lib):
    acc = {}
    def progress(step, status, payload):
        doc["status"]["steps"][step] = status
        if status == "running":
            doc["status"]["t"][step] = time.monotonic()
        elif status == "done":
            doc["status"]["ms"][step] = int((time.monotonic() - doc["status"]["t"].get(step, time.monotonic())) * 1000)
            acc[step] = payload
            try:  # 每步完成就重建部分前端物件，GET analysis 進行中即可畫已完成的分頁
                doc["output"] = to_frontend.build_partial(docs, acc, lib)
            except Exception as e:
                print("partial build failed:", step, str(e)[:100])
        _emit(job, "step", {"step": step, "status": status, "ms": doc["status"]["ms"].get(step)})
        _save(job["caseId"], doc)
    return progress


def _run_analyze(job: dict):
    case_id, start = job["caseId"], job["payload"].get("from", "s2")
    doc = {"caseId": case_id, "status": {"state": "running", "steps": {s: "pending" for s in STEPS}, "startedAt": _now(), "finishedAt": None, "ms": {}, "t": {}},
           "output": {}, "objections": []}
    _save(case_id, doc)
    try:
        docs = load_any(case_id)
        lib = lawlib.build()
        fe = run_all.run(case_id, start, images=True, docs=docs, progress=_progress_for(job, doc, docs, lib))
        doc["output"] = fe
        doc["status"].update(state="done", finishedAt=_now())
        _save(case_id, doc)
        _emit(job, "done", {"caseId": case_id, "steps": doc["status"]["ms"]})
    except Exception as e:
        doc["status"].update(state="failed", finishedAt=_now(), error=str(e)[:300])
        _save(case_id, doc)
        _emit(job, "fatal", {"code": "ANALYSIS_FAILED", "message": str(e)[:300]})
    finally:
        doc["status"].pop("t", None)


def _run_objection(job: dict, emit_done: bool = True):
    case_id, ob = job["caseId"], job["payload"]
    doc = _load(case_id)
    try:
        docs = load_any(case_id)
        fe = doc["output"]
        draft = "\n".join(p["text"] for p in fe["drafts"]["A"]["paras"])
        s4 = json.loads((RUNS / case_id / "s4_verified.json").read_text(encoding="utf-8"))["output"]["laws"]
        issues_raw = json.loads((RUNS / case_id / "s3_issues.json").read_text(encoding="utf-8"))["output"]
        res = objection.run(case_id, docs, issues_raw, fe["judge"], ob, draft, s4, {}, progress=lambda s, st, p: _emit(job, "step", {"step": s, "status": st}))
        rf = res.get("revised_finding")  # 模型偶爾回「採機關（補強法條引用）」：正規化成三值，附註留在 reply
        if rf and rf not in ("採機關", "採訴願人", "待議"):
            res["revised_finding"] = next((k for k in ("採訴願人", "採機關", "待議") if rf.startswith(k)), None)
        entry = {k: v for k, v in res.items() if k not in ("newDraft", "newIssues", "newDraftCitations")}
        entry.update(at=_now(), jobId=job["jobId"])
        doc.setdefault("objections", []).append(entry)
        if res.get("newDraft"):
            ver = f"v{len(fe['drafts']) + 1}"
            rt = RefTable(docs, prefix=f"o{len(doc['objections'])}q")
            paras = to_frontend.build_paras(res["newDraft"], docs, rt)
            fe["refs"].update(rt.refs)
            fe["drafts"][ver] = {"tmpl": fe["drafts"]["A"]["tmpl"], "head": fe["drafts"]["A"]["head"], "sub": f"（異議後重產 {ver}・待承辦人審核）", "paras": paras, "objectionId": job["jobId"]}
            fe["judge"]["afterObjection"] = {"issueId": res["issueId"], "finding": res["revised_finding"], "version": ver}
            for i in fe["issues"]:
                if i["id"] == res["issueId"] and res["revised_finding"]:
                    i["afterObjection"] = res["revised_finding"]
        _save(case_id, doc)
        if emit_done:
            _emit(job, "done", entry)
    except Exception as e:
        if not emit_done:
            raise
        _emit(job, "fatal", {"code": "OBJECTION_FAILED", "message": str(e)[:300]})


# ---------- 助手提案（chat 產生 → confirm 執行 → objection 逐項） ----------
_proposals: dict[str, dict] = {}   # pid → proposal doc


def _psave(p: dict):
    _proposals[p["id"]] = p
    d = RUNS / p["caseId"] / "proposals"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{p['id']}.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    if _ddb is not None:
        try:
            _ddb.put_item(Item={"PK": f"CASE#{p['caseId']}", "SK": f"PROPOSAL#{p['id']}", "json": json.dumps(p, ensure_ascii=False), "updatedAt": _now()})
        except Exception as e:
            print("ddb put proposal failed:", str(e)[:80])


def _pload(case_id: str, pid: str) -> dict | None:
    if pid in _proposals:
        return _proposals[pid]
    f = RUNS / case_id / "proposals" / f"{pid}.json"
    if f.exists():
        return _proposals.setdefault(pid, json.loads(f.read_text(encoding="utf-8")))
    if _ddb is not None:
        r = _ddb.get_item(Key={"PK": f"CASE#{case_id}", "SK": f"PROPOSAL#{pid}"}).get("Item")
        if r:
            return _proposals.setdefault(pid, json.loads(r["json"]))
    return None


def _item_reason(it: dict) -> str:
    t = it.get("type")
    if t == "issue":
        return {"appellant": "認定應改為採訴願人", "agency": "認定應改為採機關", "drop": "此爭點應刪除"}.get(it.get("to"), "") + (f"：{it['why']}" if it.get("why") else "")
    if t == "reissue":
        return f"納入新補件（{len(it.get('docs') or [])} 份）重新審查此爭點"
    if t in ("law", "law-rm"):
        return ("加引 " if t == "law" else "移除引用 ") + it.get("key", "") + ("" if it.get("ok", True) else f"（{it.get('msg')}；不得寫入草稿）")
    if t == "served":
        return f"送達日應更正為 {it.get('v')}（原 {it.get('from')}），期間截止 {it.get('deadline')}"
    if t == "proc":
        return "程序應進入實體審查" if it.get("v") == "merit" else f"程序應依訴願法第 77 條第 {str(it.get('v', '')).split('-')[-1]} 款不受理"
    if t == "verdict":
        return f"結論應改為「{it.get('to')}」"
    if t == "text":
        return f"{it.get('para')} 文字改寫：{it.get('how')}"
    if t == "frame":
        return f"論述角度：{it.get('angle')}"
    return json.dumps(it, ensure_ascii=False)


STEP_OF_TYPE = {"served": 0, "proc": 1, "issue": 2, "reissue": 2, "law": 3, "law-rm": 3, "verdict": 4, "text": 5, "frame": 5}
START_OF_SCOPE = {0: "s3", 1: "s3", 2: "s4", 3: "s4", 4: "s5", 5: "s6"}   # 0/1 只覆寫期間不重打 s2；2 的爭點認定由重引證決定，接著從 s4 起


def _build_revision(items: list[dict], replies: list[dict], prev_draft: str) -> dict:
    """把提案 items ＋ 重引證結果整理成 run_all 的 revision（instructions 各步／overrides 程式覆寫）。"""
    ins = {"s3": [], "s4": [], "s5": [], "s6": []}
    ov = {"prev_draft": prev_draft, "findings": {}, "drop_issues": [], "add_laws": [], "rm_laws": []}
    for it, rp in zip(items, replies):
        t, reason = it.get("type"), _item_reason(it)
        if t in ("issue", "reissue"):
            if rp.get("revised_finding"):
                ov["findings"][it["id"]] = rp["revised_finding"]
                ins["s6"].append(f"爭點 {it.get('n', it['id'])}（{it.get('title', '')}）認定已改為「{rp['revised_finding']}」：{rp.get('reply', '')[:200]}")
            if it.get("to") == "drop" and rp.get("result") in ("採納",):
                ov["drop_issues"].append(it["id"])
        elif t == "law" and it.get("ok"):
            ov["add_laws"].append({"name": it.get("key", "").split(" 第 ")[0], "article": it.get("art"), "paragraph": it.get("p") or ""})
            ins["s4"].append(reason); ins["s6"].append(f"理由中須引用 {it.get('key')}")
        elif t == "law-rm":
            ov["rm_laws"].append(it.get("key", "")); ins["s4"].append(reason); ins["s6"].append(f"草稿不得引用 {it.get('key')}")
        elif t == "served":
            ov["served"] = it.get("v"); ins["s6"].append(reason)
        elif t == "proc":
            ov["in_time"] = True if it.get("v") == "merit" else (False if str(it.get("v", "")).startswith("77-2") else None)
            ins["s3"].append(reason); ins["s6"].append(reason)
        elif t == "verdict":
            ov["verdict"] = it.get("to"); ins["s5"].append(reason); ins["s6"].append(f"結論應為「{it.get('to')}」，主文、理由、據上論結與教示均須一致")
        elif t in ("text", "frame"):
            ins["s6"].append(reason + "（其餘段落維持原文）")
    return {"instructions": ins, "overrides": ov}


def _run_proposal(job: dict):
    """confirm：① 爭點類 item 逐一重引證（不重產草稿）② 其餘 item 程式判定 ③ 依影響範圍從第 N 步起局部重跑，上游輸出當 context。"""
    case_id, pid = job["caseId"], job["payload"]["pid"]
    p = _pload(case_id, pid); doc = _load(case_id)
    p["state"] = "running"; _psave(p)
    D_OK = {"law": lambda it: ("採納", f"{it.get('key')} 已加入法規推薦並於草稿引用。") if it.get("ok") else ("無法採納", f"{it.get('msg')}；未寫入草稿。"),
            "law-rm": lambda it: ("採納", f"{it.get('key')} 已自推薦與草稿移除。"),
            "served": lambda it: ("採納", f"送達日改為 {it.get('v')}，期間截止 {it.get('deadline')}，{'在期間內' if it.get('inTime') else '已逾期'}；三方對照已註記承辦人更正。"),
            "proc": lambda it: ("採納" if it.get("v") in ("merit", "77-2") else "部分採納", "程序判定已依指示調整，期間欄位同步更新。" if it.get("v") in ("merit", "77-2") else "已於爭點與草稿附記承辦人指定之不受理事由；程序清單各款仍依卷面。"),
            "verdict": lambda it: ("採納", f"結論改為「{it.get('to')}」，相似案例改檢索同結論案例，草稿依此重寫。"),
            "text": lambda it: ("採納", f"{it.get('para')} 已依「{it.get('how')}」改寫，其餘段落維持。"),
            "frame": lambda it: ("採納", f"理由已依「{it.get('angle')}」角度重寫。")}
    try:
        docs = load_any(case_id)
        fe = doc["output"]
        vers = list(fe.get("drafts") or {})
        prev_draft = "\n".join(x["text"] for x in fe["drafts"][vers[-1]]["paras"]) if vers else ""
        s4 = json.loads((RUNS / case_id / "s4_verified.json").read_text(encoding="utf-8"))["output"]["laws"]
        issues_raw = json.loads((RUNS / case_id / "s3_issues.json").read_text(encoding="utf-8"))["output"]
        items = p["items"]; replies = [None] * len(items)
        issue_idx = [i for i, it in enumerate(items) if it.get("type") in ("issue", "reissue") and it.get("id")]
        n_ob = len(issue_idx)
        for k, i in enumerate(issue_idx):
            it = items[i]; label = f"爭點 {it.get('n', '')}：{_item_reason(it)}"
            p["progress"] = {"phase": "objection", "i": k + 1, "n": n_ob, "label": label}; _psave(p)
            _emit(job, "step", {"step": "objection", "status": "running", "i": k + 1, "n": n_ob, "label": label})
            ob = {"issueId": it["id"], "reason": _item_reason(it), "cites": it.get("docs") or [], "by": "承辦人", "proposalId": pid}
            res = objection.run(case_id, docs, issues_raw, fe["judge"], ob, prev_draft, s4, {}, regen=False)
            rf = res.get("revised_finding")
            if rf and rf not in ("採機關", "採訴願人", "待議"):
                res["revised_finding"] = next((x for x in ("採訴願人", "採機關", "待議") if rf.startswith(x)), None)
            entry = {k2: v for k2, v in res.items() if k2 not in ("newDraft", "newIssues", "newDraftCitations")}
            entry.update(at=_now(), jobId=job["jobId"]); doc.setdefault("objections", []).append(entry); _save(case_id, doc)
            replies[i] = {"label": label, "result": res["result"], "reply": res["reply"], "evidence": res.get("evidence") or [], "revised_finding": res.get("revised_finding"), "issueId": it["id"]}
            _emit(job, "step", {"step": "objection", "status": "done", "i": k + 1, "n": n_ob, "result": res["result"]})
        for i, it in enumerate(items):
            if replies[i] is None:
                r, txt = D_OK.get(it.get("type"), lambda x: ("部分採納", "已附記於草稿。"))(it)
                replies[i] = {"label": _item_reason(it), "result": r, "reply": txt, "evidence": [], "revised_finding": None, "issueId": None}
        # 局部重跑：影響起點取「有效 item」的最小步驟（無法採納的爭點 item 不算）
        eff = [STEP_OF_TYPE.get(it.get("type"), 5) for it, rp in zip(items, replies) if not (it.get("type") in ("issue", "reissue") and rp["result"] == "無法採納") and not (it.get("type") == "law" and not it.get("ok"))]
        if not eff:
            p.update(state="applied", replies=replies, appliedAt=_now(), jobId=job["jobId"], rerun=[]); _psave(p)
            _emit(job, "done", {"proposalId": pid, "replies": replies, "rerun": []}); return
        start = START_OF_SCOPE[min(eff)]
        revision = _build_revision(items, replies, prev_draft)
        steps = STEPS[STEPS.index(start):]
        p["rerun"] = steps; p["progress"] = {"phase": "rerun", "step": start, "steps": steps}; _psave(p)
        lib = lawlib.build()
        def progress(step, status, payload):
            if status == "running" and step in steps:   # 快取步驟也會 emit，只回報真的重跑的步
                p["progress"] = {"phase": "rerun", "step": step, "steps": steps}; _psave(p)
            _emit(job, "step", {"step": step, "status": status})
        new_fe = run_all.run(case_id, start, images=True, docs=docs, progress=progress, revision=revision)
        # 保留草稿版本：舊版全部留下，新版加 vN；issues 標 afterObjection 供前端「修正後」
        old_drafts = fe.get("drafts") or {}
        ver = f"v{len(old_drafts) + 1}"
        new_fe["drafts"] = {**old_drafts, ver: {**new_fe["drafts"]["A"], "sub": f"（修改提案後重產 {ver}・待承辦人審核）", "proposalId": pid}}
        for iss in new_fe.get("issues", []):
            rf = revision["overrides"]["findings"].get(iss["id"])
            if rf:
                iss["afterObjection"] = rf
        if revision["overrides"]["findings"]:
            k0, v0 = next(iter(revision["overrides"]["findings"].items()))
            new_fe.setdefault("judge", {})["afterObjection"] = {"issueId": k0, "finding": v0, "version": ver}
        doc["output"] = new_fe; doc["status"]["rerunAt"] = _now(); _save(case_id, doc)
        p.update(state="applied", replies=replies, appliedAt=_now(), jobId=job["jobId"], version=ver); p.pop("progress", None); _psave(p)
        _emit(job, "done", {"proposalId": pid, "replies": replies, "rerun": steps, "version": ver})
    except Exception as e:
        import traceback; traceback.print_exc()
        p.update(state="failed", error=str(e)[:300]); _psave(p)
        _emit(job, "fatal", {"code": "PROPOSAL_FAILED", "message": str(e)[:300]})


def _run_sync(job: dict):
    try:
        rep = sync_laws.run(ingest=True)
        _emit(job, "done", rep.get("summary", {}))
    except Exception as e:
        _emit(job, "fatal", {"code": "SYNC_FAILED", "message": str(e)[:300]})


def _worker():
    while True:
        job = _q.get()
        job["state"] = "running"
        with _lock:  # 同時只跑一個 job（1 RPS）
            {"analyze": _run_analyze, "objection": _run_objection, "sync": _run_sync, "proposal": _run_proposal}[job["kind"]](job)
        job["state"] = "done"


threading.Thread(target=_worker, daemon=True).start()


def _submit(kind: str, case_id: str | None, payload: dict | None = None) -> dict:
    for j in _jobs.values():  # 同案同類型進行中 → 回同一個
        if j["kind"] == kind and j["caseId"] == case_id and j["state"] in ("queued", "running"):
            return j
    job = {"jobId": f"an_{uuid.uuid4().hex[:12]}", "kind": kind, "caseId": case_id, "payload": payload or {}, "state": "queued",
           "events": [], "subscribers": [], "createdAt": _now()}
    _jobs[job["jobId"]] = job
    _q.put(job)
    return job


# ---------- endpoints ----------
class ObjectionIn(BaseModel):
    issueId: str
    reason: str
    cites: list[str] = []
    by: str = "承辦人"


@app.get("/api/analysis/health")
def health():
    return {"ok": True, "region": REGION, "queue": _q.qsize(), "jobs": len(_jobs), "ddb": USE_DDB}


@app.post("/api/cases/{case_id}/analyze", status_code=202)
def analyze(case_id: str, from_step: str = "s2"):
    """?from_step=s4 可從中間步驟續跑（前面步驟讀 runs/ 快取；除錯用）"""
    try:
        load_any(case_id)  # 先確認案件存在（本機或 DDB）
    except FileNotFoundError:
        raise HTTPException(404, {"code": "CASE_NOT_FOUND", "message": case_id, "retryable": False})
    job = _submit("analyze", case_id, {"from": from_step})
    return {"jobId": job["jobId"], "caseId": case_id, "eventsUrl": f"/api/jobs/{job['jobId']}/events", "state": job["state"]}


@app.post("/api/cases/{case_id}/reanalyze", status_code=202)
def reanalyze(case_id: str):
    for f in (RUNS / case_id).glob("s*.json") if (RUNS / case_id).exists() else []:
        f.unlink()
    _analyses.pop(case_id, None)
    return analyze(case_id)


@app.get("/api/cases/{case_id}/analysis")
def analysis(case_id: str):
    doc = _load(case_id)
    if not doc:
        raise HTTPException(404, {"code": "ANALYSIS_NOT_FOUND", "message": case_id, "retryable": False})
    return doc


@app.post("/api/cases/{case_id}/objection", status_code=202)
def post_objection(case_id: str, body: ObjectionIn):
    doc = _load(case_id)
    if not doc or doc["status"]["state"] != "done":
        raise HTTPException(409, {"code": "ANALYSIS_NOT_READY", "message": "先完成分析", "retryable": True})
    if not body.reason.strip():
        raise HTTPException(400, {"code": "VALIDATION", "message": "reason 必填", "retryable": False})
    job = _submit("objection", case_id, body.model_dump())
    return {"jobId": job["jobId"], "eventsUrl": f"/api/jobs/{job['jobId']}/events"}


class ChatIn(BaseModel):
    message: str
    tab: int | None = None
    readonly: bool = False
    history: list[dict] = []


@app.post("/api/cases/{case_id}/chat")
def post_chat(case_id: str, body: ChatIn):
    """助手：問答（唯讀）或修改提案（不執行）。同步回；工具迴圈 ≤ 5 輪。"""
    if not body.message.strip():
        raise HTTPException(400, {"code": "VALIDATION", "message": "message 必填", "retryable": False})
    doc = _load(case_id)
    state = (doc or {}).get("output") or {}
    if not _lock.acquire(timeout=3):  # 與分析 job 共用 1 RPS；分析／重跑進行中不排隊卡住，直接告知
        return {"kind": "refuse", "text": "本案分析或修改正在進行中，請稍候再問。", "sources": [], "cite_offer": None, "proposal": None, "tool_calls": [], "intent": assistant.classify_intent(body.message), "usage": {"input": 0, "output": 0, "ms": 0}, "busy": True}
    try:
        res = assistant.chat(case_id, body.message, state=state, tab=body.tab, history=body.history, readonly=body.readonly)
    finally:
        _lock.release()
    if res.get("proposal"):
        pid = f"pp_{uuid.uuid4().hex[:8]}"
        p = {"id": pid, "caseId": case_id, "message": body.message, "createdAt": _now(), **res["proposal"]}
        _psave(p); res["proposal"] = p
    return res


@app.get("/api/cases/{case_id}/proposals/{pid}")
def get_proposal(case_id: str, pid: str):
    p = _pload(case_id, pid)
    if not p:
        raise HTTPException(404, {"code": "PROPOSAL_NOT_FOUND", "message": pid, "retryable": False})
    return p


@app.post("/api/cases/{case_id}/proposals/{pid}/preview")
def preview_proposal(case_id: str, pid: str):
    """提案卡的「修改後」預覽：只改寫受影響段落（≤3 段、各 1 次小呼叫），不落地。"""
    p = _pload(case_id, pid)
    if not p:
        raise HTTPException(404, {"code": "PROPOSAL_NOT_FOUND", "message": pid, "retryable": False})
    if p.get("previews") is not None:
        return {"id": pid, "previews": p["previews"]}
    doc = _load(case_id)
    if not _lock.acquire(timeout=3):
        return {"id": pid, "previews": None, "busy": True}
    try:
        pv = assistant.preview(case_id, (doc or {}).get("output") or {}, p["items"])
    finally:
        _lock.release()
    p["previews"] = pv; _psave(p)
    return {"id": pid, "previews": pv}


@app.post("/api/cases/{case_id}/proposals/{pid}/confirm", status_code=202)
def confirm_proposal(case_id: str, pid: str):
    p = _pload(case_id, pid)
    if not p:
        raise HTTPException(404, {"code": "PROPOSAL_NOT_FOUND", "message": pid, "retryable": False})
    if p["state"] != "pending":
        raise HTTPException(409, {"code": "PROPOSAL_NOT_PENDING", "message": p["state"], "retryable": False})
    doc = _load(case_id)
    if not doc or doc["status"]["state"] != "done":
        raise HTTPException(409, {"code": "ANALYSIS_NOT_READY", "message": "先完成分析", "retryable": True})
    p["state"] = "queued"; _psave(p)
    job = _submit("proposal", case_id, {"pid": pid})
    return {"jobId": job["jobId"], "proposalId": pid, "eventsUrl": f"/api/jobs/{job['jobId']}/events"}


@app.post("/api/cases/{case_id}/proposals/{pid}/cancel")
def cancel_proposal(case_id: str, pid: str):
    p = _pload(case_id, pid)
    if not p:
        raise HTTPException(404, {"code": "PROPOSAL_NOT_FOUND", "message": pid, "retryable": False})
    if p["state"] not in ("pending",):
        raise HTTPException(409, {"code": "PROPOSAL_NOT_PENDING", "message": p["state"], "retryable": False})
    p.update(state="cancelled", cancelledAt=_now()); _psave(p)
    return {"id": pid, "state": "cancelled"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": job_id, "retryable": False})
    return {k: job[k] for k in ("jobId", "kind", "caseId", "state", "createdAt")} | {"events": job["events"]}


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": job_id, "retryable": False})

    def gen():
        sub: queue.Queue = queue.Queue()
        job["subscribers"].append(sub)
        try:
            for e in list(job["events"]):  # 先回放
                yield f"id: {e['seq']}\nevent: {e['event']}\ndata: {json.dumps(e['data'], ensure_ascii=False)}\n\n"
                if e["event"] in ("done", "fatal"):
                    return
            while True:
                try:
                    e = sub.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"; continue
                yield f"id: {e['seq']}\nevent: {e['event']}\ndata: {json.dumps(e['data'], ensure_ascii=False)}\n\n"
                if e["event"] in ("done", "fatal"):
                    return
        finally:
            job["subscribers"].remove(sub)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/lawlib")
def get_lawlib():
    lib = lawlib.build()
    return {"laws": lib["laws"], "rulings": lib["letters"], "judgments": lib["rulings"], "sync": lib.get("sync")}


@app.post("/api/lawlib/sync", status_code=202)
def post_sync():
    job = _submit("sync", None)
    return {"jobId": job["jobId"], "eventsUrl": f"/api/jobs/{job['jobId']}/events"}
