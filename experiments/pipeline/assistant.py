"""案件助手：問答（唯讀、有據才答）＋修改提案（propose_revision 為終止工具，只回結構，不執行）。

    res = chat(case_id, "爭點 1 改採訴願人，影片看不出離手", tab=1)
    res["kind"] in ("answer", "proposal", "clarify", "refuse")

設計（契約：plans/助手API-契約與實作清單.md）：
- classify_intent() 先用規則判「問／改」：問句的工具清單不含 propose_revision，模型無法提案 → 可測、不靠 prompt
- 工具全唯讀；propose_revision / ask_clarification 是終止工具
- 提案 items 與前端 parseIntent 同形，伺服器補查核（法規存在／條號／期間試算）與影響範圍 scope
"""
import json, re, time
from datetime import date, timedelta
from pathlib import Path

from . import lawdb, lawlib
from .common import MODEL_ID, RUNS, _converse, call_text, prompt

# ---------- 意圖（規則層） ----------
Q_RE = re.compile(r"[?？]|有沒有|嗎$|嗎[。？]?$|在哪|哪份|哪個|哪一|是什麼|多少|幾天|幾件|為何|為什麼|怎麼算|查一下|請問|告訴我")
EDIT_RE = re.compile(r"改|修改|加引|引用|援引|加入|新增|移除|刪除|重寫|改寫|潤飾|精簡|縮短|語氣|不受理|進入實體|撤銷|駁回|重新審查|重新認定|納入|更正|換成|調整")


def classify_intent(msg: str) -> str:
    """'question' | 'edit'。問句特徵優先；沒有問句特徵且含修改動詞 → edit。"""
    m = msg.strip()
    if Q_RE.search(m):
        return "question"
    return "edit" if EDIT_RE.search(m) else "question"


# ---------- 提案 item 查核與影響範圍 ----------
STEP_OF = {"served": 0, "proc": 1, "issue": 2, "reissue": 2, "law": 3, "law-rm": 3, "verdict": 4, "text": 5, "frame": 5}
STEP_TAB = [0, 0, 1, 2, 3, 4]


def compute_scope(items: list[dict]) -> list[int]:
    steps = [STEP_OF.get(i.get("type"), 5) for i in items] or [5]
    lo = min(steps)
    scope = list(range(lo, 6))
    if all(i.get("type") in ("law", "law-rm") for i in items):
        scope = [s for s in scope if s != 4]
    if all(i.get("type") in ("text", "frame") for i in items):
        scope = [5]
    return scope


def _roc(s):
    m = s and re.match(r"(\d{2,3})-(\d{1,2})-(\d{1,2})", s)
    return date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))) if m else None


def check_period(served: str | None, recv: str | None) -> dict:
    s, r = _roc(served), _roc(recv)
    if not s:
        return {"served": served, "recv": recv, "deadline": None, "inTime": None, "note": "缺送達日，無法起算"}
    dl = s + timedelta(days=30)
    dls = f"{dl.year-1911}-{dl.month:02d}-{dl.day:02d}"
    return {"served": served, "recv": recv, "deadline": dls, "inTime": (r <= dl) if r else None,
            "daysLeft": (dl - r).days if r else None, "note": f"送達 {served}，次日起 30 日至 {dls}，收文 {recv or '—'}"}


def verify_law_item(db: dict, lib: dict, it: dict) -> dict:
    """補 ok / msg / amended / key / dup。"""
    name, art = (it.get("n") or "").strip(), str(it.get("art") or "").strip()
    hit = lawdb.lookup(db, name, art) if name else {"status": "unknown_law"}
    L = next((x for x in lib.get("laws", []) if x["n"] == hit.get("law") or name.endswith(x["n"]) or x["n"].endswith(name)), None) if name else None
    key = f"{hit.get('law') or name} 第 {art} 條" + (f"第 {it['p']} 項" if it.get("p") else "") + (f"第 {it['k']} 款" if it.get("k") else "")
    out = {**it, "key": key, "amended": (L or {}).get("official") or (L or {}).get("date")}
    if hit["status"] == "unknown_law":
        out.update(ok=False, msg="法規庫查無此法規，將不引用")
    elif hit["status"] == "no_article":
        n_art = len(db[hit["law"]]["articles"])
        out.update(ok=False, msg=f"{hit['law']} 僅 {n_art} 條，第 {art} 條不存在")
    else:
        out.update(ok=True, msg=f"法規庫有・{out['amended'] or hit.get('amended', '')} 版", text=hit["text"][:200])
    return out


