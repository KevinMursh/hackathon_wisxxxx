# 分析階段 Pipeline — 我要做什麼、技術棧、驗收

> 日期：2026-09-12　負責：分析階段（Tab 1–5 的資料來源）　現況：`experiments/` 已在 case02 跑通一輪（6 次呼叫、2 分鐘）
> 上游：隊友的 `server/`（文件歸戶，Node/Express）　下游：`prototype/` 五個分頁

---

## 1. 一句話

**承辦人上傳卷宗後，系統自動產出五個分頁的內容（欄位、爭點、法規、相似案例、決定書草稿），每個結論都能點回卷證原句與真實條號，承辦人只在不同意時提異議。**

不是「AI 替承辦人決定」，是「AI 把例行比對做完，把證據攤開」。

## 2. 我真正要交付的東西

| 交付 | 形式 |
|---|---|
| 分析 API | `POST /api/cases/:id/analyze` → SSE 逐步推 `s2…s6` 結果 → `GET /api/cases/:id/analysis` 取完整 JSON |
| 五步輸出 schema | 對齊 `prototype/data.js` 的 `fields / period / checks / issues / laws / citations / sims / drafts`，前端零改動可接 |
| 異議 API | `POST /api/cases/:id/objection` → 採納／部分採納／無法採納＋證據；採納則重產草稿新版本 |
| 可追溯 | 每個爭點、每段草稿附〔檔名〕＋原文 quote；每條法條附字典查核狀態 |
| 兩案驗證 | case02（廢清法 79I 駁回）為主線；case03（建築法 81I 撤銷）不改任何東西也要合理 |

## 3. 固定 pipeline（不是 agent）

```
上傳卷宗 ─► [隊友] normalize + classify ─► docs{text, images, doc_type, source}
   │
   ├─ s2 欄位擷取      1 次 Converse（文字＋掃描圖，tool-use 強制 JSON）
   ├─ 期間／程序審查   0 次（程式：§14 次日起 30 日、八款檢核）
   ├─ s3 爭點          1 次（訴願書 vs 答辯書 vs 卷證，每爭點附 quote）
   ├─ s4 法規          KB Retrieve（法規＋判解＋函釋）＋ 1 次挑選 ＋ 程式條號查核
   ├─ s5 相似案例      KB Retrieve（101 決定書，領域 filter，排除本案）＋ 1 次「為何相似」
   └─ s6 草稿          1 次串流（few-shot：相似決定書理由段）＋ 程式查核草稿內所有條號
異議：1 次重論證（＋採納時 1 次重產草稿）
```

理由：1 RPS 下呼叫次數必須可預測；輸出形狀被前端釘死；一半步驟是程式邏輯；每步落地可單步重跑、可做 eval。

## 4. 後端技術棧（全部在允許清單內）

