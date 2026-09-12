# 文件歸戶 API 接口文檔

> 版本：v0.2（2026-09-12）　狀態：**已上線並驗收通過**
> Base URL：`http://100.20.156.38/api`（us-west-2 EC2；與前端同源，前端亦由此服務）
> Content-Type：JSON（上傳為 multipart/form-data）
> **認證：無。** 存取控制只有 Security Group 的 IP 白名單——能連到就有完整權限。正式版需加 Cognito／IAM。
> **CORS：預設放行所有來源**（`Access-Control-Allow-Origin: *`），可用 `CORS_ORIGIN=http://a,http://b` 收緊。
> 允許方法 `GET,POST,PATCH,OPTIONS`，允許標頭 `Content-Type,Last-Event-ID`。

## 0. 一眼看懂

```
POST /cases/{caseId}/files          ← 一次丟整批檔案，立刻回 jobId
GET  /jobs/{jobId}/events           ← SSE：每處理完一箱推一批結果
GET  /jobs/{jobId}                  ← 同資料，輪詢版
GET  /cases/{caseId}/files          ← 目前歸戶狀態（含人工修正）
PATCH /cases/{caseId}/files/{fileId} ← 人工改類型／來源／檔名 → 寫稽核
GET  /cases/{caseId}/files/{fileId}/text  ← 正規化後的逐頁文字（擷取文字檢視、text 型錨點）
POST /cases/{caseId}/demo           ← 用 S3 預放的示範卷宗真跑一次（非查表）
GET  /cases/{caseId}/audit          ← 稽核軌跡
GET  /health                        ← 憑證與外部工具自檢
```

流程：上傳 → 背景 正規化 → 裝箱 → Bedrock 分類 → 逐箱推結果 → 前端進工作畫面 → 承辦人就地修正。**沒有確認閘門**（v4 拍板）。

## 1. 資料模型

### 1.1 File（每個上傳檔一筆）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `fileId` | string | sha256 前 12 碼；同內容同 id（去重靠它） |
| `caseId` | string | |
| `originalName` | string | 上傳時檔名，**永不改** |
| `sha256` | string | |
| `bytes` | int | |
| `mime` | string\|null | magic bytes 判定 |
| `kind` | enum | `pdf-text` `pdf-scan` `image` `video` `office` `text` `unsupported` |
| `pages` | int\|null | 影片為 null |
| `duration` | number\|null | 影片秒數 |
| `status` | enum | `queued` `done` `error` `duplicate` `excluded` `container`（zip 母檔，本身不分類） |
| `parentFileId` | string\|null | zip 子檔指向母檔 |
| `childIds` | string[]\|null | `container` 才有 |
| `error` | Error\|null | `status=error` 時 |
| `duplicateOf` | string\|null | `status=duplicate` 時指向先到的 fileId |
| `segments` | Segment[] | 分類結果；單一文件一筆，合併卷宗多筆 |
| `rawUrl` | string | presigned GET，原檔（15 分鐘有效；過期回 403，重打 `GET files` 換新）|
| `textUrl` | string | 逐頁文字端點路徑（見 §2.5b）；無正規化產物時不存在 |
| `pageImageUrls` | string[] | presigned GET，已產出的頁圖（順序同 `imagePages`） |
| `imagePages` | int[] | 哪些頁有圖（pdf-text 只有首尾＋掃描頁） |
| `createdAt` / `updatedAt` | ISO string | |

### 1.2 Segment（一份文件的判定）

