"""助手單元測試：意圖規則、影響範圍、法規查核、期間試算、工具讀取（零 LLM）。"""
import pytest

from pipeline import assistant as A

QUESTIONS = [
    "行政罰法第 18 條第 1 項的全文是什麼？", "送達日在哪份文件？", "期間有沒有逾期？", "本案爭點有哪些", "爭點 1 的卷證在哪？",
    "有沒有撤銷的案例？", "相似案例的結論分布？", "答辯書引了哪些法條？", "裁罰準則第 2 條是什麼", "本案判定與風險？",
    "撤銷的案例有幾件？",          # 含「撤銷」但是問句 → 不得判成 edit
]
EDITS = [
    "爭點 1 改採訴願人，影片看不出離手", "加引行政罰法第 18 條第 1 項", "送達日改 114-09-16", "應依 77(2) 逾期不受理",
    "結論改為原處分撤銷", "理由二精簡一點", "從舉證責任分配的角度重寫理由", "依新補件重新審查爭點 1", "移除裁罰準則第 2 條的引用", "改好一點",
]


@pytest.mark.parametrize("q", QUESTIONS)
def test_questions_are_questions(q):
    assert A.classify_intent(q) == "question"


@pytest.mark.parametrize("q", EDITS)
def test_edits_are_edits(q):
    assert A.classify_intent(q) == "edit"


def test_question_toolset_has_no_propose():
    names = [t["toolSpec"]["name"] for t in A._tool_config("question")["tools"]]
    assert "propose_revision" not in names and "ask_clarification" in names and "lookup_article" in names
    names = [t["toolSpec"]["name"] for t in A._tool_config("edit")["tools"]]
    assert "propose_revision" in names


@pytest.mark.parametrize("items,scope", [
    ([{"type": "issue"}], [2, 3, 4, 5]),
    ([{"type": "law"}], [3, 5]),
    ([{"type": "text"}], [5]),
    ([{"type": "frame"}, {"type": "text"}], [5]),
    ([{"type": "served"}], [0, 1, 2, 3, 4, 5]),
    ([{"type": "issue"}, {"type": "law"}], [2, 3, 4, 5]),
    ([{"type": "verdict"}], [4, 5]),
])
def test_scope(items, scope):
    assert A.compute_scope(items) == scope


def test_check_period():
    p = A.check_period("114-09-16", "114-09-22")
    assert p["deadline"] == "114-10-16" and p["inTime"] is True and p["daysLeft"] == 24
    assert A.check_period("112-02-07", "114-09-25")["inTime"] is False
    assert A.check_period(None, "114-09-22")["deadline"] is None


def test_verify_law_items(state):
    out = A.enrich_items("case02", [
        {"type": "law", "n": "行政罰法", "art": "18", "p": "1"},
        {"type": "law", "n": "違反廢棄物清理法罰鍰額度裁罰準則", "art": "9"},
        {"type": "law", "n": "不存在的法", "art": "1"},
        {"type": "law", "n": "行政罰法", "art": "第18條", "p": "1", "k": "裁處罰鍰應審酌（模型塞的文字）"},
    ], state)
    assert out[0]["ok"] and out[0]["key"] == "行政罰法 第 18 條第 1 項" and out[0]["amended"] == "111-06-15" and out[0]["dup"] is True
    assert out[1]["ok"] is False and "僅 6 條" in out[1]["msg"]
    assert out[2]["ok"] is False and "查無" in out[2]["msg"]
    assert out[3]["key"] == "行政罰法 第 18 條第 1 項"   # 非數字的項款被丟掉、條號只留數字


def test_enrich_issue_served_verdict(state):
    out = A.enrich_items("case02", [{"type": "issue", "id": "I1", "to": "appellant"}, {"type": "served", "v": "114-09-16"}, {"type": "verdict", "to": "撤銷"}], state)
    assert out[0]["n"] == 1 and out[0]["from"] == "採機關" and out[0]["title"]
    assert out[1]["from"] == "114-09-18" and out[1]["deadline"] == "114-10-16" and out[1]["inTime"] is True
    assert out[2]["from"] == "訴願駁回"


def test_tools_read_only(state):
    ctx = A.Ctx("case02", state)
    r = A.run_tool(ctx, "lookup_article", {"law": "行政罰法", "article": "18"})
    assert r["status"] == "ok" and "裁處罰鍰" in r["text"] and r["version"] == "111-06-15"
    assert A.run_tool(ctx, "lookup_article", {"law": "行政罰法", "article": "999"})["status"] == "no_article"
    assert A.run_tool(ctx, "lookup_article", {"law": "火星法", "article": "1"})["status"] == "unknown_law"
    assert A.run_tool(ctx, "get_case_state", {"section": "judge"})["judge"]["verdict"] == "訴願駁回"
    assert A.run_tool(ctx, "get_case_state", {"section": "draft"})["draft"]
    assert A.run_tool(ctx, "check_period", {"served": "114-09-16"})["deadline"] == "114-10-16"
    d = A.run_tool(ctx, "get_case_doc", {"name": "訴願書"})
    assert d.get("fileId") and d["doc_type"] == "訴願書" and d["text"]
    assert A.run_tool(ctx, "get_case_doc", {"name": "不存在"})["status"] == "not_found"
    assert "error" in A.run_tool(ctx, "nope", {})


def test_build_revision_maps_items():
    import api
    items = [{"type": "issue", "id": "I1", "n": 1, "title": "T", "to": "appellant", "why": "w"},
             {"type": "law", "ok": True, "key": "行政罰法 第 18 條第 1 項", "art": "18", "p": "1"},
             {"type": "law", "ok": False, "key": "裁罰準則 第 9 條", "art": "9", "msg": "僅 6 條"},
             {"type": "law-rm", "key": "訴願法 第 58 條"},
             {"type": "served", "v": "114-09-16", "deadline": "114-10-16", "inTime": True},
             {"type": "proc", "v": "77-2"}, {"type": "verdict", "to": "撤銷"}, {"type": "text", "para": "理由二", "how": "精簡"}]
    replies = [{"result": "採納", "revised_finding": "採訴願人", "reply": "r"}] + [{"result": "採納", "reply": ""}] * 7
    rev = api._build_revision(items, replies, "舊草稿")
    ov = rev["overrides"]
    assert ov["findings"] == {"I1": "採訴願人"} and ov["add_laws"] == [{"name": "行政罰法", "article": "18", "paragraph": "1"}]
    assert ov["rm_laws"] == ["訴願法 第 58 條"] and ov["served"] == "114-09-16" and ov["in_time"] is False and ov["verdict"] == "撤銷" and ov["prev_draft"] == "舊草稿"
    assert rev["instructions"]["s5"] and any("理由二" in s for s in rev["instructions"]["s6"]) and not any("第 9 條" in s for s in rev["instructions"]["s4"])


def test_text_item_para_normalized_to_label(state):
    from pipeline.assistant import label_paras
    labeled = label_paras(list(state["drafts"].values())[-1]["paras"])
    lab, para = next((l, p) for l, p in labeled if l.startswith("理由"))
    out = A.enrich_items("case02", [{"type": "text", "para": para["text"], "how": "精簡"}, {"type": "text", "para": lab, "how": "x"}, {"type": "text", "para": "把理由三改短", "how": "x"}], state)
    assert out[0]["para"] == lab and out[1]["para"] == lab and out[2]["para"] == "理由三"
