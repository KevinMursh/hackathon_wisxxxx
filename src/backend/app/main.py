import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bedrock

FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", Path(__file__).resolve().parents[2] / "frontend"))

app = FastAPI(title="訴願智審臺 API")


class ChatIn(BaseModel):
    prompt: str
    system: str | None = None


@app.get("/api/health")
async def health():
    return {"ok": True, "region": bedrock.REGION, "model": bedrock.MODEL_ID}


@app.post("/api/chat")
async def chat(body: ChatIn):
    text = await bedrock.converse([{"role": "user", "content": [{"text": body.prompt}]}], body.system)
    return {"text": text}


@app.post("/api/chat/stream")
async def chat_stream(body: ChatIn):
    async def gen():
        async for chunk in bedrock.converse_stream(
            [{"role": "user", "content": [{"text": body.prompt}]}], body.system
        ):
            yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# 前端與 API 同源：最後才掛，避免蓋掉 /api/*
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
