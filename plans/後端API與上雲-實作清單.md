# 後端 API 與上雲 — 實作清單

> 日期：2026-09-12　依據：`docs/API-文件歸戶.md`（契約）、`docs/部署方案-後端.md`（基礎設施）
> 前置已完成：`server/normalize.mjs`（35 案綠）、`server/classify.mjs`（41 檔全對、亂檔名全對、本機 cache）
> 狀態標記：☐ 待做　☑ 完成　✗ 取消

---

## 0. 待拍板（未回覆採預設）

- ☐ 建議檔名格式 → 預設：**採前端格式** `{序}-{doc_type}_{114-09-18}.{ext}`（日期帶連字號、不附來源；來源已是分組）
- ☐ IAM Role 是否建得了 → 你先跑 `aws iam create-role --role-name appeal-ec2 … --profile hackathon`；被拒 → 走臨時憑證路線（§4 第 29 條）
- ☐ 本機開發用的雲端資源前綴 → 預設：`S3_PREFIX=dev/`、`DDB_TABLE=appeal-cases`（同表，PK 帶 `dev#` 前綴），不另開表

## 1. Store 層 `server/store/`

1. ☐ `s3.mjs`：`putRaw(caseId, fileId, ext, buffer)`、`putNormalized(caseId, fileId, dir)`（meta.json + 頁圖）、`presignGet(key, {filename})`（15 分鐘，`Content-Disposition` 帶 suggestedName）
2. ☐ `ddb.mjs`：單表 helper —— `putFile`、`getFile`、`listFiles(caseId)`、`updateFile(patch)`、`putJob`、`getJob`、`appendEvent(jobId, evt)`、`listEvents(jobId, afterSeq)`、`appendAudit`、`listAudit`、`cacheGet(sha)`、`cachePut`
3. ☐ 環境變數：`S3_BUCKET`、`S3_PREFIX`（預設空）、`DDB_TABLE`、`AWS_REGION`；缺 `S3_BUCKET`/`DDB_TABLE` 啟動即報錯退出，不假跑
4. ☐ 本機 `.env`（gitignore）指向真實 bucket/表＋`S3_PREFIX=dev/`

## 2. `server/server.mjs`

5. ☐ Express + multer（memory storage，單檔 100 MB、整批 500 MB → 413 `PAYLOAD_TOO_LARGE`）
6. ☐ `POST /api/cases/:caseId/files`：sha256 → 同批／該案既有重複標 `duplicate` → 原檔上 S3 → 建 File（`queued`）＋ Job → 202 回 `{jobId, files, eventsUrl}` → 丟進佇列
7. ☐ Job 佇列：**單 worker 序列**（1 RPS）；每 job：逐檔 normalize → 推 `normalized` 事件、正規化產物上 S3 → `pack()` → 逐箱 classify → 推 `box`/`result` → `annotateTiming` → 寫 File `done`/`error` → 推 `done`；`BEDROCK_UNAVAILABLE` → 推 `fatal`、job `failed`
8. ☐ 事件持久化：每個事件 `appendEvent` 到 DynamoDB（`EVT#{seq}`），SSE 從 DB 回放，重連帶 `Last-Event-ID` 補推
9. ☐ `GET /api/jobs/:jobId/events`：SSE（`Cache-Control: no-cache`、`X-Accel-Buffering: no`）；先回放已存事件，再 live 推；`done`/`fatal` 後關閉
10. ☐ `GET /api/jobs/:jobId`：輪詢版
11. ☐ `GET /api/cases/:caseId/files`：含 `groups`（五組含未知，依人工修正後 source）、`cutoffDate`、每檔 `rawUrl`/`pageImageUrls` presigned；`?includeExcluded`
12. ☐ `PATCH /api/cases/:caseId/files/:fileId`：驗枚舉（400 `VALIDATION`）→ 改 `doc_type`/`source`/`suggestedName`/`excluded` → 未給名則重算 → `nature` 重算、裁處書日期變動則整案 `timing` 重算 → 每欄一筆稽核 → 回更新後 File
13. ☐ `GET /api/cases/:caseId/audit`
14. ☐ `GET /api/health`：Bedrock 憑證（`ListFoundationModels` 或最小 Converse）、五個外部工具 `which`、S3 `HeadBucket`、DDB `DescribeTable`；任一 false → 503
15. ☐ 錯誤處理：統一 `{code, message, retryable}`；未捕捉例外 → 500 `INTERNAL`＋log；**沒有任何 fallback 假資料**
16. ☐ 日誌：每個 Bedrock 呼叫記 `jobId/box/ms/tokens`；stdout（systemd journal 收）

## 3. 本機端到端（`server/eval/api.test.sh`）

17. ☐ `node server.mjs` 起本機（`.env` 指 dev 前綴）
18. ☐ `curl /api/health` → 200，tools 全 true
19. ☐ `curl -F files=@…×18` 上傳 case02 亂檔名版 → 202、18 筆、含 1 筆 `duplicate`（同檔上傳兩次）
20. ☐ `curl -N /api/jobs/{id}/events` → `normalized`×18 → `box`×2 → `result`×18 → `done`
21. ☐ 上傳 `卷宗全卷合併.pdf` → `result.segments` 17 段
22. ☐ 上傳 `truncated.pdf` → 該檔 `ok:false, NORMALIZE_FAILED`，job 仍 `done`
23. ☐ `PATCH` 一檔 source 未知→第三方 → `GET files` 的 `groups` 移組、`audit` 一筆
24. ☐ `PATCH` 給非法枚舉 → 400
25. ☐ 中斷 SSE 再帶 `Last-Event-ID` 重連 → 補推不重複
26. ☐ `aws s3 ls s3://…/dev/cases/…` raw 與 normalized 都在；DynamoDB 有 FILE/JOB/EVT/AUDIT 項

## 4. 部署檔 `deploy/`

27. ☐ `ec2-userdata.sh`、`appeal.service`（加 `MemoryMax=1.6G`）、`nginx.conf`、`iam-policy.json` 從部署方案文件落成檔案
28. ☐ `server/.env.example` 補 `S3_BUCKET`/`S3_PREFIX`/`DDB_TABLE`/`BOX_FILES`/`MODEL`；根 README 環境需求改 Node 20＋外部工具，移除 `requirements.txt` 說明
29. ☐ 若 IAM Role 建不了：user-data 改為讀 `/home/app/repo/server/.env.production` 裡的 `AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN`（機器上手填、不進 repo、賽後撤銷）

## 5. 上雲（你跑，指令在 `docs/部署方案-後端.md` §3）

30. ☐ S3 bucket（block public）＋ CORS
31. ☐ DynamoDB `appeal-cases`
32. ☐ IAM Role + Instance Profile（或 §4 第 29 條退路）
33. ☐ EC2 t3.small、SG 22/80/443、user-data
34. ☐ ssh 上去填 `.env.production`、`systemctl status appeal`
35. ☐ HTTPS：`certbot --nginx -d <ip>.nip.io`

## 6. 雲上驗證

36. ☐ `curl https://<host>/api/health` → ok
37. ☐ 雲上重跑 §3 第 19–23 條（case02 亂檔名、合併卷宗、壞檔、PATCH）
38. ☐ 瀏覽器開 `https://<host>/` 前端載入（仍 mock，接線是下一輪）
39. ☐ `journalctl -u appeal` 看 Bedrock 耗時／token log
40. ☐ 記錄 Live Demo 網址進 `docs/提案/url.md`

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
