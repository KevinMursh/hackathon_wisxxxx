# TODO：`/api/lawlib` 補回 `pendingArticles`

> 日期：2026-09-13　狀態：☐ 未動工　負責：分析階段（Python 服務 :8100，`experiments/pipeline/lawlib.py`）

## 問題

法規庫的狀態欄要分辨三種「已修正」：

| 狀態 | 需要的資料 | 現況 |
|---|---|---|
| 已修正・{日}起施行（尚未生效） | `effective` 在未來 | ✅ 有（12 部裡 1 部抓得到：廢清法 117-07-15） |
| 已修正・部分條文尚未生效 | **`pendingArticles`** | ❌ **`/api/lawlib` 沒有回傳**（13 筆全無） |
| 已修正・{日} 公布（生效狀態不明） | 只有 `official` | 目前所有「無 effective」的都落這格 |

`sync_laws.py` 的 `parse()` **有**解析出 `pending`（整頁比對「尚未生效」字樣），也寫進 `lawsync.json`，
但 `lawlib.json` 的 `laws[]` 沒有帶出來，所以前端拿不到。

實例：民法 `official=115-08-17`、`effective=null`、`lawsync.pendingArticles=true`
→ 前端只能顯示「已修正・115-08-17 公布・施行日未載明」，無法說明「有條文尚未生效」。

## 要改

`experiments/pipeline/lawlib.py`（或組 `lawlib.json` 的地方）在 `laws[]` 每筆加：

```jsonc
"pendingArticles": true   // 來自 lawsync 的同名欄位
```

前端 `lawStatus()` 已經寫好對應分支，欄位一補上就會生效，不用再改前端。

## 附帶限制（要不要一併處理，看時間）

- `pendingArticles` 是**整頁比對「尚未生效」四個字**的粗篩，可能因頁面附註誤判；
  比較準的做法是解析條文區塊各自的生效標記，但工程量大，現階段標示為「依頁面標示」即可
- `effective` 取自頁面「最後生效日期」欄位，12 部只有 1 部有；沒有時**不可推定已生效**
