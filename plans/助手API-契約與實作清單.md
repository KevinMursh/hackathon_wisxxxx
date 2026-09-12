# 助手 API — 契約與實作清單（v7～v11 落地到真實程式碼）

> 日期：2026-09-13　依據：`plans/prototype-v7～v11-總確認清單.md`（使用者看到什麼）→ 本文（前後端傳什麼、怎麼驗）
> 真實程式碼在哪：前端 **`prototype/`**（Node `server.mjs` 直接 static 這個目錄，`deploy/node/push.sh` 打包它；`src/` 是 9d63f6b 的舊骨架，已不部署）；歸戶 `server/`（Node :80）；分析 `experiments/api.py`＋`pipeline/`（Python :8100，Node 反代）
> 已接線（ca9c204／c36f691，本文不重做）：上傳／demo／歸戶、s2–s6 分析、法規庫、提案確認走 `POST objection`、hash 路由
> 狀態標記：☐ 待做　☑ 完成　✗ 取消

## 0. 拍板

| 決定 | 內容 |
|---|---|
| 助手後端放哪 | Python `experiments/api.py`（pipeline、lawdb、KB retrieval、runs 快取都在這；三個 runtime 共用 1 RPS，助手與分析同一把 `_lock`） |
| 問／改怎麼分 | 兩層：① 程式 `classify_intent()` 先判（問句 → 工具清單**不含** `propose_revision`，模型無法提案）；② 模型在改句下可選 `propose_revision` 或 `ask_clarification`。可測、不靠 prompt |
| 提案不直接執行 | `propose_revision` 是終止工具：回前端畫卡。`confirm` 另一個端點才跑；`cancel` 只改狀態 |
| 確認後做什麼 | ① 爭點類 item 逐一 `objection.run(regen=False)` 重引證（採納／部分採納／無法採納＋卷證）② 其餘 item 程式判定（法規查得到→採納並保證加入推薦；查無→無法採納不寫入）③ 依「有效 item」的最小步驟從第 N 步起 `run_all.run(..., revision=…)` **真正局部重跑**：期間覆寫（不重打 s2）、認定寫入 s3 快取、法條程式加入／移除、結論改變相似案例排序、s6 附前一版草稿「未受影響段落維持原文」；全部無法採納 → 不重跑 |
| 預覽 | `POST proposals/{pid}/preview`：只改寫受影響段落（≤3 段各 1 次小呼叫、約 10–20 s）供提案卡畫 diff；結果快取在提案文件 |
| 往返方式 | `chat` 同步回（工具迴圈 ≤ 5 輪、單次 ≤ 60 s）；`confirm` 202＋job，前端輪詢 `GET analysis` 等 `objections[]` 增加（與現行 applyLiveProposal 相同） |
| 補件 | 走既有 `POST /api/cases/{id}/files`（同 caseId 累加）；結果視窗欄位對應 `segments[].suggestedName / doc_type / source / form / nature`；匯入＝重抓 `GET files`；無後端（mock 案）維持 v10b 行為 |

## 1. 端點（Python :8100，Node 反代加 `/api/cases/[^/]+/(chat|proposals/…)`）

### `POST /api/cases/{caseId}/chat`
```jsonc
// req
{ "message": "爭點 1 改採訴願人，影片看不出離手", "tab": 1, "readonly": false,
  "history": [{ "role": "user"|"assistant", "text": "…" }] }   // 最近 ≤ 6 則
// res 200
{ "kind": "answer" | "proposal" | "clarify" | "refuse",
  "text": "…",                                    // 純文字；answer 時為回答本體
  "sources": [{ "type": "law"|"decision"|"doc"|"state", "title": "…", "fileId"?: "…", "page"?: 1, "quote"?: "…" }],
  "cite_offer": { "law": "行政罰法", "article": "18", "para": "1" } | null,   // answer 查到法條 → 前端「以此提出修改」
  "proposal": null | {
    "id": "pp_ab12", "state": "pending", "summary": "…",
    "items": [ …§2… ], "scope": [2,3,4,5], "affected_tabs": [1,2,3,4] },
  "tool_calls": [{ "name": "lookup_article", "args": {…}, "ok": true }],
  "usage": { "input": 0, "output": 0, "ms": 0 } }
```
規則：`readonly=true`（已送審／已結案）→ 改句回 `refuse`；問句永遠不會回 `proposal`。

