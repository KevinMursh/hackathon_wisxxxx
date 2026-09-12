# Prototype v8 — 首頁接文件歸戶後端　前後端工作清單

> 日期：2026-09-12　範圍：**首頁上傳 → 分析中步驟一 → 卷宗瀏覽器歸戶**接真後端（`docs/API-文件歸戶.md` v0.2，已上線 http://100.20.156.38/）
> 不含：分析階段 s2–s6（另見 `docs/API-分析階段.md`，隊友負責）、結案／案件庫／助手（維持 localStorage）
> 狀態標記：☐ 待做　☑ 完成　✗ 取消

---

## 0. 待拍板（未回覆採預設）

| # | 決策 | 預設 |
|---|---|---|
| D1 | 文字怎麼給前端 | 後端補 `GET /api/cases/{id}/files/{fileId}/text` 回 `{textPerPage[]}`；不走 presigned meta.json（省一次跨網域抓取、也不暴露內部結構） |
| D2 | 合併卷宗一檔多段怎麼列 | 卷宗清單**一個 segment 一列**（同 fileId＋`fromPage/toPage`），點擊開該檔並跳該頁；母檔不另列 |
| D3 | demo 按鈕 | 後端補 `POST /api/cases/{id}/demo`，從 S3 預放的 case02 卷宗包真跑一次（亂檔名版另一個 body 參數）。**評審會點這顆，必須是真的** |
| D4 | caseId 產生方式 | 前端產 `c{yyMMdd}-{4碼亂數}`，畫面上顯示為「暫編案號」，承辦人可改填真實案號（改了就用真的） |
| D5 | presigned 15 分鐘過期 | 前端在開啟文件時若 403，自動重打 `GET files` 換新 URL（不改後端 TTL） |
| D6 | 上傳失敗 | 不退回 mock。顯示錯誤碼＋訊息＋「重試」；`health` 不 ok 時首頁上傳鈕禁用並說明 |

---

## 1. 後端要做（`server/`）

| # | 項目 | 說明 | 估時 |
|---|---|---|---|
| B1 | ☑ `GET /api/cases/{id}/files/{fileId}/text` | 回 `{fileId, pages, textPerPage:[…]}`，從 S3 `normalized/{fileId}/meta.json` 讀。供「擷取文字」檢視與分析階段 `refs` 的 `text` 型錨點反白 | 0.5h |
| B2 | ☑ `POST /api/cases/{id}/demo` | body `{pack:"case02", messy:false}`。從 S3 `demo/case02/**` 讀檔 → 走與上傳相同的 job 流程（不是查表）。需先把卷宗包上傳到 S3 一次 | 1h |
| B3 | ☑ `GET files` 增補欄位 | 每檔加 `textUrl`（B1 的路徑）、`segments[].pageImageUrl`（該段首頁圖，清單縮圖用） | 0.3h |
| B4 | ☐ `GET /api/cases` | 案件清單（案件庫卡要用）：`[{caseId, files, updatedAt, 主要 doc_type}]`。DynamoDB 需加 GSI 或用固定 PK 存索引 | 0.5h |
| B5 | ☐ 保留期與清理 | demo 反覆上傳會累積 S3／DynamoDB；加 `DELETE /api/cases/{id}` 或 S3 lifecycle 7 天 | 0.3h |
| B6 | ☐ 部署 + 雲上驗證 B1–B4 | `push.sh` | 0.3h |

## 2. 前端要做（`prototype/`）

### 2.1 不需要後端就能先做（形狀先對齊）

| # | 項目 | 說明 |
|---|---|---|
| F1 | ☑ `SRC_ORDER` 加「未知」 | 卷宗瀏覽器四組 → **五組**；三方對照仍只吃訴願人／原處分機關／第三方，「未知」與「本局」不進對照 |
| F2 | ☑ `DOCTAG` 補到 27 類 | 色標對照表照 `server/schemas/enums.json`；缺色會變無樣式 |
| F3 | ☑ doc 物件改形狀 | `{fileId, segId, doc_type, source, nature, timing, suggestedName, originalName, summary, status, pages, fromPage, toPage, rawUrl, pageImageUrls}`；`autoClassify()` 退場 |
| F4 | ☑ 卷宗清單支援 multi-segment | 依 D2：一個 segment 一列，顯示 `doc_type` 與頁碼範圍 |
| F5 | ☑ `status` 呈現 | `duplicate` 灰字「重複」、`error` 紅字＋錯誤碼、`container` 不單獨列（只列子檔）、`excluded` 灰字 |
| F6 | ☑ 保留 File 物件 | `addFiles()` 目前只留 name/size，改存原始 `File` 以便 FormData |

