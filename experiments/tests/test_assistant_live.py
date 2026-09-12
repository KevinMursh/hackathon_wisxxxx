"""真打 Bedrock（LIVE=1 才跑；約 20 秒、3 次呼叫）：一問一改一模糊，驗 kind 與工具使用。"""
import os
import pytest

from pipeline import assistant as A

pytestmark = pytest.mark.skipif(os.getenv("LIVE") != "1", reason="LIVE=1 才真打 Bedrock")


def test_live_question(state):
    r = A.chat("case02", "行政罰法第 18 條第 1 項的全文是什麼？", state=state, tab=2)
    assert r["kind"] == "answer" and "裁處罰鍰" in r["text"] and r["cite_offer"]["law"] == "行政罰法" and r["usage"]["input"] > 0


def test_live_edit(state):
    r = A.chat("case02", "爭點 1 改採訴願人，影片看不出離手；另外加引行政罰法第 18 條第 1 項", state=state, tab=1)
    assert r["kind"] == "proposal"
    types = {i["type"] for i in r["proposal"]["items"]}
    assert "issue" in types and "law" in types and r["proposal"]["scope"] == [2, 3, 4, 5]


def test_live_vague(state):
    r = A.chat("case02", "改好一點", state=state, tab=4)
    assert r["kind"] == "clarify"