| 欄位 | 型別 | 來源 | 說明 |
|---|---|---|---|
| `segId` | string | 程式 | `{fileId}#{n}` |
| `fromPage` / `toPage` | int | 模型 | 1-based，含 |
| `doc_type` | enum(27) | 模型 | 見 §1.3 |
| `source` | enum | 模型 | `訴願人` `原處分機關` `第三方` `本局` `未知`。**未知是正式值** |
| `nature` | enum | 程式查表 | `主張` `紀錄` `證物` `未知`（由 doc_type 推） |
| `timing` | enum | 程式整案算 | `處分作成前` `處分作成` `爭訟發生後` `未知`（以該案裁處書 date 為界） |
| `form` | enum | 模型 | `文字PDF` `掃描` `照片` `影片` `系統列印` `手寫` |
| `date` | string\|null | 模型 | 民國 `114-09-18`；送達證書＝簽收日、函＝發文日、照片＝時間戳 |
| `doc_no` | string\|null | 模型 | 文號原文 |
| `party_hint` | string\|null | 模型 | 當事人名，「○」原樣保留 |
| `summary` | string | 模型 | ≤30 字一句摘要；`其他` 固定「無法辨識內容」 |
| `confidence` | 0–1 | 模型＋程式 | evidence 回查失敗打 0.6 折 |
| `evidence` | string | 模型 | 判定依據，引用該檔內字樣 |
| `evidence_unverified` | bool | 程式 | evidence 引用的字樣在該檔文字裡找不到 |
| `suggestedName` | string | 程式 | 模板見 §1.4；人工可改 |
| `manual` | object\|null | 程式 | 人工修正過的欄位 `{doc_type?, source?, suggestedName?, by, at}` |
| `pageImageUrl` | string\|null | 程式 | 該段起始頁的 presigned 頁圖（卷宗清單縮圖用）|

### 1.3 doc_type 封閉清單

訴願書、訴願委任書、答辯書、答辯書檢送函、卷證目錄、裁處書、裁處書送達證書、陳述意見通知書、通知書送達證書、陳述意見書、檢舉資料、稽查紀錄、調查筆錄、採證照片、影像放大標註、採證影片、車籍資料、係數計算表、簽呈、檢驗報告、契約書、委員會決定書、閱覽卷宗申請書、言詞辯論申請書、言詞陳述申請書、參加訴願申請書、其他

前端顯示可粗分；後端不合併，因為期間計算要區分兩種送達證書、欄位擷取要精確找訴願書。

### 1.4 suggestedName

模板 `{序}-{doc_type}_{民國日期}.{副檔名}`，例 `11-裁處書送達證書_114-09-18.jpg`。
- 序號依**法定順序表**（訴願書→委任書→各式申請書→答辯書檢送函→答辯書→卷證目錄→裁處書→…→簽呈→照片→影片→其他），不依上傳順序
- 沒有 `date` 時省略日期段；`doc_type=其他` → `27-其他.{ext}`
- **副檔名以內容為準**：`其實是jpg.pdf`（內容為 JPEG）會得到 `.jpg`
- S3 key 不會改名，原檔名永遠保留；presigned 下載時才用 `suggestedName` 當檔名

### 1.5 Error

```json
{ "code": "BEDROCK_THROTTLED", "message": "…", "retryable": true }
```

| code | HTTP | 說明 |
|---|---|---|
| `UNSUPPORTED_FORMAT` | — | 該檔不送模型，`doc_type=其他`；不是錯誤，`status=done` |
| `NORMALIZE_FAILED` | — | 工具抽不出內容（壞檔、截斷）；該檔 `status=error`，其餘繼續 |
| `TOO_MANY_PAGES` | — | 掃描 PDF > 200 頁 |
| `HEIC_DECODE_FAILED` | — | 內部代碼；實際會降級為 `unsupported` + warning，不回錯 |
| `MISSING_IN_RESPONSE` | — | 模型漏回且單檔補跑仍漏 |
| `SCHEMA_INVALID` | — | 模型回非法 JSON |
| `BEDROCK_THROTTLED` | 503 | 重試 3 次仍節流；整箱失敗 |
| `BEDROCK_UNAVAILABLE` | 503 | 憑證／模型不可用；**整個 job 停** |
| `S3_WRITE_FAILED` | 500 | |
| `CASE_NOT_FOUND` / `FILE_NOT_FOUND` / `JOB_NOT_FOUND` | 404 | |
| `VALIDATION` | 400 | 欄位值不在枚舉、body 格式錯 |
| `PAYLOAD_TOO_LARGE` | 413 | 單檔 > 100 MB 或整批 > 500 MB |

## 2. Endpoints

### 2.1 `POST /cases/{caseId}/files`

上傳整批。`caseId` 不存在則建立。

Request：`multipart/form-data`，欄位 `files`（可多個）。zip 會展開，每個子檔各自成一筆。

