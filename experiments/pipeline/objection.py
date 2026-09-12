"""異議重論證：承辦人對某爭點提出理由（可勾卷證）→ 1 次呼叫重新引證 → 採納／部分採納／無法採納；
採納或部分採納 → 1 次串流重產草稿。有上限、可追溯，不是 agent loop。"""
import json
from pydantic import BaseModel, Field

from . import lawdb
from .common import call_json, prompt, stream_text
from .ingest import Doc, prompt_block
from .schemas import Quote

SYS = prompt("system")


class ObjectionResult(BaseModel):
    """對承辦人異議的重新論證結果"""
    result: str = Field(description="採納／部分採納／無法採納")
    revised_finding: str | None = Field(description="採納時該爭點的新認定（採訴願人／採機關／待議）；否則 null")
    reply: str = Field(description="給承辦人的回覆，3–5 句，說明依據卷證為何採納或不採納")
    evidence: list[Quote] = Field(description="回覆所依據的卷證原文片段 ≥ 1 則")
    draft_changes: list[str] = Field(description="若採納或部分採納，草稿需調整的段落與方向，每項一句；無法採納則空")


def run(case: str, docs: list[Doc], issues: dict, judge: dict, objection: dict, draft: str, verified: list, sims_notes: dict, progress=None, regen: bool = True) -> dict:
    """regen=False：只重引證不重產草稿（提案流程會在所有 item 判完後統一局部重跑）。"""
    emit = progress or (lambda *a: None)
    issue = next((i for i in issues["issues"] if i["id"] == objection["issueId"]), None)
    if not issue:
        raise ValueError(f"ISSUE_NOT_FOUND: {objection['issueId']}")
    cited = [d for d in docs if d.fileId in set(objection.get("cites") or [])]
    emit("objection", "running", None)
    res = call_json("s7_objection", ObjectionResult, case=case, system=SYS + "\n\n" + prompt("s7_objection"),
                    user="本案卷宗：\n" + prompt_block(docs, 6000) +
                         "\n\n爭點：\n" + json.dumps(issue, ensure_ascii=False) +
                         "\n\n原 AI 判定：\n" + json.dumps(judge, ensure_ascii=False) +
                         "\n\n承辦人異議理由：\n" + objection["reason"] +
                         ("\n\n承辦人指定引用的卷證：" + "、".join(d.name for d in cited) if cited else ""),
                    images=[p for d in cited for p in d.images][:10]).model_dump()
    out = {**objection, **res, "issueId": issue["id"], "issueTitle": issue["title"], "originalFinding": issue["finding"]}
    emit("objection", "done", out)
    if regen and res["result"] in ("採納", "部分採納"):
        emit("s6", "running", None)
        new_issues = json.loads(json.dumps(issues))
        for i in new_issues["issues"]:
            if i["id"] == issue["id"] and res["revised_finding"]:
                i["finding"], i["reason"] = res["revised_finding"], f"異議後：{res['reply'][:80]}"
        user = ("本案卷宗：\n" + prompt_block(docs, 6000) + "\n\n本案爭點（異議後）：\n" + json.dumps(new_issues, ensure_ascii=False) +
                "\n\n推薦法條、函釋、判解（含原文）：\n" + json.dumps(verified, ensure_ascii=False) +
                "\n\n承辦人異議與 AI 回覆：\n" + json.dumps(out, ensure_ascii=False) +
                "\n\n前一版草稿：\n" + draft + "\n\n請依異議結果重新撰擬決定書草稿；未受異議影響的段落盡量維持原文。")
        buf = []
        for ch in stream_text("s6_draft_v2", case=case, system=SYS + "\n\n" + prompt("s6_draft"), user=user):
            buf.append(ch)
        out["newDraft"], out["newIssues"] = "".join(buf), new_issues
        out["newDraftCitations"] = lawdb.check_citations(lawdb.load(), out["newDraft"], source="草稿v2")
        emit("s6", "done", {"draft": out["newDraft"]})
    return out