def enrich_items(case_id: str, items: list[dict], state: dict | None) -> list[dict]:
    db, lib = lawdb.load(), lawlib.build()
    issues = (state or {}).get("issues") or []
    period = (state or {}).get("period") or {}
    out = []
    for it in items:
        t = it.get("type")
        if t in ("law", "law-rm"):
            it = {**it, "art": re.sub(r"\D", "", str(it.get("art") or "")), **{f: (str(it.get(f)) if re.fullmatch(r"\d+", str(it.get(f) or "")) else None) for f in ("p", "k")}}
            v = verify_law_item(db, lib, it)
            v["dup"] = any(l["n"].startswith(f"{v.get('key','').split(' 第 ')[0]} 第 {it.get('art')} 條") for l in (state or {}).get("laws") or [])
            it = v
        elif t in ("issue", "reissue"):
            is_ = next((x for x in issues if x["id"] == it.get("id")), None)
            if is_:
                it = {**it, "n": issues.index(is_) + 1, "title": is_["title"], "from": is_.get("afterObjection") or is_.get("finding")}
        elif t == "served":
            p = check_period(it.get("v"), period.get("recv"))
            it = {**it, "from": period.get("served"), "deadline": p["deadline"], "inTime": p["inTime"], "daysLeft": p.get("daysLeft")}
        elif t == "verdict":
            it = {**it, "from": ((state or {}).get("judge") or {}).get("verdict")}
        out.append(it)
    return out


# ---------- 工具 ----------
TOOLS = [
    {"name": "lookup_article", "description": "查法規條文原文與版本日期。查無時回 status。", "schema": {"type": "object", "properties": {"law": {"type": "string"}, "article": {"type": "string"}, "paragraph": {"type": "string"}}, "required": ["law", "article"]}},
    {"name": "search_laws", "description": "語意檢索法規條文（KB）。", "schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "search_rulings", "description": "語意檢索函釋、判解（KB）。", "schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "search_decisions", "description": "語意檢索歷史訴願決定書（KB，永遠排除本案自身）。", "schema": {"type": "object", "properties": {"query": {"type": "string"}, "law": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_case_doc", "description": "讀本案某份卷證的文字（可指定頁）。", "schema": {"type": "object", "properties": {"name": {"type": "string"}, "page": {"type": "integer"}}, "required": ["name"]}},
    {"name": "get_case_state", "description": "讀本案目前分析結果的一節。", "schema": {"type": "object", "properties": {"section": {"type": "string", "enum": ["fields", "period", "checks", "issues", "laws", "citations", "sims", "judge", "draft", "files"]}}, "required": ["section"]}},
    {"name": "check_period", "description": "以送達日、收文日試算 30 日訴願期間。", "schema": {"type": "object", "properties": {"served": {"type": "string"}, "recv": {"type": "string"}}, "required": ["served"]}},
    {"name": "ask_clarification", "description": "指令模糊時反問承辦人（終止）。", "schema": {"type": "object", "properties": {"question": {"type": "string"}, "examples": {"type": "array", "items": {"type": "string"}}}, "required": ["question"]}},
    {"name": "propose_revision", "description": "把承辦人的修改要求整理成結構化提案（終止；系統會請承辦人確認後才執行）。", "schema": {"type": "object", "properties": {
        "summary": {"type": "string", "description": "一句話說明這次要改什麼"},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["issue", "reissue", "law", "law-rm", "served", "proc", "verdict", "text", "frame"]},
            "id": {"type": "string", "description": "issue/reissue：爭點 id，如 I1"},
            "to": {"type": "string", "description": "issue：appellant|agency|drop；verdict：撤銷|駁回|不受理"},
            "why": {"type": "string"},
            "n": {"type": "string", "description": "law：法規名稱"}, "art": {"type": "string"}, "p": {"type": "string"}, "k": {"type": "string"},
            "v": {"type": "string", "description": "served：114-09-16；proc：merit|77-2"},
            "para": {"type": "string", "description": "text：理由二／主文"}, "how": {"type": "string"},
            "angle": {"type": "string", "description": "frame：論述角度"},
            "docs": {"type": "array", "items": {"type": "string"}, "description": "reissue：新文件 fileId"}}, "required": ["type"]}}}, "required": ["summary", "items"]}},
]
TERMINAL = {"propose_revision", "ask_clarification"}


