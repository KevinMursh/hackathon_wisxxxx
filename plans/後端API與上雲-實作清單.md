# 後端 API 與上雲 — 實作清單

> 日期：2026-09-12　依據：`docs/API-文件歸戶.md`（契約）、`docs/部署方案-後端.md`（基礎設施）
> 前置已完成：`server/normalize.mjs`（35 案綠）、`server/classify.mjs`（41 檔全對、亂檔名全對、本機 cache）
> 狀態標記：☐ 待做　☑ 完成　✗ 取消
> 更新：2026-09-12　**已上線** http://100.20.156.38/（SG 僅開會場四組 IP ＋ 開發者 IP，無公開存取）

---

## 0. 待拍板（未回覆採預設）

| 決策 | 結論 | 依據 |
|---|---|---|
| 後端語言 | **Node 統一**（選項 C） | 隊友 `src/backend` FastAPI 僅有 health/chat，業務邏輯未實作；兩個 runtime 各持一把 1 RPS 鎖會超限 |
| 沿用隊友基礎設施 | IAM Role `ntpc-law3-ec2-role`、部署桶、SG（會場四組 IP）、EC2 `i-0317e2f9af300f2bf`、SSM `push.sh` | 已建好可用；region 改為 **us-west-2** |
| 建議檔名 | `{序}-{doc_type}_{114-09-18}.{真實副檔名}` | 採前端 `STD_NAME` 格式；副檔名以 magic bytes 為準（`其實是jpg.pdf` → `.jpg`），重新命名才有意義 |
| Bedrock 併發 | 起跑間隔 **2.0s**、同時在途 **3** | 規範限每秒請求數非同時數；實測 case02 91s→62s、零 429；現場異常改 `BEDROCK_CONCURRENCY=1` |
| 每箱檔數 | **10** | 實測 1/5/10 檔：179s / 128s / 91s；再加大受 20 圖硬上限與 8k 輸出上限擋住，邊際效益低 |
| 三軸欄位 | `source` 問模型；`nature`（主張/紀錄/證物）查表；`timing` 整案以裁處書日期為界 | 同類文件性質固定；時點需整案視野，單檔問模型會錯 |
| 來源未知 | 「未知」是正式值，無身分證據不猜 | `05-採證照片彙整頁.pdf` 無抬頭印信文號 → 回未知為正確（已更正 manifest 正解） |
| 本機隔離 | `S3_PREFIX=dev/` 兼作 DynamoDB PK 命名空間；不另開表 | — |
| EC2 OS | 現有 AL2023 **沒有 LibreOffice／ffmpeg** | user-data 要補（RPM／static build）或換 Ubuntu；會動到隊友的檔，需先知會 |

## 1. Store 層 `server/store/`

1. ☐ `s3.mjs`：`putRaw(caseId, fileId, ext, buffer)`、`putNormalized(caseId, fileId, dir)`（meta.json + 頁圖）、`presignGet(key, {filename})`（15 分鐘，`Content-Disposition` 帶 suggestedName）
2. ☐ `ddb.mjs`：單表 helper —— `putFile`、`getFile`、`listFiles(caseId)`、`updateFile(patch)`、`putJob`、`getJob`、`appendEvent(jobId, evt)`、`listEvents(jobId, afterSeq)`、`appendAudit`、`listAudit`、`cacheGet(sha)`、`cachePut`
3. ☐ 環境變數：`S3_BUCKET`、`S3_PREFIX`（預設空）、`DDB_TABLE`、`AWS_REGION`；缺 `S3_BUCKET`/`DDB_TABLE` 啟動即報錯退出，不假跑
4. ☐ 本機 `.env`（gitignore）指向真實 bucket/表＋`S3_PREFIX=dev/`

## 2. `server/server.mjs`

