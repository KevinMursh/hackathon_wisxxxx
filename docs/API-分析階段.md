# 分析階段 API 契約（步驟 2–5：欄位／爭點／法規／相似案例／草稿）

> 日期：2026-09-12　狀態：**後端已實作並本機驗證**（`experiments/api.py`，7 個端點全通；雲上部署見 `deploy/analysis/README.md`）
> 樣本：`docs/api-samples/case02.analysis.json`、`case03.analysis.json`（**就是 `GET /analysis` 的完整回應**：`status` + `output` + `objections`；case02 含 2 則無法採納的異議，case03 含 1 則採納→`drafts.v2`）、`lawlib.json`、`lawsync.json`——全部是 API 真實跑出來的，不是手寫 mock
> 上游：`docs/API-文件歸戶.md`（步驟一，已上線）

---

## 0. 前端要知道的三件事

1. **形狀對齊 `prototype/data.js`**：`fields / cls / period / checks / issues / laws / citations / alert / sims / simDist / drafts / refs` 鍵名相同，多了 `dates / judge / lawlib / files`。把 `CASE_B` 換成 `analysis.json` 的 `output` 就能畫。
2. **非同步用輪詢即可，不必接 SSE**：`GET /api/cases/{id}/analysis` 每 3 秒問一次，看 `status.steps` 哪幾步 `done`，到了就畫那個分頁。SSE 端點也有，想用再用。
3. **錨點多一種型別 `text`**：`refs[id] = [fileId, "text", {page, start, end}]`。定位是「該檔正規化文字第 page 頁的第 start–end 字元」（隊友 `normalized/{fileId}/meta.json` 的 `textPerPage[page-1]`）。前端切到該檔「擷取文字」檢視、反白那段即可。`doc` 型只開檔；`time` 型跳影片秒數。

---

## 1. Endpoints

| Method | Path | 說明 |
|---|---|---|
| `POST` | `/api/cases/{caseId}/analyze` | 步驟一 `done` 後呼叫。讀該案 files + normalized → 背景跑 s2→s6。回 `202 {jobId}`。同案重複呼叫回同一個進行中的 jobId |
| `GET` | `/api/cases/{caseId}/analysis` | 目前分析結果（見 §2）。未跑過 `404 ANALYSIS_NOT_FOUND`；跑一半回已完成的步驟＋`status` |
| `GET` | `/api/jobs/{jobId}/events` | SSE（選用）。事件：`step`（開始）→ `result`（該步資料）→ … → `done`／`fatal` |
| `POST` | `/api/cases/{caseId}/objection` | 異議：`{issueId, reason, cites: [fileId…]}` → `202 {jobId}`；完成後 `analysis.objections[]` 多一筆、採納時 `drafts` 多一版 |
| `POST` | `/api/cases/{caseId}/reanalyze` | 人工 PATCH 歸戶後重跑（同 analyze，但清掉快取） |
| `GET` | `/api/lawlib` | 法規庫畫面：`{laws[], rulings[], judgments[], sync}`（＝ `lawlib.json`） |
| `POST` | `/api/lawlib/sync` | 「同步全國法規資料庫」：逐部抓官方修正日期，回 `lawsync.json` 形狀；約 1–2 分鐘，回 `202 {jobId}` 後輪詢 `GET /api/lawlib` 的 `sync.checkedAt` |

錯誤格式同步驟一：`{code, message, retryable}`。

## 2. `GET /api/cases/{caseId}/analysis` 回應

```jsonc
{
  "caseId": "case02",
  "status": {
    "state": "running" | "done" | "failed",
    "steps": { "s2": "done", "s3": "done", "s4": "running", "s5": "pending", "s6": "pending" },
    "startedAt": "…", "finishedAt": null, "ms": { "s2": 38400, "s3": 28800 }
  },
  "output": { …下面 §3，只含已完成步驟的鍵… }
}
```

步驟 ↔ 分頁 ↔ 鍵：

| 步驟 | 分頁 | `output` 的鍵 |
|---|---|---|
| s2 | Tab 1 案件擷取 | `fields`、`cls`、`period`、`checks`、`dates` |
| s3 | Tab 2 爭點 | `issues` |
| s4 | Tab 3 法規 | `laws`、`citations`、`alert` |
| s5 | Tab 4 相似案例 | `sims`、`simDist` |
| s6 | Tab 5 草稿 | `drafts`、`judge` |
| 隨每步累積 | 跳轉 | `refs`、`files` |
| 固定 | 法規庫 | `lawlib` |

## 3. `output` 各鍵（與 data.js 的差異用 **粗體**）

