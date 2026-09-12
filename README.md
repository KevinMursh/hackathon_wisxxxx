# 2026 新北市 AI 智慧城市黑客松 — 法制局組

訴願案件審理作業流程之 AI 輔助應用。

## 目錄結構

- `資料集/` — 命題方提供之歷史訴願決定書、相關法規、司法院釋字及行政判解、行政函釋（僅供競賽使用）
- `docs/` — 命題文件、競賽環境規範與限制、支援服務清單
- `design_kc/` — 承辦人工作台設計稿（Design Components，五步驟：收案擷取/程序檢核/法規與案例/決定書草稿/稽核匯出）
- `scenarios_kc/` — 十情境承辦人角色扮演走查、欄位核對總表
- `prototype/` — 前端可互動原型（純前端展示，未串接後端模型）
- `aws/` — AWS 工作坊操作手冊（Bedrock AgentCore、Kiro）

## 環境需求

- Node.js 18+（Claude Agent SDK 底層 CLI runtime）
- Python 3.10+
- AWS CLI，設定 `hackathon` profile（黑客松發放帳號，`WSParticipantRole`）

## Setup

```bash
pip install -r requirements.txt

cp .env.example .env
# 依實際環境填入 .env（本機開發用；EC2 部署改用 Instance Profile，見下）
```

### AWS 認證

- **本機開發**：`aws configure --profile hackathon`，`.env` 裡設 `AWS_PROFILE=hackathon`
- **EC2 部署**：不要在機器上放 access key。掛 IAM Instance Profile，附上：
  - `bedrock:InvokeModel`
  - `bedrock:InvokeModelWithResponseStream`
  - `bedrock:Retrieve`（若接 Knowledge Base）

  `.env` 在 EC2 上留空 `AWS_PROFILE`，SDK 會自動走 Instance Profile 拿暫時憑證。

### 競賽環境限制（見 `docs/黑客松競賽環境規範與限制_20260722.pdf`）

- Region 僅限 `us-east-1` / `us-west-2`
- Bedrock 請求 ≤ 1 RPS，pipeline 設計必須序列化，不可平行呼叫
- 不建議大規模模型訓練；純 prompt + RAG
- EC2 僅一般機型（Standard/HPC 系列），無 GPU 額度

### 已驗證可用的模型（2026-09-12）

| 用途 | Model ID |
|---|---|
| 主力（擷取/分類/檢索/草稿） | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| 複雜法律推理備選 | `us.anthropic.claude-opus-4-5-20251101-v1:0` |
| 中文 embedding | `cohere.embed-multilingual-v3` |

## 驗證 SDK 連通

```bash
python3 -c "
import anyio
from claude_agent_sdk import query, ClaudeAgentOptions
async def main():
    async for m in query(prompt='hi', options=ClaudeAgentOptions(max_turns=1)):
        print(m)
anyio.run(main)
"
```

## 公開 repo 注意事項

- `.env`、任何 AWS access key / credentials 檔案 **絕對不進 repo**（已在 `.gitignore`）
- Model ID、region、套件依賴不是秘密，正常進 repo
- 若使用 Kiro 開發，`/.kiro` 資料夾**不可**加入 `.gitignore`（競賽規範第 9 條，需展示 specs/hooks/steering）