5. ☑ Express + multer（memory storage，單檔 100 MB、整批 500 MB → 413 `PAYLOAD_TOO_LARGE`）
6. ☑ `POST /api/cases/:caseId/files`：sha256 → 同批／該案既有重複標 `duplicate` → 原檔上 S3 → 建 File（`queued`）＋ Job → 202 回 `{jobId, files, eventsUrl}` → 丟進佇列
7. ☑ Job 佇列：**單 worker 序列**（1 RPS）；每 job：逐檔 normalize → 推 `normalized` 事件、正規化產物上 S3 → `pack()` → 逐箱 classify → 推 `box`/`result` → `annotateTiming` → 寫 File `done`/`error` → 推 `done`；`BEDROCK_UNAVAILABLE` → 推 `fatal`、job `failed`
8. ☑ 事件持久化：每個事件 `appendEvent` 到 DynamoDB（`EVT#{seq}`），SSE 從 DB 回放，重連帶 `Last-Event-ID` 補推
9. ☑ `GET /api/jobs/:jobId/events`：SSE（`Cache-Control: no-cache`、`X-Accel-Buffering: no`）；先回放已存事件，再 live 推；`done`/`fatal` 後關閉
10. ☑ `GET /api/jobs/:jobId`：輪詢版
11. ☑ `GET /api/cases/:caseId/files`：含 `groups`（五組含未知，依人工修正後 source）、`cutoffDate`、每檔 `rawUrl`/`pageImageUrls` presigned；`?includeExcluded`
12. ☑ `PATCH /api/cases/:caseId/files/:fileId`：驗枚舉（400 `VALIDATION`）→ 改 `doc_type`/`source`/`suggestedName`/`excluded` → 未給名則重算 → `nature` 重算、裁處書日期變動則整案 `timing` 重算 → 每欄一筆稽核 → 回更新後 File
13. ☑ `GET /api/cases/:caseId/audit`
14. ☑ `GET /api/health`：Bedrock 憑證（`ListFoundationModels` 或最小 Converse）、五個外部工具 `which`、S3 `HeadBucket`、DDB `DescribeTable`；任一 false → 503
15. ☑ 錯誤處理：統一 `{code, message, retryable}`；未捕捉例外 → 500 `INTERNAL`＋log；**沒有任何 fallback 假資料**
16. ☑ 日誌：每個 Bedrock 呼叫記 `jobId/box/ms/tokens`；stdout（systemd journal 收）

## 3. 本機端到端（`server/eval/api.test.sh`）

17. ☑ `node server.mjs` 起本機（`.env` 指 dev 前綴）
18. ☑ `curl /api/health` → 200，tools 全 true
19. ☑ `curl -F files=@…×18` 上傳 case02 亂檔名版 → 202、18 筆、含 1 筆 `duplicate`（同檔上傳兩次）
20. ☑ `curl -N /api/jobs/{id}/events` → `normalized`×18 → `box`×2 → `result`×18 → `done`
21. ☑ 上傳 `卷宗全卷合併.pdf` → `result.segments` 17 段
22. ☑ 上傳 `truncated.pdf` → 該檔 `ok:false, NORMALIZE_FAILED`，job 仍 `done`
23. ☑ `PATCH` 一檔 source 未知→第三方 → `GET files` 的 `groups` 移組、`audit` 一筆
24. ☑ `PATCH` 給非法枚舉 → 400
25. ☑ 中斷 SSE 再帶 `Last-Event-ID` 重連 → 補推不重複
26. ☑ `aws s3 ls s3://…/dev/cases/…` raw 與 normalized 都在；DynamoDB 有 FILE/JOB/EVT/AUDIT 項

### 本機端到端實測（2026-09-12）

case02 完整卷宗 23 檔（18 卷宗 + 合併卷宗 + 重複檔 + 壞檔 + xlsx）：**145 秒**、3 箱、22 ok / 1 error（truncated.pdf）/ 1 duplicate。
`GET files` 回 groups（訴願人 3／原處分機關 12／第三方 2／本局 0／未知 5）、cutoffDate `114-09-16`、nature／timing 推導正確、presigned URL 可用；
合併卷宗 18 段；PATCH 未知→第三方後分組即時改變並寫入稽核；非法枚舉回 400；Last-Event-ID 重連補推 29 筆。
S3 78 個物件（raw + normalized meta/頁圖），DynamoDB 23 FILE + 44 EVT + AUDIT。

**修掉的 bug**：① patch 重複給 `updatedAt` → DynamoDB 拒絕整個 job；② SSE `maxSeq` 為 NaN 導致事件全被丟棄（只剩 keepalive）；③ 重複檔沿用 sha256 前綴當 fileId → 覆蓋正本紀錄，改為 `{sha12}-d{n}`。

## 4. 部署檔 `deploy/`

