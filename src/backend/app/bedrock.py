"""Bedrock 呼叫的唯一入口。競賽規範：全帳號 ≤ 1 RPS，所以這裡用全域鎖串行化，
每次呼叫之間至少隔 MIN_INTERVAL 秒；遇到 Throttling 再退避重試。"""
import asyncio
import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-west-2")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
MIN_INTERVAL = float(os.getenv("BEDROCK_MIN_INTERVAL", "1.1"))

_client = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
    config=Config(read_timeout=180, retries={"max_attempts": 0}),
)
_lock = asyncio.Lock()
_last_call = 0.0


async def _throttle():
    """取得鎖後才回傳；呼叫端在 with 區塊內完成整個請求。"""
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_call = time.monotonic()


async def converse(messages: list[dict], system: str | None = None, max_tokens: int = 2048) -> str:
    kwargs = {
        "modelId": MODEL_ID,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.2},
    }
    if system:
        kwargs["system"] = [{"text": system}]

    async with _lock:
        for attempt in range(4):
            await _throttle()
            try:
                resp = await asyncio.to_thread(_client.converse, **kwargs)
                return resp["output"]["message"]["content"][0]["text"]
            except ClientError as e:
                if e.response["Error"]["Code"] != "ThrottlingException" or attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


async def converse_stream(messages: list[dict], system: str | None = None, max_tokens: int = 4096):
    """逐段 yield 文字，給 SSE 用。整個串流期間持有鎖，確保不與其他呼叫重疊。"""
    kwargs = {
        "modelId": MODEL_ID,
        "messages": messages,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.2},
    }
    if system:
        kwargs["system"] = [{"text": system}]

    async with _lock:
        await _throttle()
        resp = await asyncio.to_thread(_client.converse_stream, **kwargs)
        stream = resp["stream"]
        loop = asyncio.get_running_loop()
        it = iter(stream)
        while True:
            event = await loop.run_in_executor(None, next, it, None)
            if event is None:
                break
            delta = event.get("contentBlockDelta", {}).get("delta", {}).get("text")
            if delta:
                yield delta
