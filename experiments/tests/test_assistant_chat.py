"""助手對話整合測試：假 Bedrock（腳本化回合），驗「問 → answer／改 → proposal／模糊 → clarify／唯讀 → refuse」與工具迴圈。"""
from pipeline import assistant as A
from tests.conftest import FakeBedrock, text, tool


def test_question_returns_answer_with_law_source(state):
    fb = FakeBedrock([tool("lookup_article", {"law": "行政罰法", "article": "18", "paragraph": "1"}), text("行政罰法第 18 條第 1 項：裁處罰鍰，應審酌…")])
    r = A.chat("case02", "行政罰法第 18 條第 1 項的全文是什麼？", state=state, tab=2, converse=fb)
    assert r["kind"] == "answer" and r["proposal"] is None
    assert r["sources"][0]["type"] == "law" and r["sources"][0]["version"] == "111-06-15"
    assert r["cite_offer"] == {"law": "行政罰法", "article": "18", "para": "1"}
    assert [c["name"] for c in r["tool_calls"]] == ["lookup_article"]
    # 第二回合收到 toolResult
    assert fb.calls[1]["messages"][-1]["role"] == "user" and "toolResult" in fb.calls[1]["messages"][-1]["content"][0]
    # 問句：工具清單不含 propose_revision
    assert all("propose_revision" not in [t["toolSpec"]["name"] for t in c["toolConfig"]["tools"]] for c in fb.calls)


def test_question_even_if_model_tries_to_propose_is_not_a_proposal(state):
    """模型在問句下若硬呼叫 propose_revision（工具清單裡沒有），伺服器仍照終止工具處理但 intent 是 question——
    契約保證：問句永遠不會產生 proposal。這裡驗 chat 的防線：只有 edit 才把提案交出去。"""
    fb = FakeBedrock([tool("propose_revision", {"summary": "x", "items": [{"type": "issue", "id": "I1", "to": "appellant"}]})])
    r = A.chat("case02", "撤銷的案例有幾件？", state=state, converse=fb)
    assert r["intent"] == "question" and r["kind"] == "answer" and r["proposal"] is None
    assert r["tool_calls"][0] == {"name": "propose_revision", "args": {"summary": "x", "items": [{"type": "issue", "id": "I1", "to": "appellant"}]}, "ok": False}


def test_edit_returns_proposal_with_verified_items_and_scope(state):
    fb = FakeBedrock([
        tool("lookup_article", {"law": "行政罰法", "article": "18"}),
        tool("propose_revision", {"summary": "爭點 1 改採訴願人並加引行政罰法 §18 I", "items": [
            {"type": "issue", "id": "I1", "to": "appellant", "why": "影片看不出離手"},
            {"type": "law", "n": "行政罰法", "art": "18", "p": "1"},
            {"type": "law", "n": "違反廢棄物清理法罰鍰額度裁罰準則", "art": "9"},
        ]}, tid="t2"),
    ])
    r = A.chat("case02", "爭點 1 改採訴願人，影片看不出離手；另外加引行政罰法第 18 條第 1 項和裁罰準則第 9 條", state=state, tab=1, converse=fb)
    assert r["kind"] == "proposal" and r["intent"] == "edit"
    p = r["proposal"]
    assert p["state"] == "pending" and p["scope"] == [2, 3, 4, 5] and p["affected_tabs"] == [1, 2, 3, 4]
    it = {x["type"] + ":" + str(x.get("id") or x.get("art")): x for x in p["items"]}
    assert it["issue:I1"]["n"] == 1 and it["issue:I1"]["from"] == "採機關" and it["issue:I1"]["title"]
    assert it["law:18"]["ok"] and it["law:18"]["key"] == "行政罰法 第 18 條第 1 項"
    assert it["law:9"]["ok"] is False and "僅 6 條" in it["law:9"]["msg"]
    assert r["sources"][0]["type"] == "law"


def test_edit_vague_returns_clarify(state):
    fb = FakeBedrock([tool("ask_clarification", {"question": "請問要改哪個部分？", "examples": ["爭點 1 改採訴願人", "理由二精簡一點"]})])
    r = A.chat("case02", "改好一點", state=state, converse=fb)
    assert r["kind"] == "clarify" and r["proposal"] is None and "請問要改哪個部分" in r["text"] and "理由二精簡一點" in r["text"]


def test_edit_empty_items_becomes_clarify(state):
    fb = FakeBedrock([tool("propose_revision", {"summary": "？", "items": []})])
    r = A.chat("case02", "改一下", state=state, converse=fb)
    assert r["kind"] == "clarify"


def test_readonly_refuses_edit_without_calling_model(state):
    fb = FakeBedrock([])
    r = A.chat("case02", "爭點 1 改採訴願人", state=state, readonly=True, converse=fb)
    assert r["kind"] == "refuse" and fb.calls == []
    r2 = A.chat("case02", "送達日在哪份文件？", state=state, readonly=True, converse=FakeBedrock([text("在送達證書")]))
    assert r2["kind"] == "answer"


def test_tool_loop_stops_at_max_rounds(state):
    fb = FakeBedrock([tool("get_case_state", {"section": "issues"}, tid=f"t{i}") for i in range(9)])
    r = A.chat("case02", "本案爭點有哪些", state=state, converse=fb, max_rounds=3)
    assert len(fb.calls) == 3 and r["kind"] == "answer"


def test_history_and_brief_go_into_prompt(state):
    fb = FakeBedrock([text("好")])
    A.chat("case02", "送達日在哪份文件？", state=state, tab=0, history=[{"role": "user", "text": "上一句"}, {"role": "assistant", "text": "上一答"}], converse=fb)
    msgs = fb.calls[0]["messages"]
    assert msgs[0]["content"][0]["text"] == "上一句" and msgs[1]["role"] == "assistant"
    last = msgs[-1]["content"][0]["text"]
    assert "【本案摘要】" in last and "案件擷取與分類" in last and "【意圖判定】問" in last