27. ☑ `deploy/node/{setup-tools,user-data,redeploy,push}.sh` + `app.service` + `README.md`（**與隊友 FastAPI 那套並存，未覆蓋**；不用 nginx，Node 直接聽 80 並 serve prototype/）
28. ☑ `server/.env.example` 補 `S3_BUCKET`/`S3_PREFIX`/`DDB_TABLE`/`BOX_FILES`/`MODEL`；根 README 環境需求改 Node 20＋外部工具，移除 `requirements.txt` 說明
29. ✗ 若 IAM Role 建不了：user-data 改為讀 `/home/app/repo/server/.env.production` 裡的 `AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN`（機器上手填、不進 repo、賽後撤銷）

## 5. 上雲（你跑，指令在 `docs/部署方案-後端.md` §3）

30. ☑ S3 沿用 `ntpc-law3-deploy-229004791954`（已 block public），案件存 `cases/` 前綴
31. ☑ DynamoDB `appeal-cases`（us-west-2，PAY_PER_REQUEST）
32. ☑ 沿用 `ntpc-law3-ec2-role`，已補 DynamoDB inline policy
33. ☑ 沿用現有 `i-0317e2f9af300f2bf`（t3.large、SG 只開 80 給會場四組 IP）——**待隊友點頭才切換 runtime**
34. ☑ 首次切換要先 SSM 跑 `setup-tools.sh`（LibreOffice 250MB，5–10 分鐘）
35. ✗ HTTPS：現況 SG 只開 80 給會場 IP，暫不做（要的話走 CloudFront）

## 6. 雲上驗證

36. ☑ `curl http://100.20.156.38/api/health` → ok
37. ☑ 雲上重跑 §3 第 19–23 條（case02 亂檔名、合併卷宗、壞檔、PATCH）
38. ☑ 瀏覽器開 `https://<host>/` 前端載入（仍 mock，接線是下一輪）
39. ☑ `journalctl -u app-node` 看 Bedrock 耗時／token log
40. ☐ 記錄 Live Demo 網址進 `docs/提案/url.md`

### 雲上驗收結果（2026-09-12，http://100.20.156.38/）

27 檔（case02 卷宗 18 ＋ 20 頁合併卷宗 ＋ 重複檔 ＋ 壞檔 ＋ xlsx/docx/heic/zip/負樣本）：
**85 秒、3 箱、26 ok / 1 error / 3 duplicate、孤兒紀錄 0**

| 檢查項 | 結果 |
|---|---|
| 卷宗 18 檔分類與建議檔名 | 全對 |
| 合併卷宗 20 頁 | 17 段 |
| 答辯書拆檢送函 | 2 段 |
| docx 委任書 | 訴願委任書／訴願人 |
| heic | 採證照片（ffmpeg 解碼） |
| zip | 母檔 container、子檔各自分類；與既有檔同內容者標 duplicate |
| 負樣本風景照 | 其他／未知 |
| truncated.pdf | `NORMALIZE_FAILED`，其餘檔照跑 |
| PATCH 未知→第三方 | 分組即時變更、nature 重算、稽核一筆 |
| 非法枚舉 | 400 `VALIDATION` |
| presigned 原檔 | HTTP 200 application/pdf |
| SSE `Last-Event-ID: 30` 重連 | 補推 30 筆 |
| health | ok:true、missingRequired 空、degraded 空 |

**部署中踩到並修掉的**：設定檔被 redeploy 的 `rm -rf` 刪掉（移到 `/etc/app-node.conf`）、
LibreOffice 24.8.x 下架 404（改抓 stable 最新）、AL2023 缺 X11 函式庫導致 soffice 裝了卻跑不動、
AL2023 無 heif-convert（改走 ffmpeg）、zip 子檔覆蓋正本檔名、bash 3.2 把全形括號當變數名。

## 6.1 待隊友確認才執行

切換會**停掉目前的 Live URL**（http://100.20.156.38/ 現在跑 FastAPI）。步驟與回退方式見 `deploy/node/README.md`。
兩個 systemd service（`app` / `app-node`）都綁 port 80，不能同時開。

## 7. 不在本輪

- 前端接線（`prototype/api.js`、步驟一吃 SSE、卷宗列 PATCH）
- 合併卷宗真拆檔
- 登入／權限
- 分析階段（欄位擷取、三方對照、草稿）

## 8. 驗收總表

| # | 步驟 | 預期 |
|---|---|---|
| A | 本機 `npm test` | 35 passed |
| B | 本機 `node eval/run.mjs --group all --messy` | doc_type ≥90％、source ≥85％、未知 100％、負樣本 100％、分段 2/2 |
| C | §3 第 17–26 條 | 全過 |
| D | §6 第 36–39 條 | 全過 |
| E | 主控台／journal 無未捕捉例外 | — |
