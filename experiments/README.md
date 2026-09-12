# experiments/ — pipeline 實驗區

不進部署包（`deploy/push.sh` 只打包 `src/` 與 `deploy/`）。穩定後把每步搬進 `src/backend/app/pipeline/`（或 Node 對應位置）；`prompts/`、`schemas/` 是純文字，直接搬。

```
pipeline/common.py   載入案件、呼叫 Bedrock（節流 1.1s／tool-use 強制 JSON／串流／圖片／cache）、落地 runs/
prompts/             每步一個 .md；system.md 是共用角色與原則
schemas/             各步輸出 schema（由 pydantic 匯出 .json，給 Node 端用）
inputs/case02/       01-訴願書.txt、02-答辯書.txt、卷證/*.txt（pdftotext）、卷證/*.jpg（掃描與照片，走圖片輸入）
runs/                每次輸出 {case}/{step}.json：output + 耗時 + token（gitignore）
```

## 跑

```bash
cd experiments
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export AWS_PROFILE=ntpc-hackathon AWS_REGION=us-west-2
.venv/bin/python -m pipeline.common case02        # smoke：列出文件、打一次 Bedrock
```

## 寫一步的樣子

```python
from pydantic import BaseModel
from pipeline.common import load_case, call_json, docs_block, prompt

class Issue(BaseModel):
    title: str
    appellant_claim: str
    agency_reply: str
    evidence_quote: str        # 卷證原文逐字片段，程式再定位頁碼
    evidence_file: str
    ai_finding: str            # 採訴願人／採機關
    reason: str                # 一句依據

class Issues(BaseModel):
    """本案爭點清單"""
    issues: list[Issue]

case = load_case("case02")
out = call_json("s3_issues", Issues, case="case02",
                system=prompt("system") + "\n\n" + prompt("s3_issues"),
                user=docs_block(case["docs"]))
```

## 規則

- case02 是評測案，**prompt 裡不得出現本案答案**（法條、結論、事實關鍵字）；只寫一般規則
- `資料集/評測用/case02/04-標準答案.md` 跑完才開
- 每步做完拿 case03 跑一次，不改東西也合理 → 沒 overfit
- 本機與 EC2 共用 1 RPS，一次跑一個案

## 目前狀態（2026-09-12 首跑 case02）

`python -m pipeline.run_all case02`：6 次模型呼叫、約 2 分鐘。

| 步 | 做法 | 結果 |
|---|---|---|
| s2 欄位 | 1 次（文字＋9 張圖） | 送達日取自送達證書 114-09-18，自述 09-16 列入 conflicts |
| 期間／程序 | 程式 | 次日起 30 日 → 10-18 截止，收文 09-22 在期間內 |
| s3 爭點 | 1 次 | 3 爭點，各附卷證引句與一句依據 |
| s4 法規 | 1 次 + 程式查核 | 推薦 8 條全部查得到；答辯書引用的「裁罰準則」標 not_in_dataset（命題方未提供該子法） |
| s5 相似 | 規則 + 1 次 | 同法 79I／81I 五件（自動排除本案自身決定書） |
| s6 草稿 | 1 次串流 | 2,483 字，主文／事實／理由／據上論結／教示；引用 7 則、5 ok、2 not_in_dataset |

對照標準答案 7 個論證點：命中 5（構成要件與裁罰依據、卷證事證、附表項次與係數、駁斥訴願主張、維持原處分），
缺 2：廢清法 §4＋本府公告（管轄權限）、環保署 108 年函（政策說明）——前者可在 s4 prompt 加「處分機關權限依據」一項，後者資料集有函釋資料夾但 pipeline 尚未接。

## 續跑

```bash
python -m pipeline.run_all case02 --from s5     # s2–s4 讀 runs/ 快取，只重跑 s5、s6
python -m pipeline.run_all case02 --no-images   # 不送圖片（省 token，掃描件會讀不到）
```
