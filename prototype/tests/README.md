# prototype/tests — 前端瀏覽器測試（gstack 無頭 Chromium）

```bash
bash prototype/tests/chat-cards.spec.sh   # 助手卡片渲染：answer／proposal／clarify／refuse 灌後端契約 JSON → 驗元件（15 項）
bash prototype/tests/intent.spec.sh       # mock 案本機意圖規則：10 問句不出卡、6 改句出卡、模糊反問（18 項）
```
前置：`~/.claude/skills/gstack/browse/dist/browse` 存在；腳本會自行在 8765 起 http.server。
mock 案用 `#/case/B` 開（不打後端）；首頁示範卡是真跑，測試不要點。