### `GET /api/cases/{caseId}/proposals/{pid}` → 提案文件（`state`: pending／applied／cancelled／failed；applied 時有 `replies[]`）
### `POST /api/cases/{caseId}/proposals/{pid}/confirm` → `202 {jobId, proposalId}`；進行中 `GET proposal` 的 `progress = {phase:"objection", i, n, label} | {phase:"rerun", step:"s4", steps:[…]}`；完成後 `state=applied`、`replies[]`、`rerun:["s4","s5","s6"]`、`version:"v2"`；`analysis.output` 整份換新（`drafts` 保留舊版＋新 vN、`issues[].afterObjection`）
### `POST /api/cases/{caseId}/proposals/{pid}/preview` → `{previews:[{type, para:"理由二", before, after}]}`
### `POST /api/cases/{caseId}/proposals/{pid}/cancel` → `{state:"cancelled"}`

## 2. `proposal.items[]`（與 prototype `parseIntent` 同形，伺服器補查核欄位）

| type | 欄位 | 伺服器補 | 影響起點 |
|---|---|---|---|
| `issue` | `id, to: appellant\|agency\|drop, why` | `n, title, from` | 2 |
| `reissue` | `id, docs:[fileId]` | `n, title` | 2 |
| `law` / `law-rm` | `n, art, p?, k?` | `ok, msg, amended, key, dup` | 3 |
| `served` | `v: "114-09-16"` | `from, deadline, inTime` | 0 |
| `proc` | `v: "merit"\|"77-N"` | — | 1 |
| `verdict` | `to: "撤銷"\|"駁回"\|"不受理"` | `from` | 4 |
| `text` | `para: "理由二", how` | — | 5 |
| `frame` | `angle` | — | 5 |

`scope` = 從最小起點到 5；僅 law → 跳過 4；僅 text/frame → [5]。

## 3. 工具（全部唯讀，除終止工具）

| 工具 | 做什麼 | 資料來源 |
|---|---|---|
| `lookup_article(law, article, paragraph?)` | 條文原文＋版本日期；查無回 status | `lawdb.lookup` ＋ `lawlib` 修正日 |
| `search_laws(query)` / `search_rulings(query)` / `search_decisions(query, law?)` | 語意檢索；決定書永遠排除本案自身 | `retrieval.retrieve`（KB） |
| `get_case_doc(name, page?)` | 本案卷證文字 | `ingest.load_any` |
| `get_case_state(section)` | fields／period／checks／issues／laws／citations／sims／judge／draft | `runs/{case}/analysis.json` |
| `check_period(served, recv)` | 期間試算 | `run_all.period_and_checks` |
| `propose_revision(items, summary)` | **終止**：回提案 | — |
| `ask_clarification(question)` | **終止**：回反問 | — |

## 4. 前端（`prototype/app.js`）

| # | 項目 | 狀態 |
|---|---|---|
| F1 | `Api.chat / proposal / confirmProposal / cancelProposal / waitJob` | ☑ |
| F2 | `asstSend`：真案（`S.c.live && S.c.caseId`）→ `Api.chat`；mock 案維持本機規則 | ☑ |
| F3 | `renderServerReply(res)`：answer → `.msg.a`＋來源＋「以此提出修改」；clarify／refuse → `.msg.a`；proposal → `fromServerProposal` → 既有 `renderProposal` | ☑ |
| F4 | 提案確認：真案 → `applyServerProposal`：`confirmProposal` → `waitJob`（逐項進度寫卡片）→ `analysis` → `toCase` → `renderTabs` 原地更新 | ☑ |
| F5 | 補件真案：`addFilesLive`：`upload` → 輪詢 job → `listFiles` → 新檔（staged／dup）進結果視窗（改類型／來源即 PATCH）→ 匯入 | ☑ |
| F6 | `api.js` 的 localhost 預設仍指雲端 `100.20.156.38`；`?api=` 可覆蓋 | 既有 |

## 5. 測試

### 5.1 Python（`experiments/tests/`，`pytest`，不打 Bedrock）
| 檔 | 驗什麼 |
|---|---|
| `test_assistant_unit.py` | `classify_intent`：10 句問／10 句改／反例；`compute_scope`；`verify_law_item`（lawdb：ok／條號超出／查無）；`check_period`；`get_case_state` 讀 case02 快取 |
| `test_assistant_chat.py` | 假 Bedrock（monkeypatch `common._converse`）：① 問句 → 模型即使想提案也拿不到工具 → `kind=answer`；② 改句 → 模型回 `propose_revision` → `kind=proposal`、items 補齊查核、scope 正確；③ 改句 → `ask_clarification` → `clarify`；④ `readonly` → `refuse`；⑤ 工具迴圈：模型先 `lookup_article` 再答 → `sources` 有 law |
| `test_assistant_api.py` | FastAPI `TestClient`、`ANALYSIS_DDB=0`：`POST chat` → `proposal.id` → `GET proposal` → `POST confirm`（objection.run 以假函式取代）→ job done → `state=applied`、`analysis.objections` +1 → `cancel` 已 applied 回 409 |
| `test_assistant_live.py` | `LIVE=1` 才跑：真打 Bedrock 兩句（一問一改），驗 kind 與 usage |