### 2.2 要後端（接線）

| # | 項目 | 依賴 |
|---|---|---|
| F7 | ☑ `prototype/api.js`（端點與 toDocs 已寫並驗過，尚未被畫面呼叫） | 統一入口：`health / uploadFiles / streamJob / listFiles / patchFile / audit / loadDemo / fetchText`；含錯誤物件與 403 重取（D5） | — |
| F8 | ☑ 首頁上傳接 `POST files` | 產 caseId（D4）→ 202 → 進 s-run；`health` 不 ok 禁用按鈕（D6） | — |
| F9 | ☑ 分析中步驟一吃 SSE | `normalized` 先顯示格式／頁數；`result` 逐箱到、前端排隊演出逐檔浮現；`container` 顯示「壓縮檔展開 N 份」；`fatal` 顯示錯誤 | — |
| F10 | ☑ 進工作畫面改讀 `GET files` | `groups` 直接畫五組；`cutoffDate` 存起來給分析階段 | — |
| F11 | ☑ 就地修正接 `PATCH` | 改類型／來源 → 樂觀更新 → 失敗回滾；稽核從 `GET audit` 讀 | — |
| F12 | ☑ 文件檢視 | 文字類：`GET …/text` 渲染＋「原始 PDF」切換（`rawUrl`）；掃描／照片：`pageImageUrls`；影片：`rawUrl` | B1 |
| F13 | ☑ demo 按鈕改真跑 | 「載入 case02 卷宗包」「以亂檔名載入」改打 `POST demo` | B2 |
| F14 | ☐ 逾時與進度 | 預期 60–90 秒；顯示「已完成 N/M 檔」；超過 3 分鐘顯示逾時可重試 | — |

## 3. 建議執行順序

```
第 0 步（並行，互不擋）
  後端 B1 ─┐                     前端 F1–F6（用 docs/api-samples 與手寫樣本改形狀）
  後端 B2 ─┤ 兩支都做完再一起部署 B6
  後端 B3 ─┘

第 1 步  F7 api.js（契約已定，可在 B1/B2 未上線前先寫，端點缺就先報錯）
第 2 步  F8 → F9 → F10（上傳→步驟一→工作畫面，主線打通）
第 3 步  F11（PATCH）→ F12（文字／PDF／圖／影片檢視，依賴 B1）
第 4 步  F13 demo 真跑（依賴 B2）→ F14 逾時與進度
第 5 步  B4 案件庫、B5 清理（非主線，時間不夠可延）
```

**為什麼這個順序**
- F1–F6 是純前端整形，**不依賴任何後端**，可以立刻開工，也讓隊友在 B1/B2 還沒好時不會閒著
- B1（文字）擋住 F12，是後端最該先做的一支
- B2（demo）擋住 F13，但 demo 不擋主線——先確保「真上傳」跑得通，demo 只是把同一條路自動化
- B4／B5 與 demo 無關，放最後

## 4. 驗收

| # | 步驟 | 預期 |
|---|---|---|
| L1 | 首頁拖入 case02 卷宗包 20 檔 → 開始分析 | 202 取得 jobId，進分析中畫面 |
| L2 | 分析中 | 步驟一逐檔浮現「原檔名 → 類型・來源・一句摘要」，60–90 秒內完成 |
| L3 | 進工作畫面 | 卷宗瀏覽器依五組分列（含「未知」組）；重複檔灰字；壞檔紅字顯示錯誤碼 |
| L4 | 上傳 `卷宗全卷合併.pdf` | 依 D2 列出 17 列，點任一列開啟該檔並跳到對應頁 |
| L5 | 點訴願書 | 顯示擷取文字（`GET …/text`），可切換原始 PDF |
| L6 | 點掃描件／照片 | 顯示 `pageImageUrls` 頁圖 |
| L7 | 就地把某採證照片來源改「第三方」 | 立即移組；`GET audit` 有一筆；重整後仍在 |
| L8 | 點「載入 case02 卷宗包」demo | 真的走後端跑一次（非查表），結果與 L1 相同 |
| L9 | 關掉後端（或斷網）後上傳 | 顯示錯誤碼與訊息，**不出現假資料** |
| L10 | 放置 20 分鐘後再點文件 | presigned 過期自動換新 URL，仍可開啟 |
| L11 | 400px 寬 | 無橫向捲動；主控台無錯誤 |