def _tool_config(intent: str):
    names = [t["name"] for t in TOOLS if not (intent == "question" and t["name"] == "propose_revision")]
    return {"tools": [{"toolSpec": {"name": t["name"], "description": t["description"], "inputSchema": {"json": t["schema"]}}} for t in TOOLS if t["name"] in names]}


class Ctx:
    """一次對話用的案件資料（延遲載入）。"""
    def __init__(self, case_id: str, state: dict | None):
        self.case_id, self.state = case_id, state or {}
        self._docs = self._db = self._lib = None

    @property
    def db(self):
        if self._db is None:
            self._db = lawdb.load()
        return self._db

    @property
    def lib(self):
        if self._lib is None:
            self._lib = lawlib.build()
        return self._lib

    @property
    def docs(self):
        if self._docs is None:
            from .ingest import load_any
            try:
                self._docs = load_any(self.case_id)
            except Exception:
                self._docs = []
        return self._docs


def run_tool(ctx: Ctx, name: str, args: dict) -> dict:
    if name == "lookup_article":
        hit = lawdb.lookup(ctx.db, args.get("law", ""), str(args.get("article", "")))
        L = next((x for x in ctx.lib["laws"] if x["n"] == hit.get("law")), None) if hit.get("law") else None
        return {**hit, "text": hit.get("text", "")[:1200], "version": (L or {}).get("official") or (L or {}).get("date") or hit.get("amended"), "effective": (L or {}).get("effective")}
    if name in ("search_laws", "search_rulings", "search_decisions"):
        from .retrieval import retrieve
        kinds = {"search_laws": ["laws"], "search_rulings": ["rulings", "letters"], "search_decisions": ["decisions"]}[name]
        excl = {Path(f[0]).stem for f in ctx.state.get("files", [])} | {ctx.case_id}
        hits = retrieve(args["query"], kinds=kinds, law=args.get("law"), k=5, exclude_titles=excl if name == "search_decisions" else None)
        return {"hits": [{"title": h["title"], "kind": h["kind"], "text": h["text"][:500], "score": h["score"]} for h in hits]}
    if name == "get_case_doc":
        q = args.get("name", "")
        d = next((x for x in ctx.docs if q and (q in x.name or q in x.originalName or x.fileId == q)), None)
        if not d:
            return {"status": "not_found", "files": [x.name for x in ctx.docs][:30]}
        pg = args.get("page")
        txt = (d.textPerPage[pg - 1] if pg and 0 < pg <= len(d.textPerPage) else d.text) or "（無文字層：掃描件／照片／影片）"
        return {"fileId": d.fileId, "name": d.name, "doc_type": d.doc_type, "source": d.source, "pages": len(d.textPerPage) or 1, "text": txt[:3000]}
    if name == "get_case_state":
        sec = args.get("section")
        if sec == "draft":
            dr = ctx.state.get("drafts") or {}
            latest = list(dr.values())[-1] if dr else None
            return {"draft": [p["text"] for p in (latest or {}).get("paras", [])][:60]} if latest else {"status": "no_draft"}
        v = ctx.state.get(sec)
        return {sec: v} if v is not None else {"status": "not_available"}
    if name == "check_period":
        return check_period(args.get("served"), args.get("recv") or (ctx.state.get("period") or {}).get("recv"))
    return {"error": f"unknown tool {name}"}


# ---------- 主流程 ----------
def _sources_from(calls: list[dict]) -> list[dict]:
    out = []
    for c in calls:
        r = c.get("result") or {}
        if c["name"] == "lookup_article" and r.get("status") == "ok":
            out.append({"type": "law", "title": f"{r['law']} 第 {c['args'].get('article')} 條", "version": r.get("version")})
        elif c["name"] == "get_case_doc" and r.get("fileId"):
            out.append({"type": "doc", "title": r["name"], "fileId": r["fileId"], "page": c["args"].get("page")})
        elif c["name"].startswith("search_"):
            out += [{"type": "decision" if h["kind"] == "decisions" else "law", "title": h["title"]} for h in r.get("hits", [])[:3]]
        elif c["name"] == "get_case_state":
            out.append({"type": "state", "title": {"fields": "案件擷取", "period": "訴願期間", "checks": "程序審查", "issues": "爭點", "laws": "法規推薦", "citations": "引用查核", "sims": "相似案例", "judge": "AI 判定", "draft": "決定書草稿", "files": "卷宗"}.get(c["args"].get("section"), "分析結果")})
    seen, uniq = set(), []
    for s in out:
        k = (s["type"], s["title"])
        if k not in seen:
            seen.add(k); uniq.append(s)
    return uniq


