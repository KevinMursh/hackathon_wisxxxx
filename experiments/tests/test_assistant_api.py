"""API 整合測試：FastAPI TestClient；chat 用假 Bedrock；confirm 的 objection.run 以假函式取代（不打模型、不碰 DDB）。"""
import json, os, time

import pytest


@pytest.fixture(scope="module")
def client(runs_dir):
    os.environ["ANALYSIS_RUNS"] = str(runs_dir)
    os.environ["ANALYSIS_DDB"] = "0"
    import importlib
    from pipeline import common
    importlib.reload(common)
    assert str(common.RUNS) == str(runs_dir)
    import api
    importlib.reload(api)
    from fastapi.testclient import TestClient
    return TestClient(api.app), api


def _fake_objection(case, docs, issues, judge, ob, draft, verified, sims_notes, progress=None, regen=True):
    """假的重引證：理由含「訴願人」就採納，否則無法採納；提案流程 regen=False 不重產草稿。"""
    issue = next(i for i in issues["issues"] if i["id"] == ob["issueId"])
    acc = "訴願人" in ob["reason"]
    return {**ob, "issueId": issue["id"], "issueTitle": issue["title"], "originalFinding": issue["finding"],
            "result": "採納" if acc else "無法採納", "revised_finding": "採訴願人（補強）" if acc else None,   # 故意非三值，驗正規化
            "reply": "假回覆：依卷證" + ("採納" if acc else "無法採納"), "evidence": [{"file": "x.pdf", "quote": "q"}], "draft_changes": []}


RERUN_CALLS = []


def _fake_run(case, start="s2", images=True, api=None, docs=None, progress=None, revision=None):
    """假的局部重跑：記錄 start／revision，回一份改過草稿的 fe（讀原快取再改）。"""
    import json as _j
    from pipeline.common import RUNS
    RERUN_CALLS.append({"start": start, "revision": revision})
    fe = _j.loads((RUNS / case / "analysis.json").read_text(encoding="utf-8"))["output"]
    for s in ["s2", "s3", "s4", "s5", "s6"][["s2", "s3", "s4", "s5", "s6"].index(start):]:
        progress and progress(s, "running", None); progress and progress(s, "done", {})
    fe = _j.loads(_j.dumps(fe)); fe["drafts"] = {"A": {**fe["drafts"]["A"], "paras": fe["drafts"]["A"]["paras"] + [{"id": "pX", "kind": "p", "text": "（假重產）", "refs": [], "borrow": None}]}}
    for it in revision["overrides"]["add_laws"]:
        fe["laws"].append({"g": "實體法規", "n": f"{it['name']} 第 {it['article']} 條", "t": "", "rel": 90, "badges": [], "why": "承辦人指定", "lib": it["name"], "version": None})
    return fe


def test_chat_question(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock, text, tool
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([tool("lookup_article", {"law": "行政罰法", "article": "18"}), text("條文如下…")]))
    r = c.post("/api/cases/case02/chat", json={"message": "行政罰法第 18 條是什麼？", "tab": 2})
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "answer" and j["proposal"] is None and j["sources"][0]["type"] == "law"


def test_chat_validation(client):
    c, _ = client
    assert c.post("/api/cases/case02/chat", json={"message": "   "}).status_code == 400


