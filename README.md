# 2026 新北市 AI 智慧城市黑客松 — 法制局組

訴願案件審理作業流程之 AI 輔助應用。

## 目錄結構

```
資料集/
├── 命題方提供/                  ← 主辦單位交付，僅供競賽使用
│   ├── 歷史訴願決定書/           101 份（110-114 年）
│   ├── 相關法規/                 11 部
│   ├── 司法院釋字及行政判解/      19 篇
│   └── 行政函釋/                 10 篇
└── 自行蒐集/                    ← 命題方未提供，網路蒐集補充（皆為政府公開來源）
    ├── 訴願書範例官方/            新北市法制局官網下載
    ├── 答辯書範例官方/            行政院 appeal.ey.gov.tw
    ├── 相關法規補充/              政府資訊公開法全文（判解有引用但法規本體原缺）
    └── 判解函釋補充/              洗錢防制法「帳戶控制權」判準（補強判準深度）

docs/
├── 【命題文件】...pdf            命題文件
├── 黑客松競賽環境規範與限制...pdf  競賽環境規範
├── Supported AWS Services List...xlsx  支援服務與 EC2/SageMaker 額度清單
├── 訴願書跟答辯書/                更多官方文書範本（委任書/閱覽卷宗/言詞辯論等申請書）
├── 提案/                        提案相關文件
├── 資料集網路補充紀錄.md          網路補充哪些關鍵資料、為何補、判定不補的類別與理由
└── 各領域參考資料與判決結果統計.md 各領域法源是否充足 + 101份決定書判決結果交叉統計

design_kc/     — 承辦人工作台設計稿（Design Components，五步驟：收案擷取/程序檢核/法規與案例/決定書草稿/稽核匯出）
scenarios_kc/  — 十情境承辦人角色扮演走查、欄位核對總表、缺漏總表、卷宗類型討論
prototype/     — 前端可互動原型（純前端展示，未串接後端模型）
aws/           — AWS 工作坊操作手冊（Bedrock AgentCore、Kiro）
```

## 資料集分類與使用原則（重要）

`資料集/` 底下目前只有**參考/測試用**資料——命題方提供的 101 份歷史決定書＋法規/判解/函釋，以及我們自行蒐集補充的範本，用途是：

- 建 RAG 知識庫的原料（法規、判解、函釋、決定書全文）
- few-shot 範例池（草稿生成、相似案例比對）
- 開發階段的內部功能測試素材

**這批資料不等於競賽現場的 evaluation 資料集。** 屆時很可能會另外收到一批全新、held-out 的訴願案例來實測系統表現，兩者必須嚴格區分：

| | 參考/測試用資料集（現有） | Evaluation 資料集（未來） |
|---|---|---|
| 位置 | `資料集/命題方提供/` + `資料集/自行蒐集/` | `資料集/評測用（勿用於RAG）/`（已建立，內含 3 案，見該資料夾 README）|
| 用途 | 建知識庫、當 few-shot、開發期測試 | 驗收系統真實表現 |
| 可否進 RAG／向量庫 | 可以 | **不可以**——先塞進知識庫等於讓系統「看過答案」，評測分數會失真 |
| 可否當 few-shot 範例 | 可以 | **不可以**，理由同上 |
| 可否用來微調 prompt/規則 | 可以（這是開發的正常流程）| 只能拿來「跑」，跑完看結果再回頭調整開發集，不能直接把 evaluation 案例的正確答案寫死進規則 |

**拿到 evaluation 資料集時的處理原則**：獨立建資料夾、資料夾名稱明確標示「勿用於訓練/RAG」、程式碼裡的知識庫建置腳本（ingestion script）不得掃到這個資料夾、跑分時走跟正式流程一樣的路徑（不能為了評測資料另開後門邏輯）。

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