def _cite_offer(calls: list[dict]) -> dict | None:
    for c in reversed(calls):
        if c["name"] == "lookup_article" and (c.get("result") or {}).get("status") == "ok":
            return {"law": c["result"]["law"], "article": str(c["args"].get("article")), "para": c["args"].get("paragraph")}
    return None


def chat(case_id: str, message: str, *, state: dict | None = None, tab: int | None = None, history: list[dict] | None = None,
         readonly: bool = False, max_rounds: int = 5, converse=None) -> dict:
    """同步；converse 可注入（測試用假 Bedrock）。"""
    t0 = time.monotonic()
    intent = classify_intent(message)
    if readonly and intent == "edit":
        return {"kind": "refuse", "text": "本案已送審或已結案，不可修改；請「另存為新草稿」後再提出。", "sources": [], "cite_offer": None, "proposal": None, "tool_calls": [], "intent": intent, "usage": {"input": 0, "output": 0, "ms": 0}}
    ctx = Ctx(case_id, state)
    converse = converse or _converse
    sys_txt = prompt("system") + "\n\n" + prompt("assistant")
    brief = {"issues": [[i["id"], i["title"], i.get("afterObjection") or i.get("finding")] for i in (ctx.state.get("issues") or [])],
             "judge": (ctx.state.get("judge") or {}).get("verdict"), "period": {k: (ctx.state.get("period") or {}).get(k) for k in ("served", "recv", "deadline", "inTime")},
             "laws": [l["n"] for l in (ctx.state.get("laws") or [])][:20], "files": [[f[0], f[2], f[3], f[1]] for f in (ctx.state.get("files") or [])][:40]}   # [檔名, 類型, 來源, fileId]；reissue 的 docs 填 fileId
    tab_name = ["案件擷取與分類", "爭點", "法規推薦", "相似案例", "決定書草稿"][tab] if tab is not None and 0 <= tab <= 4 else "未知"
    msgs = []
    for h in (history or [])[-6:]:
        msgs.append({"role": "user" if h.get("role") == "user" else "assistant", "content": [{"text": h.get("text", "")[:1500]}]})
    msgs.append({"role": "user", "content": [{"text": f"【本案摘要】{json.dumps(brief, ensure_ascii=False)}\n【承辦人目前分頁】{tab_name}\n【意圖判定】{'問' if intent == 'question' else '改'}\n\n承辦人：{message}"}]})
    tool_cfg = _tool_config(intent)
    calls, usage = [], {"input": 0, "output": 0}
    final_text, proposal, clarify = "", None, None
    for _ in range(max_rounds):
        r = converse(modelId=MODEL_ID, system=[{"text": sys_txt}], messages=msgs, inferenceConfig={"maxTokens": 2048, "temperature": 0.1}, toolConfig=tool_cfg)
        u = r.get("usage", {}); usage["input"] += u.get("inputTokens", 0); usage["output"] += u.get("outputTokens", 0)
        content = r["output"]["message"]["content"]
        msgs.append({"role": "assistant", "content": content})
        uses = [c["toolUse"] for c in content if "toolUse" in c]
        texts = [c["text"] for c in content if "text" in c]
        if not uses:
            final_text = "\n".join(texts).strip(); break
        results = []
        stop = False
        for tu in uses:
            name, args = tu["name"], tu.get("input") or {}
            if name == "propose_revision" and intent != "edit":  # 契約：問句永遠不產生提案（工具清單本來就沒給，這是第二道防線）
                calls.append({"name": name, "args": args, "ok": False})
                results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": {"error": "此句為問句，不可提案；請直接用文字回答"}}], "status": "error"}})
            elif name == "propose_revision":
                proposal = {"summary": args.get("summary", ""), "items": args.get("items") or []}; calls.append({"name": name, "args": args, "ok": True}); stop = True
            elif name == "ask_clarification":
                clarify = args; calls.append({"name": name, "args": args, "ok": True}); stop = True
            else:
                try:
                    res = run_tool(ctx, name, args); ok = True
                except Exception as e:
                    res, ok = {"error": str(e)[:200]}, False
                calls.append({"name": name, "args": args, "ok": ok, "result": res})
                results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": res}]}})
        if stop:
            break
        msgs.append({"role": "user", "content": results})
    ms = int((time.monotonic() - t0) * 1000)
    base = {"sources": _sources_from(calls), "tool_calls": [{k: v for k, v in c.items() if k != "result"} for c in calls], "intent": intent, "usage": {**usage, "ms": ms}}
    if proposal is not None:
        items = enrich_items(case_id, proposal["items"], ctx.state)
        if not items:
            return {"kind": "clarify", "text": "我看不出要改的具體對象。可以這樣說：「爭點 2 改採訴願人，因為…」「加引行政罰法第 18 條第 1 項」「送達日改 114-09-16」「理由二精簡一點」。", "cite_offer": None, "proposal": None, **base}
        scope = compute_scope(items)
        return {"kind": "proposal", "text": proposal["summary"], "cite_offer": None,
                "proposal": {"summary": proposal["summary"], "items": items, "scope": scope, "affected_tabs": sorted({STEP_TAB[s] for s in scope}), "state": "pending"}, **base}
    if clarify is not None:
        q = clarify.get("question", "").strip()
        ex = clarify.get("examples") or []
        return {"kind": "clarify", "text": q + ("\n例如：" + "／".join(f"「{e}」" for e in ex[:3]) if ex else ""), "cite_offer": None, "proposal": None, **base}
    return {"kind": "answer", "text": final_text or "（模型未回覆文字）", "cite_offer": _cite_offer(calls), "proposal": None, **base}