def test_chat_proposal_confirm_cancel_flow(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock, tool
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([tool("propose_revision", {"summary": "爭點 1 改採訴願人；加引行政罰法 §18 I", "items": [
        {"type": "issue", "id": "I1", "to": "appellant", "why": "影片看不出離手"}, {"type": "law", "n": "行政罰法", "art": "18", "p": "1"}]})]))
    monkeypatch.setattr(api.objection, "run", _fake_objection)
    monkeypatch.setattr(api.run_all, "run", _fake_run); RERUN_CALLS.clear()

    r = c.post("/api/cases/case02/chat", json={"message": "爭點 1 改採訴願人，影片看不出離手；加引行政罰法第 18 條第 1 項", "tab": 1}).json()
    assert r["kind"] == "proposal"
    p = r["proposal"]; pid = p["id"]
    assert pid.startswith("pp_") and p["state"] == "pending" and p["caseId"] == "case02" and p["scope"] == [2, 3, 4, 5]
    assert (api.RUNS / "case02" / "proposals" / f"{pid}.json").exists()

    g = c.get(f"/api/cases/case02/proposals/{pid}")
    assert g.status_code == 200 and g.json()["items"][0]["title"]
    assert c.get("/api/cases/case02/proposals/pp_nope").status_code == 404

    n0 = len(c.get("/api/cases/case02/analysis").json().get("objections", []))
    r2 = c.post(f"/api/cases/case02/proposals/{pid}/confirm")
    assert r2.status_code == 202 and r2.json()["proposalId"] == pid
    job = r2.json()["jobId"]
    for _ in range(100):  # worker thread 序列執行
        st = c.get(f"/api/cases/case02/proposals/{pid}").json()["state"]
        if st in ("applied", "failed"):
            break
        time.sleep(0.05)
    doc = c.get(f"/api/cases/case02/proposals/{pid}").json()
    assert doc["state"] == "applied", doc.get("error")
    # 爭點 item 走重引證（1 則 objection）；法規 item 程式判定；接著從 s4 局部重跑
    assert len(doc["replies"]) == 2 and doc["replies"][0]["result"] == "採納" and doc["replies"][0]["revised_finding"] == "採訴願人"   # 「採訴願人（補強）」被正規化
    assert doc["replies"][1]["result"] == "採納" and "行政罰法 第 18 條第 1 項" in doc["replies"][1]["reply"]
    assert doc["rerun"] == ["s4", "s5", "s6"] and doc["version"] == "v2"
    assert len(RERUN_CALLS) == 1 and RERUN_CALLS[0]["start"] == "s4"
    rev = RERUN_CALLS[0]["revision"]
    assert rev["overrides"]["findings"] == {"I1": "採訴願人"} and rev["overrides"]["add_laws"][0] == {"name": "行政罰法", "article": "18", "paragraph": "1"}
    assert any("行政罰法 第 18 條第 1 項" in s for s in rev["instructions"]["s6"]) and rev["overrides"]["prev_draft"]
    an = c.get("/api/cases/case02/analysis").json()
    assert len(an["objections"]) == n0 + 1 and an["objections"][-1]["proposalId"] == pid
    assert next(i for i in an["output"]["issues"] if i["id"] == "I1")["afterObjection"] == "採訴願人"
    assert list(an["output"]["drafts"]) == ["A", "v2"] and an["output"]["drafts"]["v2"]["proposalId"] == pid and an["output"]["drafts"]["v2"]["paras"][-1]["text"] == "（假重產）"
    assert any(l["n"].startswith("行政罰法 第 18 條") for l in an["output"]["laws"])
    ev = c.get(f"/api/jobs/{job}").json()["events"]
    assert ev[-1]["event"] == "done" and ev[-1]["data"]["proposalId"] == pid and ev[-1]["data"]["rerun"] == ["s4", "s5", "s6"]

    # 已 applied 不可再 confirm／cancel
    assert c.post(f"/api/cases/case02/proposals/{pid}/confirm").status_code == 409
    assert c.post(f"/api/cases/case02/proposals/{pid}/cancel").status_code == 409


def test_cancel_pending(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock, tool
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([tool("propose_revision", {"summary": "理由二精簡", "items": [{"type": "text", "para": "理由二", "how": "精簡一點"}]})]))
    p = c.post("/api/cases/case02/chat", json={"message": "理由二精簡一點"}).json()["proposal"]
    assert p["scope"] == [5]
    r = c.post(f"/api/cases/case02/proposals/{p['id']}/cancel")
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert c.post(f"/api/cases/case02/proposals/{p['id']}/confirm").status_code == 409


def test_readonly_refuse(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([]))
    j = c.post("/api/cases/case02/chat", json={"message": "爭點 1 改採訴願人", "readonly": True}).json()
    assert j["kind"] == "refuse" and j["proposal"] is None