Response `202`：
```json
{
  "jobId": "job_01J8…",
  "caseId": "1141061379",
  "files": [
    { "fileId": "a3f9c2e1b7d4", "originalName": "IMG_3988.jpg", "bytes": 114532, "status": "queued" },
    { "fileId": "0c1d…",         "originalName": "scan_0007.pdf", "bytes": 1584002, "status": "queued" },
    { "fileId": "a3f9c2e1b7d4", "originalName": "IMG_3988(1).jpg", "bytes": 114532, "status": "duplicate", "duplicateOf": "a3f9c2e1b7d4" }
  ],
  "eventsUrl": "/api/jobs/job_01J8…/events"
}
```

同批內 sha256 相同 → 第二份直接 `duplicate`，不進箱。與該案**先前**上傳過的重複 → 同樣 `duplicate`。

### 2.2 `GET /jobs/{jobId}/events`（SSE）

`Content-Type: text/event-stream`。事件：

```
event: normalized
data: {"fileId":"a3f9…","kind":"image","pages":1,"warnings":[]}

event: box
data: {"done":1,"total":3}

event: result
data: {"fileId":"a3f9…","ok":true,"segments":[{…Segment…}],"ms":41230}

event: result
data: {"fileId":"0c1d…","ok":false,"error":{"code":"NORMALIZE_FAILED","message":"pdfinfo reports 0 pages"}}

event: container
data: {"fileId":"ab6d513f5058","childIds":["4a807d69aa44","9fa1a4cde1d1"]}

event: done
data: {"jobId":"job_…","total":27,"ok":26,"error":1,"duplicate":3,"ms":85047}

event: fatal
data: {"code":"BEDROCK_UNAVAILABLE","message":"…"}
```

- `normalized` 每檔一筆，正規化完立刻推（前端可先顯示頁數／格式）
- `container`：上傳的是 zip 時推一筆，列出展開後的子檔 id；母檔本身不送模型
- `result` **逐箱**推：一箱處理完，箱內每檔各推一筆；27 檔 = 3 箱 3 波
- zip 子檔若與案件內既有檔案內容相同（sha256 同），推 `{ok:true, duplicate:true, duplicateOf}` 且不送模型
- 連線中斷重連：帶 `Last-Event-ID`，補推漏掉的事件
- `fatal` 後不再有事件，job `status=failed`

### 2.3 `GET /jobs/{jobId}`

```json
{ "jobId":"…", "caseId":"…", "status":"running|done|failed", "boxes":{"done":1,"total":2},
  "files":[ …File（含 segments 或 error）… ], "startedAt":"…", "finishedAt":null }
```

### 2.4 `GET /cases/{caseId}/files`

該案所有檔案（人工修正後的當前狀態）。Query：`?includeExcluded=true` 含不納入者。

```json
{ "caseId":"…", "cutoffDate":"114-09-16", "files":[ …File… ],
  "groups": { "訴願人":["a3f9…"], "原處分機關":[…], "第三方":[], "本局":[], "未知":["…"] } }
```

`groups` 依每檔第一個 segment 的（人工修正後）`source` 分組，直接餵卷宗瀏覽器四＋一組。

### 2.5 `PATCH /cases/{caseId}/files/{fileId}`

人工修正。Body 任一欄位可省；`segIndex` 省略 = 0。

```json
{ "segIndex": 0, "doc_type": "採證照片", "source": "第三方", "suggestedName": "05-採證照片-02_12-40-14.jpg", "excluded": false, "by": "承辦人A" }
```

規則：
- 改 `doc_type`／`source` 而未給 `suggestedName` → 依模板重算
- `excluded=true` → `status=excluded`，仍列於 `GET files`（灰字），不進下游分析
- 每個改動欄位寫一筆稽核：`{fileId, segIndex, field, from, to, by, at, origin:"ai"}`
- `nature` 隨 `doc_type` 重算；`timing` 若改的是裁處書日期相關則整案重算

Response `200`：更新後的 File。

### 2.5b `GET /cases/{caseId}/files/{fileId}/text`

```json
{ "fileId": "…", "kind": "pdf-text", "pages": 3, "textPerPage": ["第1頁…", "第2頁…"], "warnings": [] }
```

- 掃描件／照片／影片：回 `200` 但 `textPerPage: []`（沒有文字層）→ 前端改用 `pageImageUrls`
- 沒有正規化產物（error／duplicate／container）：`404 TEXT_NOT_AVAILABLE`
- 分析階段 `refs` 的 `text` 型錨點 `{page,start,end}` 就是對 `textPerPage[page-1]` 取字元區間

### 2.5c `POST /cases/{caseId}/demo`

