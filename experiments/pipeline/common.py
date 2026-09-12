"""實驗共用層：載入案件 → 呼叫 Bedrock（節流／強制 JSON／串流／圖片）→ 結果落地 runs/。

用法：
    from pipeline.common import load_case, call_json, call_text, stream_text
    case = load_case("case02")                 # {"docs": {檔名: 文字}, "images": {檔名: Path}}
    out  = call_json("s3_issues", Issues, system=..., user=..., case="case02")
每次呼叫都寫 runs/{case}/{step}.json（輸出＋耗時＋token），壞了單步重跑。
"""
import asyncio, base64, json, os, sys, time
from pathlib import Path
from typing import Type, TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
INPUTS, PROMPTS = ROOT / "inputs", ROOT / "prompts"
RUNS = Path(os.getenv("ANALYSIS_RUNS", ROOT / "runs"))  # 雲上放 /var/lib/analysis/runs，重佈不清
REGION = os.getenv("AWS_REGION", "us-west-2")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
MIN_INTERVAL = 1.1  # 競賽規範 ≤ 1 RPS；本機與 EC2 共用同一額度

_client = boto3.client("bedrock-runtime", region_name=REGION,
                       config=Config(read_timeout=300, retries={"max_attempts": 0}))
_last = 0.0
T = TypeVar("T", bound=BaseModel)


# ---------- 輸入 ----------
def load_case(name: str) -> dict:
    d = INPUTS / name
    docs = {p.name: p.read_text(encoding="utf-8") for p in sorted(d.rglob("*.txt"))}
    images = {p.name: p for p in sorted(d.rglob("*.jpg")) + sorted(d.rglob("*.png"))}
    return {"name": name, "docs": docs, "images": images}


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def docs_block(docs: dict, only: list[str] | None = None, max_chars: int = 8000) -> str:
    """把多份文件排成 === FILE === 區塊，給模型當卷宗。"""
    parts = []
    for fn, txt in docs.items():
        if only and not any(k in fn for k in only):
            continue
        parts.append(f"=== FILE {fn} ===\n{txt[:max_chars]}")
    return "\n\n".join(parts)


def image_block(src) -> dict:
    """src 可為 Path 或 bytes（S3 讀來的頁圖）。"""
    data = src if isinstance(src, (bytes, bytearray)) else Path(src).read_bytes()
    fmt = "png" if data[:4] == b"\x89PNG" else "jpeg"
    return {"image": {"format": fmt, "source": {"bytes": bytes(data)}}}


# ---------- 呼叫 ----------
def _throttle():
    global _last
    wait = MIN_INTERVAL - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()


def _converse(**kw):
    for attempt in range(4):
        _throttle()
        try:
            return _client.converse(**kw)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ThrottlingException" or attempt == 3:
                raise
            time.sleep(2 ** attempt)


def _build(system: str, user: str, images: list[Path] | None, cache: bool):
    sys_blocks = [{"text": system}]
    if cache:
        sys_blocks.append({"cachePoint": {"type": "default"}})
    content = [image_block(p) for p in (images or [])] + [{"text": user}]
    return sys_blocks, [{"role": "user", "content": content}]


def _save(case: str | None, step: str, payload, meta: dict):
    if not case:
        return
    out = RUNS / case
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{step}.json").write_text(
        json.dumps({"meta": meta, "output": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{step}] {meta['latency_s']}s  in={meta['input_tokens']} out={meta['output_tokens']}  → runs/{case}/{step}.json", file=sys.stderr)


def call_json(step: str, schema: Type[T], *, system: str, user: str, case: str | None = None,
              images: list[Path] | None = None, cache: bool = False, max_tokens: int = 4096) -> T:
    """tool-use 強制模型輸出符合 pydantic schema 的 JSON。驗證失敗時把錯誤訊息附回去重試一次（Bedrock 不強制 required）。"""
    from pydantic import ValidationError
    tool = {"tools": [{"toolSpec": {"name": step, "description": schema.__doc__ or step, "inputSchema": {"json": schema.model_json_schema()}}}],
            "toolChoice": {"tool": {"name": step}}}
    t = time.monotonic(); usage = {"inputTokens": 0, "outputTokens": 0}; last_err = None
    for attempt in range(2):
        u = user if not last_err else user + f"\n\n【上次輸出未通過 schema 驗證，請修正並完整填寫所有必填欄位】\n{last_err}"
        sys_blocks, msgs = _build(system, u, images, cache)
        r = _converse(modelId=MODEL_ID, system=sys_blocks, messages=msgs,
                      inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1}, toolConfig=tool)
        for k in usage:
            usage[k] += r["usage"][k]
        raw = next(c["toolUse"]["input"] for c in r["output"]["message"]["content"] if "toolUse" in c)
        try:
            obj = schema.model_validate(raw); break
        except ValidationError as e:
            last_err = str(e)[:1500]
            if attempt == 1:
                raise
    _save(case, step, obj.model_dump(), {"model": MODEL_ID, "latency_s": round(time.monotonic() - t, 1),
                                          "input_tokens": usage["inputTokens"], "output_tokens": usage["outputTokens"], "retried": bool(last_err)})
    return obj


def call_text(step: str, *, system: str, user: str, case: str | None = None,
              images: list[Path] | None = None, cache: bool = False, max_tokens: int = 4096) -> str:
    sys_blocks, msgs = _build(system, user, images, cache)
    t = time.monotonic()
    r = _converse(modelId=MODEL_ID, system=sys_blocks, messages=msgs,
                  inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2})
    text = r["output"]["message"]["content"][0]["text"]
    u = r["usage"]
    _save(case, step, text, {"model": MODEL_ID, "latency_s": round(time.monotonic() - t, 1),
                             "input_tokens": u["inputTokens"], "output_tokens": u["outputTokens"]})
    return text


def stream_text(step: str, *, system: str, user: str, case: str | None = None,
                images: list[Path] | None = None, cache: bool = False, max_tokens: int = 8192):
    """逐段 yield；結束後整段落地。草稿生成用這個，看得到即時輸出。"""
    sys_blocks, msgs = _build(system, user, images, cache)
    t = time.monotonic()
    _throttle()
    r = _client.converse_stream(modelId=MODEL_ID, system=sys_blocks, messages=msgs,
                                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2})
    buf, usage = [], {}
    for ev in r["stream"]:
        d = ev.get("contentBlockDelta", {}).get("delta", {}).get("text")
        if d:
            buf.append(d)
            yield d
        if "metadata" in ev:
            usage = ev["metadata"].get("usage", {})
    _save(case, step, "".join(buf), {"model": MODEL_ID, "latency_s": round(time.monotonic() - t, 1),
                                     "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens")})


# ---------- smoke ----------
if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "case02"
    c = load_case(name)
    for fn, txt in c["docs"].items():
        print(f"{len(txt):>6} 字  {fn}")
    print(f"{len(c['images'])} 張圖片")

    class Smoke(BaseModel):
        """卷宗基本資訊"""
        appellant_masked: str
        disposition_no: str
        law_cited: list[str]

    out = call_json("smoke", Smoke, case=name,
                    system="你是訴願審議承辦助理。只根據提供的文件作答，不得臆測。",
                    user=docs_block(c["docs"], only=["裁處書正本"]) + "\n\n請填出訴願人（遮罩）、裁處書文號、所引法條。")
    print(out.model_dump_json(indent=2))
