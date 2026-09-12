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
| 確認後做什麼 | 爭點類 item → 既有 `objection.run`（重引證＋採納時重產草稿）；其他 item（法規／文字／角度／期間／程序／結論）併成一則 objection 的 reason 送同一條路（現況能力，不另開新 pipeline）；影響範圍由 item 類型算出給前端畫進度 |
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
### `POST /api/cases/{caseId}/proposals/{pid}/confirm` → `202 {jobId, eventsUrl}`；完成後 `analysis.objections[]` 增加、提案 `state=applied`、`replies[] = [{label, result, reply, evidence[]}]`
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
| F1 | `Api.chat / proposal / confirmProposal / cancelProposal` | ☐ |
| F2 | `asstSend`：真案（`S.c.live && S.c.caseId`）→ `Api.chat`；mock 案維持本機規則 | ☐ |
| F3 | `renderServerReply(res)`：answer → `.msg.a`＋來源＋「以此提出修改」；clarify／refuse → `.msg.a`；proposal → 走既有 `renderProposal`（items 已同形） | ☐ |
| F4 | 提案確認：真案 → `Api.confirmProposal` → 輪詢 → `toCase` → `renderTabs`（原地、v11 進度） | ☐ |
| F5 | 補件真案：`Api.upload(caseId)` → 輪詢 job → `listFiles` → 新檔列進結果視窗 → 匯入＝重抓 | ☐ |
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
| E1 | 本機 mock | 首頁 → case02 → 五分頁 → 助手問／改／確認 → 補件示範包 → 法規庫 → 案件庫 | 全部無主控台錯誤 |
| E2 | 雲上 http://100.20.156.38 | 首頁 → 載入 case02 卷宗包（真跑歸戶＋分析）→ 助手問「行政罰法第 18 條第 1 項」→ answer＋來源 | `kind=answer`，有版本日期 |
| E3 | 雲上 | 助手「爭點 1 改採訴願人，影片看不出離手」→ 提案卡 → 確認 → 原地更新 → 已執行卡 | `objections` +1、Tab2「修正後」 |
| E4 | 雲上 | 左欄補件上傳 1 張 jpg → 結果視窗類型／來源來自 API → 匯入 | 左欄多一檔標「新」 |
| E5 | 雲上 | 「改好一點」 | 反問無卡 |

## 6. 執行順序
1. ☐ `pipeline/assistant.py`（工具、迴圈、classify_intent、verify、scope）＋ `prompts/assistant.md`
2. ☐ `api.py` 三個端點＋提案持久化（runs／DDB `PROPOSAL#{pid}`）＋ `server/analysis-proxy.mjs` 路徑
3. ☐ 5.1 測試綠
4. ☐ 前端 F1–F5
5. ☐ 5.2 測試綠
6. ☐ `deploy/analysis/push.sh`＋`deploy/node/push.sh`
7. ☐ 5.3 MCP 驗收，結果寫回本文
