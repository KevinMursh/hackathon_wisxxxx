# deploy/node — Node 後端部署（尚未套用，等隊友確認）

> ⚠️ **還沒有對線上機器動任何手腳。** 目前 `i-0317e2f9af300f2bf`（http://100.20.156.38/）跑的仍是
> `deploy/ec2/` 那套 FastAPI。套用本目錄會**取代**機器上跑的服務。

## 為什麼要換

`src/backend` 的 FastAPI 只有 `/api/health` 與 `/api/chat`，業務邏輯未實作；文件歸戶（正規化＋分類＋
S3/DynamoDB＋SSE）已經在 `server/`（Node）做完並本機驗過。**兩個 runtime 各自持一把 1 RPS 節流鎖會超限**，
所以一台機器只能有一個後端。

## 與現有 deploy/ 的關係

| 現有（FastAPI） | 本目錄（Node） | 說明 |
|---|---|---|
| `deploy/ec2/user-data.sh` | `deploy/node/user-data.sh` | 多了 setup-tools |
| `deploy/ec2/app.service` | `deploy/node/app.service` | uvicorn → node；加 MemoryMax |
| `deploy/ec2/redeploy.sh` | `deploy/node/redeploy.sh` | pip → npm ci |
| `deploy/push.sh`（打包 src+deploy） | `deploy/node/push.sh` | 打包 server+prototype+deploy |
| — | `deploy/node/setup-tools.sh` | **新增**：poppler／ffmpeg／LibreOffice／字型 |

`deploy/config.sh`（bucket、APP_NAME、會場 IP、region）兩套共用，**未修改**。
IAM Role `ntpc-law3-ec2-role` 沿用，已補 DynamoDB `appeal-cases` 權限。

## 切換步驟（隊友點頭後）

**第一次**用 `first-switch.sh`——順序不能顛倒：機器上原本沒有 node，要先把部署包解開、裝完工具，
才能跑 `redeploy.sh`（它會 `npm ci`）。

```bash
cd ~/Desktop/hackathon_wisxxxx
./deploy/node/first-switch.sh     # 打包上傳 → 解壓 → 裝工具（5–10 分鐘）→ 停 FastAPI → 起 Node
```

**之後日常更新**：

```bash
./deploy/node/push.sh             # 約 1 分鐘
```

回頭切回 FastAPI：`systemctl disable --now app-node && systemctl restart app`。
兩個 service 名稱不同（`app-node` vs `app`），但都綁 port 80，**不能同時開**。

## 已踩過的坑（2026-09-12 首次切換）

| 症狀 | 原因 | 已修 |
|---|---|---|
| `CMD?: unbound variable` | `$CMD）` 全形括號被 bash 3.2 當成變數名的一部分 | 改 `${CMD}` |
| service 啟動失敗 `unavailable resources` | 設定檔放 `/opt/app/server/`，被 `redeploy.sh` 的 `rm -rf` 刪掉 | 移到 `/etc/app-node.conf`，由 redeploy 產生 |
| LibreOffice 下載 404 | 24.8.x 已從 stable 目錄下架 | 改成自動抓目錄內最新版 |
| tar 警告 `LIBARCHIVE.xattr.com.apple.provenance` | macOS 擴充屬性 | 打包加 `COPYFILE_DISABLE=1 --no-xattrs` |
| profile 找不到 | `config.sh` 預設 `ntpc-hackathon`（隊友的） | 跑之前帶 `AWS_PROFILE=hackathon` |

## AL2023 的坑

機器是 Amazon Linux 2023，`dnf` 裡**沒有 LibreOffice、沒有 ffmpeg**：

- ffmpeg → 先試 `ffmpeg-free`，失敗退 johnvansickle 靜態版
- LibreOffice → 官方 RPM tarball（約 250MB）
- 中文字型 → `google-noto-sans-cjk`，沒裝的話 Office 轉 PDF 會缺字

**這兩個是選配**：裝不起來服務照跑，該格式回 `unsupported`，`/api/health` 的 `degraded` 欄位會寫明
「soffice 缺少 → Office 檔無法處理」。必要工具只有 `node`、`pdftotext`、`pdftoppm`、`pdfinfo`、`file`，
缺了才會 503。

若嫌麻煩，另一條路是**改用 Ubuntu 24.04 AMI 重開一台**，`apt` 一行全裝齊（`setup-tools.sh` 已支援 apt 分支），
代價是要重跑 `create-infra.sh` 換 instance、公網 IP 會變。

## 設定檔

機器上的 `/etc/app-node.conf`（**不進 repo**，`redeploy.sh` 首次部署自動產生）。
放 `/etc` 而不是 `/opt/app/server/` 是因為每次部署都會 `rm -rf /opt/app/server`，放那裡會被自己刪掉：

```
AWS_REGION=us-west-2
MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_MIN_INTERVAL=2.0
BEDROCK_CONCURRENCY=3
BOX_FILES=10
CLASSIFY_CACHE=0
S3_BUCKET=ntpc-law3-deploy-229004791954
DDB_TABLE=appeal-cases
```

不含任何憑證——AWS 走 Instance Profile。案件檔存 `s3://<bucket>/cases/`（本機開發用 `dev/` 前綴隔離）。

## 部署後驗收

```bash
curl http://<ip>/api/health                       # ok:true、missingRequired 空、degraded 列出缺的選配
curl -F files=@卷宗包/01-訴願書/*.pdf http://<ip>/api/cases/t1/files
curl -N http://<ip>/api/jobs/<jobId>/events       # normalized → box → result → done
curl http://<ip>/api/cases/t1/files                # groups 五組、presigned URL
```

除錯：`aws ssm start-session --target i-0317e2f9af300f2bf` 進機器，`journalctl -u app-node -f`。