### 5.2 前端（`prototype/tests/`，gstack headless Chromium，本機 http.server）
| 檔 | 驗什麼 |
|---|---|
| `chat-cards.spec.sh` | 載入 mock case02，呼叫 `renderServerReply()` 灌 4 份 canned JSON（answer／proposal 3 項／clarify／refuse）：answer 出 `.msg.a` 無確認鈕、有「以此提出修改」；proposal 出 `.msg.card` 含 3 個 `.pc-item`、六步列、確認／取消；取消後 `.off`；clarify 無卡 |
| `intent.spec.sh` | mock 案：問句 10 句不出卡；改句 6 句出卡；「改好一點」反問 |

### 5.3 端到端（MCP Chrome「roy」）
| # | 站台 | 步驟 | 預期 |
|---|---|---|---|
| E1 | 本機 mock | 首頁 → case02 → 五分頁 → 助手問／改／確認 → 補件示範包 → 法規庫 → 案件庫 | ☑ 2026-09-13：法條問答有版本＋「以此提出修改」；提案卡 3 項；確認後原地重跑 4 步、Tab2「修正後：採訴願人」、plan C、已執行卡；補件示範包 2 份匯入、標「新」；法規庫 16 列、案件庫 2 列；助手在首頁／法規庫／案件庫隱藏；主控台無錯誤 |
| E2 | 雲上 http://100.20.156.38 | 首頁 → 載入 case02 卷宗包（真跑歸戶＋分析）→ 助手問「行政罰法第 18 條第 1 項」→ answer＋來源 | ☑ 歸戶 20/20 檔 46 s；分析 s2–s6 共 213 s；chat `answer`（8.9k tokens、7.4 s）：原文＋111-06-15 版＋來源＋「以此提出修改」 |
| E3 | 雲上 | 助手「爭點 1 改採訴願人，影片看不出離手」→ 提案卡 → 確認 → 原地更新 → 已執行卡 | ☑ 提案卡由伺服器 items 畫出（爭點卡＋法規列＋影響範圍 3–6）；確認 → 卡片顯示「AI 重新引證中 1/1」、四分頁「更新中」→ 已執行卡：**無法採納**，AI 引 15-採證照片證 1-1-2、17-採證影片審視結論等 5 處卷證逐點反駁；`objections` +1、修改 1 次；另一提案「加引行政罰法 §18 I」採納 → 草稿 v2 |
| E4 | 雲上 | 左欄補件上傳 1 張 jpg → 結果視窗類型／來源來自 API → 匯入 | ☑ 檔名 `messageImage_…jpg` → API 依內容判「採證照片／原處分機關」、標準檔名 `15-採證照片_114-06-27.jpg`、摘要「稽查員…煙蒂留置水溝蓋現場照片」；匯入後 23 件、標「新」；既有 22 份未重跑 |
| E5 | 雲上 | 「改好一點」 | ☑ `clarify`：反問並給 3 個例句，無卡 |

發現並修掉的雲上 bug：① `analysis-proxy.mjs` 對 POST 帶 JSON body 只轉發 content-length 不送 body → 上游等到逾時（objection／chat 全卡，既有 bug）；② Node 的 `GET /api/jobs/:id` 先攔走 `an_` job → 提案確認改輪詢 `GET proposal`（含 progress）；③ 模型 `revised_finding` 回「採機關（補強法條引用）」→ 正規化三值。
截圖：`/var/folders/x7/6h5dyqg15cq3wzk8q3cbmmbw0000gn/T/claude-chrome-screenshots-Xsr7aq/screenshot-1789231230000-0.jpg`（雲上提案卡）、`…-2.jpg`（已執行卡）、`…-3.jpg`（補件辨識結果）

## 6. 執行順序
1. ☑ `pipeline/assistant.py`（工具、迴圈、classify_intent、verify、scope）＋ `prompts/assistant.md`
2. ☑ `api.py` 三個端點＋提案持久化（runs／DDB `PROPOSAL#{pid}`）＋ `server/analysis-proxy.mjs` 路徑
3. ☑ 5.1 測試綠（46 passed；LIVE 3 skipped）
4. ☑ 前端 F1–F5
5. ☑ 5.2 測試綠（chat-cards 15／intent 18）
6. ☑ `deploy/analysis/push.sh`＋`deploy/node/push.sh`（順手修 proxy：POST 帶 JSON body 全卡的舊 bug）
7. ☑ 5.3 MCP 驗收（Chrome「roy」），結果見 §5.3
