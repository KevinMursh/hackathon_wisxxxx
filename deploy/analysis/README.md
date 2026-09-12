# deploy/analysis — 分析階段 API（Python :8100，與 Node :80 同機並存）

```
瀏覽器 → :80 Node（歸戶＋靜態前端）
              └─ analysis-proxy.mjs → 127.0.0.1:8100 Python（s2–s6／異議／法規庫）
                                          ├─ 讀 DynamoDB appeal-cases（CASE#/FILE#）＋ S3 normalized/meta.json
                                          ├─ 寫 DynamoDB CASE#{id}/ANALYSIS#latest
                                          └─ Bedrock（Claude Sonnet 4.5、KB NTERZZYNO1）
```

## 上線（一次）

```bash
./deploy/analysis/push.sh          # 打包 experiments+資料集 → S3 → SSM：建 venv、裝 systemd analysis.service、起 :8100
```
機器要有 python3.11（deploy/ec2/user-data 已裝）與 pdftotext（Node 那套 setup-tools 已裝）。

## Node 端要加的（隊友）

`server/server.mjs` 在 `app.use(express.static(...))` **之前**：
```js
import { mountAnalysisProxy } from "./analysis-proxy.mjs";
mountAnalysisProxy(app);
```
之後 `./deploy/node/push.sh`。

## 驗證

```bash
curl http://100.20.156.38/api/analysis/health
curl -X POST http://100.20.156.38/api/cases/final01/analyze       # 202 {jobId}
curl -N http://100.20.156.38/api/jobs/<jobId>/events               # step×10 → done（約 3 分鐘）
curl http://100.20.156.38/api/cases/final01/analysis | jq .status
curl http://100.20.156.38/api/lawlib | jq .sync
```

## 1 RPS

同一個帳號：Node classify（startInterval 2s、concurrency 3）與 Python pipeline（1.1s 全域鎖）**不同時跑**——分析只在歸戶 job `done` 後由前端觸發；`api.py` 內 job 序列執行。demo 時一次一案。

## 日常更新

```bash
./deploy/analysis/push.sh          # 約 1 分鐘（資料集 57MB 一起上）
sudo journalctl -u analysis -f     # 在機器上（aws ssm start-session --target i-0317e2f9af300f2bf）
```