| 層 | 服務 | 用途 | 狀態 |
|---|---|---|---|
| 運算 | **EC2** t3.large, us-west-2, `i-0317e2f9af300f2bf` | Node 20 + Express（隊友 server）＋ pipeline；systemd | ✅ 已跑，IAM Role 建得了（隊友清單 §0 第 2 項可打勾） |
| 模型 | **Bedrock Converse** — Claude Sonnet 4.5 `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | 文字＋圖片、tool-use JSON、串流、prompt cache | ✅ 本機／EC2 皆驗證 |
| 檢索 | **Bedrock Knowledge Base** + **S3 Vectors** + embedding `cohere.embed-multilingual-v3` | 法規／判解／函釋／101 決定書的語意檢索，metadata filter | ☐ 待建（§5） |
| 檔案 | **S3**（private，Block Public Access） | 原始卷宗、normalized 文字與頁圖、KB 語料、部署包 | ✅ bucket 有 |
| 資料 | **DynamoDB** 單表 | case / file / job / event / audit / 每步分析結果 / cache | ☐ 隊友清單 §1 |
| 身分 | **IAM Instance Profile** `ntpc-law3-ec2-role` | bedrock:Invoke*/Retrieve/Rerank、s3、dynamodb、SSM | ✅（需補 dynamodb 與 KB 的 Retrieve 資源） |
| 維運 | **SSM Session Manager**、systemd journal、SG 只開 80 給會場四 IP | 免 SSH、看 log | ✅ |
| 機器上工具 | poppler-utils、ffmpeg、libreoffice、file | PDF 抽字、頁圖、影片抽幀 | ☐ user-data 補裝 |
| 選配 | CloudFront（HTTPS）、Cognito（登入） | 有時間再做 | ✗ 本輪不做 |

不用的：Textract（繁中支援不明，Claude 視覺已夠）、SageMaker（無 GPU、不訓練）、Step Functions／Bedrock Agents／AgentCore（固定 pipeline 用不到）。

**要對齊的兩件事**：隊友部署方案寫 us-east-1、profile `hackathon`、SG 開 22；現有 EC2 在 us-west-2、profile `ntpc-hackathon`、SG 無 22（走 SSM）。建議統一到現有這台，DynamoDB 建在 us-west-2。

## 5. 優化：接 Bedrock Knowledge Base

現在 s4 只靠 11 部法規的條號字典，判解 19 篇、函釋 10 篇沒接；s5 靠檔名規則。KB 補的是「語意找候選」，字典保留做「條號存在性查核」，兩層都要。

| 項 | 做法 |
|---|---|
| 語料 | S3 `kb/` 下四個 prefix：`laws/`（11 法規 txt，按條切）、`rulings/`（19 判解）、`letters/`（10 函釋＋自行蒐集 3）、`decisions/`（101－3＝98 決定書）。**評測三案對應決定書不放進去** |
| metadata | 每檔一個 `.metadata.json`：`{"kind":"decision","law":"廢棄物清理法","clause":"79I","result":"駁回","year":113}`；法規：`{"kind":"law","law":"訴願法","article":"14"}` |
| 向量庫 | S3 Vectors（免開 OpenSearch 叢集）；embedding cohere multilingual v3；chunk 固定 300 token、overlap 20% |
| s4 用法 | `Retrieve(query=爭點標題＋事實一句, filter kind in [law, ruling, letter], topK=8)` → 候選給模型挑 → 程式用字典核對條號 → 不存在者標 `unverified` |
| s5 用法 | `Retrieve(query=違規事實＋爭點, filter kind=decision AND law=本案法規, topK=10)` → 程式依款次／年度重排 → top 5；比檔名規則多的是「同法不同款次但爭點相似」的案 |
| s6 用法 | few-shot 改送相似決定書「理由段」chunk（約 2k 字）而非整份，省 token、更貼爭點 |
| 額度 | Retrieve 不算模型呼叫 RPS？不確定——ingestion 若被節流，退路是本機 numpy（98 份約 3k chunk，cohere 一次 96 段，30 次呼叫可完成） |

## 5.1 法規庫（v6 畫面）的後端 —— KB 就是法規庫

v6 加的「法規庫」畫面（法規／函釋、修正日期、三時點、引用查核「未收錄」、相似案例「可借用」、「同步全國法規資料庫」）與 KB 是同一份資料：

| v6 畫面元素 | 後端來源 | 狀態 |
|---|---|---|
| 法規 12 部（名稱、修正日、條數、來源、涉案數） | `pipeline/lawlib.py` ← lawdb（資料集 PDF）＋ 101 決定書引用計數 | ✅ 數字與前端 LAWLIB 一致 |
| 函釋 12／判解 19 | KB 語料 `letters/`、`rulings/` metadata | ✅ |
| 三時點（行為時／裁處時／決定時）＋每條「版本一致／須依行政罰法 §5 比較」 | `to_frontend`：dates 由 s2 欄位算；`lawlib.version_check` 比修正日 | ✅ |
| 引用查核「未收錄」 | `not_in_dataset` → `pending` | ✅ |
| 相似案例「可借用：該案理由○ → 本案爭點○」 | s5 schema `borrow_from/for/what`；s6 草稿段落〔借自：…〕→ `paras[].borrow` | ✅ |
| **同步全國法規資料庫** | `kb/sync_laws.py`：逐部抓 law.moj.gov.tw 官方頁 → 修正日期、生效狀態、全文 → 比對 → `runs/lawsync.json`；有新修正者寫入 KB `laws/{法規}（現行）` 並 re-ingest | ✅ 真實結果：12 部比對，**廢棄物清理法 106-06-14 → 官方 115-07-15（部分條文 117-07-15 生效）、民法 → 115-08-17**；**裁罰準則（資料集沒有）補入 6 條**，case02 引用查核的「未收錄」因此可查 |
| 法規庫畫面資料 | `frontend.lawlib = {laws, rulings, judgments, sync}` | ✅ |

規則：資料集版本＝行為時法（主）；同步下來的現行版另存「（現行）」；三時點比對用官方修正日 → 廢清法案件行為時 114 年、修正 115-07-15 → 版本一致（修正在行為後）但要提示承辦人決定時已有新法。

## 6. 驗收

| # | 步驟 | 預期結果 |
|---|---|---|
| P1 | `run_all case02` | 6–8 次模型呼叫、≤ 3 分鐘、每步落地 `runs/case02/*.json` |
| P2 | s2 欄位 | 文號、裁處日、罰鍰、行為日與 `03-卷宗清單.md` 一致；送達日來自送達證書（非訴願書自述）；自述不符列入 conflicts |
| P3 | 期間 | 截止日＝送達＋30；在期間內／逾期判定正確；缺送達證書時回「無法起算」不猜 |
| P4 | s3 爭點 | 涵蓋標準答案論證點 4、6（卷證事證、駁斥訴願主張）；每爭點 ≥ 1 則 quote 且 quote 可在該檔文字中找到 |
| P5 | s4 法規 | 涵蓋標準答案「相關法條」全部；含處分機關權限依據（§4＋公告）；推薦條號 100% 在字典查得到或標 `not_in_dataset`；0 則 `unknown_law` |
| P6 | s4 函釋 | 接 KB 後，環保署 108 年函出現在推薦（標準答案點 3） |
| P7 | s5 相似 | 不含本案自身決定書；top 1 同法同款次；每件有一句「為何相似」 |
| P8 | s6 草稿 | 主文與款次＝標準答案（case02：駁回、§79 I）；純文字含主文／事實／理由／據上論結／教示；草稿內所有條號查核非 `unknown_law`；理由段涵蓋標準答案 7 點中 ≥ 6 |
| P9 | case03 不改任何東西 | 主文＝撤銷、§81 I；爭點含行政罰法 §27 裁處權時效；草稿無 case02 字眼 |
| P10 | 異議 | 對爭點 2 填「照片模糊」→ 無法採納＋指向影像放大標註與影片幀；對爭點 3 填「未個別審酌」→ 回覆有理由且引裁罰係數表 |
| P11 ✅本機／☐雲上 | API | `POST analyze` → SSE 五個 step 事件順序正確 → `GET analysis` 形狀通過前端 `data.js` 同名欄位 |
| P12 | 雲上 | 同一組 curl 在 `http://100.20.156.38/api/…` 跑過；journal 有每次呼叫的 ms／tokens |
| P14 | 法規庫 | `lawlib.laws` 12 部日期／條數與前端 LAWLIB 一致；函釋 12、判解 19 |
| P15 | 同步 | `sync_laws` 回 12 部比對結果；廢清法標 changed（官方 115-07-15）；裁罰準則 added；`lawsync.json` 可餵前端 syncLog |
| P16 | 三時點 | case02 每條法規 version 為「一致」；case C（洗錢防制法，行為 113-02-07，修正 113-07-31）→ 「須依行政罰法 §5 比較」且 alert 由比對產生 |
| P17 | borrow | sims 至少 2 件有 borrow；草稿至少 1 段帶 borrow 標記 |
| P13 | 規範 | 全程 Bedrock ≤ 1 RPS（log 相鄰呼叫間隔 ≥ 1 s）；評測三案決定書不在 KB；S3 無公開 |

## 7. 順序

1. s4 prompt 補「處分機關權限依據」＋接 `行政函釋/`、`判解/` 全文（先不用 KB，直接塞候選）→ P5
2. case03 跑一次 → P9
3. 異議步驟 → P10
4. 把 pipeline 搬進 `server/`（Node）或由 Node 呼叫 Python 子程序——與隊友定 → P11、P12
5. KB（有時間才做）→ P6，s5 換語意檢索

## 8. 不做

- 自訓／微調模型、Textract OCR、Agent 自主規劃
- 主管核可流程、登入
- 合併卷宗真拆檔（隊友 v5）