## 4.1 本輪額外決定（2026-09-12）

| 決定 | 內容 |
|---|---|
| demo 入口只留一個 | 上傳區的「載入 case02 卷宗包／以亂檔名載入」小字連結**移除**，只留「清除」；示範案件卡成為唯一 demo 入口 |
| 亂檔名不砍 | 「以亂檔名 →」移到 case02 卡片上當次要動作——它證明判定看內容不看檔名，是系統重點 |
| 首頁只留一張卡 | 示範案件卡從 3 張減為 **1 張（case02，唯一有 S3 卷宗包能真跑的）**；A／C 兩案仍在 `CASES` 內供案件庫與測試使用，只是不在首頁露出 |
| 卡片加一句說明 | 單張卡有空間，把 `cardDesc` 放回來（原本被 v7 精簡掉），讓評審一眼知道這案有什麼 |
| mock 詞彙對齊後端 | `data.js` 的 5 個舊粗標籤（送達證書／影像放大／通知書／係數計算／影片）改成後端 27 類的正式名稱，mock 與真資料不再兩套詞 |
| 內嵌大圖也送模型 | 見 `文件歸戶與自動命名-實作計畫.md`：`pdfimages` 偵測 ≥500×300，解決「有文字層但頁面壓著照片」的流失 |

## 4.2 接線實測（2026-09-12，本機後端）

用 headless Chrome 點示範案件卡（亂檔名）走完整條路：

```
 0s  點卡片 → POST /api/cases/{id}/demo
34s  第一批 normalized 事件到，佔位列開始浮現
66s  第一箱 result 回來，佔位列就地替換成判定結果
72s  done：20 份完成・0 重複・0 失敗 → 進工作畫面
     卷宗 22 列（含合併段）、分組 訴願人 2／原處分機關 15／未知 5、主控台無錯誤
```

**修掉的效能問題**：demo 端點原本逐檔從 S3 序列下載（30 秒才回 202），改平行；
`ingest` 的 S3 上傳與 DynamoDB 寫入也從序列改平行（每批 6／10）。
上傳 15 檔 **4.1 秒**回 202；demo 本機 15.8 秒（大半是筆電對 S3 的頻寬，EC2 同區應更快，待部署後量測）。

**尚未接線**：分頁 2–5（欄位／爭點／法規／草稿）走 `docs/API-分析階段.md`，該 API 由隊友負責；
工作畫面上方有黃色提示條說明「卷宗歸戶為真實結果，分頁 2–5 尚未接線」，分頁鎖住不可點。

## 4.3 F11／F12 實測（2026-09-13）

**F12 文件檢視**（後端 kind 有 7 種，mock 只有 4 種，`pdf-text` 原本落到 fallback 顯示空白 → 這就是「PDF 不能 preview」的原因）

| kind | 工具列 | 內容 |
|---|---|---|
| `pdf-text` / `office` | 原始 PDF｜擷取文字｜頁面影像｜下載 | 預設內嵌 PDF；文字讀 `GET …/text`（實測抓到訴願書全文）；影像 2 張 |
| `pdf-scan` | 原始 PDF｜頁面影像｜下載 | 掃描件沒有文字層，不給文字分頁 |
| `image` | －｜＋｜重設｜影像｜下載 | 縮放與拖曳沿用原有行為 |
| `video` | 新分頁開啟 | `<video>` 直接播 rawUrl，標示時長與抽幀數 |
| 多段檔案 | — | PDF 以 `#page=fromPage` 開在該段起始頁；文字只顯示該段頁範圍 |

presigned 過期（15 分鐘）時影像載入失敗會自動重打 `GET files` 換新網址（D5）。

**F11 就地改歸戶**：樂觀更新 → `PATCH` → 失敗回滾並提示。實測把某採證照片從「未知」改「第三方」：
畫面即時移組、`GET files` 確認伺服器端已改、`GET audit` 留下 `source: 未知 → 第三方 by 承辦人`。

## 5. 不在本輪

- 分析階段 s2–s6 接線（另一份契約，隊友負責）
- 認證與 rate limit（現況靠 SG IP 白名單）
- 合併卷宗真拆檔（只回 segment）
