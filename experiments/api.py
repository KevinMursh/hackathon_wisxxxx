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


def _run_proposal(job: dict):
    """confirm：爭點類 item 各跑一次 objection；其餘 item 併成一則 objection 的 reason（掛在第一個或指定爭點）。"""
    case_id, pid = job["caseId"], job["payload"]["pid"]
    p = _pload(case_id, pid); doc = _load(case_id)
    p["state"] = "running"; _psave(p)
    try:
        issue_items = [it for it in p["items"] if it.get("type") in ("issue", "reissue") and it.get("id")]
        others = [it for it in p["items"] if it not in issue_items]
        reqs = [{"issueId": it["id"], "reason": _item_reason(it), "cites": it.get("docs") or [], "label": f"爭點 {it.get('n', '')}：{_item_reason(it)}"} for it in issue_items]
        if others:
            first = (issue_items[0]["id"] if issue_items else (doc["output"]["issues"][0]["id"] if doc["output"].get("issues") else "I1"))
            reqs.append({"issueId": first, "reason": "；".join(_item_reason(it) for it in others), "cites": [], "label": "；".join(_item_reason(it) for it in others)})
        replies = []
        for i, rq in enumerate(reqs):
            _emit(job, "step", {"step": "objection", "status": "running", "i": i + 1, "n": len(reqs), "label": rq["label"]})
            p["progress"] = {"i": i + 1, "n": len(reqs), "label": rq["label"]}; _psave(p)   # 前端輪詢 GET proposal 看進度（Node 的 GET /jobs 先攔走 an_ job）
            sub = {"jobId": job["jobId"], "caseId": case_id, "payload": {"issueId": rq["issueId"], "reason": rq["reason"], "cites": rq["cites"], "by": "承辦人", "proposalId": pid}, "events": job["events"], "subscribers": job["subscribers"]}
            _run_objection(sub, emit_done=False)
            doc = _load(case_id); ob = doc["objections"][-1]
            replies.append({"label": rq["label"], "result": ob.get("result"), "reply": ob.get("reply"), "evidence": ob.get("evidence") or [], "revised_finding": ob.get("revised_finding"), "issueId": ob.get("issueId")})
            _emit(job, "step", {"step": "objection", "status": "done", "i": i + 1, "n": len(reqs), "result": ob.get("result")})
        p.update(state="applied", replies=replies, appliedAt=_now(), jobId=job["jobId"]); _psave(p)
        _emit(job, "done", {"proposalId": pid, "replies": replies})
    except Exception as e:
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
    with _lock:  # 與分析 job 共用 1 RPS
        res = assistant.chat(case_id, body.message, state=state, tab=body.tab, history=body.history, readonly=body.readonly)
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
