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


def _fake_objection(case, docs, issues, judge, ob, draft, verified, sims_notes, progress=None):
    """假的重引證：理由含「訴願人」就採納，否則無法採納；不重產草稿。"""
    issue = next(i for i in issues["issues"] if i["id"] == ob["issueId"])
    acc = "訴願人" in ob["reason"]
    return {**ob, "issueId": issue["id"], "issueTitle": issue["title"], "originalFinding": issue["finding"],
            "result": "採納" if acc else "無法採納", "revised_finding": "採訴願人" if acc else None,
            "reply": "假回覆：依卷證" + ("採納" if acc else "無法採納"), "evidence": [{"file": "x.pdf", "quote": "q"}], "draft_changes": [],
            **({"newDraft": "主文\n原處分撤銷。\n理由\n一、假的重產草稿。", "newIssues": issues, "newDraftCitations": []} if acc else {})}


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
    # 爭點 item 一則、其餘 item 併一則 → 2 則 objection
    assert len(doc["replies"]) == 2 and doc["replies"][0]["result"] == "採納" and doc["replies"][0]["revised_finding"] == "採訴願人"
    assert "加引 行政罰法 第 18 條第 1 項" in doc["replies"][1]["label"]
    an = c.get("/api/cases/case02/analysis").json()
    assert len(an["objections"]) == n0 + 2 and an["objections"][-2]["proposalId"] == pid
    assert next(i for i in an["output"]["issues"] if i["id"] == "I1")["afterObjection"] == "採訴願人"
    assert "v2" in an["output"]["drafts"] and an["output"]["drafts"]["v2"]["objectionId"]
    ev = c.get(f"/api/jobs/{job}").json()["events"]
    assert ev[-1]["event"] == "done" and ev[-1]["data"]["proposalId"] == pid

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
