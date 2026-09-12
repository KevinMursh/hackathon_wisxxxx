# server/ — 文件歸戶後端（Node 20）

```
bedrock.mjs                Bedrock 唯一入口：起跑節流 + 併發閘 + 退避重試 + tool-use JSON / 串流
normalize.mjs              ① 正規化：任意檔 → {text, textPerPage, images[], meta}（零 LLM）
classify.mjs               ② 標籤：裝箱 → Converse（強制 schema）→ segments + nature/timing/suggestedName
store/s3.mjs               原檔、正規化產物、presigned 下載
store/ddb.mjs              單表：File / Job / Event / Audit / Cache
prompts/classify.md        分類 system prompt（doc_type 判定要領、source 判定證據表）
schemas/classify.schema.json  模型輸出 schema（enum 即封閉清單）＋ x-derived 程式推導欄位
schemas/enums.json         doc_type(27) / source(5) / form(6) / nature(4)
eval/normalize.test.mjs    正規化驗證（零 LLM，35 案）
eval/run.mjs               分類驗證（41 檔 manifest，真打 Bedrock）
eval/manifest.json         分類正解
eval/fixtures/             對抗檔（改副檔名、壞檔、負樣本），不進 資料集/
```

## 環境變數

| Key | 預設 | 說明 |
|---|---|---|
| `AWS_PROFILE` | — | 本機用；EC2 走 Instance Profile 時留空 |
| `AWS_REGION` | `us-west-2` | 與隊友部署同區 |
| `MODEL` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | 備選 `us.anthropic.claude-opus-4-5-20251101-v1:0`（同準同速） |
| `BEDROCK_MIN_INTERVAL` | `2.0` | 請求**起跑**間隔（秒）。規範限每秒請求數，非同時數 |
| `BEDROCK_CONCURRENCY` | `3` | 同時在途上限。設 `1` 回到完全序列（現場頻繁 429 時用） |
| `BOX_FILES` | `10` | 每箱檔數上限；另有 20 圖 / 120k 字上限，先到先開新箱 |
| `CLASSIFY_CACHE` | `1` | 本機 `.cache/`；`0` 強制真打。key 含 model + prompt，改 prompt 自動失效 |
| `S3_BUCKET` | — | 必填，未設啟動即退出 |
| `S3_PREFIX` | 空 | 本機開發設 `dev/`，同時作為 DynamoDB PK 命名空間 |
| `DDB_TABLE` | — | 必填，未設啟動即退出 |

複製 `.env.example` 為 `.env`（已 gitignore）。

## 跑測試

```bash
npm ci
npm test                                      # 正規化 35 案，零 LLM，數秒
AWS_PROFILE=hackathon AWS_REGION=us-west-2 \
  node eval/run.mjs --group all               # 分類 41 檔，真打，約 2 分鐘
```

`eval/run.mjs` 參數：`--group tune|final|all`、`--messy`（亂檔名）、`--per-file`、`--box N`、`--model ID`、`--filter 字串`、`--out file.json`。

外部工具（本機 brew／EC2 dnf）：`poppler-utils`、`ffmpeg`、`libreoffice`、`file`、`qpdf`。

## 實測（2026-09-12，case02 21 檔真打）

| 設定 | 耗時 | doc_type | source |
|---|---|---|---|
| 序列（CONCURRENCY=1） | 91s | 21/21 | 21/21 |
| **併發 3 / 間隔 2s** | **62s** | 21/21 | 21/21 |
| 亂檔名（--messy） | 141s→併發後約 70s | 21/21 | 21/21 |
| 全 41 檔（tune+final） | 130s | 41/41 | 41/41 |

合併卷宗 20 頁 → 17 段全對；無身分證據回「未知」100%；負樣本 100%；建議檔名 6/6。