def load_state(case_id: str) -> dict | None:
    p = RUNS / case_id / "analysis.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get("output")
    return None


if __name__ == "__main__":
    import sys
    cid = sys.argv[1] if len(sys.argv) > 1 else "case02"
    q = " ".join(sys.argv[2:]) or "行政罰法第 18 條第 1 項全文"
    print(json.dumps(chat(cid, q, state=load_state(cid)), ensure_ascii=False, indent=1))


# ---------- 提案預覽：只改寫受影響段落（每段 1 次小呼叫），供提案卡畫「修改前 → 修改後」；不落地 ----------
CN_NUM = "一二三四五六七八九十"


def label_paras(paras: list[dict]) -> list[tuple[str, dict]]:
    """與前端 paraLabel 同規則：主文／事實N／理由N／前言。"""
    out, sect, n = [], "", 0
    for p in paras:
        if p.get("kind") == "h4":
            sect, n = p["text"].strip(), 0; continue
        n += 1
        lab = "主文" if sect == "主文" else f"事實{CN_NUM[n-1] if n <= 10 else n}" if sect == "事實" else f"理由{CN_NUM[n-1] if n <= 10 else n}" if sect == "理由" else sect or "前言"
        out.append((lab, p))
    return out


def preview(case_id: str, state: dict, items: list[dict], call=None) -> list[dict]:
    call = call or call_text
    drafts = state.get("drafts") or {}
    if not drafts:
        return []
    latest = list(drafts.values())[-1]
    labeled = label_paras(latest.get("paras") or [])
    targets = []
    for it in items:
        t = it.get("type")
        if t == "text":
            hit = next((x for x in labeled if x[0] == it.get("para")), None)
            if hit: targets.append((it, hit[0], hit[1]["text"], f"依承辦人指示改寫：{it.get('how')}"))
        elif t == "frame":
            hit = next((x for x in labeled if x[0].startswith("理由")), None)
            if hit: targets.append((it, hit[0], hit[1]["text"], f"改從「{it.get('angle')}」的角度論述"))
        elif t == "verdict":
            hit = next((x for x in labeled if x[0] == "主文"), None)
            if hit: targets.append((it, hit[0], hit[1]["text"], f"結論改為「{it.get('to')}」，主文句式須符合訴願決定書慣例"))
        elif t == "law" and it.get("ok"):
            hit = next((x for x in labeled if x[0].startswith("理由") and ("裁量" in x[1]["text"] or "審酌" in x[1]["text"])), None) or next((x for x in labeled if x[0].startswith("理由")), None)
            if hit: targets.append((it, hit[0], hit[1]["text"], f"補入引用 {it.get('key')}（{(it.get('text') or '')[:120]}），其餘內容維持"))
    out = []
    for it, lab, before, instr in targets[:3]:
        after = call("preview_para", system=prompt("system") + "\n\n你只改寫承辦人指定的這一段訴願決定書文字，輸出改寫後的段落本身，不加標題、不加說明、不加引號。",
                     user=f"段落（{lab}）：\n{before}\n\n指示：{instr}", case=None, max_tokens=1500).strip()
        out.append({"type": it.get("type"), "para": lab, "before": before, "after": after})
    return out