def test_rejected_issue_only_no_rerun(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock, tool
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([tool("propose_revision", {"summary": "爭點 2 改採機關", "items": [{"type": "issue", "id": "I2", "to": "agency", "why": "x"}]})]))
    monkeypatch.setattr(api.objection, "run", _fake_objection)   # 理由不含「訴願人」→ 無法採納
    monkeypatch.setattr(api.run_all, "run", _fake_run); RERUN_CALLS.clear()
    p = c.post("/api/cases/case02/chat", json={"message": "爭點 2 改採機關，理由 x"}).json()["proposal"]
    c.post(f"/api/cases/case02/proposals/{p['id']}/confirm")
    for _ in range(100):
        d = c.get(f"/api/cases/case02/proposals/{p['id']}").json()
        if d["state"] in ("applied", "failed"):
            break
        time.sleep(0.05)
    assert d["state"] == "applied" and d["replies"][0]["result"] == "無法採納" and d["rerun"] == [] and RERUN_CALLS == []


def test_served_override_starts_at_s3_without_s2_model(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock, tool
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([tool("propose_revision", {"summary": "送達日更正", "items": [{"type": "served", "v": "114-09-16"}, {"type": "verdict", "to": "撤銷"}]})]))
    monkeypatch.setattr(api.run_all, "run", _fake_run); RERUN_CALLS.clear()
    p = c.post("/api/cases/case02/chat", json={"message": "送達日改 114-09-16，結論改撤銷"}).json()["proposal"]
    assert p["scope"] == [0, 1, 2, 3, 4, 5]
    c.post(f"/api/cases/case02/proposals/{p['id']}/confirm")
    for _ in range(100):
        d = c.get(f"/api/cases/case02/proposals/{p['id']}").json()
        if d["state"] in ("applied", "failed"):
            break
        time.sleep(0.05)
    assert d["state"] == "applied" and RERUN_CALLS[0]["start"] == "s3"
    ov = RERUN_CALLS[0]["revision"]["overrides"]
    assert ov["served"] == "114-09-16" and ov["verdict"] == "撤銷" and d["rerun"] == ["s3", "s4", "s5", "s6"]


def test_preview_endpoint_cached(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock, tool
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([tool("propose_revision", {"summary": "理由二精簡", "items": [{"type": "text", "para": "理由二", "how": "精簡一點"}]})]))
    n = {"calls": 0}
    monkeypatch.setattr(api.assistant, "call_text", lambda step, **kw: (n.__setitem__("calls", n["calls"] + 1), "精簡後")[1])
    p = c.post("/api/cases/case02/chat", json={"message": "理由二精簡一點"}).json()["proposal"]
    r = c.post(f"/api/cases/case02/proposals/{p['id']}/preview").json()
    assert r["previews"][0]["para"] == "理由二" and r["previews"][0]["after"] == "精簡後" and r["previews"][0]["before"]
    r2 = c.post(f"/api/cases/case02/proposals/{p['id']}/preview").json()
    assert r2 == r and n["calls"] == 1    # 第二次讀快取
    assert c.post("/api/cases/case02/proposals/pp_nope/preview").status_code == 404


def test_text_only_fast_path_patches_paragraph_without_rerun(client, monkeypatch):
    c, api = client
    from tests.conftest import FakeBedrock, tool
    monkeypatch.setattr(api.assistant, "_converse", FakeBedrock([tool("propose_revision", {"summary": "主文改寫", "items": [{"type": "text", "para": "主文", "how": "改為標準句式"}]})]))
    monkeypatch.setattr(api.assistant, "call_text", lambda step, **kw: "訴願駁回。（快路徑改寫）")
    monkeypatch.setattr(api.run_all, "run", _fake_run); RERUN_CALLS.clear()
    p = c.post("/api/cases/case02/chat", json={"message": "主文改為標準句式"}).json()["proposal"]
    c.post(f"/api/cases/case02/proposals/{p['id']}/confirm")
    for _ in range(100):
        d = c.get(f"/api/cases/case02/proposals/{p['id']}").json()
        if d["state"] in ("applied", "failed"):
            break
        time.sleep(0.05)
    assert d["state"] == "applied" and d.get("fast") is True and d["rerun"] == ["s6"] and RERUN_CALLS == []
    an = c.get("/api/cases/case02/analysis").json()
    latest = an["output"]["drafts"][d["version"]]
    from pipeline.assistant import label_paras
    assert next(pp for lab, pp in label_paras(latest["paras"]) if lab == "主文")["text"] == "訴願駁回。（快路徑改寫）"