```json
{ "pack": "case02", "messy": true }
```

從 S3 `demo/{pack}/`（**不套 `S3_PREFIX`**，dev 與正式共用）讀檔，走與上傳完全相同的 job 流程——
真的送模型，不是查表。`messy:true` 會把檔名換成 `IMG_3985.jpg`／`scan_0001.pdf`／`文件(2).pdf`，
用來證明判定看內容不看檔名。回應同上傳，另帶 `pack`／`messy`。

示範卷宗要先上傳一次：`node server/scripts/upload-demo.mjs case02`（20 檔）。
`404 DEMO_NOT_LOADED` 表示還沒上傳。

實測：case02 亂檔名 20 檔 → 90 秒、20/20 成功、分組 訴願人 2／原處分機關 13／未知 5。

### 2.6 `GET /cases/{caseId}/audit`

```json
{ "entries": [ { "at":"2026-09-12T08:12:03Z", "fileId":"a3f9…", "segIndex":0, "field":"source", "from":"未知", "to":"第三方", "by":"承辦人A" } ] }
```

### 2.7 `GET /health`

```json
{ "ok": true, "version": "0.1.0", "region": "us-west-2",
  "bedrock": { "model": "us.anthropic.claude-sonnet-4-5-20250929-v1:0", "reachable": true, "concurrency": 3, "startInterval": 2 },
  "s3": { "bucket": "ntpc-law3-deploy-229004791954", "prefix": "", "ok": true },
  "dynamodb": { "table": "appeal-cases", "ok": true },
  "tools": { "pdftotext": true, "pdftoppm": true, "pdfinfo": true, "file": true, "soffice": true, "ffmpeg": true, "ffprobe": true, "qpdf": true, "unzip": true },
  "missingRequired": [], "degraded": [] }
```
`ok=false` → HTTP 503，條件是 **必要工具**（`pdftotext/pdftoppm/pdfinfo/file`）缺少，或 Bedrock／S3／DynamoDB 不通。
選配工具（soffice／ffmpeg／qpdf／unzip）缺少不影響 `ok`，只會列在 `degraded`，該格式回 `unsupported`。
前端開頁先打它；掛了就顯示錯誤，**不退回假資料**。

## 3. 儲存

| 資料 | 位置 | Key |
|---|---|---|
| 原檔 | S3 | `cases/{caseId}/raw/{fileId}.{ext}`（`S3_PREFIX` 有值時再前置，本機開發用 `dev/`）|
| 正規化產物 | S3 | `cases/{caseId}/normalized/{fileId}/meta.json`、`p{N}.jpg`、`f{N}.jpg` |
| File／Segment／人工修正 | DynamoDB `appeal-cases` | PK `CASE#{caseId}`　SK `FILE#{fileId}` |
| Job | DynamoDB | PK `JOB#{jobId}`　SK `META`；事件 SK `EVT#{seq}` |
| 稽核 | DynamoDB | PK `CASE#{caseId}`　SK `AUDIT#{ISO時間}#{seq}` |
| 分類 cache | DynamoDB | PK `CACHE#{sha256}`　SK `{model}#{promptHash}` → segments |

S3 bucket 全 private，前端一律拿 presigned URL；`Content-Disposition` 帶 `suggestedName`，下載即得標準檔名，S3 key 不改。

## 3.1 重複檔的 fileId

`fileId` 取自 sha256 前 12 碼，所以同內容不同檔名會撞號。重複者一律另給 id，**不覆蓋正本**：
同批或跨批上傳重複 → `{sha12}-d{n}`；zip 子檔與既有檔重複 → `{sha12}-z{n}`。兩者 `duplicateOf` 都指向正本。

## 4. 限制

- Bedrock ≤ 1 RPS：所有箱序列處理；同時多個 job 排隊（單一 worker）
- 每箱 ≤ 10 檔 / ≤ 20 圖 / ≤ 120k 字；case02 18 檔約 90–140 秒
- 單檔 ≤ 100 MB，整批 ≤ 500 MB；掃描 PDF ≤ 200 頁
- 影片只抽 3 幀判類型，不分析內容
- 合併卷宗回多段但**不拆檔**（下游用 `fromPage/toPage` 定位）
- 實測：27 檔（含 20 頁合併卷宗、zip、heic、office）約 85 秒 3 箱；純 case02 18 檔約 62 秒 2 箱
