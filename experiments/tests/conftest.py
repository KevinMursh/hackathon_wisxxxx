"""測試共用：不打 Bedrock、不碰 DynamoDB；runs/ 改用 tmp 目錄但先複製 case02 的分析快取進去。"""
import json, os, shutil, sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ANALYSIS_DDB", "0")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")

CASE = "case02"
SRC_RUNS = ROOT / "runs" / CASE


@pytest.fixture(scope="session")
def runs_dir(tmp_path_factory):
    """把 runs/case02（analysis.json 等快取）複製到暫存目錄，測試寫入不污染真的 runs/。"""
    d = tmp_path_factory.mktemp("runs")
    if not (SRC_RUNS / "analysis.json").exists():
        pytest.skip("缺 runs/case02/analysis.json（先跑一次 python -m pipeline.run_all case02）")
    shutil.copytree(SRC_RUNS, d / CASE)
    return d


@pytest.fixture
def state():
    return json.loads((SRC_RUNS / "analysis.json").read_text(encoding="utf-8"))["output"]


class FakeBedrock:
    """腳本化的 converse：依序回傳預先寫好的回合；記錄每次收到的 toolConfig 供斷言。"""
    def __init__(self, turns):
        self.turns, self.calls = list(turns), []

    def __call__(self, **kw):
        import copy
        self.calls.append(copy.deepcopy(kw))   # chat 會就地 append messages，深拷貝才能斷言當下的請求
        t = self.turns.pop(0) if self.turns else text("（沒有更多腳本）")
        return t


def text(s):
    return {"output": {"message": {"role": "assistant", "content": [{"text": s}]}}, "usage": {"inputTokens": 10, "outputTokens": 5}}


def tool(name, inp, tid="t1"):
    return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": tid, "name": name, "input": inp}}]}}, "usage": {"inputTokens": 10, "outputTokens": 5}}


@pytest.fixture
def fake():
    return FakeBedrock