```jsonc
"files":  [[suggestedName, fileId, doc_type, source, originalName], …]      // 顯示名／錨點用 fileId
"dates":  { "act": "114-06-27", "disp": "114-09-16", "decide": "114-12-21" } // 三時點（決定時＝收文＋3 月）

"fields": [{ "k": "收受・送達日", "a": ["114年9月16日","q3"], "d": ["114年9月16日送達","q4"], "e": ["114年9月18日送達","q5"],
             "conflict": "訴願人自述…以送達證書為準" }, …]                  // 同 data.js；ref 是 refs 的 key
"cls":    [["案件類型","違反廢棄物清理法"],["主要爭點","…"],["預判走向","實體審查"]]
"period": { "served","recv","appealSays","deadline","inTime", "servedRef","recvRef" }   // **多 deadline / inTime**
"checks": [["77(2)","於法定期間內提起","pass"|"fail"|"auto"|"na","說明"], …8 款]

"issues": [{ "id":"I1", "title", "a":[text,null], "d":[text,null], "e":[[text, ref]…],
             "law":[…], "finding":"採機關"|"採訴願人"|"待議", "reason":"一句依據" }]   // **無 lead/stance；多 finding/reason**

"laws": [{ "g":"實體法規"|"裁罰基準"|"程序法規"|"行政函釋"|"判解"|"其他", "n", "t", "rel", "badges":[[color,text]…],
           "why", "lib":"廢棄物清理法"|null,
           "version": { "warn": true, "amended":"115-07-15", "synced": true, "text":"…須依行政罰法 §5…" } | null }]  // **多 why/version；badges 是 [color,text] 不是 HTML**
"citations": [{ "n", "where", "ref":null, "status":"ok"|"gap"|"pending"|"unknown", "note" }]  // pending＝法規庫未收錄
"alert": { "title", "text" } | null                                          // 由三時點比對產生

"sims": [{ "fn", "s", "why", "one", "chips":[…], "result", "clause", "path",
           "borrow": { "from":"理由五", "to":"I1", "what":"…" } | null }]      // **多 one/result/clause/path；borrow.to 是爭點 id 不是段落 id**
"simDist": [["不受理",0],["駁回",2],["撤銷",3]]

"judge":  { "verdict":"訴願駁回", "art":"訴願法 §79I", "issues":[[title, finding]…], "risk":"low"|"mid"|"high", "riskNote", "unknownCites":[] }  // **新：判定列**
"drafts": { "A": { "tmpl":"79I", "head", "sub", "paras":[{ "id":"p7", "kind":"h4"|"p", "text", "refs":["q12"…], "borrow":["113年…案 理由三"]|null }] } }
                                                                             // **只有 A 一案；paras 純文字無 HTML；kind 無 meta**
"refs":   { "q1": [fileId, "text", {"page":1,"start":7,"end":14}], "q9": [fileId, "doc", null], "q20": [fileId, "time", 14] }
"lawlib": { "laws":[{ "n","kind","date","src","arts","cases","official","effective","status":"changed"|"same"|null,"currentArts" }],
            "rulings":[{ "n","topic","date","law","src" }], "judgments":[…同], "sync":{ "checkedAt","source","checked","changed","same","added" } }
"unverifiedQuotes": []                                                      // 引句回查失敗清單，正常為空
```

異議後（頂層 `objections[]` 與 `output` 的變化）：
```jsonc
"objections": [{ "issueId":"I2", "issueTitle", "originalFinding":"採機關", "reason":"承辦人填的", "cites":[fileId…], "by",
                 "result":"採納"|"部分採納"|"無法採納", "revised_finding":"採訴願人"|null,
                 "reply":"給承辦人的 3–5 句回覆", "evidence":[{file, quote}…], "draft_changes":[…], "at", "jobId" }]
"output.judge.afterObjection": { "issueId":"I2", "finding":"採訴願人", "version":"v2" }   // 採納時才有
"output.issues[i].afterObjection": "採訴願人"                                            // 採納時才有
"output.drafts.v2": { …同 A 的形狀…, "sub":"（異議後重產 v2・待承辦人審核）", "objectionId" }  // 採納／部分採納時多一版；refs 前綴 o1q…
```

## 4. 前端接線清單（步驟 2–5）

1. 分析中畫面步驟 2–5：由 `status.steps` 驅動（`running` 轉圈、`done` 打勾），不用 setTimeout
2. Tab 1：`checks` 8 款直接畫；`period.inTime=false` 時預判走向顯示「程序不受理」
3. Tab 2：把「AI 認定」標籤讀 `finding`，一句依據讀 `reason`；「對此有異議」送 `POST objection`
4. Tab 3：`laws[].version.warn` 畫 ⚠ 與文字；`badges` 改為 `[color,text]` 陣列；`citations.status=pending` 顯示「未收錄」；`alert` 直接畫
5. Tab 4：`borrow.to` 是爭點 id → 顯示「可借用：該案理由五 → 本案爭點 I1」；`path` 可展開 PDF
6. Tab 5：判定列讀 `judge`；`paras` 純文字（不再是 HTML）；段落 `borrow` 顯示「借自…」；`refs` 型別 `text` 要新增反白渲染
7. 法規庫畫面：`GET /api/lawlib` 取代 `LAWLIB/RULINGS` 常數；「同步」按鈕改打 `POST /api/lawlib/sync`，`syncLog` 顯示 `sync` 摘要（目前真實值：12 部比對、2 部新修正、10 部一致）
8. 卷宗瀏覽器：`refs` 的 `text` 型別 → 切「擷取文字」檢視 → 反白 `textPerPage[page-1][start:end]`

## 5. 本機開發：先用樣本

```js
// 開發期：直接 fetch 樣本；上線後把 URL 換成 /api/cases/{id}/analysis
const r = await fetch("docs/api-samples/case02.analysis.json");
const { output } = await r.json();   // 樣本沒有 status，視為全部 done
```

case03 樣本是「撤銷 §81 I、不附教示」路徑，拿來測 Tab 5 判定列與主文變化。

## 6. 不在契約內

- 步驟一（上傳、歸戶、PATCH、稽核）：見 `API-文件歸戶.md`
- 結案、法院結果、案件庫：仍走前端 localStorage（本輪不上雲）
- 助手問答：暫維持前端錨點索引
