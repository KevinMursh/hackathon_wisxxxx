# src/ — 已停用

這裡是 9d63f6b 時的最簡骨架（FastAPI `/api/health`＋`/api/chat`、舊版前端），**已不部署、不維護**。

現行程式碼：
- 前端：`prototype/`（Node `server/server.mjs` 直接 static 此目錄；`deploy/node/push.sh` 打包）
- 文件歸戶：`server/`（Node :80）
- 分析、助手、法規庫：`experiments/api.py`＋`experiments/pipeline/`（Python :8100，經 `server/analysis-proxy.mjs` 反代）

契約：`docs/API-文件歸戶.md`、`docs/API-分析階段.md`、`plans/助手API-契約與實作清單.md`。
